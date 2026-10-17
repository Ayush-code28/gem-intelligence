"""Text cleaning."""

from __future__ import annotations

import html
import re
import unicodedata

_WS = re.compile(r"\s+")
_TAGS = re.compile(r"<[^>]{0,500}>")


def clean_text(value: object, max_length: int = 2000) -> str | None:
    """Return trimmed, single-spaced text without markup/control characters, or None if empty.

    Lists (Solr multi-valued fields) are reduced to their first non-empty element.
    Non-string scalars are rejected (None) rather than coerced, so numbers never become titles.
    """
    if isinstance(value, list):
        for item in value:
            cleaned = clean_text(item, max_length)
            if cleaned:
                return cleaned
        return None
    if not isinstance(value, str):
        return None
    text = html.unescape(_TAGS.sub(" ", value))
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\t\n ")
    text = _WS.sub(" ", text).strip()
    if not text:
        return None
    if len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "…"
    return text


def first_scalar(value: object) -> object:
    """Unwrap single-element Solr arrays: [x] -> x, [] -> None."""
    if isinstance(value, list):
        return value[0] if value else None
    return value
