"""Login, first run setup and the admin wall."""

import pytest

from aniworld.web import db


def login(client, username="root", password="hunter2hunter2"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


@pytest.fixture
def admin():
    return db.create_user("root", "hunter2hunter2", role="admin")


@pytest.fixture
def plain_user():
    db.create_user("root", "hunter2hunter2", role="admin")
    return db.create_user("bob", "hunter2hunter2")


# ---------------------------------------------------------------------------
# Without auth nothing is gated
# ---------------------------------------------------------------------------
def test_pages_are_open_when_auth_is_off(client):
    assert client.get("/").status_code == 200
    assert client.get("/settings").status_code == 200


def test_the_api_is_open_when_auth_is_off(client):
    assert client.get("/api/queue").status_code == 200
    assert client.get("/api/settings").status_code == 200


def test_everyone_is_an_admin_when_auth_is_off(client):
    assert client.get("/api/ping").get_json()["scope"] == "admin"


# ---------------------------------------------------------------------------
# First run
# ---------------------------------------------------------------------------
def test_a_fresh_install_asks_for_an_admin(auth_client):
    response = auth_client.get("/")
    assert response.status_code == 302
    assert "/setup" in response.headers["Location"]


def test_the_setup_page_is_reachable(auth_client):
    assert auth_client.get("/setup").status_code == 200


def test_setup_creates_the_admin_and_signs_them_in(auth_client):
    response = auth_client.post(
        "/setup",
        data={
            "username": "root",
            "password": "hunter2hunter2",
            "confirm": "hunter2hunter2",
        },
    )
    assert response.status_code == 302
    assert db.verify_user("root", "hunter2hunter2")["role"] == "admin"
    assert auth_client.get("/").status_code == 200


def test_setup_is_closed_once_an_admin_exists(auth_client, admin):
    response = auth_client.get("/setup")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_setup_will_not_create_a_second_admin(auth_client, admin):
    auth_client.post(
        "/setup",
        data={
            "username": "sneaky",
            "password": "hunter2hunter2",
            "confirm": "hunter2hunter2",
        },
    )
    assert db.verify_user("sneaky", "hunter2hunter2") is None


def test_mismatched_passwords_are_refused(auth_client):
    auth_client.post(
        "/setup",
        data={"username": "root", "password": "hunter2hunter2", "confirm": "other"},
    )
    assert db.list_users() == []


@pytest.mark.parametrize("password", ["", "short", "1234567"])
def test_short_passwords_are_refused(auth_client, password):
    auth_client.post(
        "/setup", data={"username": "root", "password": password, "confirm": password}
    )
    assert db.list_users() == []


@pytest.mark.parametrize("username", ["", "has space", "hi!", "a" * 65, "bad/slash"])
def test_bad_usernames_are_refused(auth_client, username):
    auth_client.post(
        "/setup",
        data={
            "username": username,
            "password": "hunter2hunter2",
            "confirm": "hunter2hunter2",
        },
    )
    assert db.list_users() == []


@pytest.mark.parametrize("username", ["root", "a.b", "a-b", "a_b", "User123"])
def test_good_usernames_are_accepted(auth_client, username):
    auth_client.post(
        "/setup",
        data={
            "username": username,
            "password": "hunter2hunter2",
            "confirm": "hunter2hunter2",
        },
    )
    assert db.verify_user(username, "hunter2hunter2") is not None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def test_the_login_page_renders(auth_client, admin):
    assert auth_client.get("/login").status_code == 200


def test_a_good_password_signs_you_in(auth_client, admin):
    assert login(auth_client).status_code == 302
    assert auth_client.get("/").status_code == 200


def test_a_bad_password_does_not(auth_client, admin):
    response = login(auth_client, password="wrong-password")
    assert response.status_code == 200, "the form is shown again"
    assert auth_client.get("/api/queue").status_code == 401


def test_logging_out_ends_the_session(auth_client, admin):
    login(auth_client)
    auth_client.get("/logout")
    assert auth_client.get("/api/queue").status_code == 401


def test_login_redirects_to_setup_when_there_is_no_admin(auth_client):
    response = auth_client.get("/login")
    assert response.status_code == 302
    assert "/setup" in response.headers["Location"]


# ---------------------------------------------------------------------------
# The wall
# ---------------------------------------------------------------------------
def test_anonymous_api_calls_get_json_not_a_redirect(auth_client, admin):
    response = auth_client.get("/api/queue")
    assert response.status_code == 401
    assert response.get_json()["error"] == "authentication required"


def test_anonymous_page_visits_are_redirected(auth_client, admin):
    response = auth_client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_a_signed_in_user_can_use_the_queue(auth_client, plain_user):
    login(auth_client, "bob")
    assert auth_client.get("/api/queue").status_code == 200


def test_a_plain_user_cannot_read_settings(auth_client, plain_user):
    login(auth_client, "bob")
    response = auth_client.get("/api/settings")
    assert response.status_code == 403
    assert response.get_json()["error"] == "admin access required"


def test_a_plain_user_cannot_change_settings(auth_client, plain_user):
    login(auth_client, "bob")
    assert (
        auth_client.put("/api/settings", json={"enable_htv": True}).status_code == 403
    )


def test_a_plain_user_is_bounced_off_the_settings_page(auth_client, plain_user):
    login(auth_client, "bob")
    response = auth_client.get("/settings")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_an_admin_can_do_both(auth_client, admin):
    login(auth_client)
    assert auth_client.get("/api/settings").status_code == 200
    assert auth_client.get("/settings").status_code == 200


def test_a_plain_user_cannot_manage_api_keys(auth_client, plain_user):
    login(auth_client, "bob")
    assert auth_client.get("/api/keys").status_code == 403
    assert auth_client.post("/api/keys", json={"name": "x"}).status_code == 403


def test_the_download_queue_stays_open_to_plain_users(auth_client, plain_user):
    login(auth_client, "bob")
    response = auth_client.post("/api/download", json={"episodes": ["https://x/ep1"]})
    assert response.status_code == 200


def test_the_downloading_user_is_recorded(auth_client, plain_user):
    login(auth_client, "bob")
    queue_id = auth_client.post(
        "/api/download", json={"episodes": ["https://x/ep1"]}
    ).get_json()["queue_id"]
    assert db.get_queue_item(queue_id)["username"] == "bob"


def test_a_demoted_admin_loses_access_without_logging_out(auth_client, admin):
    """The session role is refreshed from the database on every request."""
    db.create_user("second", "hunter2hunter2", role="admin")
    login(auth_client)
    assert auth_client.get("/api/settings").status_code == 200

    db.update_user_role(admin, "user")
    with auth_client.session_transaction() as session:
        session["_role_checked"] = 0
    assert auth_client.get("/api/settings").status_code == 403


def test_a_deleted_user_is_signed_out(auth_client, plain_user):
    login(auth_client, "bob")
    db.delete_user(plain_user)
    with auth_client.session_transaction() as session:
        session["_role_checked"] = 0
    response = auth_client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "header,value",
    [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ],
)
def test_security_headers_are_set(client, header, value):
    assert client.get("/").headers[header] == value
