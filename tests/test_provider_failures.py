"""Regressions for provider failures and preview URL construction."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from aniworld.extractors.provider import voe
from aniworld.models.s_to import episode as sto
from aniworld.playwright import captcha


@pytest.fixture
def voe_preview_session(monkeypatch):
    session = SimpleNamespace(
        get=Mock(return_value=SimpleNamespace(text="", raise_for_status=Mock())),
        head=Mock(
            return_value=SimpleNamespace(
                headers={"Content-Type": "image/jpeg"}, raise_for_status=Mock()
            )
        ),
    )
    monkeypatch.setattr(voe, "GLOBAL_SESSION", session)
    return session


@pytest.mark.parametrize("quote", ["'", '"'])
@pytest.mark.parametrize("padding", ["", " \n\t"])
def test_voe_preview_requests_the_unquoted_url(voe_preview_session, quote, padding):
    session = voe_preview_session
    session.get.return_value.text = (
        f"window.location = {quote}{padding}https://mirror.example/e/abc{quote};"
    )
    headers = {"Referer": "https://voe.sx/"}
    expected = "https://mirror.example/cache/abc_storyboard_L2.jpg"

    result = voe.get_preview_image_link_from_voe(
        "https://voe.sx/e/start", headers=headers
    )

    assert result == expected
    session.get.assert_called_once_with("https://voe.sx/e/start", headers=headers)
    session.head.assert_called_once_with(
        expected, headers=headers, allow_redirects=True
    )
    session.get.return_value.raise_for_status.assert_called_once()
    session.head.return_value.raise_for_status.assert_called_once()


def test_voe_preview_without_a_redirect_does_not_request_an_image(voe_preview_session):
    with pytest.raises(ValueError, match="No redirect URL found"):
        voe.get_preview_image_link_from_voe("https://voe.sx/e/start")
    voe_preview_session.head.assert_not_called()


def test_voe_preview_rejects_a_non_image_response(voe_preview_session):
    voe_preview_session.get.return_value.text = (
        'window.location = "https://mirror.example/e/abc";'
    )
    voe_preview_session.head.return_value.headers = {"Content-Type": "text/html"}

    with pytest.raises(ValueError, match="Preview image not reachable"):
        voe.get_preview_image_link_from_voe("https://voe.sx/e/start")


@pytest.mark.parametrize("status", [404, 410])
@pytest.mark.parametrize("redirect", [False, True])
def test_deleted_voe_does_not_retry(monkeypatch, status, redirect):
    responses = [("deleted", "https://voe.sx/e/deleted", status)]
    if redirect:
        responses.insert(
            0,
            (
                'window.location="https://voe.sx/e/deleted"',
                "https://voe.sx/e/start",
                200,
            ),
        )
    fetch = Mock(side_effect=responses)
    sleep = Mock()
    monkeypatch.setattr(voe, "_voe_get", fetch)
    monkeypatch.setattr(voe.time, "sleep", sleep)
    with pytest.raises(ValueError, match=f"HTTP {status}"):
        voe.get_direct_link_from_voe("https://voe.sx/e/start")
    assert fetch.call_count == len(responses)
    sleep.assert_not_called()


def test_temporary_voe_failure_still_retries(monkeypatch):
    fetch = Mock(
        side_effect=[
            ("error", "https://voe.sx/e/start", 500),
            ("'hls': 'https://cdn.example/video.m3u8'", "https://voe.sx/e/start", 200),
        ]
    )
    sleep = Mock()
    monkeypatch.setattr(voe, "_voe_get", fetch)
    monkeypatch.setattr(voe.time, "sleep", sleep)
    assert (
        voe.get_direct_link_from_voe("https://voe.sx/e/start")
        == "https://cdn.example/video.m3u8"
    )
    sleep.assert_called_once_with(2)


def test_missing_chromium_error_survives_modal_solver(monkeypatch, tmp_path):
    from patchright import sync_api

    from aniworld import autodeps

    monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "1")
    runtime = MagicMock()
    runtime.chromium.executable_path = str(tmp_path / "missing-chromium")
    playwright = MagicMock()
    playwright.return_value.__enter__.return_value = runtime
    monkeypatch.setattr(sync_api, "sync_playwright", playwright)
    monkeypatch.setattr(autodeps, "_ensure_xvfb", Mock())
    with pytest.raises(RuntimeError, match="python -m patchright install chromium"):
        captcha.solve_sto_modal(
            "https://serienstream.to/serie/example/staffel-1/episode-1",
            "VOE",
            "Deutsch",
        )
    runtime.chromium.launch.assert_not_called()
    runtime.chromium.launch_persistent_context.assert_not_called()


def test_failed_modal_does_not_cache_serienstream_url(monkeypatch):
    episode = sto.SerienstreamEpisode(
        "https://serienstream.to/serie/example/staffel-1/episode-1"
    )
    redirect = "https://serienstream.to/r?t=example"
    monkeypatch.setattr(sto.SerienstreamEpisode, "provider_link", lambda *a: redirect)
    monkeypatch.setattr(sto, "sto_get", lambda *a: SimpleNamespace(url=redirect))
    solve = Mock(return_value=None)
    monkeypatch.setattr(captcha, "solve_sto_modal", solve)
    for _ in range(2):
        with pytest.raises(ValueError, match="Failed to resolve provider URL"):
            _ = episode.stream_url
    assert solve.call_count == 2
