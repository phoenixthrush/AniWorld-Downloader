"""Media-specific templates work through real model paths without network access."""

from types import SimpleNamespace

import pytest
from test_model_paths import MODELS

from aniworld.models.aniworld_to.episode import AniworldEpisode
from aniworld.models.common.naming import template_path
from aniworld.web import settings_store


@pytest.fixture(params=MODELS[:-1], ids=[cls.__name__ for cls, _ in MODELS[:-1]])
def episode(request, monkeypatch, tmp_path):
    cls, url = request.param
    if cls.__name__ == "MegaKinoEpisode":
        url += "#mkep=3"
    series = SimpleNamespace(
        title_cleaned="Example",
        release_year="2024",
        imdb="tt12345",
        raw_franchise_videos=[],
    )
    monkeypatch.setattr(cls, "series", property(lambda self: series), raising=False)
    monkeypatch.setattr(cls, "season", SimpleNamespace(season_number=2), raising=False)
    for name, value in {
        "title_cleaned": "Example",
        "series_title": "Example",
        "release_year": "2024",
        "season_number": 2,
        "episode_number": 3,
        "is_series": True,
        "_naming_title": "Example",
    }.items():
        monkeypatch.setattr(cls, name, value, raising=False)
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE", "Old/{title} S{season}E{episode}.mkv"
    )
    result = cls(url, selected_path=str(tmp_path))
    if cls.__name__ == "KinoxEpisode":
        result.is_movie = False
    return result


def set_templates(monkeypatch):
    monkeypatch.setenv(
        "ANIWORLD_SERIES_NAMING_TEMPLATE",
        "Series/{title}/{year}/{language}/Season {season}/{title} E{episode}.{resolution}.mp4",
    )
    monkeypatch.setenv(
        "ANIWORLD_MOVIE_NAMING_TEMPLATE",
        "Movies/{title}/{year}/{language}/{title}.{resolution}.mp4",
    )


def test_all_video_sites_use_complete_media_template(episode, monkeypatch, tmp_path):
    set_templates(monkeypatch)
    path = episode._episode_path
    movie = episode._template_kind == "movie"
    assert path.relative_to(tmp_path).parts[:4] == (
        "Movies" if movie else "Series",
        "Example",
        "2024",
        episode.selected_language,
    )
    assert path.suffix == ".mp4"
    if not movie:
        season = (
            "02"
            if type(episode).__name__
            in {
                "AniworldEpisode",
                "SerienstreamEpisode",
                "MoflixEpisode",
                "KinoxEpisode",
                "BurningSeriesEpisode",
            }
            else "01"
        )
        assert path.parent.name == f"Season {season}"
        assert "E003" in path.name
    assert episode._base_folder == tmp_path / ("Movies" if movie else "Series")
    assert episode._folder_path == path.parent
    assert episode._file_name == path.stem
    assert episode._file_extension == "mp4"
    episode.selected_path = str(tmp_path / "other")
    assert episode._episode_path == tmp_path / "other" / path.relative_to(tmp_path)


def test_all_video_sites_reuse_legacy_downloads(episode, monkeypatch):
    legacy = episode._episode_path
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"existing")
    set_templates(monkeypatch)
    assert episode._episode_path == legacy
    assert episode._file_extension == "mkv"
    assert legacy.read_bytes() == b"existing"


def test_new_download_wins_over_legacy(episode, monkeypatch):
    legacy = episode._episode_path
    set_templates(monkeypatch)
    new = episode._episode_path
    new.parent.mkdir(parents=True)
    new.touch()
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.touch()
    assert episode._episode_path == new


