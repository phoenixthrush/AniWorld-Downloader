"""End to end journeys through the app.

These are the awkward ones: something already exists, a setting changes halfway
through, or two features disagree about the same state.
"""

import json

import pytest

from aniworld.web import db, library, media, paths, settings_store, worker


@pytest.fixture
def fake_download(monkeypatch):
    """Run a queued item to completion, writing the files it claims to fetch."""

    def run(queue_id, files=(), behaviour=None):
        def build(url, extra, item, selected_path):
            base = paths.expand(selected_path) if selected_path else None

            class Episode:
                def download(self):
                    if isinstance(behaviour, Exception):
                        raise behaviour
                    for relative in files:
                        target = (base or paths.default_download_path()) / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(b"video")

            return object(), Episode()

        monkeypatch.setattr(worker, "_build_episode", build)
        monkeypatch.setattr(worker, "_notify_discord", lambda item: None)
        db.set_queue_status(queue_id, "running")
        worker._process(db.get_queue_item(queue_id))

    return run


# ---------------------------------------------------------------------------
# Downloading something that is already there
# ---------------------------------------------------------------------------
def test_queueing_the_same_series_twice_is_allowed_but_visible(client, queue_item):
    """The UI allows it, autosync uses the flag to stay out of the way."""
    url = "https://aniworld.to/anime/stream/naruto"
    client.post("/api/download", json={"episodes": ["ep1"], "series_url": url})
    assert db.is_series_queued_or_running(url) is True

    client.post("/api/download", json={"episodes": ["ep1"], "series_url": url})
    assert len(db.get_queue()) == 2


def test_a_finished_download_no_longer_blocks_the_series(client):
    url = "https://aniworld.to/anime/stream/naruto"
    queue_id = client.post(
        "/api/download", json={"episodes": ["ep1"], "series_url": url}
    ).get_json()["queue_id"]
    db.set_queue_status(queue_id, "completed")
    assert db.is_series_queued_or_running(url) is False


def test_downloading_over_an_existing_episode_is_detected_first(episode_file):
    class Series:
        title_cleaned = "Naruto"

    episode_file("Naruto", 1, 1)
    assert (1, 1) in media.downloaded_episodes(Series())
    assert (1, 2) not in media.downloaded_episodes(Series())


