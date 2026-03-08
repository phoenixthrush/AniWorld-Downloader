import os
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from ..config import ANIWORLD_CONFIG_DIR
from ..logger import get_logger

logger = get_logger(__name__)

DB_PATH = ANIWORLD_CONFIG_DIR / "aniworld.db"

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin', 'user')),
    auth_method TEXT NOT NULL DEFAULT 'local',
    sso_subject TEXT,
    sso_issuer TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_SSO_INDEX = """\
CREATE UNIQUE INDEX IF NOT EXISTS idx_sso_identity
ON users (sso_issuer, sso_subject)
WHERE sso_issuer IS NOT NULL AND sso_subject IS NOT NULL;
"""


def get_db():
    ANIWORLD_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_db(conn):
    rows = conn.execute("PRAGMA table_info(users)").fetchall()
    columns = {r["name"] for r in rows}

    if "auth_method" not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN auth_method TEXT NOT NULL DEFAULT 'local'"
        )
    if "sso_subject" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN sso_subject TEXT")
    if "sso_issuer" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN sso_issuer TEXT")

    conn.execute(_CREATE_SSO_INDEX)
    conn.commit()


def init_db():
    conn = get_db()
    try:
        conn.execute(_CREATE_TABLE)
        conn.execute(_CREATE_SSO_INDEX)
        conn.commit()
        _migrate_db(conn)
    finally:
        conn.close()

    if not has_any_admin():
        env_user = os.environ.get("ANIWORLD_WEB_ADMIN_USER", "").strip()
        env_pass = os.environ.get("ANIWORLD_WEB_ADMIN_PASS", "").strip()
        if env_user and env_pass:
            create_user(env_user, env_pass, role="admin")
            logger.info("Auto-created admin user '%s' from environment", env_user)


def has_any_admin():
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin'"
        ).fetchone()
        return row["cnt"] > 0
    finally:
        conn.close()


def create_user(username, password, role="user"):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def verify_user(username, password):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, role, auth_method FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return None, "Invalid username or password."
        if row["auth_method"] != "local":
            return None, "This account uses SSO. Please use the SSO login button."
        if check_password_hash(row["password_hash"], password):
            return {
                "id": row["id"],
                "username": row["username"],
                "role": row["role"],
            }, None
        return None, "Invalid username or password."
    finally:
        conn.close()


def find_or_create_sso_user(
    issuer, subject, username, admin_username=None, admin_subject=None
):
    def _should_be_admin():
        if admin_subject and subject == admin_subject:
            return True
        if admin_username and username == admin_username:
            return True
        return False

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, role FROM users WHERE sso_issuer = ? AND sso_subject = ?",
            (issuer, subject),
        ).fetchone()

        if row:
            user = {"id": row["id"], "username": row["username"], "role": row["role"]}
            if _should_be_admin() and row["role"] != "admin":
                conn.execute(
                    "UPDATE users SET role = 'admin' WHERE id = ?", (row["id"],)
                )
                conn.commit()
                user["role"] = "admin"
            return user

        # Check for username conflict with local users
        existing = conn.execute(
            "SELECT id, auth_method FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if existing:
            raise ValueError(
                f"Username '{username}' is already taken by a local account."
            )

        role = "admin" if _should_be_admin() else "user"
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, auth_method, sso_subject, sso_issuer) "
            "VALUES (?, ?, ?, 'oidc', ?, ?)",
            (username, "", role, subject, issuer),
        )
        conn.commit()
        return {"id": cur.lastrowid, "username": username, "role": role}
    finally:
        conn.close()


