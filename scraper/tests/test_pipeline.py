from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from scraper.config import Settings
from scraper.models import ListingRecord, RejectedRecord
from scraper.pipeline import overall_status, run_pipeline, summary_markdown
from scraper.sources.base import FetchContext, SourceAccessBlocked, SourceAdapter
from scraper.tests.conftest import FakeRepository

T0 = datetime(2030, 1, 10, 1, 0, tzinfo=UTC)


class ScriptedAdapter(SourceAdapter):
    """Yields scripted pages; an Exception entry is raised at that point."""

    requires_permission = False

    def __init__(self, name: str, pages: list[list[dict[str, Any]] | Exception]) -> None:
        super().__init__()
        self.name = name
        self.description = "scripted"
        self.pages = pages
        self.seen_ctx: FetchContext | None = None
        self.closed = False

    def iter_pages(self, ctx: FetchContext) -> Iterator[list[Mapping[str, Any]]]:
        self.seen_ctx = ctx
        for page in self.pages:
            if isinstance(page, Exception):
                raise page
            self.stats.pages_fetched += 1
            yield page

    def normalize(self, raw: Mapping[str, Any]) -> ListingRecord:
        if not raw.get("title"):
            raise RejectedRecord("missing title")
        return ListingRecord(
            source_name=self.name,
            source_id=str(raw["id"]),
            title=raw["title"],
            deadline=raw.get("deadline"),
            url=f"https://bidplus.gem.gov.in/showbidDocument/{raw['id']}",
        )

    def close(self) -> None:
        self.closed = True


def items(*ids: int, title: str = "Synthetic") -> list[dict[str, Any]]:
    return [{"id": i, "title": f"{title} {i}"} for i in ids]


def run(repo: FakeRepository, *adapters: SourceAdapter) -> Any:
    return run_pipeline(Settings(), repo, list(adapters), trigger="test", clock=lambda: T0)


def test_all_sources_succeed() -> None:
    repo = FakeRepository()
    summary = run(repo, ScriptedAdapter("a", [items(1, 2)]), ScriptedAdapter("b", [items(3)]))
    assert summary.status == "success" and summary.exit_code == 0
    record = repo.finished[summary.run_id]
    assert (record.records_found, record.records_inserted) == (3, 3)
    assert record.source_results["a"]["status"] == "success"


def test_rerun_is_idempotent() -> None:
    repo = FakeRepository()
    run(repo, ScriptedAdapter("a", [items(1, 2)]))
    second = run(repo, ScriptedAdapter("a", [items(1, 2)]))
    assert len(repo.rows) == 2
    r = second.sources["a"]
    assert (r.inserted, r.updated, r.unchanged, r.history_rows) == (0, 0, 2, 0)


def test_change_detection_through_pipeline() -> None:
    repo = FakeRepository()
    run(repo, ScriptedAdapter("a", [items(1)]))
    later = [{"id": 1, "title": "Synthetic 1", "deadline": T0 + timedelta(days=3)}]
    summary = run(repo, ScriptedAdapter("a", [later]))
    assert summary.sources["a"].updated == 1
    assert repo.history == [("id:1", "deadline", None, (T0 + timedelta(days=3)).isoformat())]


def test_partial_source_failure_is_reported_as_partial() -> None:
    repo = FakeRepository()
    ok = ScriptedAdapter("ok", [items(1)])
    bad = ScriptedAdapter("bad", [SourceAccessBlocked("blocked by gateway")])
    summary = run(repo, ok, bad)
    assert summary.status == "partial" and summary.exit_code == 2
    assert summary.sources["bad"].status == "failed"
    assert "blocked by gateway" in (summary.error_summary or "")
    assert bad.closed and ok.closed
    assert repo.finished[summary.run_id].status == "partial"


def test_all_sources_failing_is_failed() -> None:
    repo = FakeRepository()
    summary = run(
        repo, ScriptedAdapter("a", [RuntimeError("down")]), ScriptedAdapter("b", [RuntimeError("down")])
    )
    assert summary.status == "failed" and summary.exit_code == 1
    assert repo.finished[summary.run_id].status == "failed"


