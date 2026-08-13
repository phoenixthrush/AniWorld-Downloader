"""API key storage: hashing, expiry and usage tracking."""

import sqlite3

import pytest

from aniworld.web import apikeys, db


def test_generated_keys_are_prefixed_and_unique():
    keys = {apikeys.generate() for _ in range(50)}
    assert len(keys) == 50
    assert all(key.startswith(apikeys.KEY_PREFIX) for key in keys)
    assert all(len(key) > 30 for key in keys)


def test_hashing_is_stable_and_one_way():
    raw = apikeys.generate()
    assert apikeys.hash_key(raw) == apikeys.hash_key(raw)
    assert raw not in apikeys.hash_key(raw)
    assert len(apikeys.hash_key(raw)) == 64


def test_different_keys_hash_differently():
    assert apikeys.hash_key("a") != apikeys.hash_key("b")


def test_the_plain_key_never_reaches_the_database(api_key):
    raw, _ = api_key()
    with db.session() as conn:
        stored = conn.execute("SELECT key_hash, prefix FROM api_keys").fetchone()
    assert stored["key_hash"] != raw
    assert raw not in stored["key_hash"]
    assert raw.startswith(stored["prefix"])


def test_a_fresh_key_verifies(api_key):
    raw, key_id = api_key(scope="write", name="ci")
    record = db.verify_api_key(apikeys.hash_key(raw))
    assert record["id"] == key_id
    assert record["name"] == "ci"
    assert record["scope"] == "write"


def test_an_unknown_key_does_not_verify():
    assert db.verify_api_key(apikeys.hash_key("awd_not-a-real-key")) is None


@pytest.mark.parametrize("scope", apikeys.SCOPES)
def test_every_scope_can_be_stored(api_key, scope):
    raw, _ = api_key(scope=scope)
    assert db.verify_api_key(apikeys.hash_key(raw))["scope"] == scope


def test_an_invalid_scope_is_refused_by_the_schema():
    with pytest.raises(sqlite3.IntegrityError):
        db.create_api_key("bad", "hash", "awd_x", "superuser")


def test_key_hashes_are_unique():
    db.create_api_key("one", "same-hash", "awd_a", "read")
    with pytest.raises(sqlite3.IntegrityError):
        db.create_api_key("two", "same-hash", "awd_b", "read")


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------
def test_a_key_without_an_expiry_never_expires(api_key):
    raw, _ = api_key()
    assert db.verify_api_key(apikeys.hash_key(raw)) is not None
    assert db.list_api_keys()[0]["expires_at"] is None
    assert db.list_api_keys()[0]["expired"] == 0


def test_a_future_expiry_still_verifies(api_key):
    raw, _ = api_key(expires_days=30)
    assert db.verify_api_key(apikeys.hash_key(raw)) is not None
    assert db.list_api_keys()[0]["expires_at"] is not None


def test_an_expired_key_stops_verifying(api_key):
    raw, key_id = api_key(expires_days=1)
    with db.session() as conn:
        conn.execute(
            "UPDATE api_keys SET expires_at = datetime('now', '-1 hour') WHERE id = ?",
            (key_id,),
        )
    assert db.verify_api_key(apikeys.hash_key(raw)) is None


def test_an_expired_key_is_still_listed_so_it_can_be_deleted(api_key):
    _, key_id = api_key(expires_days=1)
    with db.session() as conn:
        conn.execute(
            "UPDATE api_keys SET expires_at = datetime('now', '-1 hour') WHERE id = ?",
            (key_id,),
        )
    listed = db.list_api_keys()[0]
    assert listed["id"] == key_id
    assert listed["expired"] == 1


# ---------------------------------------------------------------------------
# Listing, usage and deletion
# ---------------------------------------------------------------------------
def test_listing_never_exposes_the_hash(api_key):
    api_key()
    assert "key_hash" not in db.list_api_keys()[0]


def test_listing_is_ordered_by_creation(api_key):
    api_key(name="first")
    api_key(name="second")
    assert [k["name"] for k in db.list_api_keys()] == ["first", "second"]


def test_last_used_starts_empty(api_key):
    api_key()
    assert db.list_api_keys()[0]["last_used_at"] is None


def test_using_a_key_records_the_time(api_key):
    _, key_id = api_key()
    db.touch_api_key(key_id)
    assert db.list_api_keys()[0]["last_used_at"] is not None


def test_usage_is_only_written_once_a_minute(api_key):
    """Every API call touches the key, it must not write on each one."""
    _, key_id = api_key()
    db.touch_api_key(key_id)
    first = db.list_api_keys()[0]["last_used_at"]

    with db.session() as conn:
        conn.execute(
            "UPDATE api_keys SET last_used_at = datetime('now', '-30 seconds') "
            "WHERE id = ?",
            (key_id,),
        )
    stale = db.list_api_keys()[0]["last_used_at"]
    db.touch_api_key(key_id)
    assert db.list_api_keys()[0]["last_used_at"] == stale
    assert first is not None


def test_usage_is_written_again_after_a_minute(api_key):
    _, key_id = api_key()
    with db.session() as conn:
        conn.execute(
            "UPDATE api_keys SET last_used_at = datetime('now', '-2 minutes') "
            "WHERE id = ?",
            (key_id,),
        )
    old = db.list_api_keys()[0]["last_used_at"]
    db.touch_api_key(key_id)
    assert db.list_api_keys()[0]["last_used_at"] != old


def test_deleting_a_key_stops_it_working(api_key):
    raw, key_id = api_key()
    assert db.delete_api_key(key_id) is True
    assert db.verify_api_key(apikeys.hash_key(raw)) is None
    assert db.list_api_keys() == []


def test_deleting_twice_reports_missing(api_key):
    _, key_id = api_key()
    db.delete_api_key(key_id)
    assert db.delete_api_key(key_id) is False


def test_deleting_one_key_leaves_the_others(api_key):
    raw_a, id_a = api_key(name="a")
    raw_b, _ = api_key(name="b")
    db.delete_api_key(id_a)
    assert db.verify_api_key(apikeys.hash_key(raw_a)) is None
    assert db.verify_api_key(apikeys.hash_key(raw_b)) is not None


def test_the_creator_is_recorded():
    db.create_api_key("ci", "hash", "awd_x", "read", created_by="alice")
    assert db.list_api_keys()[0]["created_by"] == "alice"
