"""Offline checks for the manual live-check helper."""

import threading
from types import SimpleNamespace

import provider_check as checks
import pytest

from aniworld import providers, search


@pytest.mark.parametrize("direct_episodes", [True, False])
def test_first_episode_handles_direct_and_season_lists(monkeypatch, direct_episodes):
    episode = object()
    series = SimpleNamespace(
        episodes=[episode] if direct_episodes else [],
        seasons=[] if direct_episodes else [SimpleNamespace(episodes=[episode])],
    )
    provider = SimpleNamespace(
        name="HentaiHaven", episode_cls=None, series_cls=lambda **kwargs: series
    )
    monkeypatch.setattr(providers, "resolve_provider", lambda url: provider)
    assert checks.first_episode("https://example.test/title") is episode


@pytest.mark.parametrize("site_name", ["HentaiTV", "AnimeIDHentai", "HentaiHaven"])
def test_stream_check_uses_search_and_model_poster(monkeypatch, capsys, site_name):
    calls = []

    def fetch(keyword):
        calls.append(keyword)
        return [{"url": "https://example.test/episode"}]

    monkeypatch.setattr(search, "query_hentai_tv", fetch)
    monkeypatch.setattr(checks, "extractors", dict)
    monkeypatch.setattr(
        checks,
        "first_episode",
        lambda url: SimpleNamespace(
            stream_url="https://media.example.test/video.mp4",
            poster_url="https://images.example.test/poster.jpg",
        ),
    )
    assert checks.run_stream_site(site_name, "query_hentai_tv", "sample") == 0
    assert calls == ["sample"]
    output = capsys.readouterr().out
    assert f"{site_name} stream" in output
    assert f"{site_name} poster" in output
    assert "2 passed, 0 failed" in output


def test_stream_check_reports_search_failure(monkeypatch, capsys):
    monkeypatch.setattr(search, "query_hentai_tv", lambda keyword: [])
    monkeypatch.setattr(checks, "extractors", dict)
    assert checks.run_stream_site("HentaiTV", "query_hentai_tv", "sample") == 1
    assert "no titles" in capsys.readouterr().out


def test_guarded_returns_before_a_stuck_call_finishes(monkeypatch):
    release = threading.Event()
    finished = threading.Event()

    def wait():
        release.wait(2)
        finished.set()

    monkeypatch.setattr(checks, "TIMEOUT", 0.01)
    try:
        value, error = checks.guarded(wait)
        assert value is None
        assert isinstance(error, TimeoutError)
        assert not finished.is_set()
    finally:
        release.set()


def test_guarded_keeps_the_original_exception():
    error = ValueError("sample failure")

    def fail():
        raise error

    assert checks.guarded(fail) == (None, error)


@pytest.mark.parametrize("blocked", [True, False])
def test_burningseries_check_stops_after_warning_or_timeout(
    monkeypatch, capsys, blocked
):
    from aniworld.models.burningseries.series import BurningSeriesVPNWarning

    monkeypatch.setattr(
        search,
        "fetch_burningseries_series",
        lambda: [{"url": "https://bs.cine.to/serie/example"}],
    )
    monkeypatch.setattr(
        checks,
        "extractors",
        lambda: {"voe": {"direct": lambda url: "stream", "preview": None}},
    )
    monkeypatch.setattr(checks, "first_episode", lambda url: object())
    monkeypatch.setattr(
        checks,
        "hosters_of",
        lambda episode: [("German Dub", "VOE"), ("English Dub", "VOE")],
    )
    calls = []

    def embed(*args):
        calls.append(args)
        raise (
            BurningSeriesVPNWarning("VPN warning")
            if blocked
            else TimeoutError("timed out")
        )

    monkeypatch.setattr(checks, "embed_url", embed)
    assert checks.run_site("BurningSeries", "fetch_burningseries_series") == 1
    assert len(calls) == 1
    assert "remaining hosters were not checked" in capsys.readouterr().out
