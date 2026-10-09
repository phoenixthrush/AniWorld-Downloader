"""Playback options affect actions without leaking into subsequent calls."""

from types import SimpleNamespace

import pytest

from aniworld import autodeps, entry
from aniworld.models import HanimeTVEpisode
from aniworld.models.common import common
from aniworld.models.mangafire_to.series import MangaFireToChapter
from aniworld.web import media


@pytest.mark.parametrize("action", ["watch", "syncplay"])
def test_keep_watching_starts_at_the_selected_episode(monkeypatch, action):
    calls = []
    episodes = [
        SimpleNamespace(
            url=f"https://example.test/{n}",
            selected_language="Default",
            selected_provider="Default",
            selected_path="Default",
            **{action: lambda n=n: calls.append(n)},
        )
        for n in range(4)
    ]
    current = episodes[1]
    current.season = SimpleNamespace(episodes=episodes)
    current.selected_language = "English Sub"
    current.selected_provider = "VOE"
    current.selected_path = "/tmp/downloads"
    monkeypatch.setenv("ANIWORLD_KEEP_WATCHING", "1")
    entry.run_action(current, action)
    assert calls == [1, 2, 3]
    for episode in episodes[2:]:
        assert (
            episode.selected_language,
            episode.selected_provider,
            episode.selected_path,
        ) == ("English Sub", "VOE", "/tmp/downloads")


@pytest.mark.parametrize("action,enabled", [("watch", "0"), ("download", "1")])
def test_other_actions_do_not_load_the_next_episode(monkeypatch, action, enabled):
    calls = []
    obj = SimpleNamespace(**{action: lambda: calls.append(action)})
    monkeypatch.setenv("ANIWORLD_KEEP_WATCHING", enabled)
    entry.run_action(obj, action)
    assert calls == [action]


def test_force_mpv_does_not_change_the_next_player_selection(monkeypatch):
    monkeypatch.setattr(autodeps, "PLATFORM", "Darwin")
    monkeypatch.setattr(
        autodeps.DependencyManager, "fetch_binary", lambda self, name: name
    )
    monkeypatch.setenv("ANIWORLD_USE_IINA", "1")
    assert autodeps.get_player_path(use_iina=False) == "mpv"
    assert autodeps.get_player_path() == "iina"


def test_syncplay_uses_mpv_without_overwriting_player_preferences(monkeypatch, caplog):
    import logging
    import os

    commands = []
    players = []
    monkeypatch.setenv("ANIWORLD_USE_IINA", "1")
    monkeypatch.setenv("ANIWORLD_SYNCPLAY_PASSWORD", "private-room-key")
    monkeypatch.setenv("ANIWORLD_SYNCPLAY_ROOM", "my-room")
    monkeypatch.setenv("ANIWORLD_ANISKIP", "0")
    monkeypatch.setattr(
        common,
        "_resolve_stream_url_with_fallback",
        lambda *args: ("https://example.test/video", "VOE"),
    )
    monkeypatch.setattr(common, "get_syncplay_path", lambda: "syncplay")

    def player(**kwargs):
        players.append(kwargs)
        return "mpv"

    monkeypatch.setattr(common, "get_player_path", player)
    monkeypatch.setattr(
        common.subprocess, "run", lambda cmd, **kwargs: commands.append(cmd)
    )
    with caplog.at_level(logging.DEBUG):
        common.syncplay(SimpleNamespace(_file_name="episode"))
    assert players == [{"use_iina": False}]
    assert os.environ["ANIWORLD_USE_IINA"] == "1"
    command = commands[0]
    assert command[command.index("--room") + 1] == "my-room"
    assert "private-room-key" not in caplog.text
    assert "private-room-key" not in command


def test_hanime_cli_video_url_selects_one_video():
    obj = entry.model_for_url("https://hanime.tv/videos/hentai/example-1")
    assert isinstance(obj, HanimeTVEpisode)


def test_mangafire_format_setting_controls_model_and_web_ui(monkeypatch):
    monkeypatch.setenv("ANIWORLD_MANGAFIRE_FORMAT", "cbz")
    chapter = MangaFireToChapter(
        "https://mangafire.to/title/z9w-velvet-kisss/chapter/1",
        chapter_id=5484330,
        chapter_number=1,
    )
    assert chapter.mangafire_format == media.mangafire_format() == "cbz"
    explicit = MangaFireToChapter(
        chapter.chapter_url, chapter_id=5484330, chapter_number=1, format="jpg"
    )
    assert explicit.mangafire_format == "jpg"
