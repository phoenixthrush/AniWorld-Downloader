"""Poster handling, site keys and detecting what is already downloaded."""

from types import SimpleNamespace

import pytest

from aniworld.models.mangafire_to import series as mangafire
from aniworld.web import db, media


# ---------------------------------------------------------------------------
# Posters
# ---------------------------------------------------------------------------
def test_a_plain_url_is_kept():
    assert media.normalize_image("https://x/poster.jpg") == "https://x/poster.jpg"


def test_the_largest_size_wins():
    sizes = {"small": "s.jpg", "large": "l.jpg", "medium": "m.jpg"}
    assert media.normalize_image(sizes) == "l.jpg"


def test_other_dict_keys_are_tried():
    assert media.normalize_image({"src": "s.jpg"}) == "s.jpg"
    assert media.normalize_image({"whatever": "w.jpg"}) == "w.jpg"


def test_an_object_with_a_url_attribute_works():
    class Poster:
        url = "https://x/o.jpg"

    assert media.normalize_image(Poster()) == "https://x/o.jpg"


@pytest.mark.parametrize("empty", [None, "", {}, 0])
def test_nothing_becomes_an_empty_string(empty):
    assert media.normalize_image(empty) == ""


def test_posters_are_routed_through_the_proxy():
    proxied = media.proxy_image("https://x/p.jpg?size=big&v=2")
    assert proxied.startswith("/api/proxy-image?url=")
    assert "https%3A%2F%2Fx%2Fp.jpg%3Fsize%3Dbig%26v%3D2" in proxied


def test_an_empty_poster_is_not_proxied():
    assert media.proxy_image("") == ""
    assert media.proxy_image(None) == ""


def test_relative_posters_are_made_absolute():
    absolute = media.absolute_poster("/img/p.jpg", "https://serienstream.to/serie/x")
    assert absolute == "https://serienstream.to/img/p.jpg"


def test_absolute_posters_are_left_alone():
    url = "https://cdn.example/p.jpg"
    assert media.absolute_poster(url, "https://serienstream.to/serie/x") == url


# ---------------------------------------------------------------------------
# Site keys
# ---------------------------------------------------------------------------
def test_every_site_key_has_a_label():
    assert set(media.SITE_KEYS) == set(media.SITE_LABELS)


def test_known_sites_are_kept_in_order():
    assert media.normalize_default_sites(["aniworld", "sto"]) == "aniworld,sto"


def test_unknown_sites_are_dropped():
    assert media.normalize_default_sites(["aniworld", "myspace"]) == "aniworld"


def test_duplicates_are_dropped():
    assert media.normalize_default_sites(["sto", "sto"]) == "sto"


def test_case_and_whitespace_do_not_matter():
    assert media.normalize_default_sites([" AniWorld ", "STO"]) == "aniworld,sto"


def test_a_csv_string_works_too():
    assert media.normalize_default_sites("aniworld,kinox") == "aniworld,kinox"


@pytest.mark.parametrize("empty", [None, "", [], "   "])
def test_nothing_gives_an_empty_csv(empty):
    assert media.normalize_default_sites(empty) == ""


# ---------------------------------------------------------------------------
# Episode detection
# ---------------------------------------------------------------------------
class FakeSeries:
    def __init__(self, title):
        self.title_cleaned = title


def test_nothing_downloaded_yet():
    assert media.downloaded_episodes(FakeSeries("Naruto")) == set()


def test_a_downloaded_episode_is_found(episode_file):
    episode_file("Naruto", 1, 5)
    assert media.downloaded_episodes(FakeSeries("Naruto")) == {(1, 5)}


def test_several_seasons_are_found(episode_file):
    episode_file("Naruto", 1, 1)
    episode_file("Naruto", 1, 2)
    episode_file("Naruto", 2, 1)
    assert media.downloaded_episodes(FakeSeries("Naruto")) == {(1, 1), (1, 2), (2, 1)}


def test_matching_is_case_insensitive(episode_file):
    episode_file("naruto", 1, 1)
    assert media.downloaded_episodes(FakeSeries("Naruto")) == {(1, 1)}


def test_a_folder_with_a_year_suffix_still_matches(episode_file):
    episode_file("Naruto (2002)", 1, 1)
    assert media.downloaded_episodes(FakeSeries("Naruto")) == {(1, 1)}


def test_another_series_is_not_counted(episode_file):
    episode_file("Bleach", 1, 1)
    assert media.downloaded_episodes(FakeSeries("Naruto")) == set()


def test_files_without_an_episode_marker_are_ignored(downloads):
    folder = downloads / "Naruto"
    folder.mkdir()
    (folder / "poster.jpg").write_bytes(b"x")
    assert media.downloaded_episodes(FakeSeries("Naruto")) == set()


def test_a_series_without_a_title_finds_nothing():
    assert media.downloaded_episodes(FakeSeries("")) == set()


def test_three_digit_episode_numbers_work(episode_file):
    episode_file("One Piece", 1, 999)
    assert media.downloaded_episodes(FakeSeries("One Piece")) == {(1, 999)}


