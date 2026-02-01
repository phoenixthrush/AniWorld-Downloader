"""
Database models and utilities for AniWorld Downloader web authentication
"""

import hashlib
import os
import secrets
import sqlite3
from typing import Optional, Dict, List
from pathlib import Path


def get_database_path() -> str:
    """Get the persistent database path based on OS"""
    if os.path.exists("/.dockerenv"):  # 2. Docker environment
        db_dir = "/app/data"
    elif os.name == "nt":  # 2. Windows
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        db_dir = os.path.join(appdata, "aniworld")
    else:  # 3. Linux and others
        db_dir = os.path.expanduser("~/.local/share/aniworld")

    # Ensure directory exists
    Path(db_dir).mkdir(parents=True, exist_ok=True)
    return os.path.join(db_dir, "aniworld.db")


class UserDatabase:
    """SQLite database manager for user authentication"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the user database.

        Args:
            db_path: Path to the SQLite database file (if None, uses system location)
        """
        self.db_path = db_path or get_database_path()
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Create users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    is_admin BOOLEAN NOT NULL DEFAULT 0,
                    is_original_admin BOOLEAN NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)

            # Create sessions table for session management
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_token TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)

            # Create sync_jobs table for auto-sync functionality
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    anime_title TEXT NOT NULL,
                    series_url TEXT NOT NULL,
                    check_interval INTEGER NOT NULL,
                    custom_path TEXT,
                    last_checked TIMESTAMP,
                    last_found_new TIMESTAMP,
                    last_episode_count INTEGER DEFAULT 0,
                    language TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_by INTEGER,
                    FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE CASCADE
                )
            """)

            # Note: download_queue table removed - download status now handled in memory

            conn.commit()

    def _hash_password(self, password: str, salt: str) -> str:
        """
        Hash a password with salt using PBKDF2-HMAC-SHA256 (modern) or SHA256 (legacy).
        New hashes are always PBKDF2.
        """
        # PBKDF2 with 100,000 iterations
        # Result is hex string
        return hashlib.pbkdf2_hmac(
            'sha256', 
            password.encode('utf-8'), 
            salt.encode('utf-8'), 
            100000
        ).hex()

    def _hash_password_legacy(self, password: str, salt: str) -> str:
        """Legacy SHA256 hashing for migration."""
        return hashlib.sha256((password + salt).encode()).hexdigest()

    def create_user(
        self,
        username: str,
        password: str,
        is_admin: bool = False,
        is_original_admin: bool = False,
    ) -> bool:
        """
        Create a new user.

        Args:
            username: Username
            password: Plain text password
            is_admin: Whether user should have admin privileges
            is_original_admin: Whether this is the original admin user

        Returns:
            True if user was created successfully, False otherwise
        """
        try:
            salt = secrets.token_hex(16)
            password_hash = self._hash_password(password, salt)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (username, password_hash, salt, is_admin, is_original_admin)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (username, password_hash, salt, is_admin, is_original_admin),
                )
                conn.commit()
                return True

        except sqlite3.IntegrityError:
            # Username already exists
            return False
        except Exception:
            return False

    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """
        Verify user credentials.

        Args:
            username: Username
            password: Plain text password

        Returns:
            User dictionary if credentials are valid, None otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, username, password_hash, salt, is_admin, is_original_admin
                    FROM users WHERE username = ?
                """,
                    (username,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                user_id, username, stored_hash, salt, is_admin, is_original_admin = row

                # Verify password
                # 1. Try modern hash (PBKDF2)
                verified = False
                needs_update = False
                
                if self._hash_password(password, salt) == stored_hash:
                    verified = True
                # 2. Try legacy hash (SHA256)
                elif self._hash_password_legacy(password, salt) == stored_hash:
                    verified = True
                    needs_update = True
                
                if verified:
                    # Update legacy hash to modern hash if needed
                    if needs_update:
                         new_hash = self._hash_password(password, salt)
                         cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))

                    # Update last login
                    cursor.execute(
                        """
                        UPDATE users SET last_login = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """,
                        (user_id,),
                    )
                    conn.commit()

                    return {
                        "id": user_id,
                        "username": username,
                        "is_admin": bool(is_admin),
                        "is_original_admin": bool(is_original_admin),
                    }

                return None

        except Exception:
            return None

    def create_session(self, user_id: int) -> str:
        """
        Create a new session for a user.

        Args:
            user_id: User ID

        Returns:
            Session token
        """
        session_token = secrets.token_urlsafe(32)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Clean up expired sessions first
            cursor.execute("""
                DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP
            """)

            # Create new session (expires in 30 days)
            cursor.execute(
                """
                INSERT INTO sessions (session_token, user_id, expires_at)
                VALUES (?, ?, datetime('now', '+30 days'))
            """,
                (session_token, user_id),
            )

            conn.commit()

        return session_token

    def get_user_by_session(self, session_token: str) -> Optional[Dict]:
        """
        Get user information by session token.

        Args:
            session_token: Session token

        Returns:
            User dictionary if session is valid, None otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT u.id, u.username, u.is_admin, u.is_original_admin
                    FROM users u
                    JOIN sessions s ON u.id = s.user_id
                    WHERE s.session_token = ? AND s.expires_at > CURRENT_TIMESTAMP
                """,
                    (session_token,),
                )

                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "username": row[1],
                        "is_admin": bool(row[2]),
                        "is_original_admin": bool(row[3]),
                    }

                return None

        except Exception:
            return None

    def delete_session(self, session_token: str) -> bool:
        """
        Delete a session (logout).

        Args:
            session_token: Session token to delete

        Returns:
            True if session was deleted, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM sessions WHERE session_token = ?
                """,
                    (session_token,),
                )
                conn.commit()
                return cursor.rowcount > 0

        except Exception:
            return False

    def get_all_users(self) -> List[Dict]:
        """
        Get all users (admin only).

        Returns:
            List of user dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, username, is_admin, is_original_admin, created_at, last_login
                    FROM users ORDER BY username
                """)

                users = []
                for row in cursor.fetchall():
                    users.append(
                        {
                            "id": row[0],
                            "username": row[1],
                            "is_admin": bool(row[2]),
                            "is_original_admin": bool(row[3]),
                            "created_at": row[4],
                            "last_login": row[5],
                        }
                    )

                return users

        except Exception:
            return []

    def delete_user(self, user_id: int) -> bool:
        """
        Delete a user.

        Args:
            user_id: User ID to delete

        Returns:
            True if user was deleted, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
                conn.commit()
                return cursor.rowcount > 0

        except Exception:
            return False

    def update_user(
        self,
        user_id: int,
        username: str = None,
        password: str = None,
        is_admin: bool = None,
    ) -> bool:
        """
        Update user information.

        Args:
            user_id: User ID to update
            username: New username (optional)
            password: New password (optional)
            is_admin: New admin status (optional)

        Returns:
            True if user was updated, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                updates = []
                params = []

                if username is not None:
                    updates.append("username = ?")
                    params.append(username)

                if password is not None:
                    salt = secrets.token_hex(16)
                    password_hash = self._hash_password(password, salt)
                    updates.append("password_hash = ?")
                    updates.append("salt = ?")
                    params.extend([password_hash, salt])

                if is_admin is not None:
                    updates.append("is_admin = ?")
                    params.append(is_admin)

                if not updates:
                    return True  # Nothing to update

                params.append(user_id)

                cursor.execute(
                    f"""
                    UPDATE users SET {", ".join(updates)}
                    WHERE id = ?
                """,
                    params,
                )

                conn.commit()
                return cursor.rowcount > 0

        except sqlite3.IntegrityError:
            # Username already exists
            return False
        except Exception:
            return False

    def has_users(self) -> bool:
        """
        Check if any users exist in the database.

        Returns:
            True if at least one user exists, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users")
                count = cursor.fetchone()[0]
                return count > 0

        except Exception:
            return False

    def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> bool:
        """
        Change a user's password.

        Args:
            user_id: User ID
            current_password: Current password for verification
            new_password: New password

        Returns:
            True if password was changed successfully, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Get current password hash and salt
                cursor.execute(
                    """
                    SELECT password_hash, salt FROM users WHERE id = ?
                """,
                    (user_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return False

                stored_hash, salt = row

                # Verify current password
                if self._hash_password(current_password, salt) != stored_hash:
                    return False

                # Generate new salt and hash for new password
                new_salt = secrets.token_hex(16)
                new_hash = self._hash_password(new_password, new_salt)

                # Update password
                cursor.execute(
                    """
                    UPDATE users SET password_hash = ?, salt = ?
                    WHERE id = ?
                """,
                    (new_hash, new_salt, user_id),
                )

                conn.commit()
                return cursor.rowcount > 0

        except Exception:
            return False

    def cleanup_expired_sessions(self) -> None:
        """Clean up expired sessions."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM sessions WHERE expires_at < CURRENT_TIMESTAMP
                """)
                conn.commit()

        except Exception:
            pass

    # Sync Job Management Methods

    def create_sync_job(
        self,
        anime_title: str,
        series_url: str,
        check_interval: int,
        language: str,
        provider: str,
        custom_path: str = None,
        created_by: int = None,
    ) -> Optional[int]:
        """
        Create a new sync job.

        Args:
            anime_title: Title of the anime/series
            series_url: URL to the series page
            check_interval: Check interval in hours (1, 2, 4, 8, 12, 24)
            language: Language preference
            provider: Provider preference
            custom_path: Optional custom download path
            created_by: User ID who created this sync job

        Returns:
            Sync job ID if created successfully, None otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO sync_jobs (
                        anime_title, series_url, check_interval, custom_path,
                        language, provider, created_by
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        anime_title,
                        series_url,
                        check_interval,
                        custom_path,
                        language,
                        provider,
                        created_by,
                    ),
                )
                conn.commit()
                return cursor.lastrowid

        except Exception as e:
            import logging

            logging.error(f"Failed to create sync job: {e}")
            return None

    def get_sync_jobs(self, user_id: int = None, enabled_only: bool = False) -> List[Dict]:
        """
        Get sync jobs, optionally filtered by user and enabled status.

        Args:
            user_id: Optional user ID to filter by
            enabled_only: If True, only return enabled sync jobs

        Returns:
            List of sync job dictionaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM sync_jobs WHERE 1=1"
                params = []

                if user_id is not None:
                    query += " AND created_by = ?"
                    params.append(user_id)

                if enabled_only:
                    query += " AND enabled = 1"

                query += " ORDER BY created_at DESC"

                cursor.execute(query, params)

                sync_jobs = []
                for row in cursor.fetchall():
                    sync_jobs.append(
                        {
                            "id": row[0],
                            "anime_title": row[1],
                            "series_url": row[2],
                            "check_interval": row[3],
                            "custom_path": row[4],
                            "last_checked": row[5],
                            "last_found_new": row[6],
                            "last_episode_count": row[7],
                            "language": row[8],
                            "provider": row[9],
                            "created_at": row[10],
                            "enabled": bool(row[11]),
                            "created_by": row[12],
                        }
                    )

                return sync_jobs

        except Exception as e:
            import logging

            logging.error(f"Failed to get sync jobs: {e}")
            return []

    def get_sync_job(self, sync_job_id: int) -> Optional[Dict]:
        """
        Get a specific sync job by ID.

        Args:
            sync_job_id: Sync job ID

        Returns:
            Sync job dictionary if found, None otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM sync_jobs WHERE id = ?", (sync_job_id,))

                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "anime_title": row[1],
                        "series_url": row[2],
                        "check_interval": row[3],
                        "custom_path": row[4],
                        "last_checked": row[5],
                        "last_found_new": row[6],
                        "last_episode_count": row[7],
                        "language": row[8],
                        "provider": row[9],
                        "created_at": row[10],
                        "enabled": bool(row[11]),
                        "created_by": row[12],
                    }

                return None

        except Exception as e:
            import logging

            logging.error(f"Failed to get sync job: {e}")
            return None

    def update_sync_job(
        self,
        sync_job_id: int,
        check_interval: int = None,
        custom_path: str = None,
        enabled: bool = None,
        language: str = None,
        provider: str = None,
    ) -> bool:
        """
        Update a sync job.

        Args:
            sync_job_id: Sync job ID to update
            check_interval: New check interval (optional)
            custom_path: New custom path (optional)
            enabled: New enabled status (optional)
            language: New language preference (optional)
            provider: New provider preference (optional)

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                updates = []
                params = []

                if check_interval is not None:
                    updates.append("check_interval = ?")
                    params.append(check_interval)

                if custom_path is not None:
                    updates.append("custom_path = ?")
                    params.append(custom_path)

                if enabled is not None:
                    updates.append("enabled = ?")
                    params.append(enabled)

                if language is not None:
                    updates.append("language = ?")
                    params.append(language)

                if provider is not None:
                    updates.append("provider = ?")
                    params.append(provider)

                if not updates:
                    return True  # Nothing to update

                params.append(sync_job_id)

                cursor.execute(
                    f"""
                    UPDATE sync_jobs SET {", ".join(updates)}
                    WHERE id = ?
                """,
                    params,
                )

                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            import logging

            logging.error(f"Failed to update sync job: {e}")
            return False

    def update_sync_job_check_status(
        self,
        sync_job_id: int,
        last_episode_count: int = None,
        found_new: bool = False,
    ) -> bool:
        """
        Update sync job check status after checking for new episodes.

        Args:
            sync_job_id: Sync job ID
            last_episode_count: Latest episode count
            found_new: Whether new episodes were found

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if found_new:
                    cursor.execute(
                        """
                        UPDATE sync_jobs
                        SET last_checked = CURRENT_TIMESTAMP,
                            last_found_new = CURRENT_TIMESTAMP,
                            last_episode_count = ?
                        WHERE id = ?
                    """,
                        (last_episode_count, sync_job_id),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE sync_jobs
                        SET last_checked = CURRENT_TIMESTAMP,
                            last_episode_count = ?
                        WHERE id = ?
                    """,
                        (last_episode_count, sync_job_id),
                    )

                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            import logging

            logging.error(f"Failed to update sync job check status: {e}")
            return False

    def delete_sync_job(self, sync_job_id: int) -> bool:
        """
        Delete a sync job.

        Args:
            sync_job_id: Sync job ID to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM sync_jobs WHERE id = ?", (sync_job_id,))
                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            import logging

            logging.error(f"Failed to delete sync job: {e}")
            return False

