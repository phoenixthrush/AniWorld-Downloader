"""Settings, custom path and API key HTTP endpoints."""

import pytest

from aniworld.web import db, settings_store


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_settings_are_readable(client):
    body = client.get("/api/settings").get_json()
    assert body["ui_language"] == "en"
    assert "available_providers" in body


def test_a_setting_can_be_changed(client):
    assert client.put("/api/settings", json={"ui_language": "de"}).status_code == 200
    assert settings_store.ui_language() == "de"


def test_the_change_shows_up_on_the_next_read(client):
    client.put("/api/settings", json={"enable_htv": True})
    assert client.get("/api/settings").get_json()["enable_htv"] is True


def test_an_invalid_setting_is_a_400_with_a_reason(client):
    response = client.put("/api/settings", json={"ui_language": "klingon"})
    assert response.status_code == 400
    assert "klingon" in response.get_json()["error"]


def test_a_rejected_change_leaves_the_old_value(client):
    client.put("/api/settings", json={"ui_language": "de"})
    client.put("/api/settings", json={"ui_language": "klingon"})
    assert settings_store.ui_language() == "de"


def test_the_autosync_schedule_can_be_saved_as_a_sentence(client):
    response = client.put(
        "/api/settings", json={"autosync_cron": "every monday, friday at 10pm"}
    )
    assert response.status_code == 200
    assert client.get("/api/settings").get_json()["autosync_cron"] == "0 22 * * 1,5"


def test_an_impossible_autosync_schedule_is_a_400_with_a_reason(client):
    response = client.put("/api/settings", json={"autosync_cron": "every blursday"})
    assert response.status_code == 400
    assert "blursday" in response.get_json()["error"]


def test_a_too_short_autosync_interval_is_a_400(client):
    response = client.put("/api/settings", json={"autosync_interval": "10s"})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# The live reading under the schedule field
# ---------------------------------------------------------------------------
def test_fixed_times_can_be_previewed_before_they_are_saved(client):
    body = client.post(
        "/api/settings/schedule-preview",
        json={"autosync_cron": "every monday and friday at 10pm"},
    ).get_json()
    assert body["cron"] == "0 22 * * 1,5"
    assert body["description"] == "On Monday and Friday at 22:00"


def test_an_interval_can_be_previewed_before_it_is_saved(client):
    body = client.post(
        "/api/settings/schedule-preview", json={"autosync_interval": "90m"}
    ).get_json()
    assert body["interval"] == "90m"
    assert body["description"] == "Every 90 minutes"


def test_previewing_changes_nothing(client):
    """The page asks on every keystroke, long before anyone presses Save."""
    client.post("/api/settings/schedule-preview", json={"autosync_cron": "0 22 * * 1"})
    client.post("/api/settings/schedule-preview", json={"autosync_interval": "90m"})
    assert settings_store.autosync_cron() == "0 3 * * *", "still the default"
    assert settings_store.autosync_interval() == "24h", "still the default"


def test_a_preview_of_nonsense_is_a_400_with_the_reason(client):
    response = client.post(
        "/api/settings/schedule-preview", json={"autosync_cron": "every blursday"}
    )
    assert response.status_code == 400
    assert "blursday" in response.get_json()["error"]


def test_a_preview_of_an_impossible_interval_is_a_400(client):
    response = client.post(
        "/api/settings/schedule-preview", json={"autosync_interval": "10s"}
    )
    assert response.status_code == 400
    assert "at least" in response.get_json()["error"]


def test_an_empty_preview_is_a_400(client):
    assert client.post("/api/settings/schedule-preview", json={}).status_code == 400


def test_previewing_is_admin_only_like_the_rest_of_the_settings():
    from aniworld.web.views import ADMIN_ENDPOINTS

    assert "api.preview_schedule" in ADMIN_ENDPOINTS


def test_a_preview_is_described_in_the_ui_language(client, monkeypatch):
    monkeypatch.setenv("ANIWORLD_UI_LANGUAGE", "de")
    body = client.post(
        "/api/settings/schedule-preview", json={"autosync_cron": "0 22 * * 1"}
    ).get_json()
    assert body["description"] == "Jeden Montag um 22:00"


def test_the_provider_order_can_be_saved(client):
    from aniworld.web.media import WORKING_PROVIDERS

    order = list(reversed(WORKING_PROVIDERS))
    assert (
        client.put("/api/settings", json={"provider_fallback_order": order}).status_code
        == 200
    )
    assert client.get("/api/settings").get_json()["provider_fallback_order"] == order


def test_an_invalid_provider_order_is_a_400(client):
    response = client.put("/api/settings", json={"provider_fallback_order": ["Nope"]})
    assert response.status_code == 400


