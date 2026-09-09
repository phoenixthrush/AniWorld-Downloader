"""Library, genre and page endpoints."""

import base64

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


# ---------------------------------------------------------------------------
# Cards, streaming, thumbnails and progress
# ---------------------------------------------------------------------------
def test_cards_come_from_the_sidecar_and_write_one_on_first_visit(
    client, episode_file, downloads
):
    episode_file("Naruto", 1, 1)
    episode_file("Naruto", 1, 2)
    cards = client.get("/api/library/cards").get_json()["cards"]
    assert cards[0]["folder"] == "Naruto"
    assert cards[0]["title"] == "Naruto"
    assert cards[0]["episodes"] == 2
    assert cards[0]["categories"] == ["series"]
    assert cards[0]["watched"] == 0
    assert (downloads / "Naruto" / ".aniworld").exists()


def test_cards_use_the_title_and_poster_the_download_recorded(
    client, episode_file, downloads
):
    from aniworld import sidecar

    episode_file("BLACK TORCH (2026-2026) [imdbid-tt37532893]", 1, 1)
    folder = downloads / "BLACK TORCH (2026-2026) [imdbid-tt37532893]"
    data = sidecar.scan(folder)
    data["poster_url"] = "https://aniworld.to/img/black-torch.jpg"
    data["origin"] = "download"
    sidecar.write(folder, data)

    card = client.get("/api/library/cards").get_json()["cards"][0]
    assert card["title"] == "BLACK TORCH"
    assert card["year"] == "2026-2026"
    assert card["cover"] == {
        "kind": "poster",
        "url": "https://aniworld.to/img/black-torch.jpg",
    }


def test_cards_do_not_write_when_sidecars_are_off(
    client, episode_file, downloads, monkeypatch
):
    monkeypatch.setenv("ANIWORLD_LIBRARY_SIDECARS", "0")
    episode_file("Naruto", 1, 1)
    assert client.get("/api/library/cards").get_json()["cards"][0]["episodes"] == 1
    assert not (downloads / "Naruto" / ".aniworld").exists()


def test_a_title_lists_paths_titles_and_progress(client, episode_file, downloads):
    from aniworld import sidecar

    episode_file("Naruto", 1, 1)
    data = sidecar.scan(downloads / "Naruto")
    data["episodes"]["S01E001"] = {"title_de": "Anfang", "title_en": "Start"}
    sidecar.write(downloads / "Naruto", data)

    body = client.get("/api/library/title?folder=Naruto").get_json()
    episode = body["seasons"]["1"][0]
    assert episode["path"] == "Season 1/Naruto S01E001.mkv"
    assert (episode["title_de"], episode["title_en"]) == ("Anfang", "Start")
    assert episode["thumbnail"] is False
    assert episode["progress"] is None
    assert body["meta"]["title"] == "Naruto"


def test_opening_a_title_reconciles_a_stale_sidecar(client, episode_file, downloads):
    from aniworld import sidecar

    episode_file("Naruto", 1, 1)
    sidecar.load(downloads / "Naruto")
    episode_file("Naruto", 1, 2)
    client.get("/api/library/title?folder=Naruto")
    assert sorted(sidecar.read(downloads / "Naruto")["episodes"]) == [
        "S01E001",
        "S01E002",
    ]


def test_the_file_endpoint_streams_with_ranges(client, episode_file):
    path = episode_file("Naruto", 1, 1, size=4096)
    query = f"folder=Naruto&path=Season%201/{path.name}"
    full = client.get(f"/api/library/file?{query}")
    assert full.status_code == 200
    assert full.headers["Content-Type"] == "video/x-matroska"
    assert full.headers["Accept-Ranges"] == "bytes"
    assert len(full.data) == 4096

    part = client.get(f"/api/library/file?{query}", headers={"Range": "bytes=100-199"})
    assert part.status_code == 206
    assert part.headers["Content-Range"] == "bytes 100-199/4096"
    assert len(part.data) == 100


@pytest.mark.parametrize(
    "path",
    ["../../etc/passwd", "/etc/passwd", "Season 1/../../x.mkv", "Season 1/.hidden.mkv"],
)
def test_the_file_endpoint_refuses_to_leave_the_title(client, episode_file, path):
    episode_file("Naruto", 1, 1)
    assert client.get(f"/api/library/file?folder=Naruto&path={path}").status_code == 404


def test_the_file_endpoint_serves_only_finished_videos(client, downloads):
    folder = downloads / "Naruto" / "Season 1"
    folder.mkdir(parents=True)
    (folder / "Naruto S01E001.temp_full.mkv").write_bytes(b"x")
    (folder / "notes.txt").write_bytes(b"x")
    (downloads / "Naruto" / ".aniworld").write_text("ANIWORLD=1\n")
    for name in (
        "Season 1/Naruto S01E001.temp_full.mkv",
        "Season 1/notes.txt",
        ".aniworld",
    ):
        assert (
            client.get(f"/api/library/file?folder=Naruto&path={name}").status_code
            == 404
        )


