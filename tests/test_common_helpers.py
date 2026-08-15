"""Pure helpers shared by the downloader: filenames, cleanup and progress."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from aniworld.models.aniworld_to.episode import AniworldEpisode
from aniworld.models.common.common import (
    DownloadCancelled,
    _finalize_resolution_naming,
    _parse_ffmpeg_time,
    _prepare_resolution_naming,
    _progress_file_name,
    _read_container_resolution,
    _remove_empty_dirs,
    _set_naming_resolution,
    clean_title,
    format_command_for_shell,
    get_ffmpeg_progress,
    movie_folder_enabled,
)


# ---------------------------------------------------------------------------
# Filenames
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "title,expected",
    [
        ("Naruto", "Naruto"),
        ("Re:Zero", "ReZero"),
        ('A "quoted" show', "A quoted show"),
        ("Who? What!", "Who What!"),
        ("Slash/Back", "SlashBack"),
        ("Back\\Slash", "BackSlash"),
        ("Pipe|Dream", "PipeDream"),
        ("Star*Wars", "StarWars"),
        ("<script>", "script"),
        ("  padded  ", "padded"),
    ],
)
def test_forbidden_characters_are_stripped(title, expected):
    assert clean_title(title) == expected


def test_unicode_titles_survive():
    assert clean_title("Übermäßige Gewalt") == "Übermäßige Gewalt"
    assert clean_title("進撃の巨人") == "進撃の巨人"


def test_an_empty_title_stays_empty():
    assert clean_title("") == ""


def test_a_cleaned_title_is_usable_as_a_folder_name(tmp_path):
    folder = tmp_path / clean_title('Re:Zero "Season" 2?')
    folder.mkdir()
    assert folder.is_dir()


def test_container_resolution_uses_the_only_video_height(monkeypatch):
    monkeypatch.setattr(
        "aniworld.models.common.common.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stderr="Stream #0:0: Video: h264, yuv420p, 1280x720\n"
        ),
    )
    assert _read_container_resolution("episode.mkv") == "720p"


def test_container_resolution_is_unknown_with_multiple_video_streams(monkeypatch):
    monkeypatch.setattr(
        "aniworld.models.common.common.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stderr=(
                "Stream #0:0: Video: h264, yuv420p, 1280x720\n"
                "Stream #0:1: Video: h264, yuv420p, 1920x1080\n"
            )
        ),
    )
    assert _read_container_resolution("episode.mkv") == "unknown"


def test_resolution_placeholder_is_used_in_aniworld_filename(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE",
        "{title}.S{season}E{episode}.{resolution}.{language}.mp4",
    )
    episode = AniworldEpisode(
        "https://aniworld.to/anime/stream/seriesname/staffel-1/episode-1",
        series=SimpleNamespace(title_cleaned="Seriesname", release_year="", imdb=""),
        season=SimpleNamespace(season_number=1),
        episode_number=1,
        selected_path=tmp_path,
        selected_language="English Dub",
    )
    _prepare_resolution_naming(episode)
    _set_naming_resolution(episode, "720p")

    assert episode._episode_path.name == "Seriesname.S01E001.720p.English Dub.mp4"


def test_pending_resolution_is_hidden_from_progress(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE",
        "{title}.S{season}E{episode}.{resolution} - {language}.mkv",
    )
    episode = AniworldEpisode(
        "https://aniworld.to/anime/stream/seriesname/staffel-1/episode-2",
        series=SimpleNamespace(title_cleaned="Seriesname", release_year="", imdb=""),
        season=SimpleNamespace(season_number=1),
        episode_number=2,
        selected_path=tmp_path,
        selected_language="English Dub",
    )
    _prepare_resolution_naming(episode)

    assert episode._file_name == "Seriesname.S01E002.unknown - English Dub"
    assert _progress_file_name(episode) == "Seriesname.S01E002 - English Dub"


def test_finished_download_is_renamed_with_its_resolution(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE", "{title}.{resolution}.{language}.mkv"
    )
    episode = AniworldEpisode(
        "https://aniworld.to/anime/stream/seriesname/staffel-1/episode-1",
        series=SimpleNamespace(title_cleaned="Seriesname", release_year="", imdb=""),
        season=SimpleNamespace(season_number=1),
        episode_number=1,
        selected_path=tmp_path,
        selected_language="English Dub",
    )
    _prepare_resolution_naming(episode)
    unknown_path = episode._episode_path
    unknown_path.write_bytes(b"video")
    monkeypatch.setattr(
        "aniworld.models.common.common.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stderr="Stream #0:0: Video: h264, yuv420p, 1280x720\n"
        ),
    )

    _finalize_resolution_naming(episode)

    assert not unknown_path.exists()
    assert episode._episode_path.name == "Seriesname.720p.English Dub.mkv"
    assert episode._episode_path.read_bytes() == b"video"


# ---------------------------------------------------------------------------
# Command formatting
# ---------------------------------------------------------------------------
def test_a_posix_command_is_quoted_for_copy_paste():
    line = format_command_for_shell(["ffmpeg", "-i", "my file.mkv"], windows=False)
    assert line == "ffmpeg -i 'my file.mkv'"


def test_a_windows_command_uses_double_quotes():
    line = format_command_for_shell(["ffmpeg", "-i", "my file.mkv"], windows=True)
    assert line == '"ffmpeg" "-i" "my file.mkv"'


def test_windows_quoting_escapes_embedded_quotes():
    line = format_command_for_shell(['say "hi"'], windows=True)
    assert line == '"say \\"hi\\""'


def test_windows_quoting_handles_trailing_backslashes():
    line = format_command_for_shell(["C:\\path\\"], windows=True)
    assert line == '"C:\\path\\\\"'


def test_an_empty_argument_is_kept():
    assert format_command_for_shell([""], windows=True) == '""'


def test_numbers_are_stringified():
    assert format_command_for_shell(["ffmpeg", 5], windows=False) == "ffmpeg 5"


def test_the_platform_decides_by_default():
    line = format_command_for_shell(["a b"])
    assert line == ('"a b"' if os.name == "nt" else "'a b'")


# ---------------------------------------------------------------------------
# Empty folder cleanup
# ---------------------------------------------------------------------------
def test_an_empty_folder_is_removed(tmp_path):
    base = tmp_path / "base"
    folder = base / "Season 1"
    folder.mkdir(parents=True)
    _remove_empty_dirs(folder, base)
    assert not folder.exists()
    assert not base.exists()


def test_a_folder_with_files_is_kept(tmp_path):
    base = tmp_path / "base"
    folder = base / "Season 1"
    folder.mkdir(parents=True)
    (folder / "ep1.mkv").write_bytes(b"x")
    _remove_empty_dirs(folder, base)
    assert folder.exists()


def test_the_base_survives_while_a_season_remains(tmp_path):
    base = tmp_path / "base"
    empty = base / "Season 2"
    kept = base / "Season 1"
    empty.mkdir(parents=True)
    kept.mkdir()
    (kept / "ep1.mkv").write_bytes(b"x")

    _remove_empty_dirs(empty, base)
    assert not empty.exists()
    assert base.exists()


def test_the_protected_folder_is_never_removed(tmp_path):
    """With ANIWORLD_MOVIE_FOLDER=0 a movie's folder is the download root."""
    root = tmp_path / "movie-root"
    root.mkdir()
    _remove_empty_dirs(root, root, protected=str(root))
    assert root.exists()


