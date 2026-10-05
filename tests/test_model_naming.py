"""MegaKino and Moflix use full templates and reuse their legacy paths."""

import pytest

from aniworld.models.megakino import MegaKinoEpisode
from aniworld.models.moflix_stream.series import MoflixEpisode


@pytest.fixture(params=[MegaKinoEpisode, MoflixEpisode])
def model(request, monkeypatch, tmp_path):
    cls = request.param
    monkeypatch.setattr(cls, "title_cleaned", "Example")
    monkeypatch.setattr(cls, "release_year", "2024")
    monkeypatch.setattr(cls, "is_series", True)
    monkeypatch.setenv("ANIWORLD_MOVIE_FOLDER", "1")
    if cls is MegaKinoEpisode:
        url = "https://megakino.example/serials/123-example.html#mkep=3"
        season = "01"
        legacy = tmp_path / "Example" / "Example - E03.mkv"
    else:
        url = "https://moflix-stream.xyz/titles/42/season/2/episodes/3"
        season = "02"
        legacy = tmp_path / "Example (2024)" / "Season 2" / "Example (2024) S2E3.mkv"

    return cls(url, selected_path=str(tmp_path)), season, legacy


def test_default_series_template(model, tmp_path):
    episode, season, _ = model
    expected = (
        tmp_path / "Example (2024)" / f"Season {season}" / f"Example S{season}E003.mkv"
    )
    assert episode._episode_path == expected
    assert episode._base_folder == tmp_path / "Example (2024)"
    assert episode._folder_path == expected.parent
    assert episode._file_name == expected.stem
    assert episode._file_extension == "mkv"


@pytest.mark.parametrize("style", ["brace", "percent"])
def test_full_template_and_sanitization(model, tmp_path, monkeypatch, style):
    episode, season, _ = model
    monkeypatch.setattr(type(episode), "title_cleaned", "Example: /Test\\?")
    template = "{title}/{language}/{year}/Season {season}/{title} S{season}E{episode} {resolution}.mp4"
    if style == "percent":
        import re

        template = re.sub(r"\{(\w+)\}", r"%\1%", template)
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", template)
    episode._resolution = "1080p"
    assert episode._episode_path == (
        tmp_path
        / "Example Test"
        / "German Dub"
        / "2024"
        / f"Season {season}"
        / f"Example Test S{season}E003 1080p.mp4"
    )


def test_existing_legacy_download_is_reused(model):
    episode, _, legacy = model
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"existing video")
    assert episode._episode_path == legacy
    assert episode._episode_path.read_bytes() == b"existing video"


def test_new_path_wins_when_both_files_exist(model):
    episode, _, legacy = model
    new_path = episode._episode_path
    new_path.parent.mkdir(parents=True)
    new_path.touch()
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.touch()
    episode.selected_path = episode.selected_path
    assert episode._episode_path == new_path


@pytest.mark.parametrize("movie_folder", ["0", "1"])
def test_movies_have_no_episode_marker(model, tmp_path, monkeypatch, movie_folder):
    episode, _, _ = model
    monkeypatch.setattr(type(episode), "is_series", False)
    monkeypatch.setenv("ANIWORLD_MOVIE_FOLDER", movie_folder)
    folder = tmp_path / "Example (2024)" if movie_folder == "1" else tmp_path
    assert episode._episode_path == folder / "Example (2024).mkv"


def test_template_without_extension_and_changed_output_root(
    model, tmp_path, monkeypatch
):
    episode, _, _ = model
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title}")
    monkeypatch.setattr(type(episode), "title_cleaned", "Example.Part.2")
    assert episode._episode_path == tmp_path / "Example.Part.2.mkv"
    episode.selected_path = str(tmp_path / "other")
    assert episode._episode_path == tmp_path / "other" / "Example.Part.2.mkv"


def test_missing_metadata_does_not_create_empty_tags(model, tmp_path, monkeypatch):
    episode, season, _ = model
    monkeypatch.setattr(type(episode), "release_year", None)
    assert episode._episode_path == (
        tmp_path / "Example" / f"Season {season}" / f"Example S{season}E003.mkv"
    )


def test_custom_movie_template_and_legacy_movie(model, tmp_path, monkeypatch):
    episode, _, _ = model
    monkeypatch.setattr(type(episode), "is_series", False)
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE", "Movies/{title} [{year}] {language}.mp4"
    )
    expected = tmp_path / "Movies" / "Example [2024] German Dub.mp4"
    assert episode._episode_path == expected
    legacy = tmp_path / "Example (2024)" / "Example (2024).mp4"
    legacy.parent.mkdir()
    legacy.touch()
    episode.selected_path = episode.selected_path
    assert episode._episode_path == legacy