def test_the_public_ip_endpoint_reports_failures(client, monkeypatch):
    monkeypatch.setattr(
        settings_store, "fetch_public_ip", lambda: (_ for _ in ()).throw(RuntimeError())
    )
    response = client.get("/api/settings/public-ip")
    assert response.status_code == 502
    assert response.get_json()["ok"] is False


def test_the_public_ip_endpoint_passes_a_result_through(client, monkeypatch):
    monkeypatch.setattr(
        settings_store, "fetch_public_ip", lambda: {"ip": "1.2.3.4", "source": "x"}
    )
    body = client.get("/api/settings/public-ip").get_json()
    assert body == {"ok": True, "ip": "1.2.3.4", "source": "x"}


def test_discord_status_never_raises(client):
    assert client.get("/api/discord/status").status_code == 200


# ---------------------------------------------------------------------------
# Custom paths
# ---------------------------------------------------------------------------
def test_a_custom_path_can_be_added(client, tmp_path):
    response = client.post(
        "/api/custom-paths", json={"name": "Movies", "path": str(tmp_path)}
    )
    assert response.status_code == 200
    assert db.get_custom_path(response.get_json()["id"])["name"] == "Movies"


def test_custom_paths_are_listed(client, tmp_path):
    db.add_custom_path("Movies", str(tmp_path))
    assert [p["name"] for p in client.get("/api/custom-paths").get_json()["paths"]] == [
        "Movies"
    ]


@pytest.mark.parametrize(
    "payload",
    [{"name": "", "path": "/tmp"}, {"name": "x", "path": ""}, {}, {"name": "  "}],
)
def test_a_custom_path_needs_a_name_and_a_path(client, payload):
    assert client.post("/api/custom-paths", json=payload).status_code == 400


def test_a_duplicate_name_is_a_conflict(client, tmp_path):
    client.post("/api/custom-paths", json={"name": "Movies", "path": str(tmp_path)})
    response = client.post(
        "/api/custom-paths", json={"name": "Movies", "path": str(tmp_path)}
    )
    assert response.status_code == 409
    assert len(db.get_custom_paths()) == 1


def test_default_sites_are_cleaned_up(client, tmp_path):
    response = client.post(
        "/api/custom-paths",
        json={
            "name": "Movies",
            "path": str(tmp_path),
            "default_sites": ["megakino", "myspace"],
        },
    )
    assert db.get_custom_path(response.get_json()["id"])["default_sites"] == "megakino"


def test_a_custom_path_can_be_renamed(client, tmp_path):
    path_id = db.add_custom_path("Movies", str(tmp_path))
    assert (
        client.put(f"/api/custom-paths/{path_id}", json={"name": "Films"}).status_code
        == 200
    )
    assert db.get_custom_path(path_id)["name"] == "Films"


def test_updating_one_field_leaves_the_others(client, tmp_path):
    path_id = db.add_custom_path("Movies", str(tmp_path), "megakino")
    client.put(f"/api/custom-paths/{path_id}", json={"name": "Films"})
    entry = db.get_custom_path(path_id)
    assert entry["path"] == str(tmp_path)
    assert entry["default_sites"] == "megakino"


@pytest.mark.parametrize("blank", ["", "   "])
def test_the_path_cannot_be_blanked(client, tmp_path, blank):
    """An empty path resolves to the home directory, so downloads would land
    loose in it. Creating one blank is refused, editing one must be too."""
    path_id = db.add_custom_path("Movies", str(tmp_path))
    response = client.put(f"/api/custom-paths/{path_id}", json={"path": blank})
    assert response.status_code == 400
    assert "path" in response.get_json()["error"]
    assert db.get_custom_path(path_id)["path"] == str(tmp_path)


@pytest.mark.parametrize("blank", ["", "   "])
def test_the_name_cannot_be_blanked(client, tmp_path, blank):
    path_id = db.add_custom_path("Movies", str(tmp_path))
    response = client.put(f"/api/custom-paths/{path_id}", json={"name": blank})
    assert response.status_code == 400
    assert db.get_custom_path(path_id)["name"] == "Movies"


def test_a_blanked_field_does_not_apply_the_others(client, tmp_path):
    path_id = db.add_custom_path("Movies", str(tmp_path), "megakino")
    client.put(
        f"/api/custom-paths/{path_id}",
        json={"name": "Films", "path": "", "default_sites": []},
    )
    entry = db.get_custom_path(path_id)
    assert entry["name"] == "Movies"
    assert entry["default_sites"] == "megakino"


def test_a_blanked_path_can_never_resolve_to_home(client, tmp_path):
    from pathlib import Path

    from aniworld.web import paths

    path_id = db.add_custom_path("Movies", str(tmp_path))
    client.put(f"/api/custom-paths/{path_id}", json={"path": ""})
    assert paths.base_for(path_id) != Path.home()
    assert paths.base_for(path_id) == tmp_path


