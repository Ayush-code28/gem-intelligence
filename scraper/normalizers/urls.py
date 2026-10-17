"""URL validation and safe canonicalization."""

from __future__ import annotations

import posixpath
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "lang"}
)


class InvalidUrl(ValueError):
    pass


def canonicalize_url(
    url: object, allowed_hosts: frozenset[str], allowed_suffixes: tuple[str, ...] = ()
) -> str:
    """Return a canonical https URL on an allowed host, or raise InvalidUrl.

    Lower-cases scheme/host, drops credentials, default ports, fragments and tracking
    parameters, resolves dot-segments, normalizes percent-encoding and sorts the query.
    """
    if not isinstance(url, str) or not url.strip():
        raise InvalidUrl("empty url")
    raw = url.strip()
    if any(ch in raw for ch in "\r\n\t\x00 "):
        raise InvalidUrl("url contains whitespace or control characters")
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise InvalidUrl(f"unsupported scheme {scheme!r}")
    if parts.username or parts.password:
        raise InvalidUrl("credentials in url")
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in allowed_hosts and not any(host.endswith(sfx) for sfx in allowed_suffixes):
        raise InvalidUrl(f"host {host!r} not allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidUrl("invalid port") from exc
    if port not in (None, 80, 443):
        raise InvalidUrl("non-standard port")

    path = posixpath.normpath(unquote(parts.path or "/"))
    if path == ".":
        path = "/"
    if not path.startswith("/"):
        path = "/" + path
    if parts.path.endswith("/") and path != "/":
        path += "/"
    path = quote(path, safe="/:@!$&'()*+,;=-._~")

    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS
    )
    # Always https: every allowed host serves TLS, and plain http links are upgraded.
    return urlunsplit(("https", host, path, urlencode(query), ""))


def is_valid_url(url: object, allowed_hosts: frozenset[str]) -> bool:
    try:
        canonicalize_url(url, allowed_hosts)
    except InvalidUrl:
        return False
    return True
