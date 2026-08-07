"""SQLite storage for the web UI: users, download queue and custom paths."""

import json
import os
import random
import sqlite3
import time

from werkzeug.security import check_password_hash, generate_password_hash

from ..config import ANIWORLD_CONFIG_DIR
from ..logger import get_logger

logger = get_logger(__name__)

DB_PATH = ANIWORLD_CONFIG_DIR / "aniworld.db"

QUEUE_STATUSES = ("queued", "running", "completed", "failed", "cancelled")


# ---------------------------------------------------------------------------
# Connection handling
# ---------------------------------------------------------------------------
# sqlite locks the whole file on write. Several threads touch the DB (request
# handlers, the queue worker, the discord bot), so every statement retries with
# a backoff instead of blowing up on "database is locked".
def _retry(func, *args, **kwargs):
    delay = 0.1
    for attempt in range(15):
        try:
            return func(*args, **kwargs)
        except sqlite3.OperationalError as exc:
            busy = "locked" in str(exc).lower() or "busy" in str(exc).lower()
            if not busy or attempt == 14:
                raise
            time.sleep(delay + random.uniform(0, 0.05))
            delay = min(delay * 2, 5.0)


class _Cursor(sqlite3.Cursor):
    def execute(self, *args, **kwargs):
        return _retry(super().execute, *args, **kwargs)

    def executemany(self, *args, **kwargs):
        return _retry(super().executemany, *args, **kwargs)


class _Connection(sqlite3.Connection):
    def cursor(self, factory=_Cursor):
        return super().cursor(factory=factory)

    def execute(self, *args, **kwargs):
        return self.cursor().execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self.cursor().executemany(*args, **kwargs)

    def commit(self):
        return _retry(super().commit)


def get_db():
    ANIWORLD_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=60.0, factory=_Connection)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=60000;")
    except sqlite3.Error:
        pass
    return conn


class _Session:
    """Context manager that commits on success and always closes."""

    def __enter__(self):
        self.conn = get_db()
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.commit()
        finally:
            self.conn.close()
        return False