def test_a_custom_path_name_can_only_be_used_once(client, tmp_path):
    first = client.post(
        "/api/custom-paths", json={"name": "Movies", "path": str(tmp_path)}
    )
    second = client.post(
        "/api/custom-paths", json={"name": "Movies", "path": "/elsewhere"}
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert db.get_custom_paths()[0]["path"] == str(tmp_path)


def test_excluding_the_same_series_twice_is_harmless():
    url = "https://aniworld.to/anime/stream/naruto"
    db.add_autosync_exclusion(url, "Naruto")
    db.add_autosync_exclusion(url, "Naruto again")
    assert len(db.get_autosync_exclusions()) == 1


def test_creating_two_keys_with_the_same_name_is_fine(client):
    first = client.post("/api/keys", json={"name": "ci"}).get_json()
    second = client.post("/api/keys", json={"name": "ci"}).get_json()
    assert first["key"] != second["key"]
    assert len(db.list_api_keys()) == 2


# ---------------------------------------------------------------------------
# Changing a setting around a download
# ---------------------------------------------------------------------------
def test_downloads_keep_working_after_the_path_changes(
    client, fake_download, tmp_path, downloads
):
    first = client.post("/api/download", json={"episodes": ["ep1"]}).get_json()[
        "queue_id"
    ]
    fake_download(first, files=["Naruto/Season 1/Naruto S01E001.mkv"])
    assert (downloads / "Naruto/Season 1/Naruto S01E001.mkv").exists()

    new_root = tmp_path / "new-root"
    client.put("/api/settings", json={"download_path": str(new_root)})

    second = client.post("/api/download", json={"episodes": ["ep2"]}).get_json()[
        "queue_id"
    ]
    fake_download(second, files=["Bleach/Season 1/Bleach S01E001.mkv"])
    assert (new_root / "Bleach/Season 1/Bleach S01E001.mkv").exists()
    assert db.get_queue_item(second)["status"] == "completed"


def test_the_library_follows_the_download_path(
    client, episode_file, tmp_path, downloads
):
    episode_file("Naruto", 1, 1)
    assert library.list_titles() == ["Naruto"]

    other = tmp_path / "other"
    (other / "Bleach").mkdir(parents=True)
    client.put("/api/settings", json={"download_path": str(other)})
    assert library.list_titles() == ["Bleach"], "the old root is no longer browsed"


def test_turning_on_separation_changes_where_the_next_download_goes(
    client, fake_download, downloads
):
    first = client.post("/api/download", json={"episodes": ["ep1"]}).get_json()[
        "queue_id"
    ]
    fake_download(first, files=["Naruto/Naruto S01E001.mkv"])

    client.put("/api/settings", json={"lang_separation": True})
    second = client.post(
        "/api/download", json={"episodes": ["ep2"], "language": "German Sub"}
    ).get_json()["queue_id"]
    fake_download(second, files=["Bleach/Bleach S01E001.mkv"])

    assert (downloads / "Naruto").exists()
    assert (downloads / "german-sub" / "Bleach").exists()


def test_older_downloads_are_not_browsable_until_separation_goes_back_off(
    client, episode_file, downloads
):
    """Titles saved in the old flat layout sit above the language folders, so
    with separation on there is no location that lists them."""
    episode_file("Naruto", 1, 1)
    assert library.list_locations()["locations"][0]["path"] == str(downloads)

    client.put("/api/settings", json={"lang_separation": True})
    assert library.list_locations()["locations"] == []

    client.put("/api/settings", json={"lang_separation": False})
    assert library.list_titles() == ["Naruto"]


def test_changing_the_format_does_not_disturb_finished_downloads(client, episode_file):
    episode_file("Naruto", 1, 1, suffix=".mkv")
    client.put("/api/settings", json={"output_format": "mp4"})

    result = library.read_title("Naruto")
    assert result["total_episodes"] == 1, "the old mkv is still a video"
    assert settings_store.output_format() == "mp4"


def test_a_queued_item_uses_the_provider_it_was_queued_with(client):
    """Changing the fallback order later must not rewrite queued items."""
    from aniworld.web.media import WORKING_PROVIDERS

    queue_id = client.post(
        "/api/download", json={"episodes": ["ep1"], "provider": "Vidoza"}
    ).get_json()["queue_id"]
    client.put(
        "/api/settings",
        json={"provider_fallback_order": list(reversed(WORKING_PROVIDERS))},
    )
    assert db.get_queue_item(queue_id)["provider"] == "Vidoza"


def test_disabling_english_sub_does_not_touch_what_is_already_queued(client):
    queue_id = client.post(
        "/api/download", json={"episodes": ["ep1"], "language": "English Sub"}
    ).get_json()["queue_id"]
    client.put("/api/settings", json={"disable_english_sub": True})

    assert db.get_queue_item(queue_id)["language"] == "English Sub"
    assert db.get_next_queued()["id"] == queue_id
    assert (
        client.post(
            "/api/download", json={"episodes": ["ep2"], "language": "English Sub"}
        ).status_code
        == 403
    )


def test_turning_the_library_off_closes_its_pages_and_endpoints(client):
    assert client.get("/library").status_code == 200
    assert client.get("/api/library/locations").status_code == 200

    client.put("/api/settings", json={"enable_library": False})
    assert client.get("/library").status_code == 404
    assert client.get("/api/library/locations").status_code == 404


def test_turning_autosync_off_closes_its_page(client):
    client.put("/api/settings", json={"enable_autosync": True})
    assert client.get("/autosync").status_code == 200
    client.put("/api/settings", json={"enable_autosync": False})
    assert client.get("/autosync").status_code == 404


def test_the_ui_language_reaches_the_rendered_page(client):
    client.put("/api/settings", json={"ui_language": "de"})
    assert b'"de"' in client.get("/").data or b"de" in client.get("/").data


# ---------------------------------------------------------------------------
# Deleting things that are in use
# ---------------------------------------------------------------------------
def test_deleting_a_custom_path_does_not_delete_the_files(
    client, episode_file, tmp_path
):
    other = tmp_path / "other"
    other.mkdir()
    path_id = db.add_custom_path("Other", str(other))
    episode_file("Naruto", 1, 1, base=other)

    client.delete(f"/api/custom-paths/{path_id}")
    assert (other / "Naruto").exists(), "only the shortcut is gone"


def test_a_queued_item_survives_its_custom_path_being_deleted(
    client, fake_download, tmp_path, downloads
):
    path_id = db.add_custom_path("Other", str(tmp_path / "other"))
    queue_id = client.post(
        "/api/download", json={"episodes": ["ep1"], "custom_path_id": path_id}
    ).get_json()["queue_id"]

    client.delete(f"/api/custom-paths/{path_id}")
    fake_download(queue_id, files=["Naruto/Naruto S01E001.mkv"])

    assert db.get_queue_item(queue_id)["status"] == "completed"
    assert (downloads / "Naruto/Naruto S01E001.mkv").exists()


def test_deleting_a_title_leaves_its_queue_history(client, episode_file, queue_item):
    queue_id = queue_item("Naruto")
    db.set_queue_status(queue_id, "completed")
    episode_file("Naruto", 1, 1)

    client.post("/api/library/delete", json={"folder": "Naruto"})
    assert db.get_queue_item(queue_id) is not None
    assert library.list_titles() == []


def test_a_title_can_be_downloaded_again_after_being_deleted(
    client, episode_file, fake_download, downloads
):
    episode_file("Naruto", 1, 1)
    client.post("/api/library/delete", json={"folder": "Naruto"})
    assert not (downloads / "Naruto").exists()

    queue_id = client.post("/api/download", json={"episodes": ["ep1"]}).get_json()[
        "queue_id"
    ]
    fake_download(queue_id, files=["Naruto/Season 1/Naruto S01E001.mkv"])
    assert (downloads / "Naruto/Season 1/Naruto S01E001.mkv").exists()


@pytest.fixture
def signed_in_admin(auth_client):
    auth_client.post(
        "/setup",
        data={
            "username": "root",
            "password": "hunter2hunter2",
            "confirm": "hunter2hunter2",
        },
    )
    return auth_client


def test_an_admin_cannot_delete_their_own_account(signed_in_admin):
    """Belt and braces on top of the last admin rule in the database."""
    admin_id = db.list_users()[0]["id"]
    response = signed_in_admin.delete(f"/admin/api/users/{admin_id}")
    assert response.status_code == 400
    assert "own account" in response.get_json()["error"]
    assert db.has_any_admin() is True


def test_an_admin_can_remove_someone_else(signed_in_admin):
    created = signed_in_admin.post(
        "/admin/api/users",
        json={"username": "second", "password": "hunter2hunter2", "role": "admin"},
    ).get_json()
    assert (
        signed_in_admin.delete(f"/admin/api/users/{created['id']}").status_code == 200
    )
    assert [u["username"] for u in db.list_users()] == ["root"]


def test_a_duplicate_username_is_a_conflict(signed_in_admin):
    response = signed_in_admin.post(
        "/admin/api/users", json={"username": "root", "password": "hunter2hunter2"}
    )
    assert response.status_code == 409
    assert len(db.list_users()) == 1


def test_a_new_user_can_sign_in_straight_away(signed_in_admin, auth_app):
    signed_in_admin.post(
        "/admin/api/users", json={"username": "bob", "password": "hunter2hunter2"}
    )
    other = auth_app.test_client()
    other.post("/login", data={"username": "bob", "password": "hunter2hunter2"})
    assert other.get("/api/queue").status_code == 200
    assert other.get("/api/settings").status_code == 403, "bob is not an admin"


def test_promoting_a_user_grants_admin_pages(signed_in_admin, auth_app):
    created = signed_in_admin.post(
        "/admin/api/users", json={"username": "bob", "password": "hunter2hunter2"}
    ).get_json()
    other = auth_app.test_client()
    other.post("/login", data={"username": "bob", "password": "hunter2hunter2"})
    assert other.get("/api/settings").status_code == 403

    signed_in_admin.put(
        f"/admin/api/users/{created['id']}/role", json={"role": "admin"}
    )
    with other.session_transaction() as session:
        session["_role_checked"] = 0
    assert other.get("/api/settings").status_code == 200


# ---------------------------------------------------------------------------
# The queue as a whole
# ---------------------------------------------------------------------------
def test_a_full_pass_through_the_queue(client, fake_download, downloads):
    """Queue three, run them, and check the list ends up consistent."""
    ids = [
        client.post(
            "/api/download", json={"title": f"Show {n}", "episodes": [f"ep{n}"]}
        ).get_json()["queue_id"]
        for n in range(3)
    ]
    for queue_id in ids:
        fake_download(queue_id, files=[f"Show/Show S01E00{queue_id}.mkv"])

    items = client.get("/api/queue").get_json()["items"]
    assert [i["status"] for i in items] == ["completed"] * 3
    assert all(i["duration_seconds"] is not None for i in items)

    client.delete("/api/queue/completed")
    assert client.get("/api/queue").get_json()["items"] == []


def test_cancel_then_retry_then_finish(client, fake_download):
    queue_id = client.post("/api/download", json={"episodes": ["ep1"]}).get_json()[
        "queue_id"
    ]
    client.post(f"/api/queue/{queue_id}/cancel")
    assert db.get_queue_item(queue_id)["status"] == "cancelled"

    client.post(f"/api/queue/{queue_id}/retry")
    assert db.get_queue_item(queue_id)["status"] == "queued"

    fake_download(queue_id)
    assert db.get_queue_item(queue_id)["status"] == "completed"


def test_reordering_decides_what_downloads_first(client):
    first = client.post(
        "/api/download", json={"title": "A", "episodes": ["a"]}
    ).get_json()["queue_id"]
    second = client.post(
        "/api/download", json={"title": "B", "episodes": ["b"]}
    ).get_json()["queue_id"]
    client.post(f"/api/queue/{second}/move", json={"direction": "up"})
    assert worker._claim_next()["id"] == second
    assert db.get_queue_item(first)["status"] == "queued"


def test_a_crash_mid_download_is_recovered_on_restart(client, queue_item):
    queue_id = queue_item()
    db.set_queue_status(queue_id, "running")
    db.update_queue_progress(queue_id, 2, "https://x/ep3")

    db.reset_stale_running()  # what ensure_started() does on boot

    item = db.get_queue_item(queue_id)
    assert item["status"] == "queued"
    assert worker._claim_next()["id"] == queue_id


def test_errors_survive_a_reload_of_the_queue(client, fake_download):
    queue_id = client.post("/api/download", json={"episodes": ["ep1"]}).get_json()[
        "queue_id"
    ]
    fake_download(queue_id, behaviour=RuntimeError("provider exploded"))

    item = client.get("/api/queue").get_json()["items"][0]
    assert item["status"] == "failed"
    assert "provider exploded" in json.loads(item["errors"])[0]["error"]


# ---------------------------------------------------------------------------
# API keys alongside everything else
# ---------------------------------------------------------------------------
def test_a_key_queues_a_download_the_ui_can_then_see(client, api_key):
    raw, _ = api_key(scope="write")
    client.post(
        "/api/download",
        json={"title": "Naruto", "episodes": ["ep1"]},
        headers={"X-API-Key": raw},
    )
    assert [i["title"] for i in client.get("/api/queue").get_json()["items"]] == [
        "Naruto"
    ]


def test_a_key_created_in_the_ui_works_straight_away(client):
    raw = client.post("/api/keys", json={"name": "ci", "scope": "write"}).get_json()[
        "key"
    ]
    response = client.post(
        "/api/download", json={"episodes": ["ep1"]}, headers={"X-API-Key": raw}
    )
    assert response.status_code == 200


def test_revoking_a_key_stops_a_running_integration(client, api_key):
    raw, key_id = api_key(scope="write")
    assert (
        client.post(
            "/api/download", json={"episodes": ["ep1"]}, headers={"X-API-Key": raw}
        ).status_code
        == 200
    )

    client.delete(f"/api/keys/{key_id}")
    assert (
        client.post(
            "/api/download", json={"episodes": ["ep2"]}, headers={"X-API-Key": raw}
        ).status_code
        == 401
    )
    assert len(db.get_queue()) == 1


def test_an_admin_key_can_change_a_setting_that_the_next_download_uses(
    client, api_key, fake_download, downloads
):
    raw, _ = api_key(scope="admin")
    client.put(
        "/api/settings", json={"lang_separation": True}, headers={"X-API-Key": raw}
    )
    queue_id = client.post(
        "/api/download", json={"episodes": ["ep1"], "language": "German Dub"}
    ).get_json()["queue_id"]
    fake_download(queue_id, files=["Naruto/Naruto S01E001.mkv"])
    assert (downloads / "german-dub" / "Naruto").exists()