def list_users():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, username, role, auth_method, created_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_user(user_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return False, "User not found"
        if row["role"] == "admin":
            cnt = conn.execute(
                "SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin'"
            ).fetchone()["cnt"]
            if cnt <= 1:
                return False, "Cannot delete the last admin"
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return True, None
    finally:
        conn.close()


def update_user_role(user_id, new_role):
    if new_role not in ("admin", "user"):
        return False, "Invalid role"
    conn = get_db()
    try:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return False, "User not found"
        if row["role"] == "admin" and new_role != "admin":
            cnt = conn.execute(
                "SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin'"
            ).fetchone()["cnt"]
            if cnt <= 1:
                return False, "Cannot demote the last admin"
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        conn.commit()
        return True, None
    finally:
        conn.close()


# ===== Download Queue =====

_CREATE_QUEUE_TABLE = """\
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
    current_episode INTEGER NOT NULL DEFAULT 0,
    current_url TEXT,
    errors TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
"""


def init_queue_db():
    ANIWORLD_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        conn.execute(_CREATE_QUEUE_TABLE)
        # Add position column for queue reordering (migration for existing DBs)
        try:
            conn.execute(
                "ALTER TABLE download_queue ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
            )
            # Backfill: set position = id for existing rows
            conn.execute("UPDATE download_queue SET position = id WHERE position = 0")
        except Exception:
            pass  # column already exists
        # Add custom_path_id column (migration for existing DBs)
        try:
            conn.execute("ALTER TABLE download_queue ADD COLUMN custom_path_id INTEGER")
        except Exception:
            pass  # column already exists
        # Add source column (migration for existing DBs) - marks origin: 'manual' or 'sync'
        try:
            conn.execute(
                "ALTER TABLE download_queue ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
            )
        except Exception:
            pass  # column already exists
        conn.commit()
    finally:
        conn.close()


def add_to_queue(
    title,
    series_url,
    episodes,
    language,
    provider,
    username=None,
    custom_path_id=None,
    source="manual",
):
    import json

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO download_queue (title, series_url, episodes, total_episodes, language, provider, username, custom_path_id, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            ),
        )
        row_id = cur.lastrowid
        conn.execute(
            "UPDATE download_queue SET position = ? WHERE id = ?", (row_id, row_id)
        )
        conn.commit()
        return row_id
    finally:
        conn.close()


def is_series_queued_or_running(series_url, language=None):
    """Check if a series already has a queued or running item in the download queue."""
    conn = get_db()
    try:
        query = (
            "SELECT COUNT(*) AS cnt FROM download_queue "
            "WHERE series_url = ? AND status IN ('queued', 'running')"
        )
        params = [series_url]
        if language:
            query += " AND language = ?"
            params.append(language)

        row = conn.execute(query, tuple(params)).fetchone()
        return row["cnt"] > 0
    finally:
        conn.close()


def get_queue():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM download_queue ORDER BY position ASC, id ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_next_queued():
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM download_queue WHERE status = 'queued' "
            "ORDER BY position ASC, id ASC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def move_queue_item(queue_id, direction):
    """Swap position of a queued item with its neighbor. direction: 'up' or 'down'."""
    conn = get_db()
    try:
        item = conn.execute(
            "SELECT id, position FROM download_queue WHERE id = ? AND status = 'queued'",
            (queue_id,),
        ).fetchone()
        if not item:
            return False, "Item not found or not queued"

        if direction == "up":
            neighbor = conn.execute(
                "SELECT id, position FROM download_queue "
                "WHERE status = 'queued' AND position < ? "
                "ORDER BY position DESC LIMIT 1",
                (item["position"],),
            ).fetchone()
        else:
            neighbor = conn.execute(
                "SELECT id, position FROM download_queue "
                "WHERE status = 'queued' AND position > ? "
                "ORDER BY position ASC LIMIT 1",
                (item["position"],),
            ).fetchone()

        if not neighbor:
            return False, "Already at the edge"

        # Swap positions
        conn.execute(
            "UPDATE download_queue SET position = ? WHERE id = ?",
            (neighbor["position"], item["id"]),
        )
        conn.execute(
            "UPDATE download_queue SET position = ? WHERE id = ?",
            (item["position"], neighbor["id"]),
        )
        conn.commit()
        return True, None
    finally:
        conn.close()


def get_running():
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM download_queue WHERE status = 'running' LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_queue_progress(queue_id, current_episode, current_url):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE download_queue SET current_episode = ?, current_url = ? WHERE id = ?",
            (current_episode, current_url, queue_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_queue_status(queue_id, status):
    conn = get_db()
    try:
        if status in ("completed", "failed"):
            conn.execute(
                "UPDATE download_queue SET status = ?, completed_at = datetime('now') WHERE id = ?",
                (status, queue_id),
            )
        else:
            conn.execute(
                "UPDATE download_queue SET status = ? WHERE id = ?",
                (status, queue_id),
            )
        conn.commit()
    finally:
        conn.close()


def update_queue_errors(queue_id, errors_json):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE download_queue SET errors = ? WHERE id = ?",
            (errors_json, queue_id),
        )
        conn.commit()
    finally:
        conn.close()


def cancel_queue_item(queue_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT status FROM download_queue WHERE id = ?", (queue_id,)
        ).fetchone()
        if not row:
            return False, "Item not found"
        if row["status"] != "running":
            return False, "Can only cancel running items"
        conn.execute(
            "UPDATE download_queue SET status = 'cancelled' WHERE id = ?",
            (queue_id,),
        )
        conn.commit()
        return True, None
    finally:
        conn.close()


