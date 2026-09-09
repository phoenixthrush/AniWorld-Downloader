"""Session continuity regressions for issue #285; no live provider requests."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import niquests
import pytest

from aniworld import config
from aniworld.models.common import hls
from aniworld.playwright import captcha


@pytest.fixture
def session(monkeypatch):
    session = niquests.Session()
    monkeypatch.setattr(config, "GLOBAL_SESSION", session)
    return session


def test_browser_cookie_roundtrip_preserves_scope(session):
    cookie = {
        "name": "cf_clearance",
        "value": "clearance",
        "domain": ".hanime.tv",
        "path": "/videos",
        "secure": True,
        "expires": 4102444800,
        "httpOnly": True,
    }
    browser = Mock()
    browser.cookies.return_value = [cookie]
    captcha._export_session_cookies(browser)
    stored = next(iter(session.cookies))
    assert stored.domain == ".hanime.tv"
    assert stored.path == "/videos"
    assert stored.secure
    assert stored.expires == 4102444800
    browser.cookies.return_value = []
    captcha._inject_session_cookies(browser, "https://hanime.tv/videos/example")
    injected = browser.add_cookies.call_args.args[0][0]
    assert injected["domain"] == ".hanime.tv"
    assert injected["path"] == "/videos"
    assert injected["expires"] == 4102444800
    assert injected["secure"]


def test_cookie_injection_does_not_copy_foreign_or_expired_cookies(session):
    session.cookies.set("foreign", "secret", domain="other.example")
    session.cookies.set("expired", "old", domain="hanime.tv", expires=1)
    session.cookies.set("global", "unscoped")
    browser = Mock()
    browser.cookies.return_value = []
    captcha._inject_session_cookies(browser, "https://hanime.tv/")
    browser.add_cookies.assert_not_called()


def test_persistent_browser_cookie_wins_over_http_cookie(session):
    session.cookies.set("cf_clearance", "stale", domain=".hanime.tv", path="/")
    browser = Mock()
    browser.cookies.return_value = [
        {"name": "cf_clearance", "value": "fresh", "domain": ".hanime.tv", "path": "/"}
    ]
    captcha._inject_session_cookies(browser, "https://hanime.tv/")
    browser.add_cookies.assert_not_called()


def test_host_only_cookie_is_not_injected_into_subdomain(session):
    browser = Mock()
    browser.cookies.return_value = [
        {"name": "private", "value": "secret", "domain": "hanime.tv", "path": "/"}
    ]
    captcha._export_session_cookies(browser)
    assert not next(iter(session.cookies)).domain_specified
    browser.cookies.return_value = []
    captcha._inject_session_cookies(browser, "https://auth.hanime.tv/")
    browser.add_cookies.assert_not_called()


def test_hls_worker_receives_refreshed_scoped_cookies(session, monkeypatch):
    monkeypatch.setattr(hls, "_thread_local", SimpleNamespace())
    session.cookies.set("cf_clearance", "old", domain=".hanime.tv", path="/")
    worker = hls._session()
    session.cookies.set("cf_clearance", "new", domain=".hanime.tv", path="/")
    assert hls._session() is worker
    assert worker.cookies.get("cf_clearance", domain=".hanime.tv", path="/") == "new"


@pytest.fixture
def handshake(monkeypatch, session):
    from patchright import sync_api

    from aniworld import autodeps

    browser = Mock()
    browser.context.cookies.return_value = []
    page = browser.context.new_page.return_value
    monkeypatch.setattr(sync_api, "sync_playwright", MagicMock())
    monkeypatch.setattr(autodeps, "_ensure_xvfb", lambda: None)
    monkeypatch.setattr(captcha, "_launch_browser_context", lambda *a, **kw: browser)
    monkeypatch.setattr(captcha, "_attach_debug_listeners", Mock())
    monkeypatch.setattr(captcha, "_sync_session_user_agent", Mock())
    return browser, page


def test_handshake_ignores_foreign_token_and_exports_cookies(handshake, session):
    browser, page = handshake
    cookie = {"name": "auth", "value": "fresh", "domain": ".hanime.tv", "path": "/"}

    def navigate(*args, **kwargs):
        capture = page.on.call_args.args[1]
        capture(
            SimpleNamespace(
                status=200, url="https://ads.example/", header_value=lambda _: "wrong"
            )
        )
        capture(
            SimpleNamespace(
                status=200,
                url="https://auth.hanime.tv/",
                header_value=lambda _: "token",
            )
        )
        browser.context.cookies.return_value = [cookie]

    page.goto.side_effect = navigate
    assert captcha.playwright_get_hanime_manifest_token("https://hanime.tv/") == "token"
    assert session.cookies.get("auth") == "fresh"
    browser.close.assert_called_once()


def test_handshake_releases_profile_after_navigation_failure(handshake):
    browser, page = handshake
    page.goto.side_effect = RuntimeError("navigation failed")
    with pytest.raises(RuntimeError, match="navigation failed"):
        captcha.playwright_get_hanime_manifest_token("https://hanime.tv/")
    browser.close.assert_called_once()


def test_existing_clearance_does_not_finish_active_challenge(handshake, monkeypatch):
    browser, page = handshake
    browser.context.cookies.return_value = [
        {"name": "cf_clearance", "value": "stale", "domain": ".hanime.tv", "path": "/"}
    ]
    page.frames = []
    page.url = "https://hanime.tv/videos/example"
    dom = Mock(side_effect=[True, False])
    solver = Mock()
    solver.ready_to_submit.return_value = False
    monkeypatch.setattr(captcha, "_is_captcha_page_dom", dom)
    monkeypatch.setattr(captcha, "_ChallengeSolver", lambda: solver)
    monkeypatch.setattr(captcha, "_focus_page", Mock())
    monkeypatch.setattr(captcha._time, "sleep", Mock())
    assert captcha._solve_captcha_cli(page.url) == page.url
    assert dom.call_count == 2
    solver.ready_to_submit.assert_called_once()


def test_hanime_download_passes_browser_headers_to_ffmpeg(
    session, monkeypatch, tmp_path
):
    from aniworld.models.common import common

    session.headers["User-Agent"] = "Browser test UA"
    parallel = Mock(side_effect=hls.HLSUnsupported("fallback"))
    fallback = Mock()
    monkeypatch.setattr(hls, "download_hls_parallel", parallel)
    monkeypatch.setattr(hls, "cleanup_temp_files", Mock())
    monkeypatch.setattr(common, "_download_full_stream", fallback)
    monkeypatch.setattr(common, "_finalize_episode", Mock())
    common._download_hls_stream(
        tmp_path / "episode.mkv", "https://cdn.example/video.m3u8", "Episode"
    )
    assert parallel.call_args.kwargs["headers"]["User-Agent"] == "Browser test UA"
    ffmpeg_options = fallback.call_args.args[2]
    assert "User-Agent: Browser test UA\r\n" in ffmpeg_options["headers"]
    assert "Referer: https://hanime.tv/\r\n" in ffmpeg_options["headers"]
