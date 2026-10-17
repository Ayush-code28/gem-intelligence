"""Source adapter interface.

An adapter yields pages of raw items and normalizes each item. The pipeline drives the
iteration so that records from completed pages are kept even if a later page fails.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from scraper.config import Settings
from scraper.models import ListingRecord


class SourceError(RuntimeError):
    """The source could not be collected (network, access or schema problem)."""


class SourceSchemaError(SourceError):
    """The source responded, but not in the expected shape."""


class SourceAccessBlocked(SourceError):
    """The source refused access (e.g. a security gateway block page). Never worked around."""


class HttpResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    def json(self, **kwargs: Any) -> Any: ...


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> HttpResponse: ...

    def post(self, url: str, **kwargs: Any) -> HttpResponse: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class FetchContext:
    now: datetime
    watermark: datetime | None
    settings: Settings


@dataclass
class AdapterStats:
    pages_fetched: int = 0
    passes: dict[str, str] = field(default_factory=dict)  # pass name -> stop reason


class SourceAdapter(ABC):
    name: str
    description: str
    #: Provenance written to every record from this adapter.
    origin: str = "live"
    #: Whether reproduction of this source's content requires the operator's explicit confirmation.
    requires_permission: bool = True
    #: Live network sources sharing a host share a group; once one is blocked, the rest are skipped.
    access_group: str | None = None

    def __init__(self) -> None:
        self.stats = AdapterStats()

    @abstractmethod
    def iter_pages(self, ctx: FetchContext) -> Iterator[list[Mapping[str, Any]]]:
        """Yield pages of raw items. Must be bounded."""

    @abstractmethod
    def normalize(self, raw: Mapping[str, Any]) -> ListingRecord:
        """Return a validated record or raise RejectedRecord."""

    def close(self) -> None:  # noqa: B027 - optional hook
        """Release network resources."""
