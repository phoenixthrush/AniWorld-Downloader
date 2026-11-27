"""The webhook section on the settings page.

The settings are written through to the .env like the Discord bot's, so these
tests point the config directory at a temp folder and read the file back the
way the next start would.
"""

import re
from pathlib import Path

import pytest
from dotenv import dotenv_values

from aniworld.env import merge_env, quote_env_value
from aniworld.web import settings_store, webhook

EXAMPLE = Path(settings_store.__file__).parents[1] / ".env.example"
PLACEHOLDER = settings_store.SECRET_PLACEHOLDER

JELLYFIN_HEADER = 'Authorization: MediaBrowser Token="abc123"'
# Everything a careless .env writer gets wrong: quotes of both kinds, a "#"
# after a space, a backslash, and text outside ASCII
TRICKY_BODY = """{"content": "Neue Folgen ✓ #5, it's \\\\done"}"""


@pytest.fixture
def env_file(monkeypatch, tmp_path):
    """Where the settings are persisted, instead of the sandbox config dir."""
    monkeypatch.setattr(settings_store, "ANIWORLD_CONFIG_DIR", tmp_path)
    return tmp_path / ".env"


def save(client, **fields):
    return client.put("/api/settings", json={"webhook": fields})


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def test_an_unset_webhook_reads_as_off(client):
    data = client.get("/api/settings").get_json()["webhook"]
    assert data == {
        "url": "",
        "method": "POST",
        "headers_set": False,
        "body": "",
        "methods": list(webhook.METHODS),
    }


def test_the_url_is_shown_but_the_headers_never_reach_the_browser(client, monkeypatch):
    url = "https://discord.com/api/webhooks/1/abc"
    monkeypatch.setenv("ANIWORLD_WEBHOOK_URL", url)
    monkeypatch.setenv("ANIWORLD_WEBHOOK_HEADERS", "X-Token: HEADERSECRET")
    response = client.get("/api/settings")

    data = response.get_json()["webhook"]
    assert data["url"] == url, "the admin needs to see what it points at"
    assert data["headers_set"] is True
    assert "HEADERSECRET" not in response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------
def test_saving_applies_at_once_and_survives_a_restart(client, env_file):
    response = save(
        client,
        url="http://jellyfin:8096/Library/Refresh",
        method="put",
        headers=JELLYFIN_HEADER,
        body=TRICKY_BODY,
    )
    assert response.status_code == 200

    # Running process
    assert webhook.webhook_url() == "http://jellyfin:8096/Library/Refresh"
    assert webhook.webhook_method() == "PUT"
    assert webhook.webhook_headers() == {"Authorization": 'MediaBrowser Token="abc123"'}
    assert webhook.webhook_body() == TRICKY_BODY

    # What the next start reads from the .env
    loaded = dotenv_values(env_file)
    assert loaded["ANIWORLD_WEBHOOK_URL"] == "http://jellyfin:8096/Library/Refresh"
    assert loaded["ANIWORLD_WEBHOOK_METHOD"] == "PUT"
    assert loaded["ANIWORLD_WEBHOOK_HEADERS"] == JELLYFIN_HEADER
    assert loaded["ANIWORLD_WEBHOOK_BODY"] == TRICKY_BODY


def test_the_startup_rewrite_keeps_the_saved_values(client, env_file, monkeypatch):
    """Every start rebuilds the .env from the template, quotes included."""
    # merge_env also loads the file into os.environ, which would outlive the test
    monkeypatch.setattr("aniworld.env.load_dotenv", lambda *args, **kwargs: None)
    save(client, url="https://ntfy.sh/topic", headers=JELLYFIN_HEADER, body=TRICKY_BODY)
    merge_env(EXAMPLE, env_file)

    loaded = dotenv_values(env_file)
    assert loaded["ANIWORLD_WEBHOOK_URL"] == "https://ntfy.sh/topic"
    assert loaded["ANIWORLD_WEBHOOK_HEADERS"] == JELLYFIN_HEADER
    assert loaded["ANIWORLD_WEBHOOK_BODY"] == TRICKY_BODY


def test_the_placeholder_keeps_the_saved_headers(client, env_file):
    save(client, url="http://jellyfin:8096/Library/Refresh", headers=JELLYFIN_HEADER)
    response = save(
        client, url="http://jellyfin:8096/Library/Refresh", headers=PLACEHOLDER
    )
    assert response.status_code == 200

    assert webhook.webhook_headers() == {"Authorization": 'MediaBrowser Token="abc123"'}
    assert dotenv_values(env_file)["ANIWORLD_WEBHOOK_HEADERS"] == JELLYFIN_HEADER


def test_the_placeholder_is_not_a_url(client, env_file):
    """The URL is shown as it is now, so dots in it are a typo, not a keep."""
    save(client, url="http://jellyfin:8096/Library/Refresh")
    response = save(client, url=PLACEHOLDER)
    assert response.status_code == 400
    assert webhook.webhook_url() == "http://jellyfin:8096/Library/Refresh"


def test_an_empty_url_turns_it_off(client, env_file):
    save(client, url="http://jellyfin:8096/Library/Refresh", headers=JELLYFIN_HEADER)
    save(client, url="", headers="")

    assert client.get("/api/settings").get_json()["webhook"]["url"] == ""
    loaded = dotenv_values(env_file)
    assert loaded["ANIWORLD_WEBHOOK_URL"] == ""
    assert loaded["ANIWORLD_WEBHOOK_HEADERS"] == ""


def test_other_settings_leave_the_env_file_alone(client, env_file):
    client.put("/api/settings", json={"lang_separation": True})
    assert not env_file.exists()


