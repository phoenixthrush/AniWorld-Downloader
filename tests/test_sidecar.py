"""The .aniworld sidecar: a KEY=VALUE identity card per title folder."""

from pathlib import Path

import pytest

from aniworld import sidecar


class _Series:
    url = "https://aniworld.to/anime/stream/black-torch"
    title = "BLACK TORCH"
    release_year = "2026-2026"
    imdb = "tt37532893"
    poster_url = "https://aniworld.to/public/img/cover/black-torch.jpg"
    description = 'A boy who can hear cats, and a cat who says "no".'

    def __init__(self):
        self.genres = ["Action", "Fantasy"]


class _Season:
    season_number = 1


class _Episode:
    """The attributes the download finaliser reads off a real episode model."""

    def __init__(self, root, title_de="Die schwarze Fackel", title_en="Black Torch"):
        self.series = _Series()
        self.season = _Season()
        self.episode_number = 1
        self.url = "https://aniworld.to/anime/stream/black-torch/staffel-1/episode-1"
        self.title_de = title_de
        self.title_en = title_en
        self.selected_language = "German Dub"
        self.selected_provider = "VOE"
        self.is_movie = False
        self.selected_path = str(root)
        self._base_folder = root / "BLACK TORCH (2026-2026) [imdbid-tt37532893]"
        self._episode_path = self._base_folder / "Season 01" / "BLACK TORCH S01E001.mkv"


@pytest.fixture
def title_dir(tmp_path):
    folder = tmp_path / "BLACK TORCH (2026-2026) [imdbid-tt37532893]"
    (folder / "Season 01").mkdir(parents=True)
    for n in (1, 2, 3):
        (folder / "Season 01" / f"BLACK TORCH S01E{n:03d}.mkv").write_bytes(b"x")
    return folder


# ---------------------------------------------------------------------------
# Format
# ---------------------------------------------------------------------------
def test_scan_reads_identity_from_the_folder_name_and_episodes_from_files(title_dir):
    data = sidecar.scan(title_dir)
    assert (data["title"], data["year"], data["imdb"]) == (
        "BLACK TORCH",
        "2026-2026",
        "tt37532893",
    )
    assert data["origin"] == "scan"
    assert data["type"] == "series"
    assert sorted(data["episodes"]) == ["S01E001", "S01E002", "S01E003"]


def test_the_file_is_dotenv_shaped_and_round_trips(title_dir):
    data = sidecar.scan(title_dir)
    data["title"] = 'Ao-chan Can\'t Study! "quoted" \\ back'
    data["genres"] = ["Action", "Slice of Life"]
    data["episodes"]["S01E001"] = {"title_de": "Anfang|mit Strich", "title_en": "Start"}
    assert sidecar.write(title_dir, data)

    text = (title_dir / ".aniworld").read_text(encoding="utf-8")
    assert text.splitlines()[3] == "ANIWORLD=1"
    assert 'TITLE="Ao-chan Can\'t Study! \\"quoted\\" \\\\ back"' in text
    assert "S01E001=" in text

    back = sidecar.read(title_dir)
    assert back["title"] == data["title"]
    assert back["genres"] == ["Action", "Slice of Life"]
    # the first "|" splits German from English, the German half keeps the rest
    assert back["episodes"]["S01E001"] == {
        "title_de": "Anfang",
        "title_en": "mit Strich|Start",
    }


def test_a_scanned_sidecar_is_python_dotenv_readable(title_dir):
    """Anyone with a .env parser can identify the folder, that is the point."""
    from dotenv import dotenv_values

    sidecar.write(title_dir, sidecar.scan(title_dir))
    values = dotenv_values(title_dir / ".aniworld")
    assert values["TITLE"] == "BLACK TORCH"
    assert values["IMDB"] == "tt37532893"
    assert values["S01E002"] == "|"


@pytest.mark.parametrize(
    "text",
    ["", "garbage\n", "ANIWORLD=2\nTITLE=x\n", "TITLE=x\n", "\x00\x01\x02"],
)
def test_anything_malformed_reads_as_no_sidecar(title_dir, text):
    (title_dir / ".aniworld").write_text(text, encoding="utf-8", errors="ignore")
    assert sidecar.read(title_dir) is None


def test_missing_folder_reads_as_none_and_never_writes(tmp_path):
    assert sidecar.read(tmp_path / "nope") is None
    assert sidecar.write(tmp_path / "nope", sidecar.empty("x")) is False


def test_writes_can_be_switched_off(monkeypatch, title_dir):
    monkeypatch.setenv("ANIWORLD_LIBRARY_SIDECARS", "0")
    assert sidecar.write(title_dir, sidecar.scan(title_dir)) is False
    assert not (title_dir / ".aniworld").exists()
    # loading still works, it just does not store the scan
    assert sidecar.load(title_dir)["title"] == "BLACK TORCH"
    assert not (title_dir / ".aniworld").exists()


