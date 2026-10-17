"""Import listings from a local CSV or JSON file.

Imported rows go through the same validation, normalization, deduplication and change
detection as live sources. Each import is tagged with an origin:

* ``imported``  - data the operator obtained elsewhere and is responsible for (provenance,
  accuracy and any permission to republish it);
* ``synthetic`` - invented demonstration/test data. Synthetic titles are always prefixed with
  ``[SYNTHETIC]`` and synthetic records never carry a source URL, so they cannot be mistaken
  for, or link to, real GeM listings.

Accepted columns / keys (all optional except ``title`` and one of ``source_id``/``url``):
source_id, bid_number, title, organisation, ministry, department, category, listing_type,
quantity, published_at, deadline, url. Date-times must include a time; values without an
explicit offset are interpreted as IST.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterator, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from scraper.models import ListingRecord, RejectedRecord
from scraper.normalizers.dates import IST, parse_datetime
from scraper.normalizers.text import clean_text
from scraper.normalizers.urls import InvalidUrl, canonicalize_url
from scraper.sources.base import FetchContext, SourceAdapter, SourceSchemaError

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_ROWS = 200_000
BATCH_SIZE = 500
SYNTHETIC_PREFIX = "[SYNTHETIC]"

# Source links in imports may only point at the official portal.
URL_HOSTS = frozenset({"gem.gov.in"})
URL_SUFFIXES = (".gem.gov.in",)

KNOWN_FIELDS = frozenset(
    {
        "source_id",
        "id",
        "bid_number",
        "title",
        "organisation",
        "organization",
        "ministry",
        "department",
        "category",
        "listing_type",
        "quantity",
        "published_at",
        "deadline",
        "url",
    }
)


def default_source_name(path: Path, origin: str) -> str:
    if origin == "synthetic":
        return "synthetic_demo"
    stem = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_") or "file"
    return f"import_{stem}"[:60]


class FileImportAdapter(SourceAdapter):
    requires_permission = False
    access_group = None

    def __init__(self, path: str | Path, origin: str = "imported", source_name: str | None = None) -> None:
        super().__init__()
        if origin not in {"imported", "synthetic"}:
            raise ValueError("origin must be 'imported' or 'synthetic'")
        self.path = Path(path)
        self.origin = origin
        self.name = source_name or default_source_name(self.path, origin)
        if not re.fullmatch(r"[a-z0-9_]+", self.name):
            raise ValueError("source name may only contain lowercase letters, digits and underscores")
        self.description = f"{origin} file {self.path.name}"

    # ------------------------------------------------------------------ reading

    def _rows(self) -> Iterator[Mapping[str, Any]]:
        if not self.path.is_file():
            raise SourceSchemaError(f"import file not found: {self.path.name}")
        if self.path.stat().st_size > MAX_FILE_BYTES:
            raise SourceSchemaError(f"import file larger than {MAX_FILE_BYTES // (1024 * 1024)} MB")
        suffix = self.path.suffix.lower()
        if suffix == ".csv":
            with self.path.open(newline="", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                if not reader.fieldnames or "title" not in {f.strip().lower() for f in reader.fieldnames}:
                    raise SourceSchemaError("CSV must have a header row with at least a 'title' column")
                for row in reader:
                    yield {(k or "").strip().lower(): v for k, v in row.items()}
        elif suffix == ".json":
            try:
                data = json.loads(self.path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                raise SourceSchemaError(f"invalid JSON: {exc.msg} (line {exc.lineno})") from exc
            records = data.get("records") if isinstance(data, dict) else data
            if not isinstance(records, list):
                raise SourceSchemaError('JSON must be an array of objects or {"records": [...]}')
            for item in records:
                # Non-objects are passed through and rejected individually by normalize().
                yield (
                    {str(k).lower(): v for k, v in item.items()}
                    if isinstance(item, dict)
                    else {"__invalid__": item}
                )
        else:
            raise SourceSchemaError("import file must be .csv or .json")

    def iter_pages(self, ctx: FetchContext) -> Iterator[list[Mapping[str, Any]]]:
        batch: list[Mapping[str, Any]] = []
        count = 0
        for row in self._rows():
            count += 1
            if count > MAX_ROWS:
                raise SourceSchemaError(f"import exceeds {MAX_ROWS} rows; split the file")
            batch.append(row)
            if len(batch) >= BATCH_SIZE:
                self.stats.pages_fetched += 1
                yield batch
                batch = []
        if batch:
            self.stats.pages_fetched += 1
            yield batch
        self.stats.passes["file"] = f"read {count} row(s)"

    # ------------------------------------------------------------------ normalization

    def normalize(self, raw: Mapping[str, Any]) -> ListingRecord:
        if "__invalid__" in raw:
            raise RejectedRecord("row is not an object")
        title = clean_text(raw.get("title"))
        if title is None:
            raise RejectedRecord("missing title")
        if self.origin == "synthetic" and not title.startswith(SYNTHETIC_PREFIX):
            title = f"{SYNTHETIC_PREFIX} {title}"

        source_id = clean_text(raw.get("source_id"), max_length=200) or clean_text(
            raw.get("id"), max_length=200
        )
        if source_id is None and isinstance(raw.get("source_id") or raw.get("id"), int):
            source_id = str(raw.get("source_id") or raw.get("id"))

        url: str | None = None
        raw_url = raw.get("url")
        if self.origin != "synthetic" and isinstance(raw_url, str) and raw_url.strip():
            try:
                url = canonicalize_url(raw_url, URL_HOSTS, URL_SUFFIXES)
            except InvalidUrl:
                url = None  # unsafe or non-GeM link: dropped rather than published
        if source_id is None and url is None:
            raise RejectedRecord("missing source_id and valid url")

        ministry = clean_text(raw.get("ministry"), max_length=500)
        department = clean_text(raw.get("department"), max_length=500)
        organisation = clean_text(raw.get("organisation") or raw.get("organization"), max_length=1000)
        if organisation is None:
            organisation = " / ".join(dict.fromkeys(p for p in (ministry, department) if p)) or None

        quantity: Decimal | None = None
        q = raw.get("quantity")
        if isinstance(q, (int, float, str)) and not isinstance(q, bool) and str(q).strip():
            try:
                quantity = Decimal(str(q).strip().replace(",", ""))
            except InvalidOperation:
                quantity = None
            if quantity is not None and (not quantity.is_finite() or quantity < 0):
                quantity = None

        try:
            return ListingRecord(
                source_name=self.name,
                source_id=source_id,
                bid_number=clean_text(raw.get("bid_number"), max_length=100),
                title=title[:2000],
                organisation=organisation,
                ministry=ministry,
                department=department,
                category=clean_text(raw.get("category"), max_length=200),
                listing_type=clean_text(raw.get("listing_type"), max_length=100),
                quantity=quantity,
                published_at=parse_datetime(raw.get("published_at"), assume_tz=IST),
                deadline=parse_datetime(raw.get("deadline"), assume_tz=IST),
                url=url,
                data_origin=self.origin,
            )
        except ValidationError as exc:
            raise RejectedRecord(f"validation failed: {exc.error_count()} error(s)") from exc
