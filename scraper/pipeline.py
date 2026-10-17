"""Collection pipeline: fetch → validate/normalize → upsert → run summary."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from scraper.config import Settings
from scraper.database import Repository, RunRecord
from scraper.models import ListingRecord, RejectedRecord
from scraper.sources.base import FetchContext, SourceAccessBlocked, SourceAdapter

log = logging.getLogger(__name__)

# A source whose rejected share exceeds this is treated as failed (likely schema drift).
MAX_REJECTION_RATIO = 0.5
MAX_REJECTION_SAMPLES = 5


@dataclass
class SourceResult:
    status: str = "pending"  # success | failed
    origin: str = "live"
    found: int = 0
    valid: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    history_rows: int = 0
    pages_fetched: int = 0
    passes: dict[str, str] = field(default_factory=dict)
    watermark: str | None = None
    duration_seconds: float = 0.0
    error: str | None = None
    rejection_samples: list[str] = field(default_factory=list)
    access_blocked: bool = False


@dataclass
class RunSummary:
    run_id: str | None
    status: str
    started_at: datetime
    finished_at: datetime
    sources: dict[str, SourceResult]
    error_summary: str | None = None

    @property
    def exit_code(self) -> int:
        return {"success": 0, "skipped": 0, "partial": 2}.get(self.status, 1)

    def to_record(self) -> RunRecord:
        def total(attr: str) -> int:
            return sum(int(getattr(r, attr)) for r in self.sources.values())

        return RunRecord(
            status=self.status,
            finished_at=self.finished_at,
            records_found=total("found"),
            records_inserted=total("inserted"),
            records_updated=total("updated"),
            records_unchanged=total("unchanged"),
            records_rejected=total("rejected"),
            error_summary=self.error_summary,
            source_results={name: asdict(r) for name, r in self.sources.items()},
        )


def _safe_error(exc: BaseException) -> str:
    """Short error text for storage. Exception messages here never include credentials,
    but connection strings are scrubbed defensively."""
    text = f"{type(exc).__name__}: {exc}"
    if "postgres" in text.lower() and "@" in text:
        text = f"{type(exc).__name__}: database error (details withheld)"
    return text[:500]


def overall_status(results: Sequence[SourceResult]) -> str:
    if not results:
        return "skipped"
    statuses = {r.status for r in results}
    if statuses == {"success"}:
        return "success"
    if "success" in statuses:
        return "partial"
    return "failed"


def collect_source(
    adapter: SourceAdapter,
    repo: Repository,
    run_id: str,
    settings: Settings,
    now: datetime,
    clock: Callable[[], datetime],
) -> SourceResult:
    result = SourceResult(origin=adapter.origin)
    started = time.monotonic()
    records: list[ListingRecord] = []
    fetch_error: BaseException | None = None
    try:
        last_success = repo.source_watermark(adapter.name)
        watermark = last_success - timedelta(hours=settings.watermark_overlap_hours) if last_success else None
        result.watermark = watermark.isoformat() if watermark else None
        ctx = FetchContext(now=now, watermark=watermark, settings=settings)
        for page in adapter.iter_pages(ctx):
            for raw in page:
                result.found += 1
                try:
                    records.append(adapter.normalize(raw))
                except RejectedRecord as exc:
                    result.rejected += 1
                    if len(result.rejection_samples) < MAX_REJECTION_SAMPLES:
                        result.rejection_samples.append(str(exc)[:200])
    except Exception as exc:
        fetch_error = exc
        log.exception("source fetch failed", extra={"source": adapter.name})
    finally:
        result.pages_fetched = adapter.stats.pages_fetched
        result.passes = dict(adapter.stats.passes)
        adapter.close()

    result.valid = len(records)
    # Persist whatever was validly collected, even if a later page failed; nothing is deleted.
    if records:
        try:
            upsert = repo.upsert_listings(records, run_id, clock())
            result.inserted, result.updated = upsert.inserted, upsert.updated
            result.unchanged, result.history_rows = upsert.unchanged, upsert.history_rows
        except Exception as exc:
            log.exception("source persistence failed", extra={"source": adapter.name})
            result.status, result.error = "failed", f"persistence: {_safe_error(exc)}"
            result.duration_seconds = round(time.monotonic() - started, 2)
            return result

    if isinstance(fetch_error, SourceAccessBlocked):
        result.status, result.error, result.access_blocked = (
            "failed",
            f"fetch: {_safe_error(fetch_error)}",
            True,
        )
    elif fetch_error is not None:
        result.status, result.error = "failed", f"fetch: {_safe_error(fetch_error)}"
    elif result.found and result.rejected / result.found > MAX_REJECTION_RATIO:
        result.status = "failed"
        result.error = (
            f"validation: {result.rejected}/{result.found} records rejected (possible source change)"
        )
    elif result.found == 0:
        result.status, result.error = "failed", "source returned no records"
    else:
        result.status = "success"
    result.duration_seconds = round(time.monotonic() - started, 2)
    return result


def run_pipeline(
    settings: Settings,
    repo: Repository,
    adapters: Sequence[SourceAdapter],
    trigger: str = "manual",
    clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
) -> RunSummary:
    started_at = clock()
    run_id = repo.start_run(trigger, started_at)
    log.info("run started", extra={"run_id": run_id, "sources": [a.name for a in adapters]})

    results: dict[str, SourceResult] = {}
    blocked_groups: set[str] = set()
    for adapter in adapters:
        if adapter.access_group and adapter.access_group in blocked_groups:
            # Do not keep hitting a host that has just refused us.
            adapter.close()
            results[adapter.name] = SourceResult(
                origin=adapter.origin,
                status="failed",
                access_blocked=True,
                error=f"not attempted: {adapter.access_group} blocked an earlier source in this run",
            )
            continue
        result = collect_source(adapter, repo, run_id, settings, started_at, clock)
        if result.access_blocked and adapter.access_group:
            blocked_groups.add(adapter.access_group)
        results[adapter.name] = result
        log.info(
            "source finished",
            extra={"run_id": run_id, "source": adapter.name, **{k: v for k, v in asdict(result).items()}},
        )

    status = overall_status(list(results.values()))
    errors = [f"{name}: {r.error}" for name, r in results.items() if r.error]
    if status == "skipped":
        errors.append("no sources enabled")
    summary = RunSummary(
        run_id=run_id,
        status=status,
        started_at=started_at,
        finished_at=clock(),
        sources=results,
        error_summary="; ".join(errors)[:2000] or None,
    )
    repo.finish_run(run_id, summary.to_record())
    log.info("run finished", extra={"run_id": run_id, "status": status, "exit_code": summary.exit_code})
    return summary


def summary_markdown(summary: RunSummary) -> str:
    """Human-readable summary for the GitHub Actions job summary (no secrets)."""
    lines = [
        f"## Collection run `{summary.status}`",
        "",
        f"Run id: `{summary.run_id}` · started {summary.started_at.isoformat()} · "
        f"finished {summary.finished_at.isoformat()}",
        "",
        "| Source | Status | Found | Inserted | Updated | Unchanged | Rejected | Pages | Error |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, r in summary.sources.items():
        err = (r.error or "").replace("|", "\\|")
        lines.append(
            f"| {name} | {r.status} | {r.found} | {r.inserted} | {r.updated} | {r.unchanged} | "
            f"{r.rejected} | {r.pages_fetched} | {err} |"
        )
    if not summary.sources:
        lines.append("| — | skipped | 0 | 0 | 0 | 0 | 0 | 0 | no sources enabled |")
    return "\n".join(lines) + "\n"


def describe(summary: RunSummary) -> dict[str, Any]:
    return {"status": summary.status, "run_id": summary.run_id, "exit_code": summary.exit_code}