def session():
    return _Session()


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _row(conn, sql, params=()):
    found = conn.execute(sql, params).fetchone()
    return dict(found) if found else None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin', 'user')),
        auth_method TEXT NOT NULL DEFAULT 'local',
        sso_subject TEXT,
        sso_issuer TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_sso_identity ON users (sso_issuer, sso_subject)
    WHERE sso_issuer IS NOT NULL AND sso_subject IS NOT NULL
    """,
    """
    CREATE TABLE IF NOT EXISTS custom_paths (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        path TEXT NOT NULL,
        default_sites TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS download_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        series_url TEXT NOT NULL,
        episodes TEXT NOT NULL,
        total_episodes INTEGER NOT NULL,
        language TEXT NOT NULL,
        provider TEXT NOT NULL,
        username TEXT,
        status TEXT NOT NULL DEFAULT 'queued'
            CHECK(status IN ('queued','running','completed','failed','cancelled')),
        position INTEGER NOT NULL DEFAULT 0,
        current_episode INTEGER NOT NULL DEFAULT 0,
        current_url TEXT,
        errors TEXT NOT NULL DEFAULT '[]',
        custom_path_id INTEGER,
        source TEXT NOT NULL DEFAULT 'manual',
        captcha_url TEXT,
        discord_user_id TEXT,
        cancel_requested INTEGER NOT NULL DEFAULT 0,
        force_cancelled INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        started_at TEXT,
        completed_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_queue_status ON download_queue (status, position)",
    """
    CREATE TABLE IF NOT EXISTS autosync_exclusions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        series_url TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS autosync_state (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        key_hash TEXT NOT NULL UNIQUE,
        prefix TEXT NOT NULL,
        scope TEXT NOT NULL DEFAULT 'write' CHECK(scope IN ('read', 'write', 'admin')),
        created_by TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_used_at TEXT,
        expires_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_api_key_hash ON api_keys (key_hash)",
)

# Columns added after the first release. Older databases get them via ALTER.
_MIGRATIONS = {
    "users": {
        "auth_method": "TEXT NOT NULL DEFAULT 'local'",
        "sso_subject": "TEXT",
        "sso_issuer": "TEXT",
    },
    "custom_paths": {"default_sites": "TEXT NOT NULL DEFAULT ''"},
    "download_queue": {
        "position": "INTEGER NOT NULL DEFAULT 0",
        "custom_path_id": "INTEGER",
        "source": "TEXT NOT NULL DEFAULT 'manual'",
        "captcha_url": "TEXT",
        "discord_user_id": "TEXT",
        "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
        "force_cancelled": "INTEGER NOT NULL DEFAULT 0",
        "started_at": "TEXT",
    },
}

_initialized = False


def init_db():
    """Create the schema and run column migrations. Safe to call repeatedly."""
    global _initialized
    if _initialized:
        return
    with session() as conn:
        for statement in _SCHEMA:
            conn.execute(statement)
        for table, columns in _MIGRATIONS.items():
            existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            for column, spec in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")
        conn.execute("UPDATE download_queue SET position = id WHERE position = 0")
    _initialized = True
    _bootstrap_admin()


def _bootstrap_admin():
    """Create the admin account from env vars when the user table is empty."""
    if has_any_admin():
        return
    username = os.environ.get("ANIWORLD_WEB_ADMIN_USER", "").strip()
    password = os.environ.get("ANIWORLD_WEB_ADMIN_PASS", "").strip()
    if username and password:
        create_user(username, password, role="admin")
        logger.info("Created admin user '%s' from environment", username)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def has_any_admin():
    with session() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'admin'"
        ).fetchone()
        return row["n"] > 0


def create_user(username, password, role="user"):
    with session() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role),
        )
        return cur.lastrowid


def verify_user(username, password):
    with session() as conn:
        user = _row(
            conn,
            "SELECT * FROM users WHERE username = ? AND auth_method = 'local'",
            (username,),
        )
    if not user or not check_password_hash(user["password_hash"], password):
        return None
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


def find_or_create_sso_user(
    subject, issuer, username, admin_user=None, admin_subject=None
):
    """Look up an SSO identity, creating the account on first login."""
    is_admin = bool(
        (admin_subject and admin_subject == subject)
        or (admin_user and admin_user == username)
    )
    with session() as conn:
        user = _row(
            conn,
            "SELECT * FROM users WHERE sso_issuer = ? AND sso_subject = ?",
            (issuer, subject),
        )
        if user:
            if is_admin and user["role"] != "admin":
                conn.execute(
                    "UPDATE users SET role = 'admin' WHERE id = ?", (user["id"],)
                )
                user["role"] = "admin"
            return {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
            }

        # First login: make sure the display name does not collide.
        name = username
        suffix = 1
        while _row(conn, "SELECT id FROM users WHERE username = ?", (name,)):
            suffix += 1
            name = f"{username}-{suffix}"

        role = "admin" if is_admin or not has_any_admin() else "user"
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, auth_method, sso_subject, sso_issuer) "
            "VALUES (?, '', ?, 'sso', ?, ?)",
            (name, role, subject, issuer),
        )
        return {"id": cur.lastrowid, "username": name, "role": role}


def get_user(user_id):
    with session() as conn:
        return _row(
            conn,
            "SELECT id, username, role, auth_method FROM users WHERE id = ?",
            (user_id,),
        )


def list_users():
    with session() as conn:
        return _rows(
            conn,
            "SELECT id, username, role, auth_method, created_at FROM users ORDER BY id",
        )


def delete_user(user_id):
    with session() as conn:
        user = _row(conn, "SELECT role FROM users WHERE id = ?", (user_id,))
        if not user:
            return False, "User not found"
        if user["role"] == "admin" and _last_admin(conn):
            return False, "Cannot delete the last admin"
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return True, None


def update_user_role(user_id, role):
    if role not in ("admin", "user"):
        return False, "Invalid role"
    with session() as conn:
        user = _row(conn, "SELECT role FROM users WHERE id = ?", (user_id,))
        if not user:
            return False, "User not found"
        if user["role"] == "admin" and role != "admin" and _last_admin(conn):
            return False, "Cannot demote the last admin"
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    return True, None


def _last_admin(conn):
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE role = 'admin'"
    ).fetchone()
    return row["n"] <= 1


# ---------------------------------------------------------------------------
# Custom paths
# ---------------------------------------------------------------------------
def get_custom_paths():
    with session() as conn:
        return _rows(conn, "SELECT * FROM custom_paths ORDER BY name COLLATE NOCASE")


def get_custom_path(path_id):
    if not path_id:
        return None
    with session() as conn:
        return _row(conn, "SELECT * FROM custom_paths WHERE id = ?", (path_id,))


def add_custom_path(name, path, default_sites=""):
    with session() as conn:
        cur = conn.execute(
            "INSERT INTO custom_paths (name, path, default_sites) VALUES (?, ?, ?)",
            (name, path, default_sites),
        )
        return cur.lastrowid


def update_custom_path(path_id, name=None, path=None, default_sites=None):
    fields = {"name": name, "path": path, "default_sites": default_sites}
    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        return
    assignments = ", ".join(f"{k} = ?" for k in fields)
    with session() as conn:
        conn.execute(
            f"UPDATE custom_paths SET {assignments} WHERE id = ?",
            (*fields.values(), path_id),
        )


def remove_custom_path(path_id):
    with session() as conn:
        conn.execute("DELETE FROM custom_paths WHERE id = ?", (path_id,))


# ---------------------------------------------------------------------------
# Download queue
# ---------------------------------------------------------------------------
def add_to_queue(
    title,
    series_url,
    episodes,
    language,
    provider,
    username=None,
    custom_path_id=None,
    source="manual",
    discord_user_id=None,
):
    with session() as conn:
        cur = conn.execute(
            "INSERT INTO download_queue "
            "(title, series_url, episodes, total_episodes, language, provider, username, "
            " custom_path_id, source, discord_user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                series_url,
                json.dumps(episodes),
                len(episodes),
                language,
                provider,
                username,
                custom_path_id,
                source,
                discord_user_id,
            ),
        )
        queue_id = cur.lastrowid
        # position starts as the row id so new items land at the back
        conn.execute(
            "UPDATE download_queue SET position = ? WHERE id = ?", (queue_id, queue_id)
        )
        return queue_id


# How long the item has been downloading, NULL until it starts. Both timestamps
# come from sqlite, so this stays right no matter what clock the browser has.
# strftime('%s') gives whole seconds, julianday would be a float that rounds down.
_DURATION_SQL = (
    "CASE WHEN started_at IS NULL THEN NULL ELSE MAX(0, "
    "CAST(strftime('%s', COALESCE(completed_at, 'now')) AS INTEGER) - "
    "CAST(strftime('%s', started_at) AS INTEGER)) END AS duration_seconds"
)


# What is downloading right now goes on top and stays there. Then what is
# waiting, in the order it will be worked through, so moving items still makes
# sense. Everything that is done sits underneath, newest first, because that is
# the one you just watched finish.
_QUEUE_ORDER = (
    "ORDER BY CASE status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END, "
    "CASE WHEN status IN ('running', 'queued') THEN position END ASC, "
    "completed_at DESC, id DESC"
)


def get_queue():
    with session() as conn:
        return _rows(
            conn,
            f"SELECT *, {_DURATION_SQL} FROM download_queue {_QUEUE_ORDER}",
        )


def is_series_queued_or_running(series_url):
    """Stops AutoSync queueing a series that is still working through the queue."""
    with session() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM download_queue "
            "WHERE series_url = ? AND status IN ('queued','running')",
            (series_url,),
        ).fetchone()
        return row["n"] > 0


def get_queue_item(queue_id):
    with session() as conn:
        return _row(conn, "SELECT * FROM download_queue WHERE id = ?", (queue_id,))


def get_running():
    with session() as conn:
        return _row(
            conn, "SELECT * FROM download_queue WHERE status = 'running' LIMIT 1"
        )


def get_next_queued():
    with session() as conn:
        return _row(
            conn,
            "SELECT * FROM download_queue WHERE status = 'queued' "
            "ORDER BY position ASC, id ASC LIMIT 1",
        )


def set_queue_status(queue_id, status):
    if status not in QUEUE_STATUSES:
        raise ValueError(f"Invalid queue status: {status}")
    done = status in ("completed", "failed", "cancelled")
    with session() as conn:
        conn.execute(
            "UPDATE download_queue SET status = ?, "
            "started_at = CASE WHEN ? THEN datetime('now') ELSE started_at END, "
            "completed_at = CASE WHEN ? THEN datetime('now') ELSE completed_at END "
            "WHERE id = ?",
            (status, 1 if status == "running" else 0, 1 if done else 0, queue_id),
        )


def update_queue_progress(queue_id, current_episode, current_url):
    with session() as conn:
        conn.execute(
            "UPDATE download_queue SET current_episode = ?, current_url = ? WHERE id = ?",
            (current_episode, current_url, queue_id),
        )


def update_queue_errors(queue_id, errors):
    with session() as conn:
        conn.execute(
            "UPDATE download_queue SET errors = ? WHERE id = ?",
            (json.dumps(errors), queue_id),
        )


def cancel_queue_item(queue_id, force=False):
    """Ask a download to stop.

    A running item keeps its status until the worker actually stops, so the
    episode being written finishes first. Force sets the flag the downloader
    polls, which kills ffmpeg mid episode. Nothing is running for a queued
    item, so that one is cancelled straight away.
    """
    with session() as conn:
        item = _row(
            conn,
            "SELECT status, cancel_requested FROM download_queue WHERE id = ?",
            (queue_id,),
        )
        if not item:
            return False, "Item not found"
        if item["status"] not in ("queued", "running"):
            return False, "Only queued or running items can be cancelled"

        if item["status"] == "queued":
            conn.execute(
                "UPDATE download_queue SET status = 'cancelled', cancel_requested = 1, "
                "force_cancelled = ?, completed_at = datetime('now') WHERE id = ?",
                (1 if force else 0, queue_id),
            )
        elif force:
            # Marked cancelled right away so it cannot sit in limbo when the
            # worker is stuck somewhere that never reads the flag. The flag
            # still kills ffmpeg, and the worker setting it again is harmless.
            conn.execute(
                "UPDATE download_queue SET status = 'cancelled', cancel_requested = 1, "
                "force_cancelled = 1, completed_at = datetime('now') WHERE id = ?",
                (queue_id,),
            )
        else:
            conn.execute(
                "UPDATE download_queue SET cancel_requested = 1 WHERE id = ?",
                (queue_id,),
            )
    return True, None


def is_queue_force_cancelled(queue_id):
    """Polled from the ffmpeg progress loop so a force cancel lands mid episode."""
    with session() as conn:
        row = _row(
            conn,
            "SELECT force_cancelled FROM download_queue WHERE id = ?",
            (queue_id,),
        )
    return bool(row and row["force_cancelled"])


def cancel_flags(queue_id):
    """Return (cancelled, force) for the running worker to poll."""
    with session() as conn:
        item = _row(
            conn,
            "SELECT cancel_requested, force_cancelled FROM download_queue WHERE id = ?",
            (queue_id,),
        )
    if not item:
        return False, False
    return bool(item["cancel_requested"]), bool(item["force_cancelled"])


def requeue_item(queue_id):
    with session() as conn:
        item = _row(conn, "SELECT status FROM download_queue WHERE id = ?", (queue_id,))
        if not item or item["status"] not in ("failed", "cancelled"):
            return False
        conn.execute(
            "UPDATE download_queue SET status = 'queued', errors = '[]', "
            "current_episode = 0, current_url = NULL, started_at = NULL, "
            "completed_at = NULL, cancel_requested = 0, force_cancelled = 0, "
            "captcha_url = NULL WHERE id = ?",
            (queue_id,),
        )
    return True


def remove_from_queue(queue_id):
    with session() as conn:
        item = _row(conn, "SELECT status FROM download_queue WHERE id = ?", (queue_id,))
        if not item:
            return False, "Item not found"
        if item["status"] == "running":
            return False, "Cancel the item before removing it"
        conn.execute("DELETE FROM download_queue WHERE id = ?", (queue_id,))
    return True, None


def move_queue_item(queue_id, direction):
    """Swap a queued item with its neighbour so users can reorder the queue."""
    if direction not in ("up", "down"):
        return False, "direction must be 'up' or 'down'"
    with session() as conn:
        item = _row(
            conn,
            "SELECT id, position, status FROM download_queue WHERE id = ?",
            (queue_id,),
        )
        if not item:
            return False, "Item not found"
        if item["status"] != "queued":
            return False, "Only queued items can be moved"

        comparison, order = ("<", "DESC") if direction == "up" else (">", "ASC")
        neighbour = _row(
            conn,
            f"SELECT id, position FROM download_queue WHERE status = 'queued' "
            f"AND position {comparison} ? ORDER BY position {order} LIMIT 1",
            (item["position"],),
        )
        if not neighbour:
            return False, "Already at the end of the queue"

        conn.execute(
            "UPDATE download_queue SET position = ? WHERE id = ?",
            (neighbour["position"], item["id"]),
        )
        conn.execute(
            "UPDATE download_queue SET position = ? WHERE id = ?",
            (item["position"], neighbour["id"]),
        )
    return True, None


def clear_completed():
    with session() as conn:
        conn.execute(
            "DELETE FROM download_queue WHERE status IN ('completed','failed','cancelled')"
        )


def reset_stale_running():
    """Requeue items left 'running' by a previous process that died."""
    with session() as conn:
        conn.execute(
            "UPDATE download_queue SET status = 'queued', captcha_url = NULL, "
            "started_at = NULL, cancel_requested = 0, force_cancelled = 0 "
            "WHERE status = 'running'"
        )
        conn.execute("UPDATE download_queue SET captcha_url = NULL")


def set_captcha_url(queue_id, url):
    with session() as conn:
        conn.execute(
            "UPDATE download_queue SET captcha_url = ? WHERE id = ?", (url, queue_id)
        )


def clear_captcha_url(queue_id):
    with session() as conn:
        conn.execute(
            "UPDATE download_queue SET captcha_url = NULL WHERE id = ?", (queue_id,)
        )


# ---------------------------------------------------------------------------
# AutoSync
# ---------------------------------------------------------------------------
def get_autosync_exclusions():
    with session() as conn:
        return _rows(
            conn, "SELECT * FROM autosync_exclusions ORDER BY title COLLATE NOCASE"
        )


def excluded_series_urls():
    with session() as conn:
        rows = conn.execute("SELECT series_url FROM autosync_exclusions").fetchall()
        return {row["series_url"] for row in rows}


def is_autosync_excluded(series_url):
    with session() as conn:
        return (
            _row(
                conn,
                "SELECT id FROM autosync_exclusions WHERE series_url = ?",
                (series_url,),
            )
            is not None
        )


def add_autosync_exclusion(series_url, title=""):
    with session() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO autosync_exclusions (series_url, title) VALUES (?, ?)",
            (series_url, title),
        )


def remove_autosync_exclusion(series_url=None, exclusion_id=None):
    with session() as conn:
        if exclusion_id is not None:
            conn.execute(
                "DELETE FROM autosync_exclusions WHERE id = ?", (exclusion_id,)
            )
        elif series_url is not None:
            conn.execute(
                "DELETE FROM autosync_exclusions WHERE series_url = ?", (series_url,)
            )


def get_autosync_state():
    with session() as conn:
        rows = conn.execute("SELECT key, value FROM autosync_state").fetchall()
        return {row["key"]: row["value"] for row in rows}


def set_autosync_state(**values):
    with session() as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO autosync_state (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, None if value is None else str(value)),
            )


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------
# Only the hash is stored, so a leaked database does not hand out working keys.
def create_api_key(name, key_hash, prefix, scope, created_by=None, expires_days=None):
    # Expiry is computed by sqlite so it matches the datetime('now') check below
    offset = f"+{int(expires_days)} days" if expires_days else None
    with session() as conn:
        cur = conn.execute(
            "INSERT INTO api_keys (name, key_hash, prefix, scope, created_by, expires_at) "
            "VALUES (?, ?, ?, ?, ?, "
            "CASE WHEN ? IS NULL THEN NULL ELSE datetime('now', ?) END)",
            (name, key_hash, prefix, scope, created_by, offset, offset),
        )
        return cur.lastrowid


def list_api_keys():
    with session() as conn:
        return _rows(
            conn,
            "SELECT id, name, prefix, scope, created_by, created_at, last_used_at, "
            "expires_at, (expires_at IS NOT NULL AND expires_at <= datetime('now')) "
            "AS expired FROM api_keys ORDER BY id",
        )


def verify_api_key(key_hash):
    with session() as conn:
        return _row(
            conn,
            "SELECT id, name, scope FROM api_keys WHERE key_hash = ? "
            "AND (expires_at IS NULL OR expires_at > datetime('now'))",
            (key_hash,),
        )


def touch_api_key(key_id):
    """Record usage. Runs on every API call, so it writes once a minute at most."""
    with session() as conn:
        conn.execute(
            "UPDATE api_keys SET last_used_at = datetime('now') WHERE id = ? AND "
            "(last_used_at IS NULL OR last_used_at < datetime('now', '-60 seconds'))",
            (key_id,),
        )


def delete_api_key(key_id):
    with session() as conn:
        cur = conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        return cur.rowcount > 0
