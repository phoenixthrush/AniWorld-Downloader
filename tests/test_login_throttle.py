"""Brute force protection on the local login and the trusted proxy setting."""

import pytest
from werkzeug.security import check_password_hash

from aniworld.web import app as web_app
from aniworld.web import db
from aniworld.web.throttle import LoginThrottle


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def login(client, username="root", password="wrong-password", ip="10.0.0.1"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        environ_base={"REMOTE_ADDR": ip},
    )


@pytest.fixture
def admin():
    return db.create_user("root", "hunter2hunter2", role="admin")


@pytest.fixture
def clock(auth_app):
    clock = Clock()
    auth_app.extensions["login_throttle"] = LoginThrottle(clock=clock)
    return clock


# ---------------------------------------------------------------------------
# Throttle on its own
# ---------------------------------------------------------------------------
def test_a_fresh_client_is_not_blocked():
    assert LoginThrottle().retry_after("10.0.0.1", "root") == 0


def test_the_username_limit_blocks_until_the_oldest_failure_expires():
    clock = Clock()
    throttle = LoginThrottle(window=900, max_per_user=3, clock=clock)
    for _ in range(3):
        throttle.record_failure("10.0.0.1", "root")
        clock.now += 10
    assert throttle.retry_after("10.0.0.2", "root") == pytest.approx(870)
    clock.now += 870
    assert throttle.retry_after("10.0.0.2", "root") == 0


def test_the_ip_limit_spans_usernames():
    throttle = LoginThrottle(max_per_ip=3, max_per_user=100)
    for name in ("a", "b", "c"):
        throttle.record_failure("10.0.0.1", name)
    assert throttle.retry_after("10.0.0.1", "d") > 0
    assert throttle.retry_after("10.0.0.2", "d") == 0


def test_record_failure_reports_the_start_of_a_lockout():
    throttle = LoginThrottle(max_per_ip=100, max_per_user=2)
    assert throttle.record_failure("10.0.0.1", "root") is False
    assert throttle.record_failure("10.0.0.1", "root") is True


def test_a_success_clears_the_username_but_not_the_ip():
    throttle = LoginThrottle(max_per_ip=2, max_per_user=2)
    throttle.record_failure("10.0.0.1", "root")
    throttle.record_failure("10.0.0.1", "root")
    throttle.record_success("root")
    assert throttle.retry_after("10.0.0.2", "root") == 0
    assert throttle.retry_after("10.0.0.1", "other") > 0


def test_expired_entries_are_pruned():
    clock = Clock()
    throttle = LoginThrottle(window=60, clock=clock)
    throttle.record_failure("10.0.0.1", "root")
    clock.now += 3600
    throttle.record_failure("10.0.0.2", "bob")
    assert set(throttle._failures) == {("ip", "10.0.0.2"), ("user", "bob")}


# ---------------------------------------------------------------------------
# Login route
# ---------------------------------------------------------------------------
def test_too_many_failures_lock_the_account(auth_client, admin, clock):
    for i in range(5):
        assert login(auth_client, ip=f"10.0.0.{i}").status_code == 200
    response = login(auth_client, password="hunter2hunter2", ip="10.0.0.99")
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert b"Too many failed attempts" in response.data


def test_the_lock_lifts_after_the_window(auth_client, admin, clock):
    for _ in range(5):
        login(auth_client)
    clock.now += 15 * 60
    assert login(auth_client, password="hunter2hunter2").status_code == 302


def test_one_ip_guessing_many_usernames_is_blocked(auth_client, admin, clock):
    for i in range(10):
        login(auth_client, username=f"user{i}")
    assert login(auth_client, username="root").status_code == 429
    assert login(auth_client, username="root", ip="10.0.0.2").status_code == 200


def test_unknown_usernames_lock_out_like_real_ones(auth_client, admin, clock):
    # Otherwise the lockout itself would tell which accounts exist
    for _ in range(5):
        login(auth_client, username="ghost")
    assert login(auth_client, username="ghost", ip="10.0.0.2").status_code == 429


def test_a_successful_login_resets_the_username_count(auth_client, admin, clock):
    for _ in range(4):
        login(auth_client)
    assert login(auth_client, password="hunter2hunter2").status_code == 302
    auth_client.get("/logout")
    for _ in range(4):
        assert login(auth_client, ip="10.0.0.2").status_code == 200


def test_failed_logins_are_logged(auth_client, admin, clock, caplog):
    caplog.set_level("WARNING", logger="aniworld")
    login(auth_client, username="root", ip="10.0.0.7")
    assert "Failed login: user='root' ip=10.0.0.7" in caplog.text


def test_unknown_usernames_still_hash_the_password(monkeypatch):
    checked = []

    def spy(pwhash, password):
        checked.append(password)
        return check_password_hash(pwhash, password)

    monkeypatch.setattr(db, "check_password_hash", spy)
    assert db.verify_user("nobody", "some-password") is None
    assert checked == ["some-password"]


# ---------------------------------------------------------------------------
# Trusted proxy
# ---------------------------------------------------------------------------
def test_no_proxy_is_trusted_by_default():
    assert web_app._proxy_options() == {}


def test_the_trusted_proxy_may_forward_the_client_ip(monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEB_TRUSTED_PROXY", "172.18.0.2")
    options = web_app._proxy_options()
    assert options["trusted_proxy"] == "172.18.0.2"
    assert "x-forwarded-for" in options["trusted_proxy_headers"]
    assert options["clear_untrusted_proxy_headers"] is True


def proxied_client(auth_app, monkeypatch, trusted_proxy):
    """Run the app behind waitress' proxy middleware, as serve() would."""
    from waitress.proxy_headers import proxy_headers_middleware

    monkeypatch.setenv("ANIWORLD_WEB_TRUSTED_PROXY", trusted_proxy)
    options = web_app._proxy_options()
    auth_app.wsgi_app = proxy_headers_middleware(
        auth_app.wsgi_app,
        trusted_proxy=options["trusted_proxy"],
        trusted_proxy_count=options["trusted_proxy_count"],
        trusted_proxy_headers=options["trusted_proxy_headers"],
        clear_untrusted=options["clear_untrusted_proxy_headers"],
    )
    return auth_app.test_client()


def forwarded_login(client, peer, forwarded_for, username="root"):
    return client.post(
        "/login",
        data={"username": username, "password": "wrong-password"},
        environ_base={"REMOTE_ADDR": peer},
        headers={"X-Forwarded-For": forwarded_for},
    )


def test_clients_behind_the_trusted_proxy_are_counted_apart(
    auth_app, admin, clock, monkeypatch
):
    client = proxied_client(auth_app, monkeypatch, "172.18.0.2")
    for i in range(10):
        forwarded_login(client, "172.18.0.2", f"1.2.3.{i}", f"user{i}")
    # Ten failures through the proxy, but each from a different client
    throttle = auth_app.extensions["login_throttle"]
    assert throttle.retry_after("172.18.0.2", "someone") == 0
    assert throttle.retry_after("1.2.3.0", "someone") == 0


def test_a_spoofed_header_from_elsewhere_is_ignored(
    auth_app, admin, clock, monkeypatch
):
    client = proxied_client(auth_app, monkeypatch, "172.18.0.2")
    for i in range(10):
        response = forwarded_login(client, "6.6.6.6", f"9.9.9.{i}", f"user{i}")
        assert response.status_code == 200
    # All ten landed on the real address, so it is blocked now
    assert forwarded_login(client, "6.6.6.6", "9.9.9.99", "new").status_code == 429