def is_queue_cancelled(queue_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT status FROM download_queue WHERE id = ?", (queue_id,)
        ).fetchone()
        return row and row["status"] == "cancelled"
    finally:
        conn.close()


def remove_from_queue(queue_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT status FROM download_queue WHERE id = ?", (queue_id,)
        ).fetchone()
        if not row:
            return False, "Item not found"
        if row["status"] != "queued":
            return False, "Can only remove queued items"
        conn.execute("DELETE FROM download_queue WHERE id = ?", (queue_id,))
        conn.commit()
        return True, None
    finally:
        conn.close()


def delete_completed_queue_item(queue_id):
    """Delete a queue item only if its status is 'completed'. Used by auto-sync cleanup."""
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM download_queue WHERE id = ? AND status = 'completed'",
            (queue_id,),
        )
        conn.commit()
    finally:
        conn.close()


def clear_completed():
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM download_queue WHERE status IN ('completed', 'failed', 'cancelled')"
        )
        conn.commit()
    finally:
        conn.close()


# ===== Custom Download Paths =====

_CREATE_CUSTOM_PATHS_TABLE = """\
CREATE TABLE IF NOT EXISTS custom_paths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL
);
"""


def init_custom_paths_db():
    ANIWORLD_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        conn.execute(_CREATE_CUSTOM_PATHS_TABLE)
        conn.commit()
    finally:
        conn.close()


