"""AniSkip chapter files reach the player as a single argument."""

from functools import partial
from types import SimpleNamespace

import pytest

from aniworld import aniskip
from aniworld.aniskip import aniskip as aniskip_module
from aniworld.models.common import common


@pytest.fixture
def skip_data():
    return {
        "found": True,
        "results": [
            {
                "interval": {"start_time": 12.5, "end_time": 102.75},
                "skip_type": "op",
            },
            {
                "interval": {"start_time": 1300.0, "end_time": 1390.5},
                "skip_type": "ed",
            },
        ],
    }


@pytest.fixture
def playback(monkeypatch, skip_data):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("ANIWORLD_ANISKIP", "1")
    monkeypatch.setattr(aniskip, "setup_aniskip", lambda: None)
    monkeypatch.setattr(common, "get_player_path", lambda **kwargs: "mpv")
    monkeypatch.setattr(common, "get_syncplay_path", lambda: "syncplay")
    monkeypatch.setattr(common.subprocess, "run", run)
    episode = SimpleNamespace(
        _file_name="Episode with spaces",
        selected_provider="VOE",
        stream_url="https://example.test/video",
        skip_times=skip_data,
    )
    return episode, commands


@pytest.mark.parametrize("action", ["watch", "syncplay"])
@pytest.mark.parametrize("directory", ["temporary", "temporary files", "Anime's Näme"])
def test_playback_preserves_the_chapters_path(
    monkeypatch, tmp_path, playback, action, directory
):
    temporary = tmp_path / directory
    temporary.mkdir()
    monkeypatch.setattr(
        aniskip_module.tempfile,
        "NamedTemporaryFile",
        partial(aniskip_module.tempfile.NamedTemporaryFile, dir=temporary),
    )
    episode, commands = playback

    getattr(common, action)(episode)

    assert len(commands) == 1
    command = commands[0]
    chapter_files = list(temporary.iterdir())
    assert len(chapter_files) == 1
    chapters = chapter_files[0]
    assert f"--chapters-file={chapters}" in command
    assert (
        "--script-opts=skip-op_start=12.5,skip-op_end=102.75,"
        "skip-ed_start=1300.0,skip-ed_end=1390.5"
    ) in command
    assert "--force-media-title=Episode with spaces" in command
    assert chapters.read_text() == (
        ";FFMETADATA1\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=12500\nEND=102750\nTITLE=OP\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=1300000\nEND=1390500\nTITLE=ED\n"
    )
    if action == "syncplay":
        assert command.index("--chapters-file=" + str(chapters)) > command.index("--")


@pytest.mark.parametrize("action", ["watch", "syncplay"])
@pytest.mark.parametrize("state", ["disabled", "not-found", "unavailable"])
def test_playback_without_skip_times(monkeypatch, playback, action, state):
    episode, commands = playback
    if state == "disabled":
        monkeypatch.setenv("ANIWORLD_ANISKIP", "0")
    elif state == "not-found":
        episode.skip_times = {"found": False}
    else:
        del episode.skip_times

    getattr(common, action)(episode)

    assert len(commands) == 1
    assert not any(
        argument.startswith(("--chapters-file=", "--script-opts="))
        for argument in commands[0]
    )


@pytest.mark.parametrize("skip_data", [None, {}, {"found": False}])
def test_missing_skip_times_produce_no_arguments(skip_data):
    assert aniskip.build_mpv_flags(skip_data) == []
