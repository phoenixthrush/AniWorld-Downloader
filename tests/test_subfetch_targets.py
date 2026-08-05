"""Tests for where a fetched subtitle ends up, and when none is fetched at all.

The network layer (release lookup, attachment download, ffsubsync) is stubbed
out; what is exercised is the decision logic around it -- which container gets
a muxed track versus a sidecar file, and the guards that must return early
without ever reaching the network.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from aniworld.models.aniworld_to.dubsync import subfetch

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)

ANIWORLD_URL = (
    "https://aniworld.to/anime/stream/sousou-no-frieren/staffel-1/episode-5"
)

SUBTITLE = """[Script Info]
ScriptType: v4.00+

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Guten Morgen.
"""


class _Series:
    """Stands in for a real series without any of its network lookups."""

    title = "Frieren: Beyond Journey's End"
    alternative_titles = ["Sousou no Frieren"]
    mal_id = []  # empty: keeps the Jikan lookup out of the test entirely


class _Season:
    def __init__(self, number):
        self.season_number = number


class _Episode:
    def __init__(self, url=ANIWORLD_URL, season=1, episode=5):
        self.url = url
        self.series = _Series()
        self.season = _Season(season)
        self.episode_number = episode


@pytest.fixture
def no_network(monkeypatch):
    """Stub the lookup/download/align chain and record whether it was reached."""

    calls = {"lookup": 0, "download": 0}

    def fake_find(titles, episode_number, lang3):
        calls["lookup"] += 1
        return 2589985, "ass", "[Erai-raws] Sousou no Frieren - 05 [1080p][MultiSub]"

    def fake_download(attachment_id, lang3, ext, dest):
        calls["download"] += 1
        Path(dest).write_text(SUBTITLE, encoding="utf-8")

    monkeypatch.setattr(subfetch, "_find_subtitle", fake_find)
    monkeypatch.setattr(subfetch, "_download_attachment", fake_download)
    # ffsubsync may or may not be installed; keep the outcome deterministic.
    monkeypatch.setattr(subfetch, "_align_subtitle", lambda video, sub, label="": sub)
    return calls


def _make_media(path: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-metadata:s:a:0", "language=deu", str(path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return path


def _subtitle_languages(path: Path) -> list[str]:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "s",
         "-show_entries", "stream_tags=language", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in probe.stdout.split() if line]


def test_mkv_gets_a_muxed_subtitle_track(tmp_path, no_network):
    episode_file = _make_media(tmp_path / "episode.mkv")

    result = subfetch.fetch_and_mux_subtitle(_Episode(), episode_file, lang="ger")

    assert result == episode_file
    assert _subtitle_languages(episode_file) == ["ger"]
    # The downloaded subtitle is muxed in, not left lying next to the video.
    assert not (tmp_path / "episode.ger.ass").exists()


def test_mp4_gets_a_sidecar_instead(tmp_path, no_network):
    """MP4 cannot carry ASS, so the subtitle is written next to the video."""

    episode_file = _make_media(tmp_path / "episode.mp4")

    result = subfetch.fetch_and_mux_subtitle(_Episode(), episode_file, lang="ger")

    sidecar = tmp_path / "episode.ger.ass"
    assert result == sidecar
    assert sidecar.exists() and "Guten Morgen" in sidecar.read_text(encoding="utf-8")
    assert _subtitle_languages(episode_file) == []


def test_existing_subtitle_track_is_not_fetched_again(tmp_path, no_network):
    """Re-running a completed download must be a no-op, not a second fetch."""

    episode_file = _make_media(tmp_path / "episode.mkv")
    subfetch.fetch_and_mux_subtitle(_Episode(), episode_file, lang="ger")
    assert no_network["download"] == 1

    assert subfetch.fetch_and_mux_subtitle(_Episode(), episode_file, "ger") is None
    assert no_network["download"] == 1, "must not re-download an existing track"
    assert _subtitle_languages(episode_file) == ["ger"]


@pytest.mark.parametrize(
    "episode, reason",
    [
        (_Episode(url="https://s.to/serie/family-guy/staffel-1/episode-1"),
         "non-anime source has no fansub releases to search"),
        (_Episode(season=0, episode=0), "movies carry no season/episode numbering"),
    ],
)
def test_unsupported_sources_return_early(tmp_path, no_network, episode, reason):
    episode_file = _make_media(tmp_path / "episode.mkv")

    assert subfetch.fetch_and_mux_subtitle(episode, episode_file, "ger") is None
    assert no_network["lookup"] == 0, f"must not hit the network: {reason}"
    assert _subtitle_languages(episode_file) == []


def test_unknown_language_is_refused(tmp_path, no_network):
    episode_file = _make_media(tmp_path / "episode.mkv")

    assert subfetch.fetch_and_mux_subtitle(_Episode(), episode_file, "klingon") is None
    assert no_network["lookup"] == 0


def test_a_missing_release_is_not_an_error(tmp_path, monkeypatch, no_network):
    """No German subs exist for older shows; the download must still stand."""

    monkeypatch.setattr(subfetch, "_find_subtitle", lambda *args: None)
    episode_file = _make_media(tmp_path / "episode.mkv")

    assert subfetch.fetch_and_mux_subtitle(_Episode(), episode_file, "ger") is None
    assert _subtitle_languages(episode_file) == []
    assert episode_file.exists(), "the episode itself must survive untouched"