def test_default_sites_can_be_cleared(client, tmp_path):
    path_id = db.add_custom_path("Movies", str(tmp_path), "megakino")
    client.put(f"/api/custom-paths/{path_id}", json={"default_sites": []})
    assert db.get_custom_path(path_id)["default_sites"] == ""


def test_a_custom_path_can_be_deleted(client, tmp_path):
    path_id = db.add_custom_path("Movies", str(tmp_path))
    assert client.delete(f"/api/custom-paths/{path_id}").status_code == 200
    assert db.get_custom_path(path_id) is None


def test_deleting_a_custom_path_twice_is_harmless(client, tmp_path):
    path_id = db.add_custom_path("Movies", str(tmp_path))
    client.delete(f"/api/custom-paths/{path_id}")
    assert client.delete(f"/api/custom-paths/{path_id}").status_code == 200


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------
def test_a_key_is_returned_exactly_once(client):
    response = client.post("/api/keys", json={"name": "ci", "scope": "read"})
    assert response.status_code == 200
    raw = response.get_json()["key"]
    assert raw.startswith("awd_")

    listed = client.get("/api/keys").get_json()["keys"]
    assert raw not in str(listed), "the plain key must never be listed again"


def test_a_created_key_actually_works(client):
    raw = client.post("/api/keys", json={"name": "ci"}).get_json()["key"]
    assert client.get("/api/ping", headers={"X-API-Key": raw}).get_json()["scope"] == (
        "write"
    )


def test_the_default_scope_is_write(client):
    assert client.post("/api/keys", json={"name": "ci"}).get_json()["scope"] == "write"


def test_a_key_needs_a_name(client):
    assert client.post("/api/keys", json={"scope": "read"}).status_code == 400
    assert client.post("/api/keys", json={"name": "   "}).status_code == 400


def test_a_very_long_name_is_refused(client):
    assert client.post("/api/keys", json={"name": "x" * 65}).status_code == 400


def test_an_unknown_scope_is_refused(client):
    response = client.post("/api/keys", json={"name": "ci", "scope": "root"})
    assert response.status_code == 400
    assert "read, write or admin" in response.get_json()["error"]


@pytest.mark.parametrize("raw", [None, "", 0, "0"])
def test_no_expiry_means_it_never_expires(client, raw):
    key_id = client.post(
        "/api/keys", json={"name": "ci", "expires_days": raw}
    ).get_json()["id"]
    listed = next(k for k in db.list_api_keys() if k["id"] == key_id)
    assert listed["expires_at"] is None


def test_an_expiry_is_stored(client):
    client.post("/api/keys", json={"name": "ci", "expires_days": 30})
    assert db.list_api_keys()[0]["expires_at"] is not None


@pytest.mark.parametrize("days", [0.5, -1, 99999, "soon"])
def test_a_nonsense_expiry_is_refused(client, days):
    response = client.post("/api/keys", json={"name": "ci", "expires_days": days})
    assert response.status_code == 400
    assert db.list_api_keys() == []


def test_keys_can_be_listed_with_their_scopes(client):
    client.post("/api/keys", json={"name": "ci", "scope": "admin"})
    body = client.get("/api/keys").get_json()
    assert body["keys"][0]["name"] == "ci"
    assert body["scopes"] == ["read", "write", "admin"]


def test_a_key_can_be_deleted(client):
    key_id = client.post("/api/keys", json={"name": "ci"}).get_json()["id"]
    assert client.delete(f"/api/keys/{key_id}").status_code == 200
    assert db.list_api_keys() == []


def test_deleting_a_missing_key_is_a_404(client):
    assert client.delete("/api/keys/4242").status_code == 404


def test_a_deleted_key_stops_authenticating(client):
    created = client.post("/api/keys", json={"name": "ci"}).get_json()
    client.delete(f"/api/keys/{created['id']}")
    assert (
        client.get("/api/ping", headers={"X-API-Key": created["key"]}).status_code
        == 401
    )


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------
def test_ping_reports_an_open_install(client):
    body = client.get("/api/ping").get_json()
    assert body["ok"] is True
    assert body["auth_enabled"] is False
    assert body["method"] == "open"
    assert body["version"]


def test_ping_needs_a_login_when_auth_is_on(auth_client):
    db.create_user("root", "hunter2hunter2", role="admin")
    response = auth_client.get("/api/ping")
    assert response.status_code == 401
    assert response.get_json()["error"] == "authentication required"


def test_ping_reports_a_signed_in_admin(auth_client):
    db.create_user("root", "hunter2hunter2", role="admin")
    auth_client.post("/login", data={"username": "root", "password": "hunter2hunter2"})
    body = auth_client.get("/api/ping").get_json()
    assert body["auth_enabled"] is True
    assert body["method"] == "session"
    assert body["name"] == "root"
    assert body["scope"] == "admin"