def test_an_unprotected_empty_root_is_removed(tmp_path):
    root = tmp_path / "movie-root"
    root.mkdir()
    _remove_empty_dirs(root, root)
    assert not root.exists()


def test_a_missing_folder_is_not_an_error(tmp_path):
    _remove_empty_dirs(tmp_path / "gone", tmp_path / "also-gone")


def test_a_file_where_a_folder_was_expected_is_ignored(tmp_path):
    target = tmp_path / "not-a-folder"
    target.write_bytes(b"x")
    _remove_empty_dirs(target, tmp_path)
    assert target.exists()


# ---------------------------------------------------------------------------
# Movie folder setting
# ---------------------------------------------------------------------------
def test_movies_get_their_own_folder_by_default():
    assert movie_folder_enabled() is True


def test_the_movie_folder_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("ANIWORLD_MOVIE_FOLDER", "0")
    assert movie_folder_enabled() is False


def test_any_other_value_keeps_it_on(monkeypatch):
    monkeypatch.setenv("ANIWORLD_MOVIE_FOLDER", "1")
    assert movie_folder_enabled() is True


# ---------------------------------------------------------------------------
# ffmpeg progress
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,seconds",
    [
        ("00:00:00.00", 0.0),
        ("00:00:30.50", 30.5),
        ("00:01:00.00", 60.0),
        ("01:00:00.00", 3600.0),
        ("01:23:45.67", 5025.67),
    ],
)
def test_ffmpeg_timestamps_are_parsed(value, seconds):
    assert _parse_ffmpeg_time(value) == pytest.approx(seconds)


