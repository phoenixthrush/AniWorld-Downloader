"""Hanime's public HTTP handshake replaces Chromium on the working path."""

import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock

import niquests
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from curl_cffi import requests

from aniworld.extractors.provider import hanime_tv as extractor

MANIFEST = {
    "sources": [
        {"kind": "normal", "height": 720, "src": "/hls/example"},
    ]
}


def token(payload):
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    iv = b"0123456789ab"
    data = AESGCM(extractor._HANIME_AES_KEY).encrypt(
        iv, json.dumps(payload).encode(), extractor._HANIME_AES_HEADER
    )
    return encode(
        json.dumps(
            {
                "iv": encode(iv),
                "data": encode(data[:-16]),
                "tag": encode(data[-16:]),
            }
        ).encode()
    )


def response(payload=None, headers=None, failed=False):
    return SimpleNamespace(
        json=lambda: payload,
        headers=headers or {},
        raise_for_status=Mock(side_effect=RuntimeError("HTTP 403") if failed else None),
    )


@pytest.fixture
def handshake(monkeypatch):
    global_session = niquests.Session()
    global_session.cookies.set("session", "old", domain=".hanime.tv", path="/")
    session = Mock()
    session.__enter__ = Mock(return_value=session)
    session.__exit__ = Mock(return_value=False)
    session.cookies = requests.Cookies()
    session.cookies.set("session", "fresh", domain=".hanime.tv", path="/")
    session.get.return_value = response({"csrf_token": "csrf-test"})
    session.post.return_value = response(headers={"x-token": token(MANIFEST)})
    factory = Mock(return_value=session)
    browser = Mock(return_value=token(MANIFEST))
    monkeypatch.setattr(extractor, "GLOBAL_SESSION", global_session)
    monkeypatch.setattr(extractor.curl_requests, "Session", factory)
    monkeypatch.setattr(extractor, "playwright_get_hanime_manifest_token", browser)
    monkeypatch.setattr(extractor.time, "time", lambda: 1792951304)
    return SimpleNamespace(
        session=session, factory=factory, browser=browser, global_session=global_session
    )


def test_handshake_request_encryption_contains_slug_and_timestamp(monkeypatch):
    iv = b"0123456789ab"
    monkeypatch.setattr(extractor.secrets, "token_bytes", lambda size: iv)
    value = extractor._encode_hanime_handshake("example-1", 1792951304)
    envelope = json.loads(extractor.decode_base64url(value))
    assert envelope["alg"] == "AES-256-GCM"
    assert envelope["v"] == 1
    assert extractor.decode_base64url(envelope["iv"]) == iv
    payload = AESGCM(extractor._HANIME_AES_KEY).decrypt(
        iv,
        extractor.decode_base64url(envelope["data"])
        + extractor.decode_base64url(envelope["tag"]),
        extractor._HANIME_AES_HEADER,
    )
    assert json.loads(payload) == {
        "timestamp_unix": 1792951304,
        "directive": "htv_player_handshake",
        "slug": "example-1",
    }


def test_http_handshake_signs_request_and_avoids_browser(handshake):
    assert extractor.fetch_hanime_manifest("example-1") == MANIFEST
    handshake.browser.assert_not_called()
    handshake.factory.assert_called_once_with(
        impersonate="chrome", cookies=handshake.global_session.cookies
    )
    handshake.session.get.assert_called_once()
    assert handshake.session.get.call_args.args == ("https://ct.hanime.tv/csrf-token",)
    handshake.session.post.assert_called_once()
    request = handshake.session.post.call_args
    assert request.args == ("https://auth.hanime.tv/api/v11/handshake",)
    headers = request.kwargs["headers"]
    assert headers["X-Time"] == "1792951304"
    assert headers["X-Signature-Version"] == "web2"
    # Known output from the website's shipped WASM signer at this timestamp.
    assert headers["X-Signature"] == (
        "a2997eb1522213dfbcf95e0e0770b685d93f4644d71f7a3bf4e10e72913e3448"
    )
    assert headers["X-CSRF-Token"] == "csrf-test"
    assert headers["Referer"] == "https://hanime.tv/videos/hentai/example-1"
    handshake.session.__exit__.assert_called_once()
    assert (
        handshake.global_session.cookies.get("session", domain=".hanime.tv", path="/")
        == "fresh"
    )


@pytest.mark.parametrize(
    "failure", ["csrf", "http", "missing-token", "invalid-token", "empty-sources"]
)
def test_failed_static_handshake_uses_browser_once(handshake, failure):
    if failure == "csrf":
        handshake.session.get.return_value = response({})
    elif failure == "http":
        handshake.session.post.return_value = response(failed=True)
    elif failure == "missing-token":
        handshake.session.post.return_value = response()
    elif failure == "invalid-token":
        handshake.session.post.return_value = response(headers={"x-token": "invalid"})
    else:
        handshake.session.post.return_value = response(
            headers={"x-token": token({"sources": []})}
        )

    assert extractor.fetch_hanime_manifest("example-1") == MANIFEST
    handshake.browser.assert_called_once_with(
        "https://hanime.tv/videos/hentai/example-1", timeout=15
    )
    assert handshake.session.get.call_count == 1
    assert handshake.session.post.call_count == int(failure != "csrf")
    handshake.session.__exit__.assert_called_once()


def test_browser_failure_after_static_failure_is_not_retried(handshake):
    handshake.session.get.side_effect = RuntimeError("static failure")
    handshake.browser.side_effect = TimeoutError("browser failure")
    with pytest.raises(RuntimeError, match="Hanime stream handshake failed"):
        extractor.fetch_hanime_manifest("example-1")
    handshake.session.get.assert_called_once()
    handshake.browser.assert_called_once()
