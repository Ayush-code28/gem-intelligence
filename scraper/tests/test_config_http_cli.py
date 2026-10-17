from __future__ import annotations

from typing import Any

import pytest

from scraper.__main__ import EXIT_CONFIG, main
from scraper.config import ConfigError, Settings
from scraper.http import PacedHttpClient


class TestSettings:
    def test_defaults_enable_nothing(self) -> None:
        s = Settings.from_env({})
        assert s.enabled_sources == () and s.gem_permission_confirmed is False

    def test_parsing(self) -> None:
        s = Settings.from_env(
            {
                "ENABLED_SOURCES": " gem_bids_products , ,gem_bids_services",
                "GEM_REPRODUCTION_PERMISSION_CONFIRMED": "TRUE",
                "REQUEST_DELAY_SECONDS": "5",
                "MAX_PAGES_PER_SOURCE": "7",
            }
        )
        assert s.enabled_sources == ("gem_bids_products", "gem_bids_services")
        assert s.gem_permission_confirmed and s.request_delay_seconds == 5 and s.max_pages_per_source == 7

    @pytest.mark.parametrize(
        "env",
        [
            {"REQUEST_DELAY_SECONDS": "0.1"},  # too aggressive
            {"MAX_PAGES_PER_SOURCE": "100000"},  # unbounded scan
            {"MAX_RETRIES": "x"},
            {"LOG_LEVEL": "TRACE"},
        ],
    )
    def test_rejects_unsafe_values(self, env: dict[str, str]) -> None:
        with pytest.raises(ConfigError):
            Settings.from_env(env)

    def test_repr_hides_database_url(self) -> None:
        s = Settings.from_env({"DATABASE_URL": "postgresql://user:supersecret@host/db"})
        assert "supersecret" not in repr(s)


class FakeSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, str, Any]] = []

    def mount(self, prefix: str, adapter: Any) -> None:
        pass

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append((method, url, kwargs["timeout"]))

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

        return R()

    def close(self) -> None:
        pass


def test_http_client_paces_and_times_out() -> None:
    clock = {"t": 0.0}
    sleeps: list[float] = []

    def sleep(s: float) -> None:
        sleeps.append(s)
        clock["t"] += s

    session = FakeSession()
    client = PacedHttpClient("ua", 20, 3.0, 2, session=session, sleep=sleep, monotonic=lambda: clock["t"])  # type: ignore[arg-type]
    client.get("https://bidplus.gem.gov.in/a")
    clock["t"] += 1.0
    client.get("https://bidplus.gem.gov.in/b")
    assert sleeps == [pytest.approx(2.0)]
    assert all(timeout == 20 for _, _, timeout in session.calls)
    assert session.headers["User-Agent"] == "ua"
    with pytest.raises(ValueError, match="https"):
        client.get("http://bidplus.gem.gov.in/a")


class TestCli:
    @pytest.fixture(autouse=True)
    def clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in (
            "ENABLED_SOURCES",
            "GEM_REPRODUCTION_PERMISSION_CONFIRMED",
            "GEM_LIVE_ACCESS_APPROVED",
            "DATABASE_URL",
        ):
            monkeypatch.delenv(key, raising=False)

    def test_live_gem_disabled_by_default_even_for_dry_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import scraper.sources.gem_bidplus as gem

        def no_network(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("a live request was attempted")

        monkeypatch.setattr(gem.GemBidPlusAdapter, "fetch_page", no_network)
        monkeypatch.setattr(gem.GemBidPlusAdapter, "_bootstrap", no_network)
        assert main(["--sources", "gem_bids_products"]) == EXIT_CONFIG
        assert main(["--sources", "gem_bids_products", "--dry-run"]) == EXIT_CONFIG
        monkeypatch.setenv("GEM_REPRODUCTION_PERMISSION_CONFIRMED", "true")
        assert main(["--sources", "gem_bids_products"]) == EXIT_CONFIG

    def test_reproduction_permission_also_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GEM_LIVE_ACCESS_APPROVED", "true")
        assert main(["--sources", "gem_bids_products"]) == EXIT_CONFIG

    def test_import_dry_run(self, tmp_path: Any) -> None:
        summary = tmp_path / "s.md"
        args = [
            "--import-file",
            "data/samples/import_template.csv",
            "--dry-run",
            "--summary-file",
            str(summary),
        ]
        assert main(args) == 0
        assert "import_import_template | success | 2 |" in summary.read_text()

    def test_import_bad_origin_name(self) -> None:
        assert main(["--import-file", "x.csv", "--source-name", "Bad Name", "--dry-run"]) == EXIT_CONFIG

    def test_purge_requires_confirmation(self) -> None:
        assert main(["--purge-synthetic"]) == EXIT_CONFIG

    def test_unknown_source(self) -> None:
        assert main(["--sources", "nope", "--dry-run"]) == EXIT_CONFIG

    def test_missing_database_url(self) -> None:
        assert main(["--import-file", "data/samples/import_template.csv"]) == EXIT_CONFIG

    def test_nothing_enabled_dry_run_is_skipped(self, tmp_path: Any) -> None:
        summary = tmp_path / "s.md"
        assert main(["--dry-run", "--summary-file", str(summary)]) == 0
        assert "skipped" in summary.read_text()

    def test_bad_max_pages(self) -> None:
        assert main(["--dry-run", "--max-pages", "0"]) == EXIT_CONFIG

    def test_list_sources(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["--list-sources"]) == 0
        assert "gem_bids_products" in capsys.readouterr().out
