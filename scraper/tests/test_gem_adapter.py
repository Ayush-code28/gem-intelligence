from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs

import pytest
import requests

from scraper.config import Settings
from scraper.models import RejectedRecord
from scraper.normalizers.dates import IST
from scraper.sources import REGISTRY, build_adapters
from scraper.sources.base import FetchContext, SourceAccessBlocked, SourceError, SourceSchemaError
from scraper.sources.gem_bidplus import GemBidPlusAdapter, listing_url
from scraper.tests.conftest import FakeClient, FakeResponse, load_fixture, page_body, synthetic_doc

NOW = datetime(2030, 1, 10, 6, 0, tzinfo=UTC)


def make_adapter(client: FakeClient, by_type: str = "product") -> GemBidPlusAdapter:
    return GemBidPlusAdapter("gem_bids_products", by_type, "synthetic", lambda: client)


def ctx(watermark: datetime | None = None, **settings: Any) -> FetchContext:
    base = {"max_pages_per_source": 5, "refresh_max_pages": 0}
    base.update(settings)
    return FetchContext(now=NOW, watermark=watermark, settings=Settings(**base))


def fixture_docs() -> list[dict[str, Any]]:
    return json.loads(load_fixture("gem_all_bids_page_synthetic.json"))["response"]["response"]["docs"]


def sent_payload(client: FakeClient, index: int) -> dict[str, Any]:
    data = client.payloads[index]["data"]
    return json.loads(data["payload"])


class TestNormalize:
    def test_full_record(self) -> None:
        rec = make_adapter(FakeClient([])).normalize(fixture_docs()[0])
        assert rec.source_id == "900000001"
        assert rec.dedup_key == "id:900000001"
        assert rec.bid_number == "GEM/TEST/B/000001"
        assert rec.title == "Synthetic Office Chairs"
        assert rec.organisation == "Synthetic Ministry of Examples / Department of Test Fixtures"
        assert rec.category == "Products"
        assert rec.listing_type == "Bid"
        assert rec.quantity == Decimal("25")
        assert rec.deadline == datetime(2030, 1, 20, 17, 0, tzinfo=IST)
        assert rec.published_at == datetime(2030, 1, 10, 10, 0, tzinfo=IST)
        assert rec.url == "https://bidplus.gem.gov.in/showbidDocument/900000001"

    def test_missing_and_malformed_fields_become_null(self) -> None:
        rec = make_adapter(FakeClient([])).normalize(fixture_docs()[1])
        assert rec.title == "Synthetic Facility Cleaning Service (Lot A)"
        assert rec.ministry is None
        assert rec.organisation == "Synthetic Municipal Board"
        assert rec.deadline is None  # "not-a-date" is never guessed
        assert rec.category == "Services"
        assert rec.listing_type == "Reverse Auction"
        assert rec.url == "https://bidplus.gem.gov.in/list-ra-schedules/900000002"

    def test_missing_title_rejected(self) -> None:
        with pytest.raises(RejectedRecord, match="title"):
            make_adapter(FakeClient([])).normalize(fixture_docs()[2])

    @pytest.mark.parametrize("b_id", [None, [], ["abc"], [0], [-5], [True]])
    def test_missing_id_rejected(self, b_id: object) -> None:
        doc = {**synthetic_doc(1), "b_id": b_id, "id": None}
        with pytest.raises(RejectedRecord, match="b_id"):
            make_adapter(FakeClient([])).normalize(doc)

    @pytest.mark.parametrize("qty", [["abc"], [-3], ["NaN"], [None], [True]])
    def test_bad_quantity_is_null(self, qty: object) -> None:
        rec = make_adapter(FakeClient([])).normalize({**synthetic_doc(1), "b_total_quantity": qty})
        assert rec.quantity is None

    def test_unknown_codes_are_null(self) -> None:
        rec = make_adapter(FakeClient([])).normalize({**synthetic_doc(1), "b_type": [9], "b_bid_type": [9]})
        assert rec.category is None and rec.listing_type is None

    def test_listing_urls(self) -> None:
        assert listing_url(7, 1, 0).endswith("/showbidDocument/7")
        assert listing_url(7, 2, 0).endswith("/showradocumentPdf/7")
        assert listing_url(7, 2, 3).endswith("/list-ra-schedules/7")
        assert listing_url(7, 5, None).endswith("/showdirectradocumentPdf/7")
        assert listing_url(7, None, None).endswith("/showbidDocument/7")


