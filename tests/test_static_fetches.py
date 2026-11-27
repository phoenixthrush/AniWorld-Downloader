"""Static extraction succeeds before browser fallbacks, with no live requests."""

import base64
import codecs
import json
from types import SimpleNamespace
from unittest.mock import Mock

import niquests
import pytest
from curl_cffi import requests

from aniworld.extractors.provider import voe


def test_voe_request_preserves_scoped_cookies(monkeypatch):
    session = niquests.Session()
    session.cookies.set("clearance", "old", domain=".example.org", path="/player")
    cookies = requests.Cookies()
    cookies.set("clearance", "new", domain=".example.org", path="/player")
    result = SimpleNamespace(
        cookies=cookies,
        text="player",
        url="https://example.org/player",
        status_code=200,
    )
    fetch = Mock(return_value=result)
    monkeypatch.setattr(voe, "GLOBAL_SESSION", session)
    monkeypatch.setattr(voe.requests, "get", fetch)

    assert voe._voe_get(
        "https://example.org/player", {"User-Agent": "browser-agent"}, 7
    ) == ("player", "https://example.org/player", 200)
    options = fetch.call_args.kwargs
    assert options["impersonate"] == "chrome"
    assert options["timeout"] == 7
    assert options["headers"]["User-Agent"] == "browser-agent"
    assert options["cookies"] is session.cookies
    stored = next(iter(session.cookies))
    assert (stored.value, stored.domain, stored.path) == (
        "new",
        ".example.org",
        "/player",
    )


@pytest.mark.parametrize("array", [False, True])
def test_voe_json_payload_resolves_without_browser(monkeypatch, array):
    source = "https://cdn.example/video.m3u8?token=example"
    inner = base64.b64encode(json.dumps({"source": source}).encode()).decode()[::-1]
    shifted = "".join(chr(ord(char) + 3) for char in inner)
    encoded = codecs.encode(base64.b64encode(shifted.encode()).decode(), "rot_13")
    payload = json.dumps([encoded] if array else encoded)
    html = (
        '<script type="application/json">not-json</script>'
        '<script type="application/json">[null, {}, "broken"]</script>'
        f"<script id='player-data' type = 'application/json' nonce='test'>{payload}</script>"
    )
    fetch = Mock(return_value=(html, "https://voe.sx/e/example", 200))
    browser = Mock(side_effect=AssertionError("static VOE data needs no browser"))
    monkeypatch.setattr(voe, "_voe_get", fetch)
    monkeypatch.setattr(voe, "solve_captcha_page", browser)

    assert voe.get_direct_link_from_voe("https://voe.sx/e/example") == source
    fetch.assert_called_once()
    browser.assert_not_called()


def _voe_player(source):
    inner = base64.b64encode(json.dumps({"source": source}).encode()).decode()[::-1]
    shifted = "".join(chr(ord(char) + 3) for char in inner)
    encoded = codecs.encode(base64.b64encode(shifted.encode()).decode(), "rot_13")
    return f'<script type="application/json">{json.dumps(encoded)}</script>'


@pytest.mark.parametrize("redirect", [False, True])
def test_voe_uses_the_page_the_browser_loaded_after_a_challenge(monkeypatch, redirect):
    # DDoS-Guard keeps challenging the HTTP client even after the browser passed.
    source = "https://cdn.example/video.m3u8?token=example"
    player = _voe_player(source)
    embed = "https://voe.sx/e/example"
    mirror = "https://mirror.example/e/example"
    challenge = ("<title>DDoS-Guard</title>Checking your browser", embed, 403)
    fetch = Mock(return_value=challenge)
    pages = {embed: f"window.location.href = '{mirror}';" if redirect else player}
    pages[mirror] = player
    browser = Mock(side_effect=pages.get)
    monkeypatch.setattr(voe, "_voe_get", fetch)
    monkeypatch.setattr(voe, "solve_captcha_page", browser)

    assert voe.get_direct_link_from_voe(embed) == source
    expected = [embed, mirror] if redirect else [embed]
    assert [call.args[0] for call in browser.call_args_list] == expected
    assert fetch.call_count == len(expected)
