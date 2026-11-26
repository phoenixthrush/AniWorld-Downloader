"""Windows release lookups fetch only the asset that is used."""

from unittest.mock import Mock

import pytest

from aniworld import autodeps


@pytest.mark.parametrize("v3", [False, True])
def test_mpv_url_fetches_only_requested_build(monkeypatch, v3):
    fetch = Mock(return_value=["https://example.com/mpv.7z"])
    monkeypatch.setattr(autodeps, "fetch_github_asset_urls", fetch)

    assert autodeps.get_mpv_windows_url(v3=v3) == "https://example.com/mpv.7z"
    key = "v3" if v3 else "non_v3"
    fetch.assert_called_once_with(autodeps.MPV_REPO, autodeps.MPV_PATTERNS[key])


def test_mpv_url_is_none_without_match(monkeypatch):
    monkeypatch.setattr(autodeps, "fetch_github_asset_urls", Mock(return_value=[]))
    assert autodeps.get_mpv_windows_url() is None


@pytest.mark.parametrize(
    "name,resolver",
    [
        ("mpv", "get_mpv_windows_url"),
        ("syncplay", "get_syncplay_windows_url"),
        ("ffmpeg", "get_ffmpeg_windows_url"),
    ],
)
@pytest.mark.parametrize("platform", ["Windows", "Linux"])
def test_resolve_download_url(monkeypatch, tmp_path, name, resolver, platform):
    monkeypatch.setattr(autodeps, "PLATFORM", platform)
    monkeypatch.setattr(autodeps, resolver, lambda: f"https://example.com/{name}")
    manager = autodeps.DependencyManager(install_folder=tmp_path)
    dep_info = {}

    url = manager._resolve_download_url(name, dep_info)

    expected = f"https://example.com/{name}" if platform == "Windows" else None
    assert url == expected
    assert dep_info.get("url") == expected


def test_resolve_download_url_keeps_known_url(monkeypatch, tmp_path):
    monkeypatch.setattr(autodeps, "PLATFORM", "Windows")
    monkeypatch.setattr(
        autodeps, "get_mpv_windows_url", lambda: pytest.fail("unexpected lookup")
    )
    manager = autodeps.DependencyManager(install_folder=tmp_path)

    url = manager._resolve_download_url("mpv", {"url": "https://example.com/a.7z"})

    assert url == "https://example.com/a.7z"
