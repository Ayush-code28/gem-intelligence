"""Integration tests against a real, disposable Postgres (TEST_DATABASE_URL)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

from scraper.database import PostgresRepository, RunRecord
from scraper.models import ListingRecord

T0 = datetime(2030, 1, 10, 1, 0, tzinfo=UTC)


def rec(n: int = 1, **overrides: Any) -> ListingRecord:
    base: dict[str, Any] = {
        "source_name": "test_source",
        "source_id": str(n),
        "title": f"Synthetic item {n}",
        "organisation": "Department of Test Fixtures",
        "deadline": T0 + timedelta(days=10),
        "url": f"https://bidplus.gem.gov.in/showbidDocument/{n}",
    }
    base.update(overrides)
    return ListingRecord(**base)


@pytest.fixture
def repo(pg_dsn: str) -> Any:
    r = PostgresRepository.connect(pg_dsn)
    yield r
    r.close()


def q(repo: PostgresRepository, sql: str, *params: Any) -> list[tuple[Any, ...]]:
    with repo.conn.transaction(), repo.conn.cursor() as cur:
        cur.execute(sql, params)  # type: ignore[arg-type]
        return cur.fetchall()


def test_insert_then_idempotent_rerun(repo: PostgresRepository) -> None:
    run = repo.start_run("test", T0)
    first = repo.upsert_listings([rec(1), rec(2)], run, T0)
    second = repo.upsert_listings([rec(1), rec(2)], run, T0 + timedelta(days=1))
    assert (first.inserted, second.inserted, second.updated, second.unchanged) == (2, 0, 0, 2)
    assert q(repo, "select count(*) from listings") == [(2,)]
    assert q(repo, "select count(*) from listing_history") == [(0,)]
    first_seen, last_seen = q(repo, "select first_seen_at, last_seen_at from listings where source_id = '1'")[
        0
    ]
    assert first_seen == T0 and last_seen == T0 + timedelta(days=1)


def test_duplicates_within_batch_collapse(repo: PostgresRepository) -> None:
    run = repo.start_run("test", T0)
    result = repo.upsert_listings([rec(1, title="old"), rec(1, title="new")], run, T0)
    assert result.inserted == 1
    assert q(repo, "select title from listings") == [("new",)]


def test_url_fallback_dedup_key(repo: PostgresRepository) -> None:
    run = repo.start_run("test", T0)
    r = rec(5, source_id=None)
    repo.upsert_listings([r], run, T0)
    repo.upsert_listings([r], run, T0)
    assert q(repo, "select dedup_key from listings") == [
        ("url:https://bidplus.gem.gov.in/showbidDocument/5",)
    ]


def test_change_detection_writes_history(repo: PostgresRepository) -> None:
    run = repo.start_run("test", T0)
    repo.upsert_listings([rec(1)], run, T0)
    (updated_before,) = q(repo, "select updated_at from listings")[0]
    new_deadline = T0 + timedelta(days=15)
    result = repo.upsert_listings(
        [rec(1, deadline=new_deadline, title="Synthetic item 1 (amended)")], run, T0
    )
    assert result.updated == 1 and result.history_rows == 2
    rows = q(
        repo,
        "select field_name, old_value, new_value, scrape_run_id::text "
        "from listing_history order by field_name",
    )
    assert rows == [
        ("deadline", (T0 + timedelta(days=10)).isoformat(), new_deadline.isoformat(), run),
        ("title", "Synthetic item 1", "Synthetic item 1 (amended)", run),
    ]
    (updated_after,) = q(repo, "select updated_at from listings")[0]
    assert updated_after >= updated_before


def test_touch_does_not_bump_updated_at(repo: PostgresRepository) -> None:
    run = repo.start_run("test", T0)
    repo.upsert_listings([rec(1)], run, T0)
    (before,) = q(repo, "select updated_at from listings")[0]
    repo.upsert_listings([rec(1)], run, T0 + timedelta(days=2))
    (after, last_seen) = q(repo, "select updated_at, last_seen_at from listings")[0]
    assert after == before and last_seen == T0 + timedelta(days=2)


def test_null_in_new_observation_does_not_erase(repo: PostgresRepository) -> None:
    run = repo.start_run("test", T0)
    repo.upsert_listings([rec(1)], run, T0)
    result = repo.upsert_listings([rec(1, deadline=None, organisation=None)], run, T0)
    assert result.unchanged == 1
    assert q(repo, "select organisation, deadline is not null from listings") == [
        ("Department of Test Fixtures", True)
    ]


def test_last_seen_never_moves_backwards(repo: PostgresRepository) -> None:
    run = repo.start_run("test", T0)
    repo.upsert_listings([rec(1)], run, T0 + timedelta(days=1))
    repo.upsert_listings([rec(1)], run, T0)
    assert q(repo, "select last_seen_at from listings") == [(T0 + timedelta(days=1),)]


def test_run_lifecycle_and_watermark(repo: PostgresRepository) -> None:
    assert repo.source_watermark("s") is None
    run = repo.start_run("schedule", T0)
    repo.finish_run(
        run,
        RunRecord(
            status="partial",
            finished_at=T0 + timedelta(minutes=5),
            records_found=3,
            records_inserted=2,
            records_updated=0,
            records_unchanged=0,
            records_rejected=1,
            error_summary="b: failed",
            source_results={"s": {"status": "success"}, "b": {"status": "failed"}},
        ),
    )
    assert repo.source_watermark("s") == T0
    assert repo.source_watermark("b") is None  # a failed source never advances its watermark
    assert q(repo, "select status, records_found, trigger from scrape_runs") == [("partial", 3, "schedule")]


def test_database_constraints(repo: PostgresRepository) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        q(repo, "insert into scrape_runs (status) values ('bogus')")
    with pytest.raises(psycopg.errors.CheckViolation):
        q(
            repo,
            "insert into listings (source_name, dedup_key, title, content_hash, url) "
            "values ('s', 'id:1', 't', 'h', 'javascript:alert(1)')",
        )
    run = repo.start_run("test", T0)
    repo.upsert_listings([rec(1)], run, T0)
    with pytest.raises(psycopg.errors.UniqueViolation):
        q(
            repo,
            "insert into listings (source_name, dedup_key, title, content_hash, source_id) "
            "values ('test_source', 'id:1', 't', 'h', '1')",
        )


def test_cli_records_skipped_run_end_to_end(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from scraper.__main__ import main

    monkeypatch.setenv("DATABASE_URL", pg_dsn)
    monkeypatch.delenv("ENABLED_SOURCES", raising=False)
    assert main(["--trigger", "schedule", "--summary-file", str(tmp_path / "s.md")]) == 0
    with psycopg.connect(pg_dsn) as conn:
        row = conn.execute(
            "select status, trigger, error_summary, finished_at is not null from scrape_runs"
        ).fetchone()
    assert row == ("skipped", "schedule", "no sources enabled", True)


def test_origin_is_stored_and_purge_only_removes_synthetic(repo: PostgresRepository) -> None:
    run = repo.start_run("test", T0)
    repo.upsert_listings(
        [
            rec(1),
            rec(2, source_name="imp", data_origin="imported"),
            rec(3, source_name="syn", data_origin="synthetic"),
        ],
        run,
        T0,
    )
    repo.upsert_listings([rec(3, source_name="syn", data_origin="synthetic", title="changed")], run, T0)
    assert q(repo, "select data_origin, count(*) from listings group by 1 order by 1") == [
        ("imported", 1),
        ("live", 1),
        ("synthetic", 1),
    ]
    assert repo.purge_synthetic() == 1
    assert q(repo, "select data_origin from listings order by 1") == [("imported",), ("live",)]
    assert q(repo, "select count(*) from listing_history") == [(0,)]  # history cascaded


def test_collection_status_separates_live_from_imports(repo: PostgresRepository) -> None:
    def finish(run: str, at: datetime, results: dict[str, Any]) -> None:
        repo.finish_run(run, RunRecord("success", at, 0, 0, 0, 0, 0, None, results))

    imp = repo.start_run("import:synthetic", T0)
    finish(imp, T0 + timedelta(minutes=1), {"synthetic_demo": {"status": "success", "origin": "synthetic"}})
    row = q(repo, "select last_success_at, last_live_success_at, last_import_at from collection_status()")[0]
    assert row == (T0 + timedelta(minutes=1), None, T0 + timedelta(minutes=1))

    live = repo.start_run("schedule", T0 + timedelta(hours=1))
    finish(live, T0 + timedelta(hours=2), {"gem_x": {"status": "success", "origin": "live"}})
    row = q(repo, "select last_live_success_at from collection_status()")[0]
    assert row == (T0 + timedelta(hours=2),)
    stats = q(repo, "select live_listings, imported_listings, synthetic_listings from dashboard_stats()")
    assert stats == [(0, 0, 0)]


def test_cli_import_end_to_end(pg_dsn: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    import json as _json

    from scraper.__main__ import main
    from scraper.synthetic import generate

    demo = tmp_path / "demo.json"
    demo.write_text(_json.dumps({"records": generate(12)}), encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", pg_dsn)
    assert main(["--import-file", str(demo), "--origin", "synthetic"]) == 0
    assert main(["--import-file", str(demo), "--origin", "synthetic"]) == 0  # idempotent
    with psycopg.connect(pg_dsn) as conn:
        assert conn.execute(
            "select count(*), min(data_origin), max(data_origin) from listings"
        ).fetchone() == (
            12,
            "synthetic",
            "synthetic",
        )
        assert conn.execute(
            "select bool_and(title like '[SYNTHETIC]%') and bool_and(url is null) from listings"
        ).fetchone() == (True,)
        assert conn.execute("select trigger, status from scrape_runs order by started_at").fetchall() == [
            ("import:synthetic", "success"),
            ("import:synthetic", "success"),
        ]
    assert main(["--purge-synthetic", "--yes"]) == 0
    with psycopg.connect(pg_dsn) as conn:
        assert conn.execute("select count(*) from listings").fetchone() == (0,)
