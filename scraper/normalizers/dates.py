"""Date parsing with explicit timezone handling.

GeM's listing feed emits strings like ``2026-10-17T17:17:03Z`` that are really IST
wall-clock times (see docs/SOURCE_FEASIBILITY.md §3). Callers state how to interpret
naive/mislabelled values via ``assume_tz`` and ``ignore_utc_designator``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d-%m-%Y %I:%M %p",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y %I:%M %p",
    "%d/%m/%Y %H:%M",
)
_OFFSET = re.compile(r"([+-]\d{2}:?\d{2})$")

# Sanity window: anything outside is almost certainly a parsing error, not a real deadline.
MIN_YEAR = 2000
MAX_YEARS_AHEAD = 10


def parse_datetime(
    value: object,
    *,
    assume_tz: tzinfo = IST,
    ignore_utc_designator: bool = False,
    now: datetime | None = None,
) -> datetime | None:
    """Parse a date-time into an aware datetime, or return None if absent/malformed.

    * Explicit numeric offsets (``+05:30``) are always honoured.
    * A trailing ``Z`` is honoured as UTC unless ``ignore_utc_designator`` is set,
      in which case the wall-clock value is interpreted in ``assume_tz``.
    * Naive values are interpreted in ``assume_tz``.
    * Date-only values are rejected: a deadline without a time must not be invented.
    """
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None

    tz: tzinfo = assume_tz
    if text.endswith(("Z", "z")):
        text = text[:-1]
        if not ignore_utc_designator:
            tz = ZoneInfo("UTC")
    else:
        match = _OFFSET.search(text)
        if match and "T" in text:
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return None
            return _sane(parsed, now)

    for fmt in _FORMATS:
        try:
            naive = datetime.strptime(text, fmt)  # noqa: DTZ007 - tz attached explicitly below
        except ValueError:
            continue
        return _sane(naive.replace(tzinfo=tz), now)
    return None


def _sane(dt: datetime, now: datetime | None) -> datetime | None:
    if dt.tzinfo is None:
        return None
    reference = now or datetime.now(tz=IST)
    if dt.year < MIN_YEAR or dt > reference + timedelta(days=365 * MAX_YEARS_AHEAD):
        return None
    return dt
