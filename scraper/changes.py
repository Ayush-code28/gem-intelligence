"""Change detection between the stored listing and a fresh observation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from scraper.models import TRACKED_FIELDS, ListingRecord, serialize_value


@dataclass(frozen=True)
class FieldChange:
    field_name: str
    old_value: str | None
    new_value: str | None


def content_hash(values: Mapping[str, Any]) -> str:
    canonical = {name: serialize_value(values.get(name)) for name in TRACKED_FIELDS}
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def merge_observation(existing: Mapping[str, Any], record: ListingRecord) -> dict[str, Any]:
    """Combine the stored values with a new observation.

    A field that is missing (None) in the new observation keeps its stored value: absence
    in one response is not evidence that the value was removed, and must not erase data.
    """
    merged: dict[str, Any] = {}
    for name, new_value in record.tracked_values().items():
        merged[name] = existing.get(name) if new_value is None else new_value
    return merged


def diff(existing: Mapping[str, Any], merged: Mapping[str, Any]) -> list[FieldChange]:
    changes: list[FieldChange] = []
    for name in TRACKED_FIELDS:
        old = serialize_value(existing.get(name))
        new = serialize_value(merged.get(name))
        if old != new:
            changes.append(FieldChange(name, old, new))
    return changes