def test_custom_paths_are_scanned_too(episode_file, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    db.add_custom_path("Other", str(other))
    episode_file("Naruto", 1, 1, base=other)
    assert media.downloaded_episodes(FakeSeries("Naruto")) == {(1, 1)}


def test_language_folders_are_scanned_when_separation_is_on(
    monkeypatch, episode_file, downloads
):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    episode_file("Naruto", 1, 1, base=downloads / "german-dub")
    assert media.downloaded_episodes(FakeSeries("Naruto")) == {(1, 1)}


def test_turning_separation_on_hides_titles_in_the_old_layout(
    monkeypatch, episode_file, downloads
):
    """Files downloaded before the switch sit one level up and stop matching."""
    episode_file("Naruto", 1, 1)
    assert media.downloaded_episodes(FakeSeries("Naruto")) == {(1, 1)}
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    assert media.downloaded_episodes(FakeSeries("Naruto")) == set()


# ---------------------------------------------------------------------------
# Folder names for the downloaded badge
# ---------------------------------------------------------------------------
def test_folder_names_are_listed(downloads):
    (downloads / "Naruto").mkdir()
    (downloads / "Bleach").mkdir()
    assert media.downloaded_folder_names() == ["Bleach", "Naruto"]


def test_loose_files_are_not_listed(downloads):
    (downloads / "note.txt").write_text("hi")
    assert media.downloaded_folder_names() == []


def test_a_missing_root_is_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(tmp_path / "nope"))
    assert media.downloaded_folder_names() == []


def test_folders_from_every_root_are_merged(downloads, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    db.add_custom_path("Other", str(other))
    (downloads / "Naruto").mkdir()
    (other / "Bleach").mkdir()
    assert media.downloaded_folder_names() == ["Bleach", "Naruto"]


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
def test_the_mangafire_format_defaults_to_jpg():
    assert media.mangafire_format() == "jpg"


def test_the_mangafire_format_can_be_changed(monkeypatch):
    monkeypatch.setenv("MANGAFIRE_FORMAT", "pdf")
    assert media.mangafire_format() == "pdf"


def test_mangafire_loads_every_chapter_page(monkeypatch):
    calls = []
    pages = iter(
        [
            {"items": [{"id": 1}]},
            {"items": [{"id": 2}]},
            {"items": [{"id": 2}]},
        ]
    )

    def get(url):
        calls.append(url)
        return SimpleNamespace(json=lambda: next(pages))

    monkeypatch.setattr(mangafire, "_get", get)
    found = mangafire.MangaFireToSeries("https://mangafire.to/title/test-title")

    assert found.chapters_data["items"] == [{"id": 1}, {"id": 2}]
    assert [url.split("page=")[1].split("&")[0] for url in calls] == ["1", "2", "3"]


def test_mangafire_retries_after_a_captcha(monkeypatch):
    responses = iter(
        [
            SimpleNamespace(text="challenge", status_code=403),
            SimpleNamespace(
                text='{"items": []}',
                status_code=200,
                raise_for_status=lambda: None,
            ),
        ]
    )
    solved = []

    monkeypatch.setattr(
        mangafire.GLOBAL_SESSION, "get", lambda *_args, **_kwargs: next(responses)
    )
    monkeypatch.setattr(mangafire, "sign_url", lambda url: f"{url}?signed")
    monkeypatch.setattr(
        mangafire, "is_captcha_page", lambda _body, status: status == 403
    )
    monkeypatch.setattr(mangafire, "solve_captcha", solved.append)

    response = mangafire._get("https://mangafire.to/api/top-titles")

    assert response.status_code == 200
    assert solved == ["https://mangafire.to/api/top-titles?signed"]


def test_only_implemented_providers_are_offered():
    assert media.WORKING_PROVIDERS, "at least one provider must be usable"
    assert "VOE" in media.WORKING_PROVIDERS


# ---------------------------------------------------------------------------
# Site tabs that can be switched off
# ---------------------------------------------------------------------------
def test_burningseries_and_kinox_are_hidden_by_default(client):
    """Both need a captcha nobody can solve for you, so they are opt in."""
    body = client.get("/").get_data(as_text=True)
    assert 'data-site="burningseries"' not in body
    assert 'data-site="kinox"' not in body
    assert 'data-row="burningseries_series"' not in body
    assert 'data-row="kinox_movies"' not in body
    # the sites nobody gated are still there
    assert 'data-site="aniworld"' in body
    assert 'data-site="filmpalast"' in body


def test_the_flags_bring_the_tabs_back(client, monkeypatch):
    monkeypatch.setenv("ANIWORLD_ENABLE_BURNINGSERIES", "1")
    monkeypatch.setenv("ANIWORLD_ENABLE_KINOX", "1")
    body = client.get("/").get_data(as_text=True)
    assert 'data-site="burningseries"' in body
    assert 'data-site="kinox"' in body
    assert 'data-row="burningseries_series"' in body
    assert 'data-row="kinox_movies"' in body


def test_one_flag_does_not_turn_on_the_other(client, monkeypatch):
    monkeypatch.setenv("ANIWORLD_ENABLE_KINOX", "1")
    body = client.get("/").get_data(as_text=True)
    assert 'data-site="kinox"' in body
    assert 'data-site="burningseries"' not in body


def test_hiding_a_tab_leaves_its_neighbours_alone(client):
    """The browse rows sit in one list, so a bad {% if %} would swallow them."""
    body = client.get("/").get_data(as_text=True)
    for row in (
        "popular_movies",
        "filmpalast_movies",
        "cineby_movies",
        "mangafire_trending",
    ):
        assert f'data-row="{row}"' in body, row
