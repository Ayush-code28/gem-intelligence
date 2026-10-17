"""Persistence: idempotent upserts, change history and run records (Postgres via psycopg)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row

from scraper.changes import content_hash, diff, merge_observation
from scraper.models import TRACKED_FIELDS, ListingRecord


@dataclass(frozen=True)
class UpsertResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    history_rows: int = 0


@dataclass(frozen=True)
class RunRecord:
    status: str
    finished_at: datetime
    records_found: int
    records_inserted: int
    records_updated: int
    records_unchanged: int
    records_rejected: int
    error_summary: str | None
    source_results: dict[str, Any]


class Repository(Protocol):
    def start_run(self, trigger: str, started_at: datetime) -> str: ...

    def finish_run(self, run_id: str, record: RunRecord) -> None: ...

    def source_watermark(self, source_name: str) -> datetime | None: ...

    def upsert_listings(
        self, records: Sequence[ListingRecord], run_id: str, observed_at: datetime
    ) -> UpsertResult: ...


def dedupe(records: Sequence[ListingRecord]) -> list[ListingRecord]:
    """Collapse duplicates within one batch by (source_name, dedup_key); the last observation wins."""
    unique: dict[tuple[str, str], ListingRecord] = {}
    for record in records:
        unique[(record.source_name, record.dedup_key)] = record
    return list(unique.values())


_COLUMNS = ", ".join(TRACKED_FIELDS)
_SET_TRACKED = ", ".join(f"{name} = %({name})s" for name in TRACKED_FIELDS)


class PostgresRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    @classmethod
    def connect(cls, database_url: str) -> PostgresRepository:
        conn = psycopg.connect(
            database_url, autocommit=False, connect_timeout=15, application_name="gem-collector"
        )
        return cls(conn)

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ runs

    def start_run(self, trigger: str, started_at: datetime) -> str:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                "insert into public.scrape_runs (started_at, status, trigger) "
                "values (%s, 'running', %s) returning id",
                (started_at, trigger),
            )
            row = cur.fetchone()
        assert row is not None
        return str(row[0])

    def finish_run(self, run_id: str, record: RunRecord) -> None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                """
                update public.scrape_runs set
                    status = %s, finished_at = %s, records_found = %s, records_inserted = %s,
                    records_updated = %s, records_unchanged = %s, records_rejected = %s,
                    error_summary = %s, source_results = %s::jsonb
                where id = %s
                """,
                (
                    record.status,
                    record.finished_at,
                    record.records_found,
                    record.records_inserted,
                    record.records_updated,
                    record.records_unchanged,
                    record.records_rejected,
                    record.error_summary,
                    json.dumps(record.source_results, default=str),
                    run_id,
                ),
            )

    def source_watermark(self, source_name: str) -> datetime | None:
        """Start time of the most recent run in which this source completed successfully."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                """
                select max(started_at) from public.scrape_runs
                where status in ('success', 'partial')
                  and source_results -> %s ->> 'status' = 'success'
                """,
                (source_name,),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def purge_synthetic(self) -> int:
        """Delete synthetic demonstration listings (history cascades). Never touches other origins."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute("delete from public.listings where data_origin = 'synthetic'")
            return cur.rowcount

    # ------------------------------------------------------------------ listings

    def upsert_listings(
        self, records: Sequence[ListingRecord], run_id: str, observed_at: datetime
    ) -> UpsertResult:
        batch = dedupe(records)
        if not batch:
            return UpsertResult()
        inserted = updated = unchanged = history_rows = 0
        with self.conn.transaction(), self.conn.cursor(row_factory=dict_row) as cur:
            by_source: dict[str, list[str]] = {}
            for r in batch:
                by_source.setdefault(r.source_name, []).append(r.dedup_key)
            existing: dict[tuple[str, str], dict[str, Any]] = {}
            for source_name, keys in by_source.items():
                cur.execute(
                    f"select id, source_name, dedup_key, {_COLUMNS} from public.listings "  # noqa: S608
                    "where source_name = %s and dedup_key = any(%s) for update",
                    (source_name, keys),
                )
                for row in cur.fetchall():
                    existing[(row["source_name"], row["dedup_key"])] = row

            touch_ids: list[Any] = []
            history: list[tuple[Any, str, str, str | None, str | None, datetime]] = []
            for record in batch:
                current = existing.get((record.source_name, record.dedup_key))
                if current is None:
                    values = record.tracked_values()
                    cur.execute(
                        f"""
                        insert into public.listings
                            (source_name, source_id, dedup_key, data_origin, {_COLUMNS}, content_hash,
                             first_seen_at, last_seen_at, last_checked_at)
                        values (%(source_name)s, %(source_id)s, %(dedup_key)s, %(data_origin)s,
                                {", ".join(f"%({n})s" for n in TRACKED_FIELDS)}, %(content_hash)s,
                                %(observed_at)s, %(observed_at)s, %(observed_at)s)
                        on conflict (source_name, dedup_key) do nothing
                        """,  # noqa: S608 - column names are constants
                        {
                            **values,
                            "source_name": record.source_name,
                            "source_id": record.source_id,
                            "dedup_key": record.dedup_key,
                            "data_origin": record.data_origin,
                            "content_hash": content_hash(values),
                            "observed_at": observed_at,
                        },
                    )
                    inserted += cur.rowcount
                    continue

                merged = merge_observation(current, record)
                changes = diff(current, merged)
                if not changes:
                    touch_ids.append(current["id"])
                    unchanged += 1
                    continue
                cur.execute(
                    f"""
                    update public.listings set {_SET_TRACKED}, content_hash = %(content_hash)s,
                        last_seen_at = greatest(last_seen_at, %(observed_at)s),
                        last_checked_at = greatest(last_checked_at, %(observed_at)s)
                    where id = %(id)s
                    """,  # noqa: S608 - column names are constants
                    {
                        **merged,
                        "content_hash": content_hash(merged),
                        "observed_at": observed_at,
                        "id": current["id"],
                    },
                )
                updated += 1
                history.extend(
                    (current["id"], run_id, c.field_name, c.old_value, c.new_value, observed_at)
                    for c in changes
                )

            if touch_ids:
                cur.execute(
                    """
                    update public.listings set
                        last_seen_at = greatest(last_seen_at, %s),
                        last_checked_at = greatest(last_checked_at, %s)
                    where id = any(%s)
                    """,
                    (observed_at, observed_at, touch_ids),
                )
            if history:
                cur.executemany(
                    """
                    insert into public.listing_history
                        (listing_id, scrape_run_id, field_name, old_value, new_value, observed_at)
                    values (%s, %s, %s, %s, %s, %s)
                    """,
                    history,
                )
                history_rows = len(history)
        return UpsertResult(inserted, updated, unchanged, history_rows)