class TestResponseHandling:
    @pytest.mark.parametrize(
        "body",
        [
            [],
            "x",
            {"code": 200},
            {"code": 200, "response": {"response": {"docs": "x", "numFound": 1}}},
            {"code": 200, "response": {"response": {"docs": [], "numFound": "1"}}},
        ],
    )
    def test_schema_errors(self, body: Any) -> None:
        with pytest.raises(SourceSchemaError):
            GemBidPlusAdapter.parse_response(body)

    def test_error_code(self) -> None:
        with pytest.raises(SourceError, match="404"):
            GemBidPlusAdapter.parse_response({"code": 404, "message": "No record"})

    def test_csrf_token_and_payload(self) -> None:
        client = FakeClient([FakeResponse(payload=page_body([synthetic_doc(1)], 1))])
        adapter = make_adapter(client)
        list(adapter.iter_pages(ctx()))
        sent = client.payloads[0]
        assert sent["data"]["csrf_bd_gem_nk"] == "abcdef0123456789abcdef0123456789"
        payload = sent_payload(client, 0)
        assert payload["filter"]["byType"] == "product"
        assert payload["filter"]["bidStatusType"] == "ongoing_bids"
        assert payload["filter"]["sort"] == "Bid-Start-Date-Latest"
        assert "page" not in payload

    def test_missing_token_fails(self) -> None:
        client = FakeClient([], page_html="<html>no token</html>")
        with pytest.raises(SourceSchemaError, match="CSRF"):
            list(make_adapter(client).iter_pages(ctx()))

    def test_block_page_on_listing_page(self) -> None:
        client = FakeClient([], page_html=load_fixture("gem_block_page_synthetic.html"))
        with pytest.raises(SourceAccessBlocked):
            list(make_adapter(client).iter_pages(ctx()))
        assert client.payloads == []  # gives up immediately; no workaround attempted

    def test_block_page_on_data_request(self) -> None:
        client = FakeClient([FakeResponse(load_fixture("gem_block_page_synthetic.html"))])
        with pytest.raises(SourceAccessBlocked):
            list(make_adapter(client).iter_pages(ctx()))

    def test_non_json(self) -> None:
        client = FakeClient([FakeResponse("<html>maintenance</html>")])
        with pytest.raises(SourceSchemaError, match="JSON"):
            list(make_adapter(client).iter_pages(ctx()))

    def test_network_error_propagates(self) -> None:
        client = FakeClient([requests.ConnectionError("synthetic outage")])
        with pytest.raises(requests.ConnectionError):
            list(make_adapter(client).iter_pages(ctx()))


class TestPagination:
    def test_stops_when_exhausted(self) -> None:
        docs = [synthetic_doc(i) for i in range(10)]
        client = FakeClient(
            [
                FakeResponse(payload=page_body(docs, 12)),
                FakeResponse(payload=page_body([synthetic_doc(11)], 12, 10)),
            ]
        )
        adapter = make_adapter(client)
        pages = list(adapter.iter_pages(ctx()))
        assert [len(p) for p in pages] == [10, 1]
        assert sent_payload(client, 1)["page"] == 2
        assert adapter.stats.passes["new"].startswith("exhausted")

    def test_page_cap_is_enforced(self) -> None:
        posts = [
            FakeResponse(payload=page_body([synthetic_doc(p * 10 + i) for i in range(10)], 10_000))
            for p in range(3)
        ]
        adapter = make_adapter(FakeClient(posts))
        pages = list(adapter.iter_pages(ctx(max_pages_per_source=3)))
        assert len(pages) == 3
        assert adapter.stats.passes["new"] == "page cap 3 reached"

    def test_stops_at_watermark(self) -> None:
        newer = [synthetic_doc(i, start="2030-01-09T10:00:00Z") for i in range(10)]
        older = [synthetic_doc(10 + i, start="2030-01-01T10:00:00Z") for i in range(10)]
        client = FakeClient(
            [FakeResponse(payload=page_body(newer, 500)), FakeResponse(payload=page_body(older, 500))]
        )
        adapter = make_adapter(client)
        pages = list(adapter.iter_pages(ctx(watermark=datetime(2030, 1, 5, tzinfo=UTC))))
        assert len(pages) == 2  # the older page is still processed, then iteration stops
        assert adapter.stats.passes["new"] == "reached watermark after 2 page(s)"

    def test_repeated_page_detected(self) -> None:
        docs = [synthetic_doc(i) for i in range(10)]
        client = FakeClient(
            [FakeResponse(payload=page_body(docs, 100)), FakeResponse(payload=page_body(docs, 100))]
        )
        with pytest.raises(SourceError, match="repeated"):
            list(make_adapter(client).iter_pages(ctx()))

    def test_refresh_pass_uses_bounded_ist_date_window(self) -> None:
        client = FakeClient(
            [
                FakeResponse(payload=page_body([synthetic_doc(1)], 1)),
                FakeResponse(payload=page_body([synthetic_doc(2)], 1)),
            ]
        )
        adapter = make_adapter(client)
        list(adapter.iter_pages(ctx(refresh_max_pages=2, refresh_window_days=2)))
        refresh = sent_payload(client, 1)["filter"]
        assert refresh["sort"] == "Bid-End-Date-Oldest"
        assert refresh["byEndDate"] == {"from": "2030-01-10", "to": "2030-01-12"}
        assert set(adapter.stats.passes) == {"new", "refresh"}


def test_registry_and_form_encoding() -> None:
    assert set(REGISTRY) == {"gem_bids_products", "gem_bids_services"}
    adapters = build_adapters(Settings(), ("gem_bids_services",))
    assert isinstance(adapters[0], GemBidPlusAdapter) and adapters[0].by_type == "service"
    with pytest.raises(KeyError):
        build_adapters(Settings(), ("nope",))
    # payload must survive form encoding unchanged
    body = make_adapter(FakeClient([]))._payload("Bid-Start-Date-Latest", 3)
    assert json.loads(parse_qs(f"payload={requests.utils.quote(body)}")["payload"][0])["page"] == 3
