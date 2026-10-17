"""Validated, normalized listing record."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Fields compared for change detection, in a stable order.
TRACKED_FIELDS: tuple[str, ...] = (
    "bid_number",
    "title",
    "organisation",
    "ministry",
    "department",
    "category",
    "listing_type",
    "quantity",
    "published_at",
    "deadline",
    "url",
)


DataOrigin = Literal["live", "imported", "synthetic"]
DATA_ORIGINS: tuple[str, ...] = ("live", "imported", "synthetic")


class RejectedRecord(ValueError):
    """A source item that cannot be turned into a valid listing."""


class ListingRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    source_name: str = Field(pattern=r"^[a-z0-9_]+$")
    source_id: str | None = Field(default=None, min_length=1, max_length=200)
    bid_number: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=2000)
    organisation: str | None = Field(default=None, max_length=1000)
    ministry: str | None = Field(default=None, max_length=500)
    department: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=200)
    listing_type: str | None = Field(default=None, max_length=100)
    quantity: Decimal | None = Field(default=None, ge=0)
    published_at: datetime | None = None
    deadline: datetime | None = None
    url: str | None = Field(default=None, pattern=r"^https://", max_length=2000)
    #: Provenance. Not a tracked field: it is fixed by the adapter that produced the record.
    data_origin: DataOrigin = "live"

    @field_validator("published_at", "deadline")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("datetimes must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _identity(self) -> ListingRecord:
        if self.source_id is None and self.url is None:
            raise ValueError("either source_id or url is required")
        return self

    @property
    def dedup_key(self) -> str:
        """Stable id preferred; canonical URL as the fallback."""
        if self.source_id is not None:
            return f"id:{self.source_id}"
        assert self.url is not None
        return f"url:{self.url}"

    def tracked_values(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in TRACKED_FIELDS}


def serialize_value(value: Any) -> str | None:
    """Stable text form used for hashing and listing_history."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        normalized = value.normalize()
        return format(normalized, "f")
    return str(value)
