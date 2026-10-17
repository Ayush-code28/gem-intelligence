"""Collector configuration, read from environment variables.

Secrets (DATABASE_URL) are never included in repr() or logs.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


def _int(env: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return value


def _float(env: Mapping[str, str], name: str, default: float, minimum: float, maximum: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return value


def _bool(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    database_url: str | None = field(default=None, repr=False)
    enabled_sources: tuple[str, ...] = ()
    gem_permission_confirmed: bool = False
    gem_live_access_approved: bool = False
    user_agent: str = "GeMIntelligenceCollector/1.0"
    request_timeout_seconds: float = 20.0
    request_delay_seconds: float = 3.0
    max_retries: int = 3
    max_pages_per_source: int = 100
    refresh_window_days: int = 2
    refresh_max_pages: int = 20
    watermark_overlap_hours: int = 48
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        sources = tuple(s.strip() for s in env.get("ENABLED_SOURCES", "").split(",") if s.strip())
        log_level = env.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ConfigError("LOG_LEVEL must be DEBUG, INFO, WARNING or ERROR")
        return cls(
            database_url=env.get("DATABASE_URL", "").strip() or None,
            enabled_sources=sources,
            gem_permission_confirmed=_bool(env, "GEM_REPRODUCTION_PERMISSION_CONFIRMED"),
            gem_live_access_approved=_bool(env, "GEM_LIVE_ACCESS_APPROVED"),
            user_agent=env.get("COLLECTOR_USER_AGENT", "").strip() or cls.user_agent,
            # Lower bounds keep request pacing conservative even if misconfigured.
            request_timeout_seconds=_float(env, "REQUEST_TIMEOUT_SECONDS", 20.0, 5.0, 120.0),
            request_delay_seconds=_float(env, "REQUEST_DELAY_SECONDS", 3.0, 1.0, 60.0),
            max_retries=_int(env, "MAX_RETRIES", 3, 0, 5),
            max_pages_per_source=_int(env, "MAX_PAGES_PER_SOURCE", 100, 1, 500),
            refresh_window_days=_int(env, "REFRESH_WINDOW_DAYS", 2, 0, 14),
            refresh_max_pages=_int(env, "REFRESH_MAX_PAGES", 20, 0, 200),
            watermark_overlap_hours=_int(env, "WATERMARK_OVERLAP_HOURS", 48, 1, 24 * 14),
            log_level=log_level,
        )
