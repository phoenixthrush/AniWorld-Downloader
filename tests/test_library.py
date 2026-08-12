"""Library browsing and deleting, including the traversal guards."""

import os

import pytest

from aniworld.web import db, library


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
def test_the_default_root_is_a_location(downloads):
    result = library.list_locations()
    assert result["lang_separation"] is False
    assert result["locations"][0]["label"] == "Default"
    assert result["locations"][0]["path"] == str(downloads)
    assert result["locations"][0]["exists"] is True


def test_a_missing_root_is_reported_rather_than_hidden(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(tmp_path / "nope"))
    assert library.list_locations()["locations"][0]["exists"] is False


def test_custom_paths_show_up_as_locations(tmp_path):
    (tmp_path / "movies").mkdir()
    path_id = db.add_custom_path("Movies", str(tmp_path / "movies"))
    labels = {loc["label"]: loc for loc in library.list_locations()["locations"]}
    assert labels["Movies"]["custom_path_id"] == path_id


def test_with_separation_only_existing_language_folders_are_listed(
    monkeypatch, downloads
):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    (downloads / "german-dub").mkdir()
    locations = library.list_locations()["locations"]
    assert [loc["lang_folder"] for loc in locations] == ["german-dub"]


def test_with_separation_and_nothing_on_disk_there_is_nothing_to_browse(
    monkeypatch, downloads
):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    assert library.list_locations()["locations"] == []


# ---------------------------------------------------------------------------
# Titles
# ---------------------------------------------------------------------------
def test_titles_are_listed_alphabetically(downloads):
    for name in ("Zebra", "apple", "Mango"):
        (downloads / name).mkdir()
    assert library.list_titles() == ["apple", "Mango", "Zebra"]


def test_an_empty_root_lists_nothing(downloads):
    assert library.list_titles() == []


def test_a_missing_root_lists_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(tmp_path / "nope"))
    assert library.list_titles() == []


def test_hidden_folders_are_skipped(downloads):
    (downloads / ".cache").mkdir()
    (downloads / "Naruto").mkdir()
    assert library.list_titles() == ["Naruto"]


def test_loose_files_are_skipped(downloads):
    (downloads / "readme.txt").write_text("hi")
    assert library.list_titles() == []


def test_language_folders_are_not_listed_as_titles(downloads):
    (downloads / "german-dub").mkdir()
    (downloads / "Naruto").mkdir()
    assert library.list_titles() == ["Naruto"]


def test_titles_inside_a_language_folder_are_listed(downloads):
    (downloads / "german-dub" / "Naruto").mkdir(parents=True)
    assert library.list_titles(lang_folder="german-dub") == ["Naruto"]


def test_titles_of_a_custom_path(tmp_path):
    (tmp_path / "movies" / "Dune").mkdir(parents=True)
    path_id = db.add_custom_path("Movies", str(tmp_path / "movies"))
    assert library.list_titles(path_id) == ["Dune"]


def test_an_unknown_custom_path_is_an_error():
    with pytest.raises(library.LibraryError):
        library.list_titles(4242)


def test_an_unknown_language_folder_is_an_error():
    with pytest.raises(library.LibraryError) as exc:
        library.list_titles(lang_folder="klingon-dub")
    assert "Invalid language folder" in str(exc.value)


# ---------------------------------------------------------------------------
# Reading one title
# ---------------------------------------------------------------------------
def test_episodes_are_grouped_by_season(episode_file):
    episode_file("Naruto", 1, 1)
    episode_file("Naruto", 1, 2)
    episode_file("Naruto", 2, 1)
    result = library.read_title("Naruto")
    assert sorted(result["seasons"]) == ["1", "2"]
    assert [e["episode"] for e in result["seasons"]["1"]] == [1, 2]
    assert result["total_episodes"] == 3


def test_sizes_are_summed(episode_file):
    episode_file("Naruto", 1, 1, size=100)
    episode_file("Naruto", 1, 2, size=200)
    assert library.read_title("Naruto")["total_size"] == 300


def test_episodes_come_back_in_order(episode_file):
    for number in (3, 1, 2):
        episode_file("Naruto", 1, number)
    episodes = [e["episode"] for e in library.read_title("Naruto")["seasons"]["1"]]
    assert episodes == [1, 2, 3]


def test_non_video_files_are_listed_but_not_counted(episode_file):
    episode_file("Naruto", 1, 1)
    episode_file("Naruto", 1, 2, suffix=".srt")
    result = library.read_title("Naruto")
    assert len(result["seasons"]["1"]) == 2
    assert result["total_episodes"] == 1, "subtitles are not an episode"


def test_partial_downloads_are_hidden(episode_file, downloads):
    episode_file("Naruto", 1, 1)
    partial = downloads / "Naruto" / "Season 1" / ".temp_full S01E002.mkv"
    partial.write_bytes(b"x")
    assert library.read_title("Naruto")["total_episodes"] == 1


