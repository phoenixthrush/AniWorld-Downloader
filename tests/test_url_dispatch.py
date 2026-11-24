"""Dispatch passes the same normalized URLs to provider lookup and models."""

import json
import sys
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import provider_check as checks
import pytest

from aniworld import entry, menu
from aniworld.models import (
    SerienstreamEpisode,
    SerienstreamSeason,
    SerienstreamSeries,
)
from aniworld.providers import resolve_provider
from aniworld.web import autosync, db, discord_bot, worker
from aniworld.web.views import api_media

SERIES = "https://serienstream.to/serie/example"
ALIAS = "https://serienstream.to/serie/stream/example"
SEASON = SERIES + "/staffel-1"
EPISODE = SEASON + "/episode-1"


@pytest.fixture
def sto_provider():
    series = Mock(
        return_value=SimpleNamespace(title="Example", seasons=[], download=Mock())
    )
    season = Mock(
        return_value=SimpleNamespace(episodes=[], episode_languages={}, download=Mock())
    )
    episode = Mock(return_value=SimpleNamespace(provider_data={}, download=Mock()))
    provider = replace(
        resolve_provider(SERIES),
        series_cls=series,
        season_cls=season,
        episode_cls=episode,
    )
    return SimpleNamespace(
        provider=provider, series=series, season=season, episode=episode
    )


@pytest.mark.parametrize(
    "suffix,cls",
    [
        ("", SerienstreamSeries),
        ("/staffel-1", SerienstreamSeason),
        ("/staffel-1/episode-1", SerienstreamEpisode),
    ],
)
def test_model_dispatch_normalizes_serienstream_aliases(suffix, cls):
    model = entry.model_for_url(f"  {ALIAS}{suffix}/  ")

    assert isinstance(model, cls)
    assert model.url == SERIES + suffix


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            " http://www.moflix-stream.xyz/titles/42/silo/season/2/episodes/3/ ",
            "https://moflix-stream.xyz/titles/42/season/2/episodes/3",
        ),
        (
            " http://www.moflix-stream.xyz/titles/42/silo/?season=2&episode=3 ",
            "https://moflix-stream.xyz/titles/42?season=2&episode=3",
        ),
        (
            " https://megakino.example/serials/123-example.html#mkep=3 ",
            "https://megakino.example/serials/123-example.html#mkep=3",
        ),
        (
            " https://kinox.to/Stream/Example.html?Season=2&Episode=3 ",
            "https://kinox.to/Stream/Example.html?Season=2&Episode=3",
        ),
    ],
)
def test_model_dispatch_preserves_episode_selectors(monkeypatch, url, expected):
    factory = Mock()
    provider = replace(
        resolve_provider(url),
        episode_cls=factory,
        season_cls=factory,
        series_cls=factory,
    )
    lookup = Mock(return_value=provider)
    monkeypatch.setattr(entry, "resolve_provider", lookup)

    assert entry.model_for_url(url) is factory.return_value

    lookup.assert_called_once_with(expected)
    factory.assert_called_once_with(url=expected)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/serie/stream/example",
        "https://serienstream.to.evil.test/serie/stream/example",
        "https://moflix-stream.xyz/titles/42/silo/unknown/extra",
    ],
)
def test_model_dispatch_still_rejects_unsupported_urls(url):
    with pytest.raises(ValueError):
        entry.model_for_url(url)


@pytest.mark.parametrize("mode", ["interactive", "no-menu", "episode-file"])
@pytest.mark.parametrize(
    "kind,suffix",
    [("series", ""), ("season", "/staffel-1"), ("episode", "/staffel-1/episode-1")],
)
def test_cli_dispatch_uses_normalized_urls(
    monkeypatch, tmp_path, sto_provider, mode, kind, suffix
):
    raw = f"  {ALIAS}{suffix}/  "
    if mode == "episode-file":
        episode_file = tmp_path / "urls.txt"
        episode_file.write_text(raw + "\n")
        argv = ["--episode-file", str(episode_file)]
    elif mode == "no-menu":
        argv = ["--no-menu", raw]
    else:
        argv = [raw]
    monkeypatch.setattr(sys, "argv", ["aniworld", *argv])
    lookup = Mock(return_value=sto_provider.provider)
    monkeypatch.setattr(entry, "resolve_provider", lookup)
    show_menu = Mock(return_value=None)
    monkeypatch.setattr(menu, "app", show_menu)

    result = entry.aniworld()

    expected = SERIES + suffix
    assert lookup.called
    assert all(call.args == (expected,) for call in lookup.call_args_list)
    if mode == "interactive" and kind == "series":
        assert result == 130
        show_menu.assert_called_once_with(url=expected)
    else:
        assert result == 0
        factory = getattr(sto_provider, kind)
        factory.assert_called_once_with(url=expected)
        factory.return_value.download.assert_called_once_with()
        show_menu.assert_not_called()


