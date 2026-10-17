"""Row Level Security / privilege tests, run as the Supabase `anon` and `authenticated` roles."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from scraper.database import PostgresRepository, RunRecord
from scraper.models import ListingRecord

T0 = datetime(2030, 1, 10, 1, 0, tzinfo=UTC)


@pytest.fixture
def seeded(pg_dsn: str) -> Iterator[dict[str, Any]]:
    repo = PostgresRepository.connect(pg_dsn)
    run = repo.start_run("test", T0)
    repo.upsert_listings(
        [
            ListingRecord(
                source_name="s", source_id="1", title="Synthetic", url="https://bidplus.gem.gov.in/x/1"
            )
        ],
        run,
        T0,
    )
    repo.finish_run(
        run,
        RunRecord(
            "success", T0, 1, 1, 0, 0, 0, "internal detail", {"s": {"status": "success", "error": None}}
        ),
    )
    admin_id, user_id = uuid.uuid4(), uuid.uuid4()
    with repo.conn.transaction():
        repo.conn.execute("insert into auth.users (id) values (%s), (%s)", (admin_id, user_id))
        repo.conn.execute("insert into public.admins (user_id) values (%s)", (admin_id,))
    repo.close()
    yield {"dsn": pg_dsn, "admin": admin_id, "user": user_id}


def as_role(dsn: str, role: str, sub: uuid.UUID | None = None) -> psycopg.Connection[Any]:
    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute(f"set role {role}")  # type: ignore[arg-type]
    if sub is not None:
        conn.execute("select set_config('request.jwt.claim.sub', %s, false)", (str(sub),))
    return conn


DISPLAY = "id, title, organisation, deadline, url, category, data_origin, first_seen_at, last_checked_at"


def test_anon_reads_public_listing_columns(seeded: dict[str, Any]) -> None:
    with as_role(seeded["dsn"], "anon") as conn:
        rows = conn.execute(f"select {DISPLAY} from public.listings").fetchall()  # type: ignore[arg-type]
        assert len(rows) == 1
        assert conn.execute("select count(*) from public.listing_history").fetchone() == (0,)


@pytest.mark.parametrize("column", ["content_hash", "dedup_key"])
def test_anon_cannot_read_internal_columns(seeded: dict[str, Any], column: str) -> None:
    with as_role(seeded["dsn"], "anon") as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(f"select {column} from public.listings")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "statement",
    [
        "insert into public.listings (source_name, dedup_key, title, content_hash, source_id) "
        "values ('s','id:9','t','h','9')",
        "update public.listings set title = 'defaced'",
        "delete from public.listings",
        "insert into public.listing_history (listing_id, field_name) select id, 'x' from public.listings",
        "delete from public.listing_history",
        "insert into public.scrape_runs (status) values ('success')",
        "update public.scrape_runs set status = 'success'",
        "insert into public.admins (user_id) values (gen_random_uuid())",
    ],
)
@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_public_roles_cannot_write(seeded: dict[str, Any], role: str, statement: str) -> None:
    with (
        as_role(seeded["dsn"], role, seeded["admin"]) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(statement)  # type: ignore[arg-type]


def test_anon_cannot_read_runs_or_admins(seeded: dict[str, Any]) -> None:
    with as_role(seeded["dsn"], "anon") as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("select * from public.scrape_runs")
    with as_role(seeded["dsn"], "anon") as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("select * from public.admins")


def test_non_admin_user_sees_no_runs(seeded: dict[str, Any]) -> None:
    with as_role(seeded["dsn"], "authenticated", seeded["user"]) as conn:
        assert conn.execute("select count(*) from public.scrape_runs").fetchone() == (0,)
        assert conn.execute("select public.is_admin()").fetchone() == (False,)
        assert conn.execute("select count(*) from public.admins").fetchone() == (0,)


def test_admin_user_sees_runs(seeded: dict[str, Any]) -> None:
    with as_role(seeded["dsn"], "authenticated", seeded["admin"]) as conn:
        assert conn.execute("select public.is_admin()").fetchone() == (True,)
        row = conn.execute("select status, error_summary from public.scrape_runs").fetchone()
        assert row == ("success", "internal detail")


def test_public_functions_expose_only_aggregates(seeded: dict[str, Any]) -> None:
    with as_role(seeded["dsn"], "anon") as conn:
        stats = conn.execute("select total_listings from public.dashboard_stats()").fetchone()
        assert stats == (1,)
        status = conn.execute(
            "select last_success_at, last_run_status, sources_succeeded from public.collection_status()"
        ).fetchone()
        assert status == (T0, "success", ["s"])
        cols = [d.name for d in conn.execute("select * from public.collection_status()").description or []]
        assert "error_summary" not in cols
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("select public.is_admin()")