def test_load_stores_the_scan_once(title_dir):
    assert not (title_dir / ".aniworld").exists()
    sidecar.load(title_dir)
    assert (title_dir / ".aniworld").exists()
    first = (title_dir / ".aniworld").read_text()
    sidecar.load(title_dir)
    assert (title_dir / ".aniworld").read_text() == first


def test_writes_are_atomic_no_temp_left_behind(title_dir):
    sidecar.write(title_dir, sidecar.scan(title_dir))
    assert [p.name for p in title_dir.iterdir() if p.name.startswith(".aniworld")] == [
        ".aniworld"
    ]


# ---------------------------------------------------------------------------
# Scanning details
# ---------------------------------------------------------------------------
def test_in_progress_and_hidden_files_are_not_episodes(title_dir):
    (title_dir / "Season 01" / "BLACK TORCH S01E004.temp_full.mkv").write_bytes(b"x")
    (title_dir / ".aniworld-thumbs").mkdir()
    (title_dir / ".aniworld-thumbs" / "BLACK TORCH S01E009.mkv").write_bytes(b"x")
    assert sorted(sidecar.scan(title_dir)["episodes"]) == [
        "S01E001",
        "S01E002",
        "S01E003",
    ]


def test_movies_set_the_type_but_have_no_episode_lines(tmp_path):
    folder = tmp_path / "Your Name (2016)"
    folder.mkdir()
    (folder / "Your Name.mkv").write_bytes(b"x")
    data = sidecar.scan(folder)
    assert data["type"] == "movies"
    assert data["episodes"] == {}
    assert (data["title"], data["year"]) == ("Your Name", "2016")


def test_a_series_with_a_bonus_film_is_both(title_dir):
    (title_dir / "BLACK TORCH - The Movie.mkv").write_bytes(b"x")
    assert sidecar.scan(title_dir)["type"] == "series,movies"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Naruto (2002-2007) [imdbid-tt0409591]", ("Naruto", "2002-2007", "tt0409591")),
        ("Naruto (2002)", ("Naruto", "2002", "")),
        ("Naruto [imdbid-tt0409591]", ("Naruto", "", "tt0409591")),
        ("Steins;Gate 0", ("Steins;Gate 0", "", "")),
        ("Fate/Zero (2011) extra", ("Fate/Zero (2011) extra", "", "")),
    ],
)
def test_folder_names_parse_like_the_default_template(name, expected):
    assert sidecar.parse_folder_name(name) == expected


def test_reconcile_keeps_titles_of_files_that_still_exist(title_dir):
    data = sidecar.scan(title_dir)
    data["episodes"]["S01E001"]["title_en"] = "Kept"
    (title_dir / "Season 01" / "BLACK TORCH S01E003.mkv").unlink()
    (title_dir / "Season 01" / "BLACK TORCH S01E004.mkv").write_bytes(b"x")
    data, changed = sidecar.reconcile(title_dir, data, sidecar.video_files(title_dir))
    assert changed
    assert sorted(data["episodes"]) == ["S01E001", "S01E002", "S01E004"]
    assert data["episodes"]["S01E001"]["title_en"] == "Kept"


# ---------------------------------------------------------------------------
# Recording a download
# ---------------------------------------------------------------------------
def test_a_finished_download_writes_the_series_identity(tmp_path):
    episode = _Episode(tmp_path)
    episode._episode_path.parent.mkdir(parents=True)
    episode._episode_path.write_bytes(b"x")

    assert sidecar.record_download(episode, episode._episode_path)
    data = sidecar.read(episode._base_folder)
    assert data["origin"] == "download"
    assert data["site"] == "aniworld"
    assert data["series_url"] == _Series.url
    assert data["poster_url"] == _Series.poster_url
    assert data["genres"] == ["Action", "Fantasy"]
    assert data["episodes"]["S01E001"] == {
        "title_de": "Die schwarze Fackel",
        "title_en": "Black Torch",
    }


def test_a_second_download_adds_its_episode_and_keeps_the_rest(tmp_path):
    first = _Episode(tmp_path)
    first._episode_path.parent.mkdir(parents=True)
    first._episode_path.write_bytes(b"x")
    sidecar.record_download(first, first._episode_path)

    second = _Episode(tmp_path, title_de="Zwei", title_en="Two")
    second.episode_number = 2
    second._episode_path = second._base_folder / "Season 01" / "BLACK TORCH S01E002.mkv"
    second._episode_path.write_bytes(b"x")
    second.series.poster_url = ""  # a page that failed to give a poster
    sidecar.record_download(second, second._episode_path)

    data = sidecar.read(first._base_folder)
    assert data["poster_url"] == _Series.poster_url, "known data is not blanked"
    assert data["episodes"]["S01E001"]["title_en"] == "Black Torch"
    assert data["episodes"]["S01E002"]["title_de"] == "Zwei"


