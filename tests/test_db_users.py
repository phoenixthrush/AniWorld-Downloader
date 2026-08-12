"""Accounts: local logins, SSO identities and the last admin rule."""

import sqlite3

import pytest

from aniworld.web import db


def test_new_database_has_no_admin():
    assert db.has_any_admin() is False


def test_creating_an_admin_flips_that(monkeypatch):
    db.create_user("root", "hunter2hunter2", role="admin")
    assert db.has_any_admin() is True


def test_a_plain_user_is_not_an_admin():
    db.create_user("bob", "hunter2hunter2")
    assert db.has_any_admin() is False


def test_password_is_not_stored_in_the_clear():
    db.create_user("bob", "hunter2hunter2")
    with db.session() as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert "hunter2hunter2" not in stored
    assert len(stored) > 20


def test_correct_password_logs_in():
    db.create_user("bob", "hunter2hunter2")
    user = db.verify_user("bob", "hunter2hunter2")
    assert user["username"] == "bob"
    assert user["role"] == "user"
    assert "password_hash" not in user


@pytest.mark.parametrize(
    "username,password",
    [
        ("bob", "wrong-password"),
        ("bob", ""),
        ("BOB", "hunter2hunter2"),
        ("nobody", "hunter2hunter2"),
    ],
)
def test_bad_credentials_are_rejected(username, password):
    db.create_user("bob", "hunter2hunter2")
    assert db.verify_user(username, password) is None


def test_usernames_are_unique():
    db.create_user("bob", "hunter2hunter2")
    with pytest.raises(sqlite3.IntegrityError):
        db.create_user("bob", "another-password")