@pytest.mark.parametrize(
    "cls,url",
    [
        (cls, url)
        for cls, url in MODELS
        if cls.__name__ in {"MegaKinoEpisode", "MoflixEpisode", "KinoxEpisode"}
    ],
)
def test_mixed_video_sites_select_movie_template(cls, url, monkeypatch, tmp_path):
    series = SimpleNamespace(title_cleaned="Example", release_year="2024")
    monkeypatch.setattr(cls, "series", property(lambda self: series), raising=False)
    monkeypatch.setattr(cls, "title_cleaned", "Example", raising=False)
    monkeypatch.setattr(cls, "release_year", "2024", raising=False)
    monkeypatch.setattr(cls, "is_series", False, raising=False)
    monkeypatch.setenv("ANIWORLD_SERIES_NAMING_TEMPLATE", "Series/{title}.mkv")
    monkeypatch.setenv("ANIWORLD_MOVIE_NAMING_TEMPLATE", "Movies/{title} ({year}).mp4")
    item = cls(url, selected_path=tmp_path)
    if cls.__name__ == "KinoxEpisode":
        item.is_movie = True
    assert item._episode_path == tmp_path / "Movies" / "Example (2024).mp4"


@pytest.mark.parametrize("style", ["brace", "percent"])
def test_missing_metadata_and_sanitization(tmp_path, style):
    template = "{title} ({year}) [imdbid-{imdbid}]/{title} - {chapter_title}"
    if style == "percent":
        template = template.replace("{", "%").replace("}", "%")
    assert (
        template_path(
            tmp_path,
            template,
            {
                "title": "Example: /Test\\?",
                "year": None,
                "imdbid": "",
                "chapter_title": "",
            },
            is_series=True,
            extension="",
        )
        == tmp_path / "Example Test" / "Example Test"
    )


@pytest.mark.parametrize("movie_folder", [False, True])
def test_movie_folder_policy(tmp_path, movie_folder):
    assert (
        template_path(
            tmp_path,
            "Movies/{title}/{title}.mp4",
            {"title": "Example"},
            is_series=False,
            movie_folder=movie_folder,
        )
        == (tmp_path / "Movies" / "Example" if movie_folder else tmp_path)
        / "Example.mp4"
    )


def test_template_settings_survive_env_merge_and_export(tmp_path, monkeypatch):
    from pathlib import Path

    from aniworld.env import merge_env

    env = tmp_path / ".env"
    values = {
        "ANIWORLD_SERIES_NAMING_TEMPLATE": "{title}/E{episode}.mp4",
        "ANIWORLD_MOVIE_NAMING_TEMPLATE": "{title}.mkv",
        "ANIWORLD_MANGA_NAMING_TEMPLATE": "{title}/Chapter {chapter}",
    }
    env.write_text("\n".join(f'{key}="{value}"' for key, value in values.items()))
    merge_env(Path(__file__).parents[1] / "src/aniworld/.env.example", env)
    for key, value in values.items():
        assert f'{key}="{value}"' in env.read_text()
        monkeypatch.setenv(key, value)
        assert f"{key}=" in settings_store.export_env()


@pytest.mark.parametrize(
    "number,title,year", [(1, "First Film", "2020"), (2, "Second Film", "2024")]
)
def test_aniworld_movies_use_their_own_metadata(
    tmp_path, monkeypatch, number, title, year
):
    import json

    monkeypatch.setenv(
        "ANIWORLD_MOVIE_NAMING_TEMPLATE",
        "{title} ({year}) [imdbid-{imdbid}]/{title}.mp4",
    )
    episode = AniworldEpisode(
        f"https://aniworld.to/anime/stream/example/filme/film-{number}",
        series=SimpleNamespace(
            title_cleaned="Parent Series", release_year="1990", imdb="tt999"
        ),
        season=SimpleNamespace(season_number=0),
        episode_number=number,
        title_de=title,
        selected_path=tmp_path,
    )
    metadata = {
        "@type": "Movie",
        "datePublished": f"{year}-01-01",
        "sameAs": "https://imdb.com/title/tt12345",
    }
    monkeypatch.setattr(
        episode,
        "_AniworldEpisode__html",
        f'<script type="application/ld+json">{json.dumps(metadata)}</script>',
    )
    assert (
        episode._episode_path
        == tmp_path / f"{title} ({year}) [imdbid-tt12345]" / f"{title}.mp4"
    )


