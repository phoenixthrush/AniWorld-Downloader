"""Backend download roots share one policy without changing CLI destinations."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aniworld import arguments
from aniworld.models.animeidhentai.episode import AnimeIDHentaiEpisode
from aniworld.models.aniworld_to.episode import AniworldEpisode
from aniworld.models.burningseries.series import BurningSeriesEpisode
from aniworld.models.filmo_to.episode import FilmoEpisode
from aniworld.models.filmpalast_to.episode import FilmPalastEpisode
from aniworld.models.hanime_tv.episode import HanimeTVEpisode
from aniworld.models.hentai_tv.episode import HentaiTVEpisode
from aniworld.models.hentaihaven.episode import HentaiHavenEpisode
from aniworld.models.kinox.series import KinoxEpisode
from aniworld.models.mangafire_to.series import MangaFireToChapter, MangaFireToSeries
from aniworld.models.megakino.series import MegaKinoEpisode
from aniworld.models.moflix_stream.series import MoflixEpisode
from aniworld.models.s_to.episode import SerienstreamEpisode

MODELS = [
    (AniworldEpisode, "https://aniworld.to/anime/stream/example/staffel-1/episode-1"),
    (SerienstreamEpisode, "https://s.to/serie/example/staffel-1/episode-1"),
    (HanimeTVEpisode, "https://hanime.tv/videos/hentai/example-1"),
    (HentaiTVEpisode, "https://hentai.tv/hentai/example-episode-2"),
    (AnimeIDHentaiEpisode, "https://animeidhentai.com/641/example-episode-2-sub-eng"),
    (HentaiHavenEpisode, "https://hentaihaven.xxx/watch/example/episode-2/"),
    (MegaKinoEpisode, "https://megakino.example/serials/123-example.html"),
    (MoflixEpisode, "https://moflix-stream.xyz/titles/42/season/2/episodes/3"),
    (KinoxEpisode, "https://kinox.to/Stream/Example.html"),
    (BurningSeriesEpisode, "https://bs.to/serie/example/1/1-example/de"),
    (FilmPalastEpisode, "https://filmpalast.to/stream/example"),
    (FilmoEpisode, "https://filmo.to/movies/example"),
    (MangaFireToChapter, "https://mangafire.to/title/example/chapter/1"),
]


@pytest.fixture(params=MODELS, ids=[cls.__name__ for cls, _ in MODELS])
def model(request):
    cls, url = request.param
    return lambda selected_path=None: cls(url, selected_path=selected_path)


@pytest.fixture
def home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    # expanduser uses HOME on Unix and USERPROFILE on Windows.
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return home


@pytest.mark.parametrize(
    "path", ["Videos/Media", "~/Videos/Media", Path("Videos/Media")]
)
def test_selected_paths_expand_beneath_home(model, home, monkeypatch, path):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(home / "ignored"))
    assert Path(model(path).selected_path) == home / "Videos/Media"


@pytest.mark.parametrize("path", ["Videos/Media", "~/Videos/Media"])
def test_configured_paths_expand_beneath_home(model, home, monkeypatch, path):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", path)
    assert Path(model().selected_path) == home / "Videos/Media"


@pytest.mark.parametrize("setting", [None, "", "   "])
def test_default_download_root(model, home, monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv("ANIWORLD_DOWNLOAD_PATH", raising=False)
    else:
        monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", setting)
    assert Path(model().selected_path) == home / "Downloads"


def test_absolute_paths_are_preserved(model, home, tmp_path):
    destination = tmp_path / "absolute media"
    assert Path(model(destination).selected_path) == destination


def test_configured_path_whitespace_matches_library_root(model, home, monkeypatch):
    from aniworld.web.paths import default_download_path

    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", "  ~/Videos with spaces  ")
    expected = home / "Videos with spaces"
    assert Path(model().selected_path) == expected
    assert default_download_path() == expected


@pytest.mark.parametrize("selected", ["", "   "])
def test_blank_selection_uses_configured_root(model, home, monkeypatch, selected):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", "~/Configured")
    assert Path(model(selected).selected_path) == home / "Configured"


def test_explicit_path_spaces_are_preserved(model, home):
    assert Path(model("  Media  ").selected_path) == home / "  Media  "


def test_relative_parent_components_are_preserved(model, home):
    assert Path(model("../Media").selected_path) == home / "../Media"


def test_symlink_root_is_preserved(model, home, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = home / "linked-media"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if sys.platform == "win32" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows requires symlink privileges for this case")
        raise
    selected = Path(model(link).selected_path)
    assert selected == link
    assert selected.resolve() == target.resolve()


@pytest.mark.parametrize(
    "cls,url", MODELS[:-1], ids=[cls.__name__ for cls, _ in MODELS[:-1]]
)
def test_changing_selected_root_updates_complete_video_path(
    cls, url, home, monkeypatch
):
    series = SimpleNamespace(
        title_cleaned="Example", release_year="2024", imdb="", raw_franchise_videos=[]
    )
    season = SimpleNamespace(season_number=1)
    # Supply metadata only; exercise the real path properties and setters.
    monkeypatch.setattr(cls, "series", property(lambda self: series), raising=False)
    monkeypatch.setattr(cls, "season", property(lambda self: season), raising=False)
    for name, value in {
        "title_cleaned": "Example",
        "series_title": "Example",
        "release_year": "2024",
        "season_number": 1,
        "episode_number": 1,
        "is_series": True,
    }.items():
        monkeypatch.setattr(cls, name, value, raising=False)
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE",
        "{title}/Season {season}/{title} S{season}E{episode}.mkv",
    )
    episode = cls(url, selected_path="~/First")
    old_path = episode._episode_path
    relative = old_path.relative_to(home / "First")
    episode.selected_path = "Second"
    assert episode._episode_path == home / "Second" / relative
    assert episode._episode_path != old_path


def test_relative_cli_output_stays_beneath_working_directory(model, home, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["aniworld", "--output", "./downloads"])
    arguments.parse_args()
    assert Path(model().selected_path) == Path.cwd() / "downloads"


def test_mangafire_download_uses_expanded_selected_path(home, monkeypatch):
    series = SimpleNamespace(title="Example")
    chapter = MangaFireToChapter(
        "https://mangafire.to/title/example/chapter/1",
        series=series,
        chapter_number=1,
        selected_path="~/Manga",
        format="jpg",
    )
    page = SimpleNamespace(download=Mock())
    monkeypatch.setattr(chapter, "_MangaFireToChapter__pages", [page])
    destination = chapter.download()
    assert destination == home / "Manga" / "Example" / "Chapter 1"
    assert destination.is_dir()
    page.download.assert_called_once_with(destination, total_pages=1)


def test_mangafire_series_uses_shared_configured_root(home, monkeypatch):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", "~/Manga")
    series = MangaFireToSeries("https://mangafire.to/title/123-example")
    monkeypatch.setattr(MangaFireToSeries, "title", "Example")
    chapter = SimpleNamespace(folder_name="Chapter 1", download=Mock())
    destination = series.download(chapters=[chapter])
    assert destination == home / "Manga" / "Example"
    chapter.download.assert_called_once_with(
        destination / "Chapter 1", chapter_index=1, total_chapters=1
    )


def test_mangafire_explicit_folder_remains_a_direct_destination(home, monkeypatch):
    chapter = MangaFireToChapter(
        "https://mangafire.to/title/example/chapter/1",
        chapter_number=1,
        selected_path="~/ignored",
        format="jpg",
    )
    page = SimpleNamespace(download=Mock())
    monkeypatch.setattr(chapter, "_MangaFireToChapter__pages", [page])
    assert chapter.download(folder="direct/Chapter 1") == Path("direct/Chapter 1")
    assert (Path.cwd() / "direct/Chapter 1").is_dir()
    assert not (home / "direct").exists()
