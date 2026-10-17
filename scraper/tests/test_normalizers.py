from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scraper.normalizers.dates import IST, parse_datetime
from scraper.normalizers.text import clean_text, first_scalar
from scraper.normalizers.urls import InvalidUrl, canonicalize_url, is_valid_url

HOSTS = frozenset({"bidplus.gem.gov.in"})
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class TestCleanText:
    def test_collapses_whitespace_and_unescapes(self) -> None:
        assert clean_text("  Office&nbsp;  <b>Chairs</b>\n\t x ") == "Office Chairs x"

    def test_unwraps_solr_arrays(self) -> None:
        assert clean_text(["", "  ", "Value"]) == "Value"
        assert clean_text([]) is None

    @pytest.mark.parametrize("value", [None, "", "   ", 12, 3.5, True, {"a": 1}])
    def test_missing_or_non_text_is_none(self, value: object) -> None:
        assert clean_text(value) is None

    def test_strips_control_characters(self) -> None:
        assert clean_text("A\x00B\x07C") == "ABC"

    def test_truncates(self) -> None:
        out = clean_text("x" * 50, max_length=10)
        assert out is not None and len(out) == 10 and out.endswith("…")

    def test_first_scalar(self) -> None:
        assert first_scalar([5]) == 5
        assert first_scalar([]) is None
        assert first_scalar("a") == "a"


class TestParseDatetime:
    def test_gem_z_values_are_ist_wall_clock(self) -> None:
        dt = parse_datetime("2026-10-17T17:17:03Z", assume_tz=IST, ignore_utc_designator=True, now=NOW)
        assert dt == datetime(2026, 10, 17, 17, 17, 3, tzinfo=IST)
        assert dt is not None and dt.astimezone(UTC) == datetime(2026, 10, 17, 11, 47, 3, tzinfo=UTC)

    def test_z_is_utc_by_default(self) -> None:
        dt = parse_datetime("2026-10-17T17:17:03Z", now=NOW)
        assert dt == datetime(2026, 10, 17, 17, 17, 3, tzinfo=UTC)

    def test_explicit_offset_honoured(self) -> None:
        dt = parse_datetime("2026-10-17T10:00:00+05:30", ignore_utc_designator=True, now=NOW)
        assert dt is not None and dt.utcoffset() == timedelta(hours=5, minutes=30)

    def test_naive_uses_assumed_tz(self) -> None:
        assert parse_datetime("17-10-2026 05:30 PM", now=NOW) == datetime(2026, 10, 17, 17, 30, tzinfo=IST)

    def test_list_input(self) -> None:
        assert parse_datetime(["2026-10-17 09:00"], now=NOW) == datetime(2026, 10, 17, 9, 0, tzinfo=IST)

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "not-a-date",
            "2026-13-45T10:00:00Z",
            "2026-10-17",
            1760000000,
            [],
            "1999-01-01 10:00",
            "2090-01-01 10:00",
        ],
    )
    def test_missing_malformed_date_only_or_absurd_is_none(self, value: object) -> None:
        # Date-only values are rejected: the collector must not invent a deadline time.
        assert parse_datetime(value, now=NOW) is None

    def test_always_timezone_aware(self) -> None:
        dt = parse_datetime("2026-10-17 09:00", now=NOW)
        assert dt is not None and dt.tzinfo is not None


class TestCanonicalizeUrl:
    def test_normalizes(self) -> None:
        url = "HTTP://BidPlus.GeM.gov.in:443/a/./b/../showbidDocument/123?utm_source=x&z=1&a=2#frag"
        assert canonicalize_url(url, HOSTS) == "https://bidplus.gem.gov.in/a/showbidDocument/123?a=2&z=1"

    def test_idempotent(self) -> None:
        once = canonicalize_url("https://bidplus.gem.gov.in/showbidDocument/1?b=2&a=1", HOSTS)
        assert canonicalize_url(once, HOSTS) == once

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "data:text/html,hi",
            "ftp://bidplus.gem.gov.in/x",
            "https://evil.example.com/showbidDocument/1",
            "https://bidplus.gem.gov.in.evil.com/x",
            "https://user:pass@bidplus.gem.gov.in/x",
            "https://bidplus.gem.gov.in:8443/x",
            "https://bidplus.gem.gov.in/x y",
            "",
            None,
            42,
        ],
    )
    def test_rejects_unsafe(self, url: object) -> None:
        with pytest.raises(InvalidUrl):
            canonicalize_url(url, HOSTS)
        assert not is_valid_url(url, HOSTS)

    def test_dot_segments_cannot_escape_root(self) -> None:
        assert (
            canonicalize_url("https://bidplus.gem.gov.in/../../etc", HOSTS)
            == "https://bidplus.gem.gov.in/etc"
        )
