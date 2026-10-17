"""CLI entry point: ``python -m scraper``.

    python -m scraper                                   # run ENABLED_SOURCES (live adapters)
    python -m scraper --import-file data.csv            # import an operator file (origin: imported)
    python -m scraper --import-file demo.json --origin synthetic
    python -m scraper --purge-synthetic --yes           # delete synthetic demo records

Exit codes: 0 success (or nothing enabled), 1 failed, 2 partial (some sources failed),
3 configuration error.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from scraper.config import ConfigError, Settings
from scraper.database import PostgresRepository, UpsertResult
from scraper.logging_setup import configure_logging
from scraper.models import ListingRecord
from scraper.pipeline import run_pipeline, summary_markdown
from scraper.sources import REGISTRY, build_adapters
from scraper.sources.base import SourceAdapter
from scraper.sources.file_import import FileImportAdapter

log = logging.getLogger("scraper")

EXIT_CONFIG = 3


class DryRunRepository:
    """Collects without writing anything; used by --dry-run."""

    def __init__(self) -> None:
        self.records: list[ListingRecord] = []

    def start_run(self, trigger: str, started_at: datetime) -> str:
        return "dry-run"

    def finish_run(self, run_id: str, record: Any) -> None:
        return None

    def source_watermark(self, source_name: str) -> datetime | None:
        return None

    def upsert_listings(self, records: Any, run_id: str, observed_at: datetime) -> UpsertResult:
        self.records.extend(records)
        return UpsertResult(inserted=len(records))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m scraper", description=__doc__)
    parser.add_argument("--sources", help="comma-separated override of ENABLED_SOURCES")
    parser.add_argument("--dry-run", action="store_true", help="fetch and validate, but write nothing")
    parser.add_argument("--max-pages", type=int, help="override MAX_PAGES_PER_SOURCE (1-500)")
    parser.add_argument("--no-refresh", action="store_true", help="skip the closing-soon refresh pass")
    parser.add_argument("--trigger", default=os.environ.get("COLLECTION_TRIGGER", "manual"))
    parser.add_argument("--summary-file", help="write a Markdown run summary to this path")
    parser.add_argument("--sample-output", help="dry-run only: write normalized records as JSON here")
    parser.add_argument("--list-sources", action="store_true")
    parser.add_argument(
        "--import-file", help="import listings from a .csv or .json file instead of live sources"
    )
    parser.add_argument("--origin", choices=["imported", "synthetic"], default="imported")
    parser.add_argument("--source-name", help="source name for imported records (default: from file name)")
    parser.add_argument(
        "--purge-synthetic", action="store_true", help="delete all synthetic listings, then exit"
    )
    parser.add_argument("--yes", action="store_true", help="confirm --purge-synthetic")
    return parser.parse_args(argv)


LIVE_GATE_MESSAGE = (
    "Live GeM collection is disabled. GeM's security gateway blocks automated clients "
    "(docs/SOURCE_FEASIBILITY.md section 3a); the collector will not work around that. "
    "Enable only after GeM approves automated access (GEM_LIVE_ACCESS_APPROVED=true) and grants "
    "reproduction permission (GEM_REPRODUCTION_PERMISSION_CONFIRMED=true)."
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        configure_logging("INFO")
        log.error("configuration error", extra={"error": str(exc)})
        return EXIT_CONFIG
    configure_logging(settings.log_level)

    if args.list_sources:
        for name in sorted(REGISTRY):
            print(name)
        return 0

    if args.purge_synthetic:
        return purge_synthetic(settings, confirmed=args.yes)

    if args.sources is not None:
        settings = replace(
            settings, enabled_sources=tuple(s.strip() for s in args.sources.split(",") if s.strip())
        )
    if args.max_pages is not None:
        if not 1 <= args.max_pages <= 500:
            log.error("--max-pages must be between 1 and 500")
            return EXIT_CONFIG
        settings = replace(settings, max_pages_per_source=args.max_pages)
    if args.no_refresh:
        settings = replace(settings, refresh_max_pages=0)

    adapters: list[SourceAdapter]
    if args.import_file:
        try:
            adapters = [FileImportAdapter(args.import_file, origin=args.origin, source_name=args.source_name)]
        except ValueError as exc:
            log.error("configuration error", extra={"error": str(exc)})
            return EXIT_CONFIG
    else:
        try:
            adapters = build_adapters(settings, settings.enabled_sources)
        except KeyError as exc:
            log.error("configuration error", extra={"error": str(exc)})
            return EXIT_CONFIG

    live_gated = [a.name for a in adapters if a.requires_permission]
    if live_gated:
        # Applies to dry runs too: a dry run still sends live requests.
        if not settings.gem_live_access_approved:
            log.error(LIVE_GATE_MESSAGE, extra={"sources": live_gated})
            return EXIT_CONFIG
        if not args.dry_run and not settings.gem_permission_confirmed:
            log.error(
                "GEM_REPRODUCTION_PERMISSION_CONFIRMED is not true. Obtain written permission from GeM SPV "
                "before storing GeM data for publication (docs/SOURCE_FEASIBILITY.md section 4).",
                extra={"sources": live_gated},
            )
            return EXIT_CONFIG

    if args.dry_run:
        dry = DryRunRepository()
        summary = run_pipeline(settings, dry, adapters, trigger="dry-run")
        if args.sample_output:
            with open(args.sample_output, "w", encoding="utf-8") as fh:
                json.dump([r.model_dump(mode="json") for r in dry.records], fh, indent=2, ensure_ascii=False)
    else:
        if not settings.database_url:
            log.error("DATABASE_URL is not set")
            return EXIT_CONFIG
        try:
            repo = PostgresRepository.connect(settings.database_url)
        except Exception as exc:
            # Never log the exception text: it can echo connection parameters.
            log.error("database connection failed", extra={"error_type": type(exc).__name__})
            return 1
        try:
            trigger = f"import:{args.origin}" if args.import_file else args.trigger
            summary = run_pipeline(
                settings, repo, adapters, trigger=trigger, clock=lambda: datetime.now(tz=UTC)
            )
        finally:
            repo.close()

    if args.summary_file:
        with open(args.summary_file, "w", encoding="utf-8") as fh:
            fh.write(summary_markdown(summary))
    return summary.exit_code


def purge_synthetic(settings: Settings, confirmed: bool) -> int:
    if not confirmed:
        log.error("--purge-synthetic deletes all synthetic listings; re-run with --yes to confirm")
        return EXIT_CONFIG
    if not settings.database_url:
        log.error("DATABASE_URL is not set")
        return EXIT_CONFIG
    try:
        repo = PostgresRepository.connect(settings.database_url)
    except Exception as exc:
        log.error("database connection failed", extra={"error_type": type(exc).__name__})
        return 1
    try:
        deleted = repo.purge_synthetic()
    finally:
        repo.close()
    log.info("synthetic listings deleted", extra={"deleted": deleted})
    return 0


if __name__ == "__main__":
    sys.exit(main())
