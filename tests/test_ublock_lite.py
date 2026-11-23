"""uBlock Origin Lite is on by default and never needs the network once installed."""

import threading
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from aniworld import autodeps
from aniworld.playwright import captcha


@pytest.fixture
def no_fetch(monkeypatch):
    fetch = Mock(side_effect=AssertionError("unexpected release lookup"))
    monkeypatch.setattr(autodeps, "fetch_github_asset_urls", fetch)
    return fetch


def test_ublock_can_be_disabled(monkeypatch, no_fetch):
    monkeypatch.setenv("ANIWORLD_UBLOCK", "0")
    assert autodeps.ensure_ublock_lite() is None
    no_fetch.assert_not_called()


def test_ublock_is_on_by_default_and_uses_installed_copy(
    tmp_path, monkeypatch, no_fetch
):
    monkeypatch.delenv("ANIWORLD_UBLOCK", raising=False)
    monkeypatch.setattr(autodeps, "ANIWORLD_CONFIG_DIR", tmp_path)
    extension = tmp_path / "ublock-lite"
    extension.mkdir()
    (extension / "manifest.json").write_text("{}")
    assert autodeps.ensure_ublock_lite() == str(extension.resolve())


def test_ublock_respects_no_auto_install(tmp_path, monkeypatch, no_fetch):
    monkeypatch.setenv("ANIWORLD_UBLOCK", "1")
    monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "1")
    monkeypatch.setattr(autodeps, "ANIWORLD_CONFIG_DIR", tmp_path)
    assert autodeps.ensure_ublock_lite() is None
    assert not (tmp_path / "ublock-lite").exists()


def test_captcha_browser_loads_ublock_in_temp_profile(tmp_path, monkeypatch):
    executable = tmp_path / "chromium"
    executable.touch()
    extension = str(tmp_path / "ublock-lite")
    runtime = Mock()
    runtime.chromium.executable_path = str(executable)
    monkeypatch.setattr(autodeps, "ensure_ublock_lite", lambda: extension)

    handle = captcha._launch_browser_context(runtime)

    runtime.chromium.launch.assert_not_called()
    (user_data_dir,), options = runtime.chromium.launch_persistent_context.call_args
    assert options["headless"] is False
    assert options["no_viewport"] is True
    assert f"--disable-extensions-except={extension}" in options["args"]
    assert f"--load-extension={extension}" in options["args"]
    handle.close()
    handle.context.close.assert_called_once()
    assert not Path(user_data_dir).exists()


@pytest.fixture
def release(tmp_path, monkeypatch):
    """Serve a fake uBOL zip and return (config dir, download mock)."""
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", "{}")
    url = "https://example.invalid/uBOLite_2026.1122.1948.chromium.zip"
    config = tmp_path / "config"
    monkeypatch.setenv("ANIWORLD_UBLOCK", "1")
    monkeypatch.setattr(autodeps, "ANIWORLD_CONFIG_DIR", config)
    monkeypatch.setattr(autodeps, "fetch_github_asset_urls", Mock(return_value=[url]))
    response = Mock()
    response.iter_content.return_value = [archive.read_bytes()]
    download = Mock(return_value=response)
    monkeypatch.setattr(autodeps.GLOBAL_SESSION, "get", download)
    return config, download


def test_ublock_downloads_and_unpacks_once(release):
    config, download = release

    assert autodeps.ensure_ublock_lite() == str((config / "ublock-lite").resolve())
    assert autodeps.ensure_ublock_lite() == str((config / "ublock-lite").resolve())
    download.assert_called_once()
    assert (config / "ublock-lite" / "manifest.json").is_file()
    assert sorted(p.name for p in config.iterdir()) == ["ublock-lite"]


def test_parallel_first_runs_download_once(release):
    config, download = release
    barrier = threading.Barrier(4)
    results = []

    def run():
        barrier.wait()
        results.append(autodeps.ensure_ublock_lite())

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [str((config / "ublock-lite").resolve())] * 4
    download.assert_called_once()
    assert sorted(p.name for p in config.iterdir()) == ["ublock-lite"]


def test_failed_download_leaves_nothing_behind(release):
    config, download = release
    download.return_value.raise_for_status.side_effect = OSError("HTTP 503")

    assert autodeps.ensure_ublock_lite() is None
    assert list(config.iterdir()) == []


def test_hentai_tv_browser_loads_ublock_in_temp_profile(tmp_path, monkeypatch):
    from patchright import sync_api

    from aniworld.models.hentai_tv import player

    extension = str(tmp_path / "ublock-lite")
    monkeypatch.setattr(autodeps, "ensure_patchright_chromium", lambda: None)
    monkeypatch.setattr(autodeps, "ensure_ublock_lite", lambda: extension)
    runtime = MagicMock()
    chromium = runtime.__enter__.return_value.chromium
    chromium.executable_path = "/fake/chromium"
    context = chromium.launch_persistent_context.return_value
    context.new_page.return_value.evaluate.return_value = {
        "url": "https://media.example/video.mp4",
        "error": None,
    }
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: runtime)
    monkeypatch.setattr(player.Path, "is_file", lambda self: True)

    assert player._resolve_browser("https://nhplayer.com/p", 5) == (
        "https://media.example/video.mp4"
    )
    chromium.launch.assert_not_called()
    (user_data_dir,), options = chromium.launch_persistent_context.call_args
    assert options["headless"] is True
    assert options["executable_path"] == "/fake/chromium"
    assert f"--load-extension={extension}" in options["args"]
    context.close.assert_called_once()
    assert not Path(user_data_dir).exists()


def test_broken_install_without_manifest_is_replaced(release):
    config, download = release
    broken = config / "ublock-lite"
    broken.mkdir(parents=True)
    (broken / "leftover.js").write_text("")

    assert autodeps.ensure_ublock_lite() == str(broken.resolve())
    assert sorted(p.name for p in broken.iterdir()) == ["manifest.json"]
    assert download.call_args.kwargs["timeout"] == 60
