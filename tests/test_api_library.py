"""Library, genre and page endpoints."""

import pytest

from aniworld.web import db
from aniworld.web.views import api_media


@pytest.fixture(autouse=True)
def empty_browse_cache():
    """The browse cache lives for the process, clear it between tests."""
    api_media._browse_cache.clear()
    yield
    api_media._browse_cache.clear()


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------
def test_locations_are_listed(client, downloads):
    body = client.get("/api/library/locations").get_json()
    assert body["locations"][0]["path"] == str(downloads)


def test_titles_are_listed(client, episode_file):
    episode_file("Naruto", 1, 1)
    titles = client.get("/api/library/titles").get_json()["titles"]
    assert [t["folder"] for t in titles] == ["Naruto"]


def test_titles_of_a_custom_path(client, episode_file, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    path_id = db.add_custom_path("Other", str(other))
    episode_file("Naruto", 1, 1, base=other)
    body = client.get(f"/api/library/titles?path_id={path_id}").get_json()
    assert [t["folder"] for t in body["titles"]] == ["Naruto"]


def test_a_bad_path_id_is_a_400(client):
    assert client.get("/api/library/titles?path_id=4242").status_code == 400


def test_a_non_numeric_path_id_is_treated_as_the_default(client, episode_file):
    episode_file("Naruto", 1, 1)
    assert client.get("/api/library/titles?path_id=abc").status_code == 200


def test_one_title_is_read(client, episode_file):
    episode_file("Naruto", 1, 1)
    body = client.get("/api/library/title?folder=Naruto").get_json()
    assert body["total_episodes"] == 1
    assert body["seasons"]["1"][0]["episode"] == 1


def test_reading_needs_a_folder(client):
    assert client.get("/api/library/title").status_code == 400


def test_reading_a_missing_title_is_a_400(client):
    assert client.get("/api/library/title?folder=Nope").status_code == 400


@pytest.mark.parametrize("folder", ["../../etc", "..", "a/b"])
def test_reading_refuses_traversal(client, folder):
    assert client.get(f"/api/library/title?folder={folder}").status_code == 400


def test_a_title_can_be_deleted(client, episode_file, downloads):
    episode_file("Naruto", 1, 1)
    body = client.post("/api/library/delete", json={"folder": "Naruto"}).get_json()
    assert body == {"ok": True, "deleted": 1}
    assert not (downloads / "Naruto").exists()


def test_an_episode_can_be_deleted(client, episode_file):
    episode_file("Naruto", 1, 1)
    episode_file("Naruto", 1, 2)
    response = client.post(
        "/api/library/delete", json={"folder": "Naruto", "season": 1, "episode": 1}
    )
    assert response.get_json()["deleted"] == 1
    assert (
        client.get("/api/library/title?folder=Naruto").get_json()["total_episodes"] == 1
    )


def test_deleting_needs_a_folder(client):
    assert client.post("/api/library/delete", json={}).status_code == 400


def test_deleting_something_missing_is_a_400(client):
    assert (
        client.post("/api/library/delete", json={"folder": "Nope"}).status_code == 400
    )


def test_every_library_endpoint_closes_when_the_library_is_off(client, monkeypatch):
    monkeypatch.setenv("ANIWORLD_ENABLE_LIBRARY", "0")
    assert client.get("/api/library/locations").status_code == 404
    assert client.get("/api/library/titles").status_code == 404
    assert client.get("/api/library/title?folder=x").status_code == 404
    assert client.post("/api/library/delete", json={"folder": "x"}).status_code == 404


# ---------------------------------------------------------------------------
# Genres
# ---------------------------------------------------------------------------
@pytest.fixture
def genres(monkeypatch):
    from aniworld import search

    listing = [
        {"name": "Action", "slug": "action"},
        {"name": "Mecha", "slug": "mecha"},
    ]
    monkeypatch.setattr(api_media, "fetch_genres", lambda: listing)

    pages = {}

    def fetch(slug, page=1):
        return pages.get((slug, page))

    monkeypatch.setattr(api_media, "fetch_genre_animes", fetch)
    assert search is not None
    return pages


def test_the_genre_list_is_served(client, genres):
    body = client.get("/api/genres").get_json()
    assert [genre["slug"] for genre in body["genres"]] == ["action", "mecha"]


def test_a_genre_page_is_served_with_proxied_posters(client, genres):
    genres[("mecha", 1)] = {
        "results": [
            {
                "title": "BULLBUSTER",
                "url": "https://aniworld.to/anime/stream/bullbuster",
                "genre": "Mecha",
                "poster_url": "https://aniworld.to/p.jpg",
            }
        ],
        "has_more": True,
    }
    body = client.get("/api/genre?slug=mecha").get_json()
    assert body["page"] == 1
    assert body["has_more"] is True
    assert body["results"][0]["title"] == "BULLBUSTER"
    assert body["results"][0]["poster_url"].startswith("/api/proxy-image?url=")


def test_a_later_page_is_requested(client, genres):
    genres[("mecha", 2)] = {"results": [], "has_more": False}
    assert client.get("/api/genre?slug=mecha&page=2").get_json()["page"] == 2


@pytest.mark.parametrize("slug", ["", "nope", "../../etc/passwd", "action/../mecha"])
def test_an_unknown_genre_is_a_404(client, genres, slug):
    """The slug goes into a URL, so only known ones are allowed through."""
    response = client.get(f"/api/genre?slug={slug}")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Unknown genre"


def test_a_non_numeric_page_is_a_400(client, genres):
    assert client.get("/api/genre?slug=mecha&page=abc").status_code == 400


@pytest.mark.parametrize("page", ["0", "-5"])
def test_a_page_below_one_is_clamped(client, genres, page):
    genres[("mecha", 1)] = {"results": [], "has_more": False}
    assert client.get(f"/api/genre?slug=mecha&page={page}").get_json()["page"] == 1


def test_a_failed_genre_fetch_is_a_500(client, genres):
    assert client.get("/api/genre?slug=mecha").status_code == 500


def test_genre_pages_are_cached(client, genres, monkeypatch):
    calls = []

    def fetch(slug, page=1):
        calls.append((slug, page))
        return {"results": [], "has_more": False}

    monkeypatch.setattr(api_media, "fetch_genre_animes", fetch)
    client.get("/api/genre?slug=mecha")
    client.get("/api/genre?slug=mecha")
    assert calls == [("mecha", 1)], "the second call comes from the cache"


def test_different_pages_are_cached_separately(client, genres, monkeypatch):
    calls = []

    def fetch(slug, page=1):
        calls.append((slug, page))
        return {"results": [], "has_more": False}

    monkeypatch.setattr(api_media, "fetch_genre_animes", fetch)
    client.get("/api/genre?slug=mecha&page=1")
    client.get("/api/genre?slug=mecha&page=2")
    assert calls == [("mecha", 1), ("mecha", 2)]


# ---------------------------------------------------------------------------
# Browse rows
# ---------------------------------------------------------------------------
def test_a_browse_row_is_served_from_the_cache(client):
    """The row views hold their fetch function directly, so the cache is
    seeded here rather than stubbing the fetch."""
    import time

    api_media._browse_cache["new_animes"] = (
        time.time(),
        [{"title": "Naruto", "url": "https://x", "poster_url": "https://x/p.jpg"}],
    )
    body = client.get("/api/new-animes").get_json()
    assert body["results"][0]["title"] == "Naruto"
    assert body["results"][0]["poster_url"].startswith("/api/proxy-image?url=")


def test_a_browse_row_that_fails_is_a_500(client, monkeypatch):
    monkeypatch.setattr(api_media, "_cached", lambda key, fetch: None)
    assert client.get("/api/new-animes").status_code == 500


def test_a_failed_fetch_is_not_cached(monkeypatch):
    """A blip must not blank the row for the next hour."""
    calls = []

    def flaky():
        calls.append(1)
        raise RuntimeError("upstream down")

    assert api_media._cached("row", flaky) is None
    assert api_media._cached("row", flaky) is None
    assert len(calls) == 2, "it is tried again rather than served from a cached failure"


def test_a_good_fetch_is_cached(monkeypatch):
    calls = []

    def once():
        calls.append(1)
        return [{"title": "Naruto"}]

    assert api_media._cached("row", once) == [{"title": "Naruto"}]
    assert api_media._cached("row", once) == [{"title": "Naruto"}]
    assert len(calls) == 1


def test_a_stale_cache_entry_is_refetched(monkeypatch):
    import time

    calls = []

    def fetch():
        calls.append(1)
        return ["fresh"]

    api_media._browse_cache["row"] = (time.time() - api_media.BROWSE_TTL - 1, ["stale"])
    assert api_media._cached("row", fetch) == ["fresh"]
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def test_the_home_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"AniWorld" in response.data


def test_the_settings_page_renders(client):
    assert client.get("/settings").status_code == 200


def test_the_library_page_renders(client):
    assert client.get("/library").status_code == 200


def test_the_autosync_page_is_hidden_until_enabled(client, monkeypatch):
    assert client.get("/autosync").status_code == 404
    monkeypatch.setenv("ANIWORLD_ENABLE_AUTOSYNC", "1")
    assert client.get("/autosync").status_code == 200


def test_hanime_is_hidden_from_the_home_page_by_default(client):
    assert b'data-site="htv"' not in client.get("/").data


def test_hanime_appears_once_enabled(client, monkeypatch):
    monkeypatch.setenv("ANIWORLD_ENABLE_HTV", "1")
    assert b'data-site="htv"' in client.get("/").data


def test_the_genre_bar_is_on_the_home_page(client):
    assert b'id="genreList"' in client.get("/").data


def test_the_favicon_is_served(client):
    assert client.get("/favicon.ico").status_code == 200


def test_an_unknown_page_is_a_404(client):
    assert client.get("/nope").status_code == 404