@pytest.mark.parametrize(
    "endpoint,kind,suffix",
    [
        ("series", "series", ""),
        ("seasons", "series", ""),
        ("episodes", "season", "/staffel-1"),
        ("providers", "episode", "/staffel-1/episode-1"),
    ],
)
def test_web_dispatch_uses_normalized_urls(
    client, monkeypatch, sto_provider, endpoint, kind, suffix
):
    lookup = Mock(return_value=sto_provider.provider)
    monkeypatch.setattr(api_media, "resolve_provider", lookup)
    monkeypatch.setattr(api_media.media, "downloaded_episodes", lambda series: set())

    response = client.get(
        f"/api/{endpoint}",
        query_string={"url": f"  {ALIAS}{suffix}/  ", "series_url": f" {ALIAS}/ "},
    )

    assert response.status_code == 200
    lookup.assert_called_once_with(SERIES + suffix)
    if endpoint == "episodes":
        sto_provider.series.assert_called_once_with(url=SERIES)
        sto_provider.season.assert_called_once_with(
            url=SEASON, series=sto_provider.series.return_value
        )
    else:
        getattr(sto_provider, kind).assert_called_once_with(url=SERIES + suffix)


@pytest.mark.parametrize("as_dict", [False, True])
def test_worker_dispatch_uses_normalized_urls(
    queue_item, monkeypatch, sto_provider, as_dict
):
    raw = f"  {ALIAS}/staffel-1/episode-1/  "
    queued = {"url": raw} if as_dict else raw
    lookup = Mock(return_value=sto_provider.provider)
    monkeypatch.setattr(worker, "resolve_provider", lookup)
    queue_id = queue_item(episodes=[queued])

    worker._process(db.get_queue_item(queue_id))

    assert db.get_queue_item(queue_id)["status"] == "completed"
    lookup.assert_called_once_with(EPISODE)
    assert sto_provider.episode.call_args.kwargs["url"] == EPISODE
    sto_provider.episode.return_value.download.assert_called_once_with()


def test_worker_normalizes_manga_parent_urls(monkeypatch):
    series_url = "https://mangafire.to/title/z9w-example"
    chapter_url = series_url + "/chapter/1"
    series = Mock()
    chapter = Mock()
    provider = replace(
        resolve_provider(chapter_url), series_cls=series, episode_cls=chapter
    )
    monkeypatch.setattr(worker, "resolve_provider", lambda url: provider)

    worker._build_episode(
        f" {chapter_url}/ ",
        {"_series_url": f" {series_url}/ ", "_format": "cbz"},
        {"language": "English Dub", "provider": "MangaFire"},
        None,
    )

    series.assert_called_once_with(url=series_url)
    assert chapter.call_args.kwargs["url"] == chapter_url
    assert chapter.call_args.kwargs["series"] is series.return_value


def test_menu_normalizes_urls_before_loading_models():
    assert menu.MenuApp(f" {ALIAS}/ ").url == SERIES


def test_discord_dispatch_normalizes_series_urls(monkeypatch, sto_provider):
    sto_provider.series.return_value.seasons = [
        SimpleNamespace(episodes=[SimpleNamespace(url=EPISODE)])
    ]
    lookup = Mock(return_value=sto_provider.provider)
    monkeypatch.setattr(discord_bot, "resolve_provider", lookup)

    discord_bot._enqueue(
        "Example", f" {ALIAS}/ ", "series", "German Dub", "VOE", "user", "42"
    )

    lookup.assert_called_once_with(SERIES)
    sto_provider.series.assert_called_once_with(url=SERIES)
    item = db.get_queue()[0]
    assert item["series_url"] == SERIES
    assert json.loads(item["episodes"]) == [EPISODE]


def test_autosync_dispatch_normalizes_series_urls(monkeypatch, sto_provider, downloads):
    lookup = Mock(return_value=sto_provider.provider)
    monkeypatch.setattr(autosync, "resolve_provider", lookup)
    monkeypatch.setattr(autosync, "detect_languages", lambda *args: {"German Dub"})
    monkeypatch.setattr(autosync, "episodes_in_folder", lambda folder: set())
    monkeypatch.setattr(autosync, "_missing_episodes", lambda *args: [EPISODE])
    candidate = {
        "title": "Example",
        "series_url": f" {ALIAS}/ ",
        "folder": downloads,
        "lang_folder": None,
        "custom_path_id": None,
        "root_name": "Default",
        "new_languages": {"German Dub"},
        "new_episodes_with_langs": {},
    }

    result = autosync._handle(candidate, "VOE")

    assert result["status"] == "queued"
    lookup.assert_called_once_with(SERIES)
    sto_provider.series.assert_called_once_with(url=SERIES)
    assert db.get_queue_item(result["queue_id"])["series_url"] == SERIES


def test_manual_provider_dispatch_normalizes_urls(monkeypatch, sto_provider):
    from aniworld import providers

    sto_provider.series.return_value.episodes = [object()]
    provider = replace(sto_provider.provider, episode_cls=None)
    monkeypatch.setattr(providers, "resolve_provider", lambda url: provider)

    assert (
        checks.first_episode(f" {ALIAS}/ ")
        is sto_provider.series.return_value.episodes[0]
    )
    sto_provider.series.assert_called_once_with(url=SERIES)