@pytest.mark.parametrize("value", ["", "garbage", "1:2", "a:b:c", "N/A"])
def test_an_unparsable_timestamp_is_zero(value):
    assert _parse_ffmpeg_time(value) == 0.0


def test_the_progress_snapshot_has_the_fields_the_ui_reads():
    progress = get_ffmpeg_progress()
    for field in ("percent", "time", "speed", "active"):
        assert field in progress


def test_the_snapshot_is_a_copy():
    """The UI must not be able to corrupt the live progress dict."""
    snapshot = get_ffmpeg_progress()
    snapshot["percent"] = 999
    assert get_ffmpeg_progress()["percent"] != 999


def test_nothing_is_downloading_to_begin_with():
    assert get_ffmpeg_progress()["active"] is False


# ---------------------------------------------------------------------------
# Cancelling
# ---------------------------------------------------------------------------
def test_a_deliberate_cancel_has_its_own_exception_type():
    """The worker tells a kill apart from a real failure by this type."""
    assert issubclass(DownloadCancelled, Exception)
    with pytest.raises(DownloadCancelled):
        raise DownloadCancelled("stopped")


def test_a_cancel_is_still_caught_by_a_broad_handler():
    try:
        raise DownloadCancelled("stopped")
    except Exception as exc:
        assert isinstance(exc, DownloadCancelled)


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
def test_the_version_is_a_real_version():
    from packaging.version import Version

    from aniworld.web.version import get_version

    version = get_version()
    assert version, "the navbar would show an empty version"
    Version(version)  # raises for anything that is not PEP 440


def test_pyproject_carries_a_valid_version():
    """The installed metadata can lag behind an edit, so check the source too."""
    import re

    from packaging.version import Version

    for parent in Path(__file__).resolve().parents:
        pyproject = parent / "pyproject.toml"
        if pyproject.exists():
            match = re.search(
                r'^\s*version\s*=\s*"([^"]+)"',
                pyproject.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
            assert match, "pyproject.toml has no version"
            Version(match.group(1))
            return
    pytest.skip("running outside the source tree")


@pytest.mark.parametrize(
    "lower,higher",
    [
        ("4.9.0", "4.10.0"),
        ("4.8.6", "4.9.0"),
        ("1.0.0", "1.0.1"),
        ("4.10.0", "4.11.0"),
        ("0.9.9", "1.0.0"),
    ],
)
def test_versions_compare_numerically_not_alphabetically(lower, higher):
    """4.10.0 is newer than 4.9.0, a string compare would say otherwise."""
    from packaging.version import parse as parse_version

    assert parse_version(lower) < parse_version(higher)