@pytest.mark.parametrize(
    "fields, reason",
    [
        ({"url": "jellyfin:8096/Library/Refresh"}, "http:// or https://"),
        ({"url": "ftp://host/file"}, "http:// or https://"),
        ({"url": "http://host:port/x"}, "not valid"),
        ({"method": "DELETE"}, "Invalid webhook method"),
        ({"headers": "X-Ok: 1 | justatoken"}, "Name: value"),
        ({"headers": "My Header: 1"}, "Name: value"),
        ({"body": "line one\nline two"}, "one line"),
        ({"url": "http://host/x\r\nX-Evil: 1"}, "one line"),
        ({"body": "Hello ${USER}"}, "variable"),
    ],
)
def test_a_webhook_that_cannot_work_is_refused(client, env_file, fields, reason):
    save(client, url="https://ntfy.sh/topic", body="kept")
    response = save(client, **fields)

    assert response.status_code == 400
    assert reason in response.get_json()["error"]
    assert webhook.webhook_url() == "https://ntfy.sh/topic", "nothing was applied"
    assert dotenv_values(env_file)["ANIWORLD_WEBHOOK_BODY"] == "kept"


def test_a_webhook_that_is_not_an_object_is_refused(client):
    response = client.put("/api/settings", json={"webhook": "http://x"})
    assert response.status_code == 400


def test_a_refused_webhook_stops_the_rest_of_the_payload(client, env_file):
    response = client.put(
        "/api/settings",
        json={"lang_separation": True, "webhook": {"method": "DELETE"}},
    )
    assert response.status_code == 400
    assert client.get("/api/settings").get_json()["lang_separation"] is False


# ---------------------------------------------------------------------------
# The test button
# ---------------------------------------------------------------------------
class FakeResponse:
    status_code = 204
    reason = "No Content"
    text = ""


def test_the_test_button_sends_the_saved_webhook(client, env_file, monkeypatch):
    sent = []

    def fake_request(method, url, **kwargs):
        sent.append((method, url, kwargs["headers"]))
        return FakeResponse()

    monkeypatch.setattr(webhook.niquests, "request", fake_request)
    save(client, url="http://jellyfin:8096/Library/Refresh", headers=JELLYFIN_HEADER)

    response = client.post("/api/webhook/test")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "status": "204 No Content", "body": ""}
    assert sent == [
        (
            "POST",
            "http://jellyfin:8096/Library/Refresh",
            {"Authorization": 'MediaBrowser Token="abc123"'},
        )
    ]


def test_the_test_button_without_a_url_explains(client):
    body = client.post("/api/webhook/test").get_json()
    assert body == {"ok": False, "error": "No webhook URL is set"}


def test_the_test_button_needs_an_admin():
    """It makes the server send a request, so it is not for every user."""
    from aniworld.web.views import ADMIN_ENDPOINTS

    assert "api.send_test_webhook" in ADMIN_ENDPOINTS


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def test_the_export_has_the_method_and_body_but_no_secrets(
    client, env_file, monkeypatch, tmp_path
):
    save(
        client,
        url="https://discord.com/api/webhooks/1/URLSECRET",
        headers="X-Token: HEADERSECRET",
        method="PATCH",
        body=TRICKY_BODY,
    )
    exported = client.get("/api/settings/env").get_data(as_text=True)

    assert "URLSECRET" not in exported
    assert "HEADERSECRET" not in exported
    assert "ANIWORLD_WEBHOOK_URL" not in exported
    assert "ANIWORLD_WEBHOOK_HEADERS" not in exported

    written = tmp_path / "exported.env"
    written.write_text(exported, encoding="utf-8")
    loaded = dotenv_values(written)
    assert loaded["ANIWORLD_WEBHOOK_METHOD"] == "PATCH"
    assert loaded["ANIWORLD_WEBHOOK_BODY"] == TRICKY_BODY, "a JSON body reads back"


@pytest.mark.parametrize(
    "value",
    [
        r"C:\Users\new folder\Downloads",
        r"C:\new\Downloads",
        'say "hi"',
        "it's",
        "plain",
        "{title} S{season}E{episode}.mkv",
    ],
)
def test_exported_values_read_back_unchanged(tmp_path, value):
    """A "\\n" inside plain double quotes would come back as a line break."""
    written = tmp_path / "x.env"
    written.write_text(f"KEY={settings_store._env_value(value)}\n")
    assert dotenv_values(written)["KEY"] == value


def test_quoting_leaves_an_empty_value_bare():
    assert quote_env_value("") == ""


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def test_the_integrations_pane_has_the_webhook_card(client):
    body = client.get("/settings").get_data(as_text=True)
    pane = body.split('id="pane-integrations"', 1)[1].split('class="settings-pane"', 1)[
        0
    ]

    for element in (
        "webhookUrl",
        "webhookMethod",
        "webhookHeaders",
        "webhookBody",
        "saveWebhookBtn",
        "testWebhookBtn",
        "webhookStatus",
    ):
        assert f'id="{element}"' in pane, element
    for method in webhook.METHODS:
        assert f'<option value="{method}">' in pane, method


def test_every_webhook_text_has_a_german_translation(client):
    body = client.get("/settings").get_data(as_text=True)
    keys = set(re.findall(r'data-i18n="(settings\.webhook[^"]*)"', body))
    script = (
        Path(settings_store.__file__).parent / "static" / "settings.js"
    ).read_text(encoding="utf-8")
    keys |= set(re.findall(r't\("(settings\.webhook[^"]*)"', script))
    i18n = (Path(settings_store.__file__).parent / "static" / "i18n.js").read_text(
        encoding="utf-8"
    )

    assert len(keys) >= 10
    missing = sorted(key for key in keys if f'"{key}":' not in i18n)
    assert missing == []
