"""Where a download ends up: defaults, custom paths and language separation."""

from pathlib import Path

import pytest

from aniworld.web import db, paths


# ---------------------------------------------------------------------------
# Expanding configured paths
# ---------------------------------------------------------------------------
def test_an_absolute_path_is_kept(tmp_path):
    assert paths.expand(str(tmp_path)) == tmp_path


def test_a_relative_path_lands_below_home():
    assert paths.expand("Videos/Anime") == Path.home() / "Videos/Anime"


def test_a_tilde_is_expanded():
    assert paths.expand("~/Anime") == Path.home() / "Anime"


def test_the_default_path_comes_from_the_setting(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(tmp_path / "media"))
    assert paths.default_download_path() == tmp_path / "media"


def test_an_unset_path_falls_back_to_downloads(monkeypatch):
    monkeypatch.delenv("ANIWORLD_DOWNLOAD_PATH", raising=False)
    assert paths.default_download_path() == Path.home() / "Downloads"


def test_a_blank_path_falls_back_too(monkeypatch):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", "   ")
    assert paths.default_download_path() == Path.home() / "Downloads"


# ---------------------------------------------------------------------------
# Language folders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "language,folder",
    [
        ("German Dub", "german-dub"),
        ("German Sub", "german-sub"),
        ("English Dub", "english-dub"),
        ("English Sub", "english-sub"),
    ],
)
def test_known_languages_map_to_their_folder(language, folder):
    assert paths.lang_folder_for(language) == folder


def test_an_unknown_language_is_slugified():
    assert paths.lang_folder_for("Japanese Dub") == "japanese-dub"


def test_separation_is_off_by_default():
    assert paths.lang_separation_enabled() is False


# ---------------------------------------------------------------------------
# Picking the target
# ---------------------------------------------------------------------------
def test_without_separation_the_downloader_decides():
    """None means 'use the naming template below the default root'."""
    assert paths.target_path("German Dub") is None


def test_separation_adds_the_language_folder(monkeypatch, downloads):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    assert paths.target_path("German Sub") == str(downloads / "german-sub")


def test_a_custom_path_is_used_as_is(tmp_path):
    path_id = db.add_custom_path("Movies", str(tmp_path / "movies"))
    assert paths.target_path("German Dub", path_id) == str(tmp_path / "movies")


def test_a_custom_path_also_gets_language_folders(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    path_id = db.add_custom_path("Movies", str(tmp_path / "movies"))
    assert paths.target_path("English Dub", path_id) == str(
        tmp_path / "movies" / "english-dub"
    )


def test_a_deleted_custom_path_falls_back_to_the_default(tmp_path, downloads):
    """The naming template is applied on top either way, so this matches
    what an item with no custom path at all would get."""
    path_id = db.add_custom_path("Movies", str(tmp_path / "movies"))
    db.remove_custom_path(path_id)
    assert paths.target_path("German Dub", path_id) == str(downloads)
    assert paths.base_for(path_id) == downloads


def test_a_deleted_custom_path_falls_back_with_separation_on(monkeypatch, downloads):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    path_id = db.add_custom_path("Movies", "/tmp/gone")
    db.remove_custom_path(path_id)
    assert paths.target_path("German Dub", path_id) == str(downloads / "german-dub")


def test_base_for_prefers_the_custom_path(tmp_path, downloads):
    path_id = db.add_custom_path("Movies", str(tmp_path / "movies"))
    assert paths.base_for(path_id) == tmp_path / "movies"
    assert paths.base_for(None) == downloads


def test_custom_path_base_of_a_missing_id_is_none():
    assert paths.custom_path_base(4242) is None
    assert paths.custom_path_base(None) is None


def test_a_relative_custom_path_lands_below_home():
    path_id = db.add_custom_path("Rel", "Videos/Anime")
    assert paths.custom_path_base(path_id) == Path.home() / "Videos/Anime"


# ---------------------------------------------------------------------------
# Roots and scanning
# ---------------------------------------------------------------------------
def test_the_default_root_is_always_listed(downloads):
    roots = paths.download_roots()
    assert roots[0] == ("Default", None, downloads)


def test_custom_paths_are_listed_after_it(tmp_path):
    path_id = db.add_custom_path("Movies", str(tmp_path / "movies"))
    assert paths.download_roots()[1] == ("Movies", path_id, tmp_path / "movies")


def test_custom_roots_are_sorted_by_name(tmp_path):
    db.add_custom_path("Zebra", str(tmp_path / "z"))
    db.add_custom_path("apple", str(tmp_path / "a"))
    assert [name for name, _, _ in paths.download_roots()] == [
        "Default",
        "apple",
        "Zebra",
    ]


def test_without_separation_scanning_uses_the_roots(downloads, tmp_path):
    db.add_custom_path("Movies", str(tmp_path / "movies"))
    assert paths.scan_bases() == [downloads, tmp_path / "movies"]


def test_with_separation_scanning_uses_the_language_folders(monkeypatch, downloads):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    bases = paths.scan_bases()
    assert len(bases) == len(paths.ALL_LANG_FOLDERS)
    assert downloads / "german-dub" in bases


def test_separation_multiplies_every_root(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    db.add_custom_path("Movies", str(tmp_path / "movies"))
    assert len(paths.scan_bases()) == 2 * len(paths.ALL_LANG_FOLDERS)
