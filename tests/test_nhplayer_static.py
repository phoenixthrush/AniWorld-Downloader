"""nhplayer's current HTTP challenge resolves before the Chromium fallback."""

import base64
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aniworld.models.hentai_tv import player

PLAYER = "https://nhplayer.com/player.php?vid=opaque-input"
MEDIA = "https://cdn.example/video.mp4?signed=media-token"


def page_html():
    return """
        <span id="random-a" data-first="12345678"></span>
        <input id="random-b" value="abcdefgh">
        <div id="random-c" data-third="87654321"></div>
        <template id="random-d"><p>hgfedcba</p></template>
        <span id="random-e" data-time="1792950000"></span>
        <script>window._pV={vid:"encoded-input",ct:"challenge-input",pid:"page",st:"state"};</script>
        <script src="player-core-v2.php?nonce=fresh"></script>
    """


SCRIPT = """
    function a(){return document.getElementById('random-a')}
    function b(){return document.getElementById('random-b')}
    function c(){return document.getElementById('random-c')}
    function d(){return document.getElementById('random-d')}
    function e(){return document.getElementById('random-e')}
    var parts=[a().getAttribute('data-first'),c().getAttribute('data-third'),e().getAttribute('data-time')];
    var opaqueChallenge='challenge-value';
    var opaqueRequest='request-value';
    var unrelatedFingerprint={sc:scrollEvents};
    var params=new URLSearchParams({sc:opaqueChallenge,rid:opaqueRequest});
"""


def response(text="", payload=None, status=200):
    def raise_for_status():
        if status >= 400:
            raise RuntimeError(f"HTTP {status}")

    return SimpleNamespace(
        text=text, json=lambda: payload, raise_for_status=raise_for_status
    )


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(player.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(
        player.time, "sleep", lambda seconds: setattr(clock, "now", clock.now + seconds)
    )
    return clock


def test_http_resolves_fresh_challenge_without_browser(monkeypatch, clock):
    session = FakeSession(
        [response(page_html()), response(SCRIPT), response(payload={"url": MEDIA})]
    )
    factory = Mock(return_value=session)
    browser = Mock(side_effect=AssertionError("working HTTP path needs no browser"))
    monkeypatch.setattr(player.requests, "Session", factory)
    monkeypatch.setattr(player, "_resolve_browser", browser)

    assert player.resolve_stream_url(PLAYER) == MEDIA
    factory.assert_called_once_with(impersonate="chrome")
    assert [url for url, _ in session.calls] == [
        PLAYER,
        "https://nhplayer.com/player-core-v2.php?nonce=fresh",
        "https://nhplayer.com/get-video-url-v2.php",
    ]
    options = session.calls[-1][1]
    params = options["params"]
    assert params["vid"] == "encoded-input"
    assert params["c"] == "challenge-input"
    assert params["sc"] == "challenge-value"
    assert params["rid"] == "request-value"
    assert params["p4"] == "hgfedcba"
    challenge = "".join(params[key] for key in ("p1", "p2", "p3", "p4", "t"))
    assert hashlib.sha256((challenge + params["pow"]).encode()).digest()[0] == 0
    client = json.loads(base64.b64decode(params["fp"]))
    assert client["t"] >= 800
    assert set(client) == {"t", "b"}
    assert options["headers"]["Referer"] == PLAYER
    assert session.closed
    browser.assert_not_called()


@pytest.mark.parametrize("failure", ["changed-layout", "server-error", "invalid-url"])
def test_http_failure_uses_browser_once_and_closes_session(monkeypatch, clock, failure):
    replies = [response(page_html()), response(SCRIPT)]
    if failure == "changed-layout":
        replies = [response("<html>new player layout</html>")]
    elif failure == "server-error":
        replies.append(response(status=403))
    else:
        replies.append(response(payload={"url": "javascript:alert(1)"}))
    session = FakeSession(replies)
    browser = Mock(return_value=MEDIA)
    monkeypatch.setattr(player.requests, "Session", Mock(return_value=session))
    monkeypatch.setattr(player, "_resolve_browser", browser)

    assert player.resolve_stream_url(PLAYER, timeout=8) == MEDIA
    browser.assert_called_once_with(PLAYER, 8)
    assert session.closed


def test_challenge_layout_changes_are_rejected():
    markup = player._PlayerMarkup()
    markup.feed(page_html())
    with pytest.raises(ValueError, match="layout"):
        player._challenge_fields(markup, "new challenge script")


def test_challenge_timeout_does_not_continue_work(monkeypatch):
    monkeypatch.setattr(
        player.hashlib, "sha256", lambda _: SimpleNamespace(digest=lambda: b"x" * 32)
    )
    monkeypatch.setattr(player.time, "monotonic", lambda: 10)
    with pytest.raises(TimeoutError, match="challenge"):
        player._solve_work("challenge", deadline=9)
