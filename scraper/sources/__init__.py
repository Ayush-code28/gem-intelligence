"""Registry of source adapters."""

from __future__ import annotations

from collections.abc import Callable

from scraper.config import Settings
from scraper.http import PacedHttpClient
from scraper.sources.base import HttpClient, SourceAdapter
from scraper.sources.gem_bidplus import GemBidPlusAdapter


def _client_factory(settings: Settings) -> Callable[[], HttpClient]:
    def make() -> HttpClient:
        return PacedHttpClient(
            user_agent=settings.user_agent,
            timeout_seconds=settings.request_timeout_seconds,
            delay_seconds=settings.request_delay_seconds,
            max_retries=settings.max_retries,
        )

    return make


AdapterFactory = Callable[[Settings], SourceAdapter]

REGISTRY: dict[str, AdapterFactory] = {
    "gem_bids_products": lambda s: GemBidPlusAdapter(
        "gem_bids_products", "product", "GeM ongoing Bids/RAs — products", _client_factory(s)
    ),
    "gem_bids_services": lambda s: GemBidPlusAdapter(
        "gem_bids_services", "service", "GeM ongoing Bids/RAs — services", _client_factory(s)
    ),
}


def build_adapters(settings: Settings, names: tuple[str, ...]) -> list[SourceAdapter]:
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        raise KeyError(f"unknown source(s): {', '.join(unknown)}; available: {', '.join(sorted(REGISTRY))}")
    return [REGISTRY[n](settings) for n in dict.fromkeys(names)]