def test_a_download_upgrades_a_scanned_sidecar(tmp_path):
    episode = _Episode(tmp_path)
    episode._episode_path.parent.mkdir(parents=True)
    episode._episode_path.write_bytes(b"x")
    sidecar.load(episode._base_folder)
    assert sidecar.read(episode._base_folder)["origin"] == "scan"
    sidecar.record_download(episode, episode._episode_path)
    assert sidecar.read(episode._base_folder)["origin"] == "download"


def test_no_title_folder_means_no_sidecar(tmp_path):
    """A flat template drops files into the download root; nothing to identify."""
    episode = _Episode(tmp_path)
    episode._base_folder = tmp_path
    episode._episode_path = tmp_path / "BLACK TORCH S01E001.mkv"
    episode._episode_path.write_bytes(b"x")
    assert sidecar.record_download(episode, episode._episode_path) is False
    assert not (tmp_path / ".aniworld").exists()


def test_a_model_whose_properties_raise_still_gets_a_sidecar(tmp_path):
    class Broken(_Episode):
        @property
        def title_de(self):
            raise RuntimeError("page gone")

        @property
        def series(self):
            raise RuntimeError("page gone")

    episode = _Episode(tmp_path)
    # swap the class after construction so the raising properties shadow the
    # attributes, the way a half-loaded page would on a real model
    episode.__class__ = Broken
    episode._episode_path.parent.mkdir(parents=True)
    episode._episode_path.write_bytes(b"x")
    assert sidecar.record_download(episode, episode._episode_path)
    data = sidecar.read(episode._base_folder)
    assert data["title"] == "BLACK TORCH"  # from the folder name
    assert data["episodes"]["S01E001"]["title_en"] == "Black Torch"


def test_record_download_never_raises(tmp_path):
    assert sidecar.record_download(object(), tmp_path / "x.mkv") is False
    assert sidecar.record_download(None, None) is False


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def test_episodes_on_disk_comes_from_the_sidecar(title_dir):
    assert sidecar.episodes_on_disk(title_dir) == {(1, 1), (1, 2), (1, 3)}


def test_find_folders_matches_by_series_url_not_name(tmp_path):
    episode = _Episode(tmp_path)
    episode._episode_path.parent.mkdir(parents=True)
    episode._episode_path.write_bytes(b"x")
    sidecar.record_download(episode, episode._episode_path)
    renamed = tmp_path / "something else entirely"
    episode._base_folder.rename(renamed)

    assert sidecar.find_folders(
        [tmp_path], "HTTP://WWW.aniworld.to/anime/stream/black-torch/"
    ) == [renamed]
    assert (
        sidecar.find_folders([tmp_path], "https://aniworld.to/anime/stream/other") == []
    )
    assert sidecar.find_folders([tmp_path / "missing"], _Series.url) == []


def test_forget_files_drops_titles_and_thumbnails(title_dir):
    sidecar.write(title_dir, sidecar.scan(title_dir))
    thumb = sidecar.thumbnail_path(title_dir, "Season 01/BLACK TORCH S01E003.mkv")
    thumb.parent.mkdir()
    thumb.write_bytes(b"\xff\xd8\xff")
    (title_dir / "Season 01" / "BLACK TORCH S01E003.mkv").unlink()

    sidecar.forget_files(title_dir, ["Season 01/BLACK TORCH S01E003.mkv"])
    assert not thumb.exists()
    assert sorted(sidecar.read(title_dir)["episodes"]) == ["S01E001", "S01E002"]


def test_thumbnail_paths_cannot_collide_across_seasons(title_dir):
    a = sidecar.thumbnail_path(title_dir, "Season 01/Ep.mkv")
    b = sidecar.thumbnail_path(title_dir, "Season 02/Ep.mkv")
    assert a != b
    assert a.parent == Path(title_dir) / ".aniworld-thumbs"


def test_remove_clears_sidecar_and_thumbs(title_dir):
    sidecar.write(title_dir, sidecar.scan(title_dir))
    thumb = sidecar.thumbnail_path(title_dir, "Season 01/BLACK TORCH S01E001.mkv")
    thumb.parent.mkdir()
    thumb.write_bytes(b"x")
    sidecar.remove(title_dir)
    assert not (title_dir / ".aniworld").exists()
    assert not thumb.parent.exists()


def test_a_folder_that_merely_holds_a_video_gets_no_scanned_sidecar(tmp_path):
    """A Downloads folder is full of directories that are not this tool's."""
    folder = tmp_path / "some-project"
    folder.mkdir()
    (folder / "demo.mp4").write_bytes(b"x")
    data = sidecar.load(folder)
    assert data["type"] == "movies"
    assert not (folder / ".aniworld").exists()


def test_language_tags_are_not_genres():
    assert sidecar.clean_genres(
        ["Action", "EngSub", "Ger", "GerSub", "Drama", "Action", "", None]
    ) == ["Action", "Drama"]