def get_custom_paths():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, path FROM custom_paths ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_custom_path(name, path):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO custom_paths (name, path) VALUES (?, ?)",
            (name, path),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def remove_custom_path(path_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM custom_paths WHERE id = ?", (path_id,))
        conn.commit()
    finally:
        conn.close()


def get_custom_path_by_id(path_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, path FROM custom_paths WHERE id = ?", (path_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ===== Auto-Sync Jobs =====

_CREATE_AUTOSYNC_TABLE = """\
CREATE TABLE IF NOT EXISTS autosync_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    series_url TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'German Dub',
    provider TEXT NOT NULL DEFAULT 'VOE',
    custom_path_id INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    added_by TEXT,
    last_check TEXT,
    last_new_found TEXT,
    episodes_found INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_autosync_db():
    ANIWORLD_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        conn.execute(_CREATE_AUTOSYNC_TABLE)
        # Add UNIQUE index on series_url (migration for existing DBs)
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_autosync_series_url "
                "ON autosync_jobs (series_url)"
            )
        except sqlite3.IntegrityError:
            # Duplicates already exist — deduplicate keeping the lowest id
            conn.execute(
                "DELETE FROM autosync_jobs WHERE id NOT IN "
                "(SELECT MIN(id) FROM autosync_jobs GROUP BY series_url)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_autosync_series_url "
                "ON autosync_jobs (series_url)"
            )
        conn.commit()
    finally:
        conn.close()


def add_autosync_job(
    title, series_url, language, provider, custom_path_id=None, added_by=None
):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO autosync_jobs "
            "(title, series_url, language, provider, custom_path_id, added_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, series_url, language, provider, custom_path_id, added_by),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_autosync_jobs(username=None):
    """Return all sync jobs. If *username* is given, only that user's jobs."""
    conn = get_db()
    try:
        if username:
            rows = conn.execute(
                "SELECT * FROM autosync_jobs WHERE added_by = ? ORDER BY id",
                (username,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM autosync_jobs ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_autosync_job(job_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM autosync_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_autosync_by_url(series_url):
    """Return the first sync job that matches *series_url*, or None."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM autosync_jobs WHERE series_url = ? LIMIT 1",
            (series_url,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_autosync_job(job_id, **fields):
    """Update arbitrary columns on a sync job."""
    if not fields:
        return
    allowed = {
        "title",
        "series_url",
        "language",
        "provider",
        "custom_path_id",
        "enabled",
        "last_check",
        "last_new_found",
        "episodes_found",
    }
    filtered = {k: v for k, v in fields.items() if k in allowed}
    if not filtered:
        return
    set_clause = ", ".join(f"{k} = ?" for k in filtered)
    values = list(filtered.values()) + [job_id]
    conn = get_db()
    try:
        conn.execute(f"UPDATE autosync_jobs SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def remove_autosync_job(job_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM autosync_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if not row:
            return False, "Job not found"
        conn.execute("DELETE FROM autosync_jobs WHERE id = ?", (job_id,))
        conn.commit()
        return True, None
    finally:
        conn.close()


# ===== Statistics =====


def get_sync_stats():
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) AS cnt FROM autosync_jobs").fetchone()[
            "cnt"
        ]
        enabled = conn.execute(
            "SELECT COUNT(*) AS cnt FROM autosync_jobs WHERE enabled = 1"
        ).fetchone()["cnt"]
        disabled = total - enabled
        last_check = conn.execute(
            "SELECT MAX(last_check) AS lc FROM autosync_jobs"
        ).fetchone()["lc"]
        last_new = conn.execute(
            "SELECT MAX(last_new_found) AS ln FROM autosync_jobs"
        ).fetchone()["ln"]
        total_eps = conn.execute(
            "SELECT COALESCE(SUM(episodes_found), 0) AS s FROM autosync_jobs"
        ).fetchone()["s"]
        jobs = conn.execute(
            "SELECT id, title, series_url, language, provider, enabled, "
            "last_check, last_new_found, episodes_found, added_by, created_at "
            "FROM autosync_jobs ORDER BY id"
        ).fetchall()
        return {
            "total_jobs": total,
            "enabled": enabled,
            "disabled": disabled,
            "last_check": last_check,
            "last_new_found": last_new,
            "total_episodes_found": total_eps,
            "jobs": [dict(r) for r in jobs],
        }
    finally:
        conn.close()


def get_queue_stats():
    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) AS cnt FROM download_queue").fetchone()[
            "cnt"
        ]
        by_status = {}
        for row in conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM download_queue GROUP BY status"
        ).fetchall():
            by_status[row["status"]] = row["cnt"]
        running = conn.execute(
            "SELECT title, current_episode, total_episodes FROM download_queue "
            "WHERE status = 'running' LIMIT 1"
        ).fetchone()
        return {
            "total": total,
            "by_status": by_status,
            "currently_running": dict(running) if running else None,
        }
    finally:
        conn.close()


def get_general_stats():
    conn = get_db()
    try:
        total_downloads = conn.execute(
            "SELECT COUNT(*) AS cnt FROM download_queue "
            "WHERE status IN ('completed', 'failed')"
        ).fetchone()["cnt"]
        completed = conn.execute(
            "SELECT COUNT(*) AS cnt FROM download_queue WHERE status = 'completed'"
        ).fetchone()["cnt"]
        failed = conn.execute(
            "SELECT COUNT(*) AS cnt FROM download_queue WHERE status = 'failed'"
        ).fetchone()["cnt"]
        total_episodes = conn.execute(
            "SELECT COALESCE(SUM(total_episodes), 0) AS s FROM download_queue "
            "WHERE status = 'completed'"
        ).fetchone()["s"]
        last_24h = conn.execute(
            "SELECT COUNT(*) AS cnt FROM download_queue "
            "WHERE status = 'completed' "
            "AND completed_at >= datetime('now', '-1 day')"
        ).fetchone()["cnt"]
        # Average duration (completed items with both timestamps)
        avg_dur = conn.execute(
            "SELECT AVG("
            "  (julianday(completed_at) - julianday(created_at)) * 86400"
            ") AS avg_s FROM download_queue "
            "WHERE status = 'completed' AND completed_at IS NOT NULL"
        ).fetchone()["avg_s"]
        # Most downloaded titles
        top_titles = conn.execute(
            "SELECT title, COUNT(*) AS cnt FROM download_queue "
            "WHERE status = 'completed' GROUP BY title "
            "ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
        # Episodes per language
        by_language = conn.execute(
            "SELECT language, COUNT(*) AS cnt, "
            "COALESCE(SUM(total_episodes), 0) AS eps "
            "FROM download_queue WHERE status = 'completed' "
            "GROUP BY language ORDER BY cnt DESC"
        ).fetchall()
        # Anime vs Series (heuristic: aniworld.to = anime, s.to = series)
        anime_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM download_queue "
            "WHERE status = 'completed' AND series_url LIKE '%aniworld.to%'"
        ).fetchone()["cnt"]
        series_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM download_queue "
            "WHERE status = 'completed' AND series_url LIKE '%s.to%'"
        ).fetchone()["cnt"]
        return {
            "total_downloads": total_downloads,
            "completed": completed,
            "failed": failed,
            "total_episodes": total_episodes,
            "last_24h_completed": last_24h,
            "average_duration_seconds": round(avg_dur, 1) if avg_dur else None,
            "top_titles": [
                {"title": r["title"], "count": r["cnt"]} for r in top_titles
            ],
            "by_language": [
                {"language": r["language"], "downloads": r["cnt"], "episodes": r["eps"]}
                for r in by_language
            ],
            "anime_downloads": anime_count,
            "series_downloads": series_count,
        }
    finally:
        conn.close()