def test_bootstrap_admin_from_the_environment(monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEB_ADMIN_USER", "docker-admin")
    monkeypatch.setenv("ANIWORLD_WEB_ADMIN_PASS", "hunter2hunter2")
    monkeypatch.setattr(db, "_initialized", False)
    db.init_db()

    user = db.verify_user("docker-admin", "hunter2hunter2")
    assert user["role"] == "admin"


def test_bootstrap_is_skipped_when_an_admin_exists(monkeypatch):
    db.create_user("root", "hunter2hunter2", role="admin")
    monkeypatch.setenv("ANIWORLD_WEB_ADMIN_USER", "docker-admin")
    monkeypatch.setenv("ANIWORLD_WEB_ADMIN_PASS", "hunter2hunter2")
    monkeypatch.setattr(db, "_initialized", False)
    db.init_db()

    assert db.verify_user("docker-admin", "hunter2hunter2") is None
    assert len(db.list_users()) == 1


def test_bootstrap_needs_both_halves(monkeypatch):
    monkeypatch.setenv("ANIWORLD_WEB_ADMIN_USER", "docker-admin")
    monkeypatch.setattr(db, "_initialized", False)
    db.init_db()
    assert db.list_users() == []


# ---------------------------------------------------------------------------
# Listing, roles and deletion
# ---------------------------------------------------------------------------
def test_listing_hides_the_hash():
    db.create_user("bob", "hunter2hunter2")
    assert "password_hash" not in db.list_users()[0]


def test_get_user_by_id():
    user_id = db.create_user("bob", "hunter2hunter2")
    assert db.get_user(user_id)["username"] == "bob"
    assert db.get_user(999) is None


def test_promote_and_demote():
    root = db.create_user("root", "hunter2hunter2", role="admin")
    bob = db.create_user("bob", "hunter2hunter2")
    assert db.update_user_role(bob, "admin") == (True, None)
    assert db.get_user(bob)["role"] == "admin"
    assert db.update_user_role(root, "user") == (True, None)


def test_the_last_admin_cannot_be_demoted():
    root = db.create_user("root", "hunter2hunter2", role="admin")
    db.create_user("bob", "hunter2hunter2")
    ok, error = db.update_user_role(root, "user")
    assert not ok
    assert "last admin" in error
    assert db.get_user(root)["role"] == "admin"


def test_the_last_admin_cannot_be_deleted():
    root = db.create_user("root", "hunter2hunter2", role="admin")
    ok, error = db.delete_user(root)
    assert not ok
    assert "last admin" in error
    assert db.get_user(root) is not None


def test_an_admin_can_go_once_another_exists():
    root = db.create_user("root", "hunter2hunter2", role="admin")
    db.create_user("second", "hunter2hunter2", role="admin")
    assert db.delete_user(root) == (True, None)
    assert db.get_user(root) is None


def test_plain_users_can_always_be_deleted():
    db.create_user("root", "hunter2hunter2", role="admin")
    bob = db.create_user("bob", "hunter2hunter2")
    assert db.delete_user(bob) == (True, None)


def test_invalid_role_is_rejected():
    bob = db.create_user("bob", "hunter2hunter2")
    ok, error = db.update_user_role(bob, "superuser")
    assert not ok
    assert error == "Invalid role"


def test_deleting_a_missing_user_reports_it():
    assert db.delete_user(4242) == (False, "User not found")


# ---------------------------------------------------------------------------
# SSO
# ---------------------------------------------------------------------------
def test_first_sso_login_creates_the_account():
    user = db.find_or_create_sso_user("sub-1", "https://idp", "alice")
    assert user["username"] == "alice"
    assert db.get_user(user["id"])["auth_method"] == "sso"


def test_the_first_sso_user_becomes_admin():
    user = db.find_or_create_sso_user("sub-1", "https://idp", "alice")
    assert user["role"] == "admin"


def test_later_sso_users_are_plain():
    db.find_or_create_sso_user("sub-1", "https://idp", "alice")
    second = db.find_or_create_sso_user("sub-2", "https://idp", "bob")
    assert second["role"] == "user"


def test_second_login_reuses_the_account():
    first = db.find_or_create_sso_user("sub-1", "https://idp", "alice")
    again = db.find_or_create_sso_user("sub-1", "https://idp", "alice")
    assert first["id"] == again["id"]
    assert len(db.list_users()) == 1


def test_the_subject_identifies_the_user_not_the_name():
    first = db.find_or_create_sso_user("sub-1", "https://idp", "alice")
    renamed = db.find_or_create_sso_user("sub-1", "https://idp", "alice-renamed")
    assert renamed["id"] == first["id"]


def test_same_subject_at_a_different_issuer_is_a_different_person():
    first = db.find_or_create_sso_user("sub-1", "https://idp-a", "alice")
    second = db.find_or_create_sso_user("sub-1", "https://idp-b", "alice")
    assert first["id"] != second["id"]


def test_a_clashing_display_name_gets_a_suffix():
    db.create_user("alice", "hunter2hunter2")
    user = db.find_or_create_sso_user("sub-1", "https://idp", "alice")
    assert user["username"] == "alice-2"


def test_clashes_keep_counting_up():
    db.create_user("alice", "hunter2hunter2")
    db.find_or_create_sso_user("sub-1", "https://idp", "alice")
    third = db.find_or_create_sso_user("sub-2", "https://idp", "alice")
    assert third["username"] == "alice-3"


def test_configured_admin_subject_is_promoted():
    db.find_or_create_sso_user("someone-else", "https://idp", "first")
    user = db.find_or_create_sso_user(
        "sub-boss", "https://idp", "boss", admin_subject="sub-boss"
    )
    assert user["role"] == "admin"


def test_configured_admin_username_is_promoted():
    db.find_or_create_sso_user("someone-else", "https://idp", "first")
    user = db.find_or_create_sso_user(
        "sub-boss", "https://idp", "boss", admin_user="boss"
    )
    assert user["role"] == "admin"


def test_an_existing_account_is_promoted_on_the_next_login():
    db.find_or_create_sso_user("first", "https://idp", "first")
    db.find_or_create_sso_user("sub-boss", "https://idp", "boss")
    assert db.get_user(3) is None

    promoted = db.find_or_create_sso_user(
        "sub-boss", "https://idp", "boss", admin_subject="sub-boss"
    )
    assert promoted["role"] == "admin"


def test_sso_accounts_cannot_be_used_for_password_login():
    db.find_or_create_sso_user("sub-1", "https://idp", "alice")
    assert db.verify_user("alice", "") is None
