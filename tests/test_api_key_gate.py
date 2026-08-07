"""What an API key is allowed to do, checked against the real app."""

import pytest

from aniworld.web import apikeys, db


def headers(raw):
    return {apikeys.HEADER: raw}


def bearer(raw):
    return {"Authorization": f"Bearer {raw}"}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def test_a_key_identifies_itself(client, api_key):
    raw, _ = api_key(scope="write", name="ci key")
    body = client.get("/api/ping", headers=headers(raw)).get_json()
    assert body["method"] == "api_key"
    assert body["name"] == "ci key"
    assert body["scope"] == "write"


def test_a_key_works_as_a_bearer_token(client, api_key):
    raw, _ = api_key()
    assert (
        client.get("/api/ping", headers=bearer(raw)).get_json()["method"] == "api_key"
    )


def test_an_unknown_key_is_rejected(client):
    response = client.get("/api/ping", headers=headers("awd_made-up"))
    assert response.status_code == 401
    assert "Invalid" in response.get_json()["error"]


def test_an_expired_key_is_rejected(client, api_key):
    raw, key_id = api_key(expires_days=1)
    with db.session() as conn:
        conn.execute(
            "UPDATE api_keys SET expires_at = datetime('now', '-1 hour') WHERE id = ?",
            (key_id,),
        )
    assert client.get("/api/queue", headers=headers(raw)).status_code == 401


def test_a_deleted_key_stops_working_at_once(client, api_key):
    raw, key_id = api_key()
    assert client.get("/api/queue", headers=headers(raw)).status_code == 200
    db.delete_api_key(key_id)
    assert client.get("/api/queue", headers=headers(raw)).status_code == 401


def test_using_a_key_records_the_time(client, api_key):
    raw, key_id = api_key()
    assert db.list_api_keys()[0]["last_used_at"] is None
    client.get("/api/ping", headers=headers(raw))
    used = next(k for k in db.list_api_keys() if k["id"] == key_id)
    assert used["last_used_at"] is not None


def test_pages_ignore_keys_entirely(client, api_key):
    """The gate only guards /api/, a key is not a way into the HTML pages."""
    raw, _ = api_key()
    assert client.get("/", headers=headers(raw)).status_code == 200


def test_no_key_means_no_key_identity(client):
    assert client.get("/api/ping").get_json()["method"] == "open"


# ---------------------------------------------------------------------------
# Read scope
# ---------------------------------------------------------------------------
def test_a_read_key_can_read(client, api_key):
    raw, _ = api_key(scope="read")
    assert client.get("/api/queue", headers=headers(raw)).status_code == 200


def test_a_read_key_cannot_write(client, api_key, queue_item):
    raw, _ = api_key(scope="read")
    queue_id = queue_item()
    response = client.post(f"/api/queue/{queue_id}/cancel", headers=headers(raw))
    assert response.status_code == 403
    assert "read only" in response.get_json()["error"]
    assert db.get_queue_item(queue_id)["status"] == "queued"


def test_a_read_key_cannot_delete(client, api_key, queue_item):
    raw, _ = api_key(scope="read")
    queue_id = queue_item()
    assert (
        client.delete(f"/api/queue/{queue_id}", headers=headers(raw)).status_code == 403
    )
    assert db.get_queue_item(queue_id) is not None


def test_a_read_key_cannot_start_a_download(client, api_key):
    raw, _ = api_key(scope="read")
    response = client.post(
        "/api/download", json={"episodes": ["x"]}, headers=headers(raw)
    )
    assert response.status_code == 403
    assert db.get_queue() == []