def test_a_symlink_out_of_the_title_is_refused(
    client, episode_file, downloads, tmp_path
):
    import os

    episode_file("Naruto", 1, 1)
    outside = tmp_path / "outside.mkv"
    outside.write_bytes(b"secret")
    try:
        os.symlink(outside, downloads / "Naruto" / "Season 1" / "link.mkv")
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    assert (
        client.get(
            "/api/library/file?folder=Naruto&path=Season%201/link.mkv"
        ).status_code
        == 404
    )


_JPEG = (
    "data:image/jpeg;base64,"
    + base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9").decode()
)


def test_a_thumbnail_round_trips(client, episode_file, downloads):
    path = episode_file("Naruto", 1, 1)
    body = {"folder": "Naruto", "path": f"Season 1/{path.name}", "image": _JPEG}
    response = client.post("/api/library/thumbnail", json=body)
    assert response.get_json() == {"ok": True, "stored": True}
    assert (
        downloads / "Naruto" / ".aniworld-thumbs" / "Season 1__Naruto S01E001.jpg"
    ).exists()

    fetched = client.get(
        f"/api/library/thumbnail?folder=Naruto&path=Season%201/{path.name}"
    )
    assert fetched.status_code == 200
    assert fetched.headers["Content-Type"] == "image/jpeg"
    assert fetched.data.startswith(b"\xff\xd8\xff")

    episode = client.get("/api/library/title?folder=Naruto").get_json()["seasons"]["1"][
        0
    ]
    assert episode["thumbnail"] is True


