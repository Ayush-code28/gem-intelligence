from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from scraper.changes import content_hash, diff, merge_observation
from scraper.models import ListingRecord, serialize_value


def record(**overrides: object) -> ListingRecord:
    base: dict[str, object] = {
        "source_name": "test_source",
        "source_id": "1",
        "title": "Synthetic item",
        "organisation": "Department of Test Fixtures",
        "deadline": datetime(2030, 1, 20, 11, 30, tzinfo=UTC),
        "quantity": Decimal("5"),
        "url": "https://bidplus.gem.gov.in/showbidDocument/1",
    }
    base.update(overrides)
    return ListingRecord(**base)  # type: ignore[arg-type]


def test_no_change_when_identical() -> None:
    r = record()
    assert diff(r.tracked_values(), merge_observation(r.tracked_values(), r)) == []


def test_deadline_change_detected() -> None:
    old = record().tracked_values()
    new = record(deadline=datetime(2030, 1, 25, 11, 30, tzinfo=UTC))
    changes = diff(old, merge_observation(old, new))
    assert [c.field_name for c in changes] == ["deadline"]
    assert changes[0].old_value == "2030-01-20T11:30:00+00:00"
    assert changes[0].new_value == "2030-01-25T11:30:00+00:00"


def test_same_instant_different_timezone_is_not_a_change() -> None:
    from scraper.normalizers.dates import IST

    old = record().tracked_values()
    new = record(deadline=datetime(2030, 1, 20, 17, 0, tzinfo=IST))
    assert diff(old, merge_observation(old, new)) == []


def test_missing_field_in_new_observation_keeps_stored_value() -> None:
    old = record().tracked_values()
    merged = merge_observation(old, record(organisation=None, deadline=None))
    assert merged["organisation"] == "Department of Test Fixtures"
    assert diff(old, merged) == []


def test_decimal_representation_is_stable() -> None:
    assert serialize_value(Decimal("5.000")) == serialize_value(Decimal("5"))
    old = record(quantity=Decimal("5.00")).tracked_values()
    assert diff(old, merge_observation(old, record(quantity=Decimal("5")))) == []


def test_content_hash_stable_and_sensitive() -> None:
    a = record().tracked_values()
    assert content_hash(a) == content_hash(dict(a))
    assert content_hash(a) != content_hash(record(title="Other").tracked_values())


def test_dedup_key_prefers_source_id_then_url() -> None:
    assert record().dedup_key == "id:1"
    assert record(source_id=None).dedup_key == "url:https://bidplus.gem.gov.in/showbidDocument/1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"title": "   "},
        {"source_id": None, "url": None},
        {"url": "http://bidplus.gem.gov.in/x"},
        {"deadline": datetime(2030, 1, 1)},  # noqa: DTZ001 - naive on purpose
        {"quantity": Decimal("-1")},
        {"source_name": "Bad Name"},
    ],
)
def test_schema_validation_rejects(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        record(**overrides)
