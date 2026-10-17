"""Adapter for GeM BidPlus "All Bids" public listing (https://bidplus.gem.gov.in/all-bids).

Access method verified on 2026-10-17 (docs/SOURCE_FEASIBILITY.md): the public page embeds a
CSRF token and loads listings with POST /all-bids-data, 10 per page. No login or CAPTCHA.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from scraper.models import ListingRecord, RejectedRecord
from scraper.normalizers.dates import IST, parse_datetime
from scraper.normalizers.text import clean_text, first_scalar
from scraper.normalizers.urls import InvalidUrl, canonicalize_url
from scraper.sources.base import (
    FetchContext,
    HttpClient,
    SourceAccessBlocked,
    SourceAdapter,
    SourceError,
    SourceSchemaError,
)

log = logging.getLogger(__name__)

BASE_URL = "https://bidplus.gem.gov.in"
LISTING_PAGE = f"{BASE_URL}/all-bids"
DATA_ENDPOINT = f"{BASE_URL}/all-bids-data"
ALLOWED_HOSTS = frozenset({"bidplus.gem.gov.in"})
PAGE_SIZE = 10
CSRF_FIELD = "csrf_bd_gem_nk"
# Observed 2026-10-17: GeM's security gateway answers HTTP 200 with this page when it blocks a client.
_BLOCK_MARKERS = ("page is blocked due to security issue", "<title>error occured</title>")
_TOKEN_RE = re.compile(r"""['"]csrf_bd_gem_nk['"]\s*:\s*['"]([A-Za-z0-9]{16,128})['"]""")

CATEGORY_BY_B_TYPE = {0: "Products", 1: "Services"}
LISTING_TYPE_BY_BID_TYPE = {1: "Bid", 2: "Reverse Auction", 5: "Direct Reverse Auction"}


def _int_or_none(value: object) -> int | None:
    value = first_scalar(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def check_not_blocked(text: str) -> None:
    lowered = text[:5000].lower()
    if any(marker in lowered for marker in _BLOCK_MARKERS):
        raise SourceAccessBlocked(
            "GeM security gateway blocked the request. The collector identifies itself honestly and will "
            "not impersonate a browser; access must be arranged with GeM (see docs/SOURCE_FEASIBILITY.md)."
        )


def listing_url(b_id: int, bid_type: int | None, eval_type: int | None) -> str:
    """Build the official document URL exactly as the portal's own JavaScript does."""
    if bid_type == 5:
        path = f"/showdirectradocumentPdf/{b_id}"
    elif bid_type == 2:
        path = f"/list-ra-schedules/{b_id}" if (eval_type or 0) > 0 else f"/showradocumentPdf/{b_id}"
    else:
        path = f"/showbidDocument/{b_id}"
    return canonicalize_url(BASE_URL + path, ALLOWED_HOSTS)


class GemBidPlusAdapter(SourceAdapter):
    origin = "live"
    requires_permission = True
    access_group = "gem.gov.in"

    def __init__(
        self,
        name: str,
        by_type: str,
        description: str,
        client_factory: Callable[[], HttpClient],
    ) -> None:
        super().__init__()
        self.name = name
        self.by_type = by_type
        self.description = description
        self._client_factory = client_factory
        self._client: HttpClient | None = None
        self._token: str | None = None

    # ------------------------------------------------------------------ network

    @property
    def client(self) -> HttpClient:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def _bootstrap(self) -> None:
        response = self.client.get(LISTING_PAGE)
        check_not_blocked(response.text)
        match = _TOKEN_RE.search(response.text)
        if not match:
            raise SourceSchemaError("CSRF token not found on the public listing page")
        self._token = match.group(1)

    def _payload(self, sort: str, page: int, end_from: str = "", end_to: str = "") -> str:
        body: dict[str, Any] = {
            "param": {"searchBid": "", "searchType": "fullText"},
            "filter": {
                "bidStatusType": "ongoing_bids",
                "byType": self.by_type,
                "highBidValue": "",
                "byEndDate": {"from": end_from, "to": end_to},
                "sort": sort,
            },
        }
        if page > 1:
            body["page"] = page
        return json.dumps(body, separators=(",", ":"))

    def fetch_page(self, sort: str, page: int, end_from: str = "", end_to: str = "") -> tuple[list[Any], int]:
        if self._token is None:
            self._bootstrap()
        assert self._token is not None
        response = self.client.post(
            DATA_ENDPOINT,
            data={"payload": self._payload(sort, page, end_from, end_to), CSRF_FIELD: self._token},
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": LISTING_PAGE},
        )
        self.stats.pages_fetched += 1
        check_not_blocked(response.text)
        try:
            body = response.json()
        except ValueError as exc:
            raise SourceSchemaError("listing response is not JSON") from exc
        return self.parse_response(body)

    @staticmethod
    def parse_response(body: Any) -> tuple[list[Any], int]:
        if not isinstance(body, dict):
            raise SourceSchemaError("listing response is not an object")
        if body.get("code") != 200:
            raise SourceError(f"listing endpoint returned code {body.get('code')!r}")
        inner = body.get("response")
        inner = inner.get("response") if isinstance(inner, dict) else None
        if not isinstance(inner, dict):
            raise SourceSchemaError("missing response.response")
        docs, num_found = inner.get("docs"), inner.get("numFound")
        if not isinstance(docs, list) or not isinstance(num_found, int) or isinstance(num_found, bool):
            raise SourceSchemaError("missing docs/numFound")
        if len(docs) > PAGE_SIZE * 5:
            raise SourceSchemaError("unexpectedly large page")
        return docs, num_found

    # ------------------------------------------------------------------ iteration

    def iter_pages(self, ctx: FetchContext) -> Iterator[list[Mapping[str, Any]]]:
        settings = ctx.settings
        yield from self._paged(
            "new",
            sort="Bid-Start-Date-Latest",
            max_pages=settings.max_pages_per_source,
            stop_before=ctx.watermark,
        )
        if settings.refresh_window_days > 0 and settings.refresh_max_pages > 0:
            today = ctx.now.astimezone(IST).date()
            yield from self._paged(
                "refresh",
                sort="Bid-End-Date-Oldest",
                max_pages=settings.refresh_max_pages,
                end_from=today.isoformat(),
                end_to=(today + timedelta(days=settings.refresh_window_days)).isoformat(),
            )

    def _paged(
        self,
        pass_name: str,
        *,
        sort: str,
        max_pages: int,
        stop_before: datetime | None = None,
        end_from: str = "",
        end_to: str = "",
    ) -> Iterator[list[Mapping[str, Any]]]:
        previous_ids: list[Any] | None = None
        for page in range(1, max_pages + 1):
            docs, num_found = self.fetch_page(sort, page, end_from, end_to)
            ids = [d.get("id") if isinstance(d, dict) else None for d in docs]
            if previous_ids is not None and ids and ids == previous_ids:
                raise SourceError(f"{pass_name}: page {page} repeated the previous page; pagination ignored")
            previous_ids = ids
            items: list[Mapping[str, Any]] = [d for d in docs if isinstance(d, dict)]
            yield items
            if not docs or page * PAGE_SIZE >= num_found:
                self.stats.passes[pass_name] = f"exhausted after {page} page(s)"
                return
            if stop_before is not None and self._all_older(items, stop_before):
                self.stats.passes[pass_name] = f"reached watermark after {page} page(s)"
                return
        self.stats.passes[pass_name] = f"page cap {max_pages} reached"
        log.warning("page cap reached", extra={"source": self.name, "pass": pass_name, "pages": max_pages})

    @staticmethod
    def _all_older(items: Sequence[Mapping[str, Any]], watermark: datetime) -> bool:
        starts = [
            parse_datetime(i.get("final_start_date_sort"), assume_tz=IST, ignore_utc_designator=True)
            for i in items
        ]
        return bool(starts) and all(s is not None and s < watermark for s in starts)

    # ------------------------------------------------------------------ normalization

    def normalize(self, raw: Mapping[str, Any]) -> ListingRecord:
        b_id = _int_or_none(raw.get("b_id")) or _int_or_none(raw.get("id"))
        if b_id is None or b_id <= 0:
            raise RejectedRecord("missing or invalid b_id")

        title = clean_text(raw.get("b_category_name")) or clean_text(raw.get("bd_category_name"))
        if title is None:
            raise RejectedRecord("missing title")
        boq_title = clean_text(raw.get("bbt_title"), max_length=300)
        if boq_title:
            title = f"{title} ({boq_title})"

        ministry = clean_text(raw.get("ba_official_details_minName"), max_length=500)
        department = clean_text(raw.get("ba_official_details_deptName"), max_length=500)
        org_parts = [p for p in (ministry, department) if p]
        organisation = " / ".join(dict.fromkeys(org_parts)) or None

        b_type = _int_or_none(raw.get("b_type"))
        bid_type = _int_or_none(raw.get("b_bid_type"))
        eval_type = _int_or_none(raw.get("b_eval_type"))

        quantity: Decimal | None = None
        q = first_scalar(raw.get("b_total_quantity"))
        if isinstance(q, (int, float, str)) and not isinstance(q, bool):
            try:
                quantity = Decimal(str(q))
            except InvalidOperation:
                quantity = None
            if quantity is not None and (not quantity.is_finite() or quantity < 0):
                quantity = None

        try:
            url = listing_url(b_id, bid_type, eval_type)
        except InvalidUrl as exc:  # pragma: no cover - URL is built from an int
            raise RejectedRecord(str(exc)) from exc

        try:
            return ListingRecord(
                source_name=self.name,
                source_id=str(b_id),
                bid_number=clean_text(raw.get("b_bid_number"), max_length=100),
                title=title[:2000],
                organisation=organisation,
                ministry=ministry,
                department=department,
                category=CATEGORY_BY_B_TYPE.get(b_type) if b_type is not None else None,
                listing_type=LISTING_TYPE_BY_BID_TYPE.get(bid_type) if bid_type is not None else None,
                quantity=quantity,
                published_at=parse_datetime(
                    raw.get("final_start_date_sort"), assume_tz=IST, ignore_utc_designator=True
                ),
                deadline=parse_datetime(
                    raw.get("final_end_date_sort"), assume_tz=IST, ignore_utc_designator=True
                ),
                url=url,
            )
        except ValidationError as exc:
            raise RejectedRecord(f"validation failed: {exc.error_count()} error(s)") from exc

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