def test_aniworld_movie_does_not_inherit_parent_year_or_imdb(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "ANIWORLD_MOVIE_NAMING_TEMPLATE",
        "{title} ({year}) [imdbid-{imdbid}]/{title}.mkv",
    )
    episode = AniworldEpisode(
        "https://aniworld.to/anime/stream/example/filme/film-1",
        series=SimpleNamespace(
            title_cleaned="Parent", release_year="1990", imdb="tt999"
        ),
        season=SimpleNamespace(season_number=0),
        episode_number=1,
        title_de="Film",
        selected_path=tmp_path,
    )
    monkeypatch.setattr(episode, "_AniworldEpisode__html", "<html></html>")
    assert episode._episode_path == tmp_path / "Film" / "Film.mkv"


def test_new_template_resolution_is_finalized_and_reused(episode, monkeypatch):
    from aniworld.models.common import common

    set_templates(monkeypatch)
    common._prepare_resolution_naming(episode)
    old = episode._episode_path
    old.parent.mkdir(parents=True)
    old.write_bytes(b"video")
    monkeypatch.setattr(common, "_read_container_resolution", lambda path: "720p")
    common._finalize_resolution_naming(episode)
    new = episode._episode_path
    assert not old.exists()
    assert new.name.endswith(".720p.mp4")
    assert new.read_bytes() == b"video"
    common._prepare_resolution_naming(episode)
    assert episode._episode_path == new


def test_resolution_search_prefers_new_file_over_legacy(episode, monkeypatch):
    from aniworld.models.common import common

    legacy = episode._episode_path
    set_templates(monkeypatch)
    common._set_naming_resolution(episode, "720p")
    new = episode._episode_path
    new.parent.mkdir(parents=True)
    new.write_bytes(b"new")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"legacy")
    monkeypatch.setattr(common, "_read_container_resolution", lambda path: "720p")
    common._prepare_resolution_naming(episode)
    assert episode._episode_path == new


def test_resolution_finalization_never_overwrites_legacy(episode, monkeypatch):
    from aniworld.models.common import common

    legacy = episode._episode_path
    set_templates(monkeypatch)
    old = episode._episode_path
    old.parent.mkdir(parents=True)
    old.write_bytes(b"new download")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"legacy download")
    monkeypatch.setattr(common, "_read_container_resolution", lambda path: "720p")
    common._finalize_resolution_naming(episode)
    assert legacy.read_bytes() == b"legacy download"
    assert episode._episode_path.name.endswith(".720p.mp4")
    assert episode._episode_path.read_bytes() == b"new download"


def test_new_templates_reuse_resolved_legacy_download(episode, monkeypatch):
    from aniworld.models.common import common

    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "Old/{title}.{resolution}.mkv")
    common._set_naming_resolution(episode, "720p")
    legacy = episode._episode_path
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy")
    set_templates(monkeypatch)
    monkeypatch.setattr(common, "_read_container_resolution", lambda path: "720p")
    common._prepare_resolution_naming(episode)
    assert episode._episode_path == legacy


def test_web_movie_preview_uses_its_own_template(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(tmp_path))
    monkeypatch.setenv("ANIWORLD_SERIES_NAMING_TEMPLATE", "Series/{title}.mkv")
    monkeypatch.setenv(
        "ANIWORLD_MOVIE_NAMING_TEMPLATE", "Movies/{title} ({year})/{title}.mp4"
    )
    assert settings_store.preview_paths()["movie"] == str(
        tmp_path / "Movies" / "Your Name (2016)" / "Your Name.mp4"
    )


def test_web_format_changes_both_active_video_templates(monkeypatch):
    monkeypatch.setenv("ANIWORLD_SERIES_NAMING_TEMPLATE", "Series/{title}.mp4")
    monkeypatch.setenv("ANIWORLD_MOVIE_NAMING_TEMPLATE", "Movies/{title}.mkv")
    assert settings_store.read_settings()["output_format"] == "mp4"
    settings_store.update_settings({"output_format": "mkv"})
    import os

    assert os.environ["ANIWORLD_SERIES_NAMING_TEMPLATE"] == "Series/{title}.mkv"
    assert os.environ["ANIWORLD_MOVIE_NAMING_TEMPLATE"] == "Movies/{title}.mkv"


@pytest.mark.parametrize("template", ["", "Folder/", "Folder/{year}", "Folder/.."])
def test_empty_filename_is_rejected(tmp_path, template):
    with pytest.raises(ValueError, match="filename"):
        template_path(tmp_path, template, {"year": ""}, is_series=True)


