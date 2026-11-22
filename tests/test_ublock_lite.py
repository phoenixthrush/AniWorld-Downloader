"""uBlock Origin Lite is opt-in and never needs the network once installed."""

import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from aniworld import autodeps
from aniworld.playwright import captcha


@pytest.fixture
def no_fetch(monkeypatch):
    fetch = Mock(side_effect=AssertionError("unexpected release lookup"))
    monkeypatch.setattr(autodeps, "fetch_github_asset_urls", fetch)
    return fetch


def test_ublock_is_off_by_default(monkeypatch, no_fetch):
    monkeypatch.delenv("ANIWORLD_UBLOCK", raising=False)
    assert autodeps.ensure_ublock_lite() is None
    no_fetch.assert_not_called()


def test_ublock_uses_installed_copy(tmp_path, monkeypatch, no_fetch):
    monkeypatch.setenv("ANIWORLD_UBLOCK", "1")
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
    assert handle.browser is None
    handle.close()
    handle.context.close.assert_called_once()
    assert not Path(user_data_dir).exists()


def test_ublock_downloads_and_unpacks_once(tmp_path, monkeypatch):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", "{}")
    url = "https://example.invalid/uBOLite_2026.1122.1948.chromium.zip"
    config = tmp_path / "config"
    monkeypatch.setenv("ANIWORLD_UBLOCK", "1")
    monkeypatch.delenv("ANIWORLD_NO_AUTO_INSTALL", raising=False)
    monkeypatch.setattr(autodeps, "ANIWORLD_CONFIG_DIR", config)
    monkeypatch.setattr(autodeps, "fetch_github_asset_urls", Mock(return_value=[url]))
    response = Mock()
    response.iter_content.return_value = [archive.read_bytes()]
    monkeypatch.setattr(autodeps.GLOBAL_SESSION, "get", Mock(return_value=response))

    assert autodeps.ensure_ublock_lite() == str((config / "ublock-lite").resolve())
    assert (config / "ublock-lite" / "manifest.json").is_file()
    assert sorted(p.name for p in config.iterdir()) == ["ublock-lite"]