def test_ping_reports_a_signed_in_user(auth_client):
    db.create_user("root", "hunter2hunter2", role="admin")
    db.create_user("bob", "hunter2hunter2")
    auth_client.post("/login", data={"username": "bob", "password": "hunter2hunter2"})
    body = auth_client.get("/api/ping").get_json()
    assert body["scope"] == "write", "a plain user is not an admin"


# ---------------------------------------------------------------------------
# Exporting the running settings
#
# Settings live in the environment and reset on a restart on purpose. This is
# the way out for anyone who wants one to stick.
# ---------------------------------------------------------------------------
def test_the_settings_can_be_downloaded_as_an_env_file(client):
    response = client.get("/api/settings/env")
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    assert "aniworld.env" in response.headers["Content-Disposition"]
    assert response.mimetype == "text/plain"


def test_the_export_holds_what_is_running(client):
    client.put(
        "/api/settings",
        json={"enable_kinox": True, "ui_language": "de", "autosync_interval": "6h"},
    )
    body = client.get("/api/settings/env").get_data(as_text=True)
    assert "ANIWORLD_ENABLE_KINOX=1" in body
    assert "ANIWORLD_UI_LANGUAGE=de" in body
    assert "ANIWORLD_AUTOSYNC_INTERVAL=6h" in body


def test_the_export_covers_every_site(client):
    from aniworld.web.media import SITE_KEYS

    body = client.get("/api/settings/env").get_data(as_text=True)
    for site in SITE_KEYS:
        assert f"ANIWORLD_ENABLE_{site.upper()}=" in body, site


def test_the_export_leaves_secrets_out(client, monkeypatch):
    """It lands in a downloads folder, so nothing worth stealing goes in it."""
    monkeypatch.setenv("ANIWORLD_DISCORD_TOKEN", "super-secret-token")
    monkeypatch.setenv("ANIWORLD_OIDC_CLIENT_SECRET", "oidc-secret")
    monkeypatch.setenv("ANIWORLD_WEB_ADMIN_PASS", "hunter2hunter2")

    body = client.get("/api/settings/env").get_data(as_text=True)
    for secret in ("super-secret-token", "oidc-secret", "hunter2hunter2"):
        assert secret not in body
    for key in (
        "ANIWORLD_DISCORD_TOKEN",
        "ANIWORLD_OIDC_CLIENT_SECRET",
        "ANIWORLD_WEB_ADMIN_PASS",
    ):
        assert key not in body


def test_the_export_reads_back_as_the_same_settings(client, tmp_path):
    """A file that does not load back the way it was written is no use."""
    from dotenv import dotenv_values

    client.put(
        "/api/settings",
        json={
            "autosync_mode": "cron",
            "autosync_cron": "every monday and friday at 10pm",
            "output_format": "mp4",
            "enable_htv": True,
            "enable_megakino": False,
        },
    )
    written = tmp_path / ".env"
    written.write_text(client.get("/api/settings/env").get_data(as_text=True))
    loaded = dotenv_values(written)

    assert loaded["ANIWORLD_AUTOSYNC_CRON"] == "0 22 * * 1,5", "quotes survive"
    assert loaded["ANIWORLD_ENABLE_HTV"] == "1"
    assert loaded["ANIWORLD_ENABLE_MEGAKINO"] == "0"
    assert loaded["ANIWORLD_NAMING_TEMPLATE"].endswith(".mp4"), "spaces survive"
    assert loaded["ANIWORLD_UI_LANGUAGE"] == "en"


def test_the_export_needs_an_admin():
    from aniworld.web.views import ADMIN_ENDPOINTS

    assert "api.export_env" in ADMIN_ENDPOINTS


def test_the_path_preview_follows_a_path_that_is_being_typed(client, tmp_path):
    """The box under the field updates before anything is saved."""
    typed = str(tmp_path / "nas")
    body = client.get(
        "/api/settings/path-preview", query_string={"download_path": typed}
    ).get_json()
    assert body["episode"].startswith(typed)
    assert body["movie"].startswith(typed)


def test_the_path_preview_changes_nothing(client, tmp_path):
    before = settings_store.read_settings()["download_path"]
    client.get(
        "/api/settings/path-preview", query_string={"download_path": "/tmp/nope"}
    )
    assert settings_store.read_settings()["download_path"] == before


def test_the_path_preview_falls_back_to_the_saved_path(client):
    body = client.get("/api/settings/path-preview").get_json()
    assert body["episode"].startswith(settings_store.read_settings()["download_path"])


def test_the_path_preview_needs_an_admin():
    from aniworld.web.views import ADMIN_ENDPOINTS

    assert "api.path_preview" in ADMIN_ENDPOINTS