def test_files_without_an_episode_marker_are_ignored(episode_file, downloads):
    episode_file("Naruto", 1, 1)
    (downloads / "Naruto" / "poster.jpg").write_bytes(b"x")
    assert len(library.read_title("Naruto")["seasons"]["1"]) == 1


def test_an_empty_title_folder_reads_as_empty(downloads):
    (downloads / "Naruto").mkdir()
    result = library.read_title("Naruto")
    assert result["seasons"] == {}
    assert result["total_episodes"] == 0


def test_reading_a_missing_title_is_an_error():
    with pytest.raises(library.LibraryError):
        library.read_title("Nope")


@pytest.mark.parametrize(
    "folder", ["../secrets", "..", "a/b", "a\\b", "", "sub/../../etc"]
)
def test_traversal_attempts_are_refused(folder):
    with pytest.raises(library.LibraryError):
        library.read_title(folder)


@pytest.mark.skipif(os.name == "nt", reason="symlinks need extra rights on Windows")
def test_a_symlink_out_of_the_library_is_refused(downloads, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (downloads / "escape").symlink_to(outside)
    with pytest.raises(library.LibraryError):
        library.read_title("escape")


# ---------------------------------------------------------------------------
# Deleting
# ---------------------------------------------------------------------------
def test_deleting_a_whole_title(episode_file, downloads):
    episode_file("Naruto", 1, 1)
    assert library.delete("Naruto") == 1
    assert not (downloads / "Naruto").exists()


def test_deleting_one_season_keeps_the_others(episode_file, downloads):
    episode_file("Naruto", 1, 1)
    episode_file("Naruto", 2, 1)
    assert library.delete("Naruto", season=1) == 1
    assert not (downloads / "Naruto" / "Season 1").exists()
    assert (downloads / "Naruto" / "Season 2").exists()


def test_deleting_a_season_removes_all_of_its_episodes(episode_file):
    for number in (1, 2, 3):
        episode_file("Naruto", 1, number)
    assert library.delete("Naruto", season=1) == 3


def test_deleting_a_single_episode(episode_file, downloads):
    kept = episode_file("Naruto", 1, 1)
    episode_file("Naruto", 1, 2)
    assert library.delete("Naruto", season=1, episode=2) == 1
    assert kept.exists()


def test_deleting_an_episode_does_not_hit_its_neighbours(episode_file):
    """S01E01 must not match S01E010."""
    episode_file("Naruto", 1, 1)
    episode_file("Naruto", 1, 10)
    assert library.delete("Naruto", season=1, episode=1) == 1
    remaining = [e["episode"] for e in library.read_title("Naruto")["seasons"]["1"]]
    assert remaining == [10]


def test_deleting_an_episode_takes_its_subtitles_too(episode_file):
    episode_file("Naruto", 1, 1)
    episode_file("Naruto", 1, 1, suffix=".srt")
    assert library.delete("Naruto", season=1, episode=1) == 2


def test_empty_folders_are_cleaned_up(episode_file, downloads):
    episode_file("Naruto", 1, 1)
    library.delete("Naruto", season=1, episode=1)
    assert not (downloads / "Naruto").exists()


def test_deleting_something_that_is_not_there_is_an_error(episode_file):
    episode_file("Naruto", 1, 1)
    with pytest.raises(library.LibraryError):
        library.delete("Naruto", season=9)


def test_deleting_a_missing_title_is_an_error():
    with pytest.raises(library.LibraryError):
        library.delete("Nope")


@pytest.mark.parametrize("folder", ["../downloads", "..", "a/b", ""])
def test_delete_refuses_traversal(folder):
    with pytest.raises(library.LibraryError):
        library.delete(folder)


def test_deleting_from_a_custom_path(episode_file, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    path_id = db.add_custom_path("Other", str(other))
    episode_file("Naruto", 1, 1, base=other)
    assert library.delete("Naruto", custom_path_id=path_id) == 1
    assert not (other / "Naruto").exists()


def test_the_same_title_in_another_root_is_untouched(episode_file, tmp_path, downloads):
    other = tmp_path / "other"
    other.mkdir()
    path_id = db.add_custom_path("Other", str(other))
    episode_file("Naruto", 1, 1)
    episode_file("Naruto", 1, 1, base=other)

    library.delete("Naruto", custom_path_id=path_id)
    assert (downloads / "Naruto").exists()


def test_custom_path_labels():
    path_id = db.add_custom_path("Movies", "/tmp/movies")
    assert library.custom_path_labels() == {path_id: "Movies"}


# ---------------------------------------------------------------------------
# Movie detection (files with no SxxExx pattern)
# ---------------------------------------------------------------------------
def test_a_video_file_without_an_episode_marker_is_grouped_as_a_movie(downloads):
    (downloads / "Your Name").mkdir()
    (downloads / "Your Name" / "Your Name.mkv").write_bytes(b"x" * 500)
    result = library.read_title("Your Name")
    assert [e["file"] for e in result["seasons"]["movie"]] == ["Your Name.mkv"]
    assert result["total_episodes"] == 1


def test_movie_files_are_numbered_in_stable_alphabetical_order(downloads):
    folder = downloads / "Trilogy"
    folder.mkdir()
    (folder / "Part 2.mkv").write_bytes(b"x")
    (folder / "Part 1.mkv").write_bytes(b"x")
    movies = library.read_title("Trilogy")["seasons"]["movie"]
    assert [m["file"] for m in movies] == ["Part 1.mkv", "Part 2.mkv"]
    assert [m["episode"] for m in movies] == [1, 2]


def test_a_non_video_file_without_an_episode_marker_still_does_not_appear(downloads):
    (downloads / "Naruto").mkdir()
    (downloads / "Naruto" / "poster.jpg").write_bytes(b"x")
    result = library.read_title("Naruto")
    assert result["seasons"] == {}


def test_a_title_with_both_seasons_and_a_movie_keeps_them_separate(
    episode_file, downloads
):
    episode_file("Naruto", 1, 1)
    (downloads / "Naruto" / "Naruto The Movie.mkv").write_bytes(b"x")
    result = library.read_title("Naruto")
    assert sorted(result["seasons"]) == ["1", "movie"]


def test_deleting_a_single_movie_file(downloads):
    folder = downloads / "Trilogy"
    folder.mkdir()
    (folder / "Part 1.mkv").write_bytes(b"x")
    (folder / "Part 2.mkv").write_bytes(b"x")
    assert library.delete("Trilogy", season="movie", episode=1) == 1
    remaining = [m["file"] for m in library.read_title("Trilogy")["seasons"]["movie"]]
    assert remaining == ["Part 2.mkv"]


def test_deleting_all_movies_of_a_title(downloads):
    folder = downloads / "Trilogy"
    folder.mkdir()
    (folder / "Part 1.mkv").write_bytes(b"x")
    (folder / "Part 2.mkv").write_bytes(b"x")
    assert library.delete("Trilogy", season="movie") == 2
    assert not folder.exists(), "the now-empty title folder is pruned, like any other"


def test_deleting_an_out_of_range_movie_index_is_an_error(downloads):
    folder = downloads / "Trilogy"
    folder.mkdir()
    (folder / "Part 1.mkv").write_bytes(b"x")
    with pytest.raises(library.LibraryError):
        library.delete("Trilogy", season="movie", episode=5)


def test_a_temp_file_with_the_marker_mid_name_is_not_shown_as_a_movie(downloads):
    folder = downloads / "Some Film"
    folder.mkdir()
    (folder / "Some Film (2026).temp_full.mkv").write_bytes(b"x")
    result = library.read_title("Some Film")
    assert result["seasons"] == {}


# ---------------------------------------------------------------------------
# Series/movies classification
# ---------------------------------------------------------------------------
def test_a_series_only_folder_is_classified_as_series(episode_file):
    episode_file("Naruto", 1, 1)
    titles = library.list_titles_with_meta()
    assert titles == [{"folder": "Naruto", "categories": ["series"]}]


def test_a_movie_only_folder_is_classified_as_movies(downloads):
    folder = downloads / "Your Name"
    folder.mkdir()
    (folder / "Your Name.mkv").write_bytes(b"x")
    titles = library.list_titles_with_meta()
    assert titles == [{"folder": "Your Name", "categories": ["movies"]}]


def test_a_folder_with_both_is_classified_as_both(episode_file, downloads):
    episode_file("Naruto", 1, 1)
    (downloads / "Naruto" / "Naruto The Movie.mkv").write_bytes(b"x")
    titles = library.list_titles_with_meta()
    assert titles == [{"folder": "Naruto", "categories": ["series", "movies"]}]


def test_an_in_progress_movie_download_is_still_classified_as_a_movie(downloads):
    folder = downloads / "Some Film"
    folder.mkdir()
    (folder / "Some Film (2026).temp_full.mkv").write_bytes(b"x")
    titles = library.list_titles_with_meta()
    assert titles == [{"folder": "Some Film", "categories": ["movies"]}]


def test_an_empty_folder_falls_back_to_series(downloads):
    (downloads / "Empty Show").mkdir()
    titles = library.list_titles_with_meta()
    assert titles == [{"folder": "Empty Show", "categories": ["series"]}]


# ---------------------------------------------------------------------------
# Temp-file infix handling
# ---------------------------------------------------------------------------
def test_a_temp_episode_with_the_marker_mid_name_is_not_shown(downloads):
    folder = downloads / "Naruto" / "Season 1"
    folder.mkdir(parents=True)
    (folder / "Naruto S01E001.temp_full.mkv").write_bytes(b"x")
    result = library.read_title("Naruto")
    assert result["seasons"] == {}
