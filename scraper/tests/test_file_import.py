from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from scraper.config import Settings
from scraper.models import RejectedRecord
from scraper.normalizers.dates import IST
from scraper.pipeline import run_pipeline
from scraper.sources.base import FetchContext, SourceSchemaError
from scraper.sources.file_import import FileImportAdapter
from scraper.synthetic import generate
from scraper.tests.conftest import FakeRepository

REPO = Path(__file__).resolve().parents[2]
CTX = FetchContext(now=datetime(2030, 1, 1, tzinfo=UTC), watermark=None, settings=Settings())


def rows(adapter: FileImportAdapter) -> list[Any]:
    return [r for page in adapter.iter_pages(CTX) for r in page]


def write_json(tmp_path: Path, records: Any, name: str = "data.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(records), encoding="utf-8")
    return p


def test_csv_template_imports(tmp_path: Path) -> None:
    adapter = FileImportAdapter(REPO / "data/samples/import_template.csv")
    assert adapter.name == "import_import_template"
    records = [adapter.normalize(r) for r in rows(adapter)]
    assert [r.source_id for r in records] == ["EXAMPLE-0001", "EXAMPLE-0002"]
    first, second = records
    assert first.data_origin == "imported"
    assert first.organisation == "Example Ministry / Example Department"
    assert first.quantity == Decimal("25")
    assert first.deadline == datetime(2030, 1, 20, 17, 0, tzinfo=IST)
    assert second.organisation == "Example Municipal Board"
    assert second.quantity is None
    assert second.deadline == datetime(2030, 1, 25, 15, 0, tzinfo=IST)  # naive → IST


def test_json_template_imports() -> None:
    adapter = FileImportAdapter(REPO / "data/samples/import_template.json")
    (record,) = [adapter.normalize(r) for r in rows(adapter)]
    assert record.title.startswith("[EXAMPLE ROW")


def test_json_array_and_urls(tmp_path: Path) -> None:
    path = write_json(
        tmp_path,
        [
            {"id": 7, "title": "A", "url": "https://bidplus.gem.gov.in/showbidDocument/7#x"},
            {"source_id": "8", "title": "B", "url": "https://evil.example.com/phish"},
            {"source_id": "9", "title": "C", "url": "javascript:alert(1)"},
            {"title": "D", "url": "https://gem.gov.in/some/page"},
        ],
    )
    adapter = FileImportAdapter(path)
    out = [adapter.normalize(r) for r in rows(adapter)]
    assert out[0].source_id == "7" and out[0].url == "https://bidplus.gem.gov.in/showbidDocument/7"
    assert out[1].url is None and out[2].url is None  # unsafe/non-GeM links dropped, never published
    assert out[3].source_id is None and out[3].dedup_key == "url:https://gem.gov.in/some/page"


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ({"source_id": "1"}, "title"),
        ({"source_id": "1", "title": "   "}, "title"),
        ({"title": "no id"}, "source_id"),
        ({"title": "bad url only", "url": "https://evil.example.com"}, "source_id"),
        ({"title": "neg", "source_id": "1", "quantity": "-5", "deadline": "2030-02-30T10:00:00"}, None),
    ],
)
def test_validation(tmp_path: Path, row: dict[str, Any], reason: str | None) -> None:
    adapter = FileImportAdapter(write_json(tmp_path, [row]))
    (raw,) = rows(adapter)
    if reason is None:
        rec = adapter.normalize(raw)
        assert rec.quantity is None and rec.deadline is None  # malformed values become null
    else:
        with pytest.raises(RejectedRecord, match=reason):
            adapter.normalize(raw)


def test_non_object_rows_rejected(tmp_path: Path) -> None:
    adapter = FileImportAdapter(write_json(tmp_path, {"records": ["x", 3]}))
    for raw in rows(adapter):
        with pytest.raises(RejectedRecord, match="not an object"):
            adapter.normalize(raw)


@pytest.mark.parametrize(
    ("name", "content", "match"),
    [
        ("bad.json", "{not json", "invalid JSON"),
        ("obj.json", '{"foo": 1}', "array"),
        ("data.xml", "<x/>", ".csv or .json"),
        ("nohdr.csv", "a,b\n1,2\n", "title"),
    ],
)
def test_file_errors(tmp_path: Path, name: str, content: str, match: str) -> None:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    with pytest.raises(SourceSchemaError, match=match):
        rows(FileImportAdapter(p))


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SourceSchemaError, match="not found"):
        rows(FileImportAdapter(tmp_path / "nope.csv"))


def test_bad_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="origin"):
        FileImportAdapter(tmp_path / "x.csv", origin="live")
    with pytest.raises(ValueError, match="source name"):
        FileImportAdapter(tmp_path / "x.csv", source_name="Bad Name")


def test_synthetic_records_are_labelled_and_unlinked(tmp_path: Path) -> None:
    path = write_json(
        tmp_path,
        [{"source_id": "1", "title": "Chairs", "url": "https://bidplus.gem.gov.in/showbidDocument/1"}],
    )
    adapter = FileImportAdapter(path, origin="synthetic")
    assert adapter.name == "synthetic_demo"
    rec = adapter.normalize(rows(adapter)[0])
    assert rec.title == "[SYNTHETIC] Chairs"
    assert rec.url is None and rec.data_origin == "synthetic"


def test_generator_is_labelled_deterministic_and_revisable() -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    base = generate(30, 0, now)
    assert base == generate(30, 0, now)
    assert all(r["title"].startswith("[SYNTHETIC]") and "url" not in r for r in base)
    assert all(r["bid_number"].startswith("SYN/") for r in base)
    revised = generate(30, 1, now)
    changed = {r["source_id"] for r, o in zip(revised, base, strict=True) if r != o}
    assert changed == {"SYN-00007", "SYN-00011", "SYN-00014", "SYN-00021", "SYN-00022", "SYN-00028"}


def test_import_through_pipeline_and_reimport_detects_changes(tmp_path: Path) -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    first = write_json(tmp_path, {"records": generate(30, 0, now)}, "r0.json")
    second = write_json(tmp_path, {"records": generate(30, 1, now)}, "r1.json")
    repo = FakeRepository()
    s1 = run_pipeline(Settings(), repo, [FileImportAdapter(first, origin="synthetic")], clock=lambda: now)
    s2 = run_pipeline(Settings(), repo, [FileImportAdapter(second, origin="synthetic")], clock=lambda: now)
    assert s1.status == "success" and s1.sources["synthetic_demo"].inserted == 30
    assert s1.sources["synthetic_demo"].origin == "synthetic"
    r2 = s2.sources["synthetic_demo"]
    assert (r2.inserted, r2.updated, r2.unchanged) == (0, 6, 24)
    assert {f for _, f, _, _ in repo.history} == {"deadline", "title"}
