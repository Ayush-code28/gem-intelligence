from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from scraper.changes import content_hash, diff, merge_observation
from scraper.database import RunRecord, UpsertResult, dedupe
from scraper.models import ListingRecord

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- HTTP fakes


class FakeResponse:
    def __init__(self, text: str = "", payload: Any = None, status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = text if payload is None else json.dumps(payload)
        self._payload = payload

    def json(self, **kwargs: Any) -> Any:
        if self._payload is None:
            return json.loads(self.text)
        return self._payload


class FakeClient:
    """Serves the listing shell on GET and queued responses on POST; records payloads."""

    def __init__(self, posts: Sequence[FakeResponse | Exception], page_html: str | None = None) -> None:
        self.shell = page_html if page_html is not None else load_fixture("gem_listing_page_synthetic.html")
        self.posts = list(posts)
        self.payloads: list[dict[str, Any]] = []
        self.request_count = 0
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.request_count += 1
        return FakeResponse(self.shell)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.request_count += 1
        self.payloads.append({"url": url, **kwargs})
        if not self.posts:
            raise AssertionError("unexpected extra request")
        item = self.posts.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        self.closed = True


def page_body(docs: list[dict[str, Any]], num_found: int, start: int = 0) -> dict[str, Any]:
    return {"code": 200, "response": {"response": {"numFound": num_found, "start": start, "docs": docs}}}


def synthetic_doc(
    n: int, start: str = "2030-01-10T10:00:00Z", end: str = "2030-01-20T17:00:00Z"
) -> dict[str, Any]:
    return {
        "id": str(900_100_000 + n),
        "b_id": [900_100_000 + n],
        "b_bid_number": [f"GEM/TEST/B/{n:06d}"],
        "b_category_name": [f"Synthetic item {n}"],
        "b_type": [0],
        "b_bid_type": [1],
        "ba_official_details_deptName": ["Department of Test Fixtures"],
        "final_start_date_sort": [start],
        "final_end_date_sort": [end],
    }


# --------------------------------------------------------------------------- in-memory repository


class FakeRepository:
    """In-memory Repository using the same merge/diff logic as PostgresRepository."""

    def __init__(self, watermarks: dict[str, datetime] | None = None, fail_upsert: bool = False) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.history: list[tuple[str, str, str | None, str | None]] = []
        self.runs: dict[str, dict[str, Any]] = {}
        self.finished: dict[str, RunRecord] = {}
        self.watermarks = watermarks or {}
        self.fail_upsert = fail_upsert

    def start_run(self, trigger: str, started_at: datetime) -> str:
        run_id = str(uuid.uuid4())
        self.runs[run_id] = {"trigger": trigger, "started_at": started_at}
        return run_id

    def finish_run(self, run_id: str, record: RunRecord) -> None:
        self.finished[run_id] = record

    def source_watermark(self, source_name: str) -> datetime | None:
        return self.watermarks.get(source_name)

    def upsert_listings(
        self, records: Sequence[ListingRecord], run_id: str, observed_at: datetime
    ) -> UpsertResult:
        if self.fail_upsert:
            raise RuntimeError("simulated database outage")
        inserted = updated = unchanged = history_rows = 0
        for record in dedupe(records):
            key = (record.source_name, record.dedup_key)
            current = self.rows.get(key)
            if current is None:
                values = record.tracked_values()
                self.rows[key] = {**values, "content_hash": content_hash(values), "last_seen_at": observed_at}
                inserted += 1
                continue
            merged = merge_observation(current, record)
            changes = diff(current, merged)
            if changes:
                current.update(merged, content_hash=content_hash(merged))
                updated += 1
                for c in changes:
                    self.history.append((record.dedup_key, c.field_name, c.old_value, c.new_value))
                history_rows += len(changes)
            else:
                unchanged += 1
            current["last_seen_at"] = observed_at
        return UpsertResult(inserted, updated, unchanged, history_rows)


# --------------------------------------------------------------------------- real Postgres


def _apply_schema(conn: psycopg.Connection[Any]) -> None:
    files = [REPO_ROOT / "supabase/tests/local_supabase_shim.sql"]
    files += sorted((REPO_ROOT / "supabase/migrations").glob("*.sql"))
    for path in files:
        conn.execute(path.read_text(encoding="utf-8"))  # type: ignore[arg-type]


@pytest.fixture
def pg_dsn() -> Iterator[str]:
    """A fresh, migrated database per test. Skipped unless TEST_DATABASE_URL is set."""
    base = os.environ.get("TEST_DATABASE_URL")
    if not base:
        pytest.skip("TEST_DATABASE_URL not set; database tests skipped")
    parts = urlsplit(base)
    name = f"gem_test_{uuid.uuid4().hex[:10]}"
    admin_dsn = urlunsplit(parts._replace(path="/postgres"))
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')  # type: ignore[arg-type]
    dsn = urlunsplit(parts._replace(path=f"/{name}"))
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            _apply_schema(conn)
        yield dsn
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(f'drop database if exists "{name}" with (force)')  # type: ignore[arg-type]