def test_a_missing_thumbnail_is_a_404(client, episode_file):
    path = episode_file("Naruto", 1, 1)
    assert (
        client.get(
            f"/api/library/thumbnail?folder=Naruto&path=Season%201/{path.name}"
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "image,reason",
    [
        ("data:image/png;base64,iVBORw0KGgo=", "Only JPEG"),
        ("data:image/jpeg;base64,!!!", "base64"),
        ("data:image/jpeg;base64,aGVsbG8=", "not a JPEG"),
    ],
)
def test_bad_thumbnails_are_refused(client, episode_file, image, reason):
    path = episode_file("Naruto", 1, 1)
    body = {"folder": "Naruto", "path": f"Season 1/{path.name}", "image": image}
    response = client.post("/api/library/thumbnail", json=body)
    assert response.status_code == 400
    assert reason in response.get_json()["error"]


def test_an_oversized_thumbnail_is_refused(client, episode_file):
    """The payload is built here rather than passed through parametrize.

    A parameter becomes part of the test id, and every reporter writes ids
    out: a megabyte of base64 in the parameter list turns into a
    megabyte-long id in the terminal, the junit xml and the cache, which is
    slow enough on a Windows console to look like a hung test run.
    """
    from aniworld.web import library

    oversized = (
        "data:image/jpeg;base64,"
        + base64.b64encode(
            b"\xff\xd8\xff" + b"\x00" * (library.THUMBNAIL_MAX_BYTES + 1024)
        ).decode()
    )
    path = episode_file("Naruto", 1, 1)
    response = client.post(
        "/api/library/thumbnail",
        json={"folder": "Naruto", "path": f"Season 1/{path.name}", "image": oversized},
    )
    assert response.status_code == 400
    assert "too large" in response.get_json()["error"]


def test_thumbnails_are_not_stored_when_sidecars_are_off(
    client, episode_file, downloads, monkeypatch
):
    monkeypatch.setenv("ANIWORLD_LIBRARY_SIDECARS", "0")
    path = episode_file("Naruto", 1, 1)
    body = {"folder": "Naruto", "path": f"Season 1/{path.name}", "image": _JPEG}
    assert (
        client.post("/api/library/thumbnail", json=body).get_json()["stored"] is False
    )
    assert not (downloads / "Naruto" / ".aniworld-thumbs").exists()


def test_progress_is_stored_and_shows_up_on_title_and_cards(client, episode_file):
    path = episode_file("Naruto", 1, 1)
    body = {
        "folder": "Naruto",
        "path": f"Season 1/{path.name}",
        "position": 100,
        "duration": 1400,
    }
    response = client.post("/api/library/progress", json=body)
    assert response.get_json()["progress"]["watched"] is False

    episode = client.get("/api/library/title?folder=Naruto").get_json()["seasons"]["1"][
        0
    ]
    assert episode["progress"]["position"] == 100
    card = client.get("/api/library/cards").get_json()["cards"][0]
    assert card["in_progress"] == 1

    body.update(position=1350)
    assert client.post("/api/library/progress", json=body).get_json()["progress"][
        "watched"
    ]
    card = client.get("/api/library/cards").get_json()["cards"][0]
    assert (card["watched"], card["in_progress"]) == (1, 0)


def test_progress_can_be_toggled(client, episode_file):
    path = episode_file("Naruto", 1, 1)
    body = {"folder": "Naruto", "path": f"Season 1/{path.name}", "watched": True}
    assert client.post("/api/library/progress", json=body).get_json()["progress"][
        "watched"
    ]
    body["watched"] = False
    progress = client.post("/api/library/progress", json=body).get_json()["progress"]
    assert progress == {
        "position": 0.0,
        "duration": 0.0,
        "watched": False,
        "updated_at": progress["updated_at"],
    }


def test_progress_for_a_file_that_does_not_exist_is_a_404(client, episode_file):
    episode_file("Naruto", 1, 1)
    body = {"folder": "Naruto", "path": "Season 1/nope.mkv", "position": 1}
    assert client.post("/api/library/progress", json=body).status_code == 404


def test_progress_is_per_account_when_auth_is_on(auth_client, episode_file):
    from aniworld.web import db

    path = episode_file("Naruto", 1, 1)
    db.create_user("alice", "pw-alice-1", role="admin")
    db.create_user("bob", "pw-bob-1", role="user")
    body = {
        "folder": "Naruto",
        "path": f"Season 1/{path.name}",
        "position": 50,
        "duration": 100,
    }

    auth_client.post("/login", data={"username": "alice", "password": "pw-alice-1"})
    auth_client.post("/api/library/progress", json=body)
    auth_client.get("/logout")

    auth_client.post("/login", data={"username": "bob", "password": "pw-bob-1"})
    episode = auth_client.get("/api/library/title?folder=Naruto").get_json()["seasons"][
        "1"
    ][0]
    assert episode["progress"] is None


def test_continue_watching_lists_started_episodes_and_drops_deleted_files(
    client, episode_file, downloads
):
    one = episode_file("Naruto", 1, 1)
    two = episode_file("Naruto", 1, 2)
    for path in (one, two):
        client.post(
            "/api/library/progress",
            json={
                "folder": "Naruto",
                "path": f"Season 1/{path.name}",
                "position": 30,
                "duration": 100,
            },
        )
    two.unlink()
    items = client.get("/api/library/continue").get_json()["items"]
    assert [(i["folder"], i["season"], i["episode"]) for i in items] == [
        ("Naruto", 1, 1)
    ]
    assert items[0]["position"] == 30


def test_deleting_an_episode_forgets_its_progress_thumbnail_and_title(
    client, episode_file, downloads
):
    from aniworld import sidecar

    path = episode_file("Naruto", 1, 1)
    episode_file("Naruto", 1, 2)
    relative = f"Season 1/{path.name}"
    client.get("/api/library/cards")  # writes the sidecar
    client.post(
        "/api/library/thumbnail",
        json={"folder": "Naruto", "path": relative, "image": _JPEG},
    )
    client.post(
        "/api/library/progress",
        json={"folder": "Naruto", "path": relative, "position": 5, "duration": 100},
    )
    client.post(
        "/api/library/delete", json={"folder": "Naruto", "season": 1, "episode": 1}
    )

    assert not list((downloads / "Naruto" / ".aniworld-thumbs").glob("*.jpg"))
    assert sorted(sidecar.read(downloads / "Naruto")["episodes"]) == ["S01E002"]
    assert client.get("/api/library/continue").get_json()["items"] == []


def test_deleting_the_last_episode_removes_the_sidecar_too(
    client, episode_file, downloads
):
    episode_file("Naruto", 1, 1)
    client.get("/api/library/cards")
    assert (downloads / "Naruto" / ".aniworld").exists()
    client.post(
        "/api/library/delete", json={"folder": "Naruto", "season": 1, "episode": 1}
    )
    assert not (downloads / "Naruto").exists()


def test_new_endpoints_need_the_library_to_be_on(client, episode_file, monkeypatch):
    path = episode_file("Naruto", 1, 1)
    monkeypatch.setenv("ANIWORLD_ENABLE_LIBRARY", "0")
    assert client.get("/api/library/cards").status_code == 404
    assert client.get("/api/library/continue").status_code == 404
    assert (
        client.get(
            f"/api/library/file?folder=Naruto&path=Season%201/{path.name}"
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/library/progress", json={"folder": "Naruto", "path": "x"}
        ).status_code
        == 404
    )


def test_a_card_without_a_poster_falls_back_to_a_cached_frame(client, episode_file):
    path = episode_file("Naruto", 1, 1)
    client.post(
        "/api/library/thumbnail",
        json={"folder": "Naruto", "path": f"Season 1/{path.name}", "image": _JPEG},
    )
    card = client.get("/api/library/cards").get_json()["cards"][0]
    assert card["cover"] == {"kind": "thumb", "stem": "Season 1__Naruto S01E001"}
    fetched = client.get(
        f"/api/library/thumbnail?folder=Naruto&stem={card['cover']['stem']}"
    )
    assert fetched.status_code == 200
    assert (
        client.get("/api/library/thumbnail?folder=Naruto&stem=../x").status_code == 404
    )
