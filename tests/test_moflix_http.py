"""Moflix challenges use Chromium without hiding other HTTP failures."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aniworld.models.moflix_stream import http

URL = http.BASE_URL + "/api/v1/titles?perPage=24"


def response(status=200, challenge=False):
    result = http.requests.Response()
    result.status_code = status
    result.ok = 200 <= status < 400
    if challenge:
        result.headers["cf-mitigated"] = "challenge"
    return result


@pytest.mark.parametrize(
    "status,challenge", [(200, False), (403, False), (403, True), (503, True)]
)
def test_only_cloudflare_challenges_use_the_browser(monkeypatch, status, challenge):
    original = response(status, challenge)
    get = Mock(return_value=original)
    browser = Mock(return_value=response())
    monkeypatch.setattr(http.requests, "get", get)
    monkeypatch.setattr(http, "_browser_get", browser)
    result = http.get_response(URL, {"session": "test"}, "csrf-test")
    assert result is (browser.return_value if challenge else original)
    assert get.call_args.kwargs["headers"]["X-XSRF-TOKEN"] == "csrf-test"
    assert get.call_args.kwargs["cookies"] == {"session": "test"}
    assert browser.call_count == int(challenge)


def test_rate_limits_retry_without_starting_a_browser(monkeypatch):
    success = response()
    get = Mock(side_effect=[response(429), response(429), success])
    sleep = Mock()
    browser = Mock()
    monkeypatch.setattr(http.requests, "get", get)
    monkeypatch.setattr(http.time, "sleep", sleep)
    monkeypatch.setattr(http, "_browser_get", browser)
    assert http.get_response(URL) is success
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]
    browser.assert_not_called()


def test_rate_limit_retries_are_bounded(monkeypatch):
    limited = response(429)
    get = Mock(return_value=limited)
    monkeypatch.setattr(http.requests, "get", get)
    monkeypatch.setattr(http.time, "sleep", lambda seconds: None)
    assert http.get_response(URL) is limited
    assert get.call_count == 3


@pytest.mark.parametrize(
    "outcome", ["success", "forbidden", "navigation-error", "challenge-timeout"]
)
def test_browser_response_and_cleanup(monkeypatch, outcome):
    from patchright import sync_api

    from aniworld import autodeps
    from aniworld.playwright import captcha

    page = Mock()
    page.evaluate.return_value = {
        "url": URL,
        "status": 403 if outcome == "forbidden" else 200,
        "reason": "Forbidden" if outcome == "forbidden" else "OK",
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"pagination": {"data": [{"id": 42}]}}),
    }
    if outcome == "navigation-error":
        page.goto.side_effect = RuntimeError("navigation failed")
    handle = SimpleNamespace(context=Mock(), close=Mock())
    handle.context.new_page.return_value = page
    runtime = Mock()
    runtime.return_value.__enter__ = Mock()
    runtime.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(sync_api, "sync_playwright", runtime)
    monkeypatch.setattr(autodeps, "_ensure_xvfb", Mock())
    monkeypatch.setattr(captcha, "_launch_browser_context", lambda *a, **k: handle)
    monkeypatch.setattr(captcha, "_sync_session_user_agent", Mock())
    monkeypatch.setattr(captcha, "_inject_session_cookies", Mock())
    monkeypatch.setattr(captcha, "_export_session_cookies", Mock())
    monkeypatch.setattr(
        captcha, "_is_captcha_page_dom", lambda page: outcome == "challenge-timeout"
    )
    monkeypatch.setattr(http.time, "monotonic", Mock(side_effect=[0, 31]))

    if outcome in ("navigation-error", "challenge-timeout"):
        with pytest.raises(
            RuntimeError, match="navigation failed|blocked by Cloudflare"
        ):
            http._browser_get(URL)
    else:
        result = http._browser_get(URL)
        assert result.json()["pagination"]["data"] == [{"id": 42}]
        if outcome == "forbidden":
            with pytest.raises(http.requests.exceptions.HTTPError):
                result.raise_for_status()
        else:
            result.raise_for_status()
        assert page.evaluate.call_args.args[1] == URL
        assert page.evaluate.call_args.kwargs["isolated_context"] is False
    handle.close.assert_called_once()


def test_browser_timeout_override_is_used(monkeypatch):
    from contextlib import contextmanager

    from aniworld.playwright import captcha

    page = Mock()
    closed = Mock()

    @contextmanager
    def browser(url):
        try:
            yield Mock(), page
        finally:
            closed()

    monkeypatch.setenv("ANIWORLD_CAPTCHA_TIMEOUT", "5")
    monkeypatch.setattr(captcha, "_browser", browser)
    monkeypatch.setattr(captcha, "_is_captcha_page_dom", lambda page: True)
    monkeypatch.setattr(http.time, "monotonic", Mock(side_effect=[0, 6]))
    with pytest.raises(RuntimeError, match="blocked by Cloudflare"):
        http._browser_get(URL)
    page.wait_for_timeout.assert_not_called()
    closed.assert_called_once()
