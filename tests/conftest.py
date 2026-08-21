"""Shared fixtures.

Every test runs against a throwaway config directory, a throwaway database and
a throwaway download folder, so nothing here can touch a real install. None of
these tests reach the network, providers are never called for real.
"""

import os
import shutil
import tempfile
from pathlib import Path

# Has to happen before aniworld is imported: config.py reads this at import
# time to decide where .env, the database and the flask secret live.
_SANDBOX = Path(tempfile.mkdtemp(prefix="aniworld-tests-"))
os.environ["ANIWORLD_INSTALL_FOLDER"] = str(_SANDBOX / "config")

import pytest

from aniworld.web import app as web_app
from aniworld.web import db

# Prefixes wiped between tests. Settings live in the environment, so without
# this a test that flips a setting would change the next one's behaviour.
_OWNED_PREFIXES = ("ANIWORLD_", "MANGAFIRE_")


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_SANDBOX, ignore_errors=True)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Nothing here may talk to aniworld.to or a hoster.

    A test that forgets to stub a fetch would otherwise pass quietly against
    the live site and start failing the day that site changes.
    """
    import socket

    def blocked(*args, **kwargs):
        raise RuntimeError(
            "a test tried to open a network connection, stub the fetch instead"
        )

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Reset every setting and point downloads at a temp folder."""
    for key in list(os.environ):
        if key.startswith(_OWNED_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANIWORLD_INSTALL_FOLDER", str(_SANDBOX / "config"))

    downloads = tmp_path / "downloads"
    downloads.mkdir()
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", str(downloads))
    return downloads


@pytest.fixture(autouse=True)
def no_background_threads(monkeypatch):
    """No test may start the real queue worker or Auto-Sync.

    Both spawn a daemon thread that lives for the rest of the process, and
    ensure_started() only starts one per process, so a single test that calls
    it for real leaks a thread into every test after it. fresh_db repoints
    DB_PATH per test and the worker re-reads it on every poll, so that thread
    then claims rows out of later tests' databases and marks them running and
    then failed. It shows up as an unrelated test failing on the queue order,
    on a different test each run, and only when the timing lines up.
    """
    from aniworld.web import autosync, worker

    monkeypatch.setattr(worker, "ensure_started", lambda: None)
    monkeypatch.setattr(autosync, "ensure_started", lambda: None)


@pytest.fixture(autouse=True)
def fresh_autosync_anchor(monkeypatch):
    """Auto-Sync counts fixed times from when the process first saw them.

    That moment is remembered in a module global, so without this a test that
    looks at the schedule would fix the anchor for every test after it.
    """
    from aniworld.web import autosync

    monkeypatch.setattr(autosync, "_anchored_at", None)


@pytest.fixture
def downloads(clean_env):
    """The default download root for this test."""
    return clean_env


@pytest.fixture(autouse=True)
def fresh_db(clean_env, monkeypatch, tmp_path):
    """A brand new database per test."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "aniworld.db")
    monkeypatch.setattr(db, "_initialized", False)
    db.init_db()
    yield
    monkeypatch.setattr(db, "_initialized", False)


@pytest.fixture
def make_app(monkeypatch):
    """Build a real app without starting the worker or the discord bot."""

    def factory(**kwargs):
        monkeypatch.setattr(web_app, "_start_background_services", lambda: None)
        application = web_app.create_app(**kwargs)
        application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        return application

    return factory


@pytest.fixture
def app(make_app):
    """The usual setup: no accounts, everyone is an admin."""
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_app(make_app):
    return make_app(auth_enabled=True)


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
@pytest.fixture
def queue_item():
    """Put an item in the queue with sensible defaults."""

    def factory(title="Test Anime", episodes=None, **kwargs):
        options = {
            "series_url": f"https://aniworld.to/anime/stream/{title.lower()}",
            "language": "German Dub",
            "provider": "VOE",
        }
        options.update(kwargs)
        return db.add_to_queue(
            title=title,
            episodes=episodes if episodes is not None else ["ep1"],
            **options,
        )

    return factory


@pytest.fixture
def episode_file(downloads):
    """Create a fake downloaded episode and return its path."""

    def factory(title, season, episode, base=None, suffix=".mkv", size=1024):
        root = Path(base) if base else downloads
        folder = root / title / f"Season {season}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{title} S{season:02d}E{episode:03d}{suffix}"
        path.write_bytes(b"x" * size)
        return path

    return factory


@pytest.fixture
def api_key():
    """Mint a working API key and return (raw key, id)."""
    from aniworld.web import apikeys

    def factory(scope="write", name="test key", expires_days=None):
        raw = apikeys.generate()
        key_id = db.create_api_key(
            name=name,
            key_hash=apikeys.hash_key(raw),
            prefix=raw[:10],
            scope=scope,
            expires_days=expires_days,
        )
        return raw, key_id

    return factory