def test_unknown_placeholder_is_rejected(tmp_path):
    with pytest.raises(KeyError, match="unknown"):
        template_path(tmp_path, "{unknown}.mkv", {}, is_series=True)


def test_metadata_cannot_escape_download_root(tmp_path):
    path = template_path(
        tmp_path,
        "{title}/{title}.mkv",
        {"title": "../../other\\..\\movie:C"},
        is_series=True,
    )
    assert path.is_relative_to(tmp_path)
    assert len(path.relative_to(tmp_path).parts) == 2


def test_all_video_sites_support_percent_templates_and_default_extension(
    episode, monkeypatch
):
    monkeypatch.setenv(
        f"ANIWORLD_{episode._template_kind.upper()}_NAMING_TEMPLATE",
        "%title%/%language%/%year%/%title%",
    )
    path = episode._episode_path
    assert path.name == "Example.mkv"
    assert path.parent.name == "2024"
    assert path.parent.parent.name == episode.selected_language


def test_all_video_sites_reject_unsupported_container(episode, monkeypatch):
    monkeypatch.setenv(
        f"ANIWORLD_{episode._template_kind.upper()}_NAMING_TEMPLATE", "{title}.avi"
    )
    with pytest.raises(ValueError, match=".mkv or .mp4"):
        _ = episode._episode_path


def test_resolution_finalization_preserves_conflicting_target(episode, monkeypatch):
    from aniworld.models.common import common

    set_templates(monkeypatch)
    old = episode._episode_path
    old.parent.mkdir(parents=True)
    old.write_bytes(b"pending download")
    common._set_naming_resolution(episode, "720p")
    new = episode._episode_path
    new.write_bytes(b"previous download")
    common._set_naming_resolution(episode, "unknown")
    monkeypatch.setattr(common, "_read_container_resolution", lambda path: "720p")
    with pytest.raises(FileExistsError, match="already exists"):
        common._finalize_resolution_naming(episode)
    assert old.read_bytes() == b"pending download"
    assert new.read_bytes() == b"previous download"


def test_settings_api_previews_and_exports_media_templates(
    client, monkeypatch, tmp_path
):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(tmp_path))
    monkeypatch.setenv("ANIWORLD_SERIES_NAMING_TEMPLATE", "Series/{title}.mp4")
    monkeypatch.setenv("ANIWORLD_MOVIE_NAMING_TEMPLATE", "Movies/{title} ({year}).mkv")
    monkeypatch.setenv(
        "ANIWORLD_MANGA_NAMING_TEMPLATE", "Manga/{title}/Chapter {chapter}"
    )
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.get_json()["path_preview"]["movie"] == str(
        tmp_path / "Movies" / "Your Name (2016).mkv"
    )
    assert client.put("/api/settings", json={"output_format": "mkv"}).status_code == 200
    assert (
        client.get("/api/settings/path-preview").get_json()["episode"].endswith(".mkv")
    )
    exported = client.get("/api/settings/env")
    assert exported.status_code == 200
    assert b"ANIWORLD_SERIES_NAMING_TEMPLATE=Series/{title}.mkv" in exported.data
    assert (
        b'ANIWORLD_MANGA_NAMING_TEMPLATE="Manga/{title}/Chapter {chapter}"'
        in exported.data
    )


def test_web_queue_uses_model_template_and_custom_language_root(
    episode,
    monkeypatch,
    tmp_path,
    queue_item,
):
    from aniworld.web import db, worker

    set_templates(monkeypatch)
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    root = tmp_path / "custom"
    custom_id = db.add_custom_path("Custom", str(root))
    written = []

    def download(self):
        path = self._episode_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"queued download")
        written.append(path)

    monkeypatch.setattr(type(episode), "download", download)
    url = episode.url
    queue_id = queue_item(episodes=[url], custom_path_id=custom_id)
    worker._process(db.get_queue_item(queue_id))
    result = db.get_queue_item(queue_id)
    assert result["status"] == "completed", result
    assert len(written) == 1
    assert written[0].is_relative_to(root / "german-dub")
    assert written[0].suffix == ".mp4"
