"""HTTP client with timeouts, conservative pacing and bounded retries."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

RETRY_STATUSES = (429, 500, 502, 503, 504)


class PacedHttpClient:
    """A requests.Session wrapper that waits at least `delay_seconds` between requests.

    Retries are bounded and limited to transient failures (connection errors, 429, 5xx),
    honouring Retry-After. POST is retried because the GeM listing XHR is a read-only query.
    """

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float,
        delay_seconds: float,
        max_retries: int,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeout = timeout_seconds
        self.delay = delay_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request: float | None = None
        self.request_count = 0
        self.session = session or requests.Session()
        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=2.0,
            status_forcelist=RETRY_STATUSES,
            allowed_methods=frozenset({"GET", "POST"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=1)
        self.session.mount("https://", adapter)
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "en"})

    def _pace(self) -> None:
        if self._last_request is not None:
            wait = self.delay - (self._monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._monotonic()

    def request(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> requests.Response:
        if not url.startswith("https://"):
            raise ValueError("only https URLs are allowed")
        self._pace()
        self.request_count += 1
        started = self._monotonic()
        response = self.session.request(
            method, url, data=data, headers=dict(headers or {}), timeout=self.timeout, allow_redirects=True
        )
        log.debug(
            "http request",
            extra={
                "method": method,
                "url": url,
                "status": response.status_code,
                "elapsed_ms": round((self._monotonic() - started) * 1000),
            },
        )
        response.raise_for_status()
        return response

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self.session.close()