def test_records_from_completed_pages_are_kept_when_a_later_page_fails() -> None:
    repo = FakeRepository()
    summary = run(repo, ScriptedAdapter("a", [items(1, 2), ConnectionError("page 2 timed out")]))
    r = summary.sources["a"]
    assert r.status == "failed" and r.inserted == 2
    assert len(repo.rows) == 2


def test_failed_run_never_removes_existing_listings() -> None:
    repo = FakeRepository()
    run(repo, ScriptedAdapter("a", [items(1, 2, 3)]))
    run(repo, ScriptedAdapter("a", [items(1)]))  # 2 and 3 absent from a partial scan
    run(repo, ScriptedAdapter("a", [RuntimeError("down")]))
    assert len(repo.rows) == 3


def test_high_rejection_ratio_fails_source() -> None:
    repo = FakeRepository()
    pages = [[{"id": 1, "title": "ok"}, {"id": 2}, {"id": 3}]]
    summary = run(repo, ScriptedAdapter("a", pages))
    r = summary.sources["a"]
    assert r.status == "failed" and r.rejected == 2 and "possible source change" in (r.error or "")
    assert r.rejection_samples == ["missing title", "missing title"]


def test_some_rejections_are_tolerated() -> None:
    summary = run(FakeRepository(), ScriptedAdapter("a", [[*items(1, 2, 3), {"id": 4}]]))
    assert summary.sources["a"].status == "success" and summary.sources["a"].rejected == 1


def test_empty_source_is_not_success() -> None:
    summary = run(FakeRepository(), ScriptedAdapter("a", [[]]))
    assert summary.status == "failed"


def test_persistence_failure() -> None:
    repo = FakeRepository(fail_upsert=True)
    summary = run(repo, ScriptedAdapter("a", [items(1)]))
    assert summary.status == "failed"
    assert (summary.sources["a"].error or "").startswith("persistence:")


def test_no_sources_is_skipped() -> None:
    repo = FakeRepository()
    summary = run(repo)
    assert summary.status == "skipped" and summary.exit_code == 0
    assert repo.finished[summary.run_id].error_summary == "no sources enabled"


def test_watermark_applies_overlap() -> None:
    adapter = ScriptedAdapter("a", [items(1)])
    run(FakeRepository(watermarks={"a": T0}), adapter)
    assert adapter.seen_ctx is not None
    assert adapter.seen_ctx.watermark == T0 - timedelta(hours=48)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [([], "skipped"), (["success"], "success"), (["success", "failed"], "partial"), (["failed"], "failed")],
)
def test_overall_status(statuses: list[str], expected: str) -> None:
    from scraper.pipeline import SourceResult

    assert overall_status([SourceResult(status=s) for s in statuses]) == expected


def test_summary_markdown_escapes_pipes() -> None:
    summary = run(FakeRepository(), ScriptedAdapter("a", [RuntimeError("a|b")]))
    assert "a\\|b" in summary_markdown(summary)


def test_blocked_host_is_not_retried_by_sibling_sources() -> None:
    first = ScriptedAdapter("gem_a", [SourceAccessBlocked("blocked")])
    second = ScriptedAdapter("gem_b", [items(1)])
    other = ScriptedAdapter("elsewhere", [items(2)])
    first.access_group = second.access_group = "gem.gov.in"
    summary = run(FakeRepository(), first, second, other)
    assert summary.sources["gem_a"].access_blocked
    b = summary.sources["gem_b"]
    assert b.status == "failed" and b.pages_fetched == 0 and "not attempted" in (b.error or "")
    assert second.seen_ctx is None and second.closed  # never contacted
    assert summary.sources["elsewhere"].status == "success"
    assert summary.status == "partial"


def test_source_results_record_origin() -> None:
    adapter = ScriptedAdapter("a", [items(1)])
    adapter.origin = "imported"
    summary = run(FakeRepository(), adapter)
    assert summary.to_record().source_results["a"]["origin"] == "imported"