def test_search_stays_open_to_read_keys(client, api_key, monkeypatch):
    """Search is a POST only because the query goes in the body."""
    from aniworld.web import sitesearch

    monkeypatch.setattr(sitesearch, "search", lambda site, keyword: [])
    raw, _ = api_key(scope="read")
    response = client.post(
        "/api/search", json={"keyword": "naruto"}, headers=headers(raw)
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Write scope
# ---------------------------------------------------------------------------
def test_a_write_key_can_write(client, api_key, queue_item):
    raw, _ = api_key(scope="write")
    queue_id = queue_item()
    assert (
        client.post(f"/api/queue/{queue_id}/cancel", headers=headers(raw)).status_code
        == 200
    )
    assert db.get_queue_item(queue_id)["status"] == "cancelled"


def test_a_write_key_can_queue_a_download(client, api_key):
    raw, _ = api_key(scope="write")
    response = client.post(
        "/api/download",
        json={"title": "Naruto", "episodes": ["https://x/ep1"]},
        headers=headers(raw),
    )
    assert response.status_code == 200
    assert db.get_queue_item(response.get_json()["queue_id"])["title"] == "Naruto"


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/settings"),
        ("put", "/api/settings"),
        ("post", "/api/custom-paths"),
        ("get", "/api/autosync/status"),
    ],
)
def test_a_write_key_cannot_touch_admin_endpoints(client, api_key, method, path):
    raw, _ = api_key(scope="write")
    call = getattr(client, method)
    response = call(path, json={}, headers=headers(raw))
    assert response.status_code == 403
    assert "full access" in response.get_json()["error"]


# ---------------------------------------------------------------------------
# Admin scope
# ---------------------------------------------------------------------------
def test_an_admin_key_can_read_settings(client, api_key):
    raw, _ = api_key(scope="admin")
    assert client.get("/api/settings", headers=headers(raw)).status_code == 200


def test_an_admin_key_can_change_settings(client, api_key):
    raw, _ = api_key(scope="admin")
    response = client.put(
        "/api/settings", json={"enable_htv": True}, headers=headers(raw)
    )
    assert response.status_code == 200

    from aniworld.web import settings_store

    assert settings_store.htv_enabled() is True


def test_an_admin_key_can_add_a_custom_path(client, api_key, tmp_path):
    raw, _ = api_key(scope="admin")
    response = client.post(
        "/api/custom-paths",
        json={"name": "Movies", "path": str(tmp_path)},
        headers=headers(raw),
    )
    assert response.status_code == 200
    assert len(db.get_custom_paths()) == 1


# ---------------------------------------------------------------------------
# Keys cannot manage keys
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("scope", apikeys.SCOPES)
def test_no_key_may_list_keys(client, api_key, scope):
    raw, _ = api_key(scope=scope)
    response = client.get("/api/keys", headers=headers(raw))
    assert response.status_code == 403
    assert "cannot manage API keys" in response.get_json()["error"]


def test_no_key_may_mint_another_key(client, api_key):
    """Otherwise a leaked key could quietly upgrade itself."""
    raw, _ = api_key(scope="admin")
    response = client.post(
        "/api/keys", json={"name": "sneaky", "scope": "admin"}, headers=headers(raw)
    )
    assert response.status_code == 403
    assert len(db.list_api_keys()) == 1


def test_no_key_may_delete_another_key(client, api_key):
    raw, _ = api_key(scope="admin")
    _, victim = api_key(name="victim")
    assert client.delete(f"/api/keys/{victim}", headers=headers(raw)).status_code == 403
    assert len(db.list_api_keys()) == 2


# ---------------------------------------------------------------------------
# Keys and the session layer
# ---------------------------------------------------------------------------
def test_a_key_gets_past_the_login_wall(auth_client, api_key):
    db.create_user("root", "hunter2hunter2", role="admin")
    raw, _ = api_key(scope="write")
    assert auth_client.get("/api/queue").status_code == 401
    assert auth_client.get("/api/queue", headers=headers(raw)).status_code == 200


def test_an_admin_key_gets_past_the_admin_wall(auth_client, api_key):
    db.create_user("root", "hunter2hunter2", role="admin")
    raw, _ = api_key(scope="admin")
    assert auth_client.get("/api/settings").status_code == 401
    assert auth_client.get("/api/settings", headers=headers(raw)).status_code == 200


def test_a_key_skips_the_first_run_setup_redirect(auth_client, api_key):
    """No admin exists yet, but a key holder is not a browser to redirect."""
    raw, _ = api_key(scope="write")
    assert auth_client.get("/api/queue", headers=headers(raw)).status_code == 200
