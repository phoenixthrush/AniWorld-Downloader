"""Browser setup follows browser use, independently of download destinations."""

import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from aniworld import autodeps, entry


@pytest.mark.parametrize("path", ["/app/Downloads", "Videos", ""])
@pytest.mark.parametrize("action", ["Download", "Watch", "Syncplay"])
def test_http_only_actions_do_not_prepare_browser(monkeypatch, path, action):
    ensure = Mock(side_effect=AssertionError("unexpected browser setup"))
    monkeypatch.setattr(autodeps, "ensure_patchright_chromium", ensure)
    # Also guard the previously imported startup alias against regression.
    monkeypatch.setattr(entry, "ensure_patchright_chromium", ensure, raising=False)
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", path)
    monkeypatch.setenv("ANIWORLD_NO_MENU", "1")
    monkeypatch.setattr(entry, "set_terminal_title", Mock())
    monkeypatch.setattr(
        entry,
        "parse_args",
        lambda: SimpleNamespace(
            web_ui=False, action=action, url=["https://example.test/video"]
        ),
    )
    operation = Mock()
    model = SimpleNamespace(**{action.lower(): operation})
    monkeypatch.setattr(entry, "model_for_url", lambda url: model)
    assert entry.aniworld() == 0
    operation.assert_called_once_with()
    ensure.assert_not_called()


def test_web_startup_does_not_prepare_browser(monkeypatch):
    from aniworld import web

    ensure = Mock(side_effect=AssertionError("unexpected browser setup"))
    monkeypatch.setattr(autodeps, "ensure_patchright_chromium", ensure)
    monkeypatch.setattr(entry, "ensure_patchright_chromium", ensure, raising=False)
    monkeypatch.setattr(entry, "set_terminal_title", Mock())
    monkeypatch.setattr(
        entry,
        "parse_args",
        lambda: SimpleNamespace(
            web_ui=True,
            web_expose=False,
            web_port=8080,
            no_browser=True,
            web_force_sso=False,
            web_sso=False,
            web_auth=False,
        ),
    )
    start = Mock()
    monkeypatch.setattr(web, "start_web_ui", start)
    assert entry.aniworld() == 0
    start.assert_called_once()
    ensure.assert_not_called()


@pytest.fixture
def browser_install(monkeypatch, tmp_path):
    from patchright import sync_api
    from patchright._impl import _driver

    executable = tmp_path / "chromium"
    driver = tmp_path / "node"
    driver.touch()
    runtime = MagicMock()
    runtime.chromium.executable_path = str(executable)
    playwright = MagicMock()
    playwright.return_value.__enter__.return_value = runtime
    monkeypatch.setattr(sync_api, "sync_playwright", playwright)
    monkeypatch.setattr(
        _driver, "compute_driver_executable", lambda: (str(driver), "cli.js")
    )
    monkeypatch.setattr(_driver, "get_driver_env", lambda: {"driver": "env"})
    install = Mock()
    monkeypatch.setattr(autodeps.subprocess, "run", install)
    monkeypatch.setattr(
        autodeps,
        "_ensure_xvfb",
        Mock(side_effect=AssertionError("headless setup must not need Xvfb")),
    )
    monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "0")
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "browsers"))
    monkeypatch.delenv("PLAYWRIGHT_NODEJS_PATH", raising=False)
    return SimpleNamespace(
        executable=executable,
        driver=driver,
        runtime=runtime,
        playwright=playwright,
        install=install,
    )


@pytest.mark.parametrize("platform", ["Linux", "Darwin", "Windows"])
@pytest.mark.parametrize("path", ["/app/Downloads", "Other Downloads"])
def test_installed_chromium_is_reused(browser_install, monkeypatch, platform, path):
    monkeypatch.setattr(autodeps, "PLATFORM", platform)
    monkeypatch.setenv("ANIWORLD_DOWNLOAD_PATH", path)
    browser_install.executable.touch()
    autodeps.ensure_patchright_chromium()
    browser_install.install.assert_not_called()
    browser_install.playwright.assert_called_once_with()
    browser_install.runtime.chromium.launch.assert_not_called()


def test_missing_chromium_is_installed_once_then_reused(browser_install):
    browser_install.install.side_effect = lambda *args, **kwargs: (
        browser_install.executable.touch()
    )
    autodeps.ensure_patchright_chromium()
    autodeps.ensure_patchright_chromium()
    browser_install.install.assert_called_once_with(
        [
            browser_install.driver.resolve().as_posix(),
            "cli.js",
            "install",
            "chromium",
            "--no-shell",
        ],
        check=True,
        env={"driver": "env"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert browser_install.playwright.call_count == 2


def test_disabled_auto_install_does_not_probe_or_install(browser_install, monkeypatch):
    monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "1")
    autodeps.ensure_patchright_chromium()
    browser_install.playwright.assert_not_called()
    browser_install.install.assert_not_called()


def test_default_cache_is_selected_before_browser_probe(
    browser_install, monkeypatch, tmp_path
):
    import os

    cache = tmp_path / "browser-cache"
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(autodeps, "_default_playwright_browsers_path", lambda: cache)
    browser_install.executable.touch()

    def probe():
        assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == cache.resolve().as_posix()
        assert (
            os.environ["PLAYWRIGHT_NODEJS_PATH"]
            == browser_install.driver.resolve().as_posix()
        )
        return browser_install.playwright.return_value

    monkeypatch.setattr("patchright.sync_api.sync_playwright", probe)
    autodeps.ensure_patchright_chromium()
    browser_install.install.assert_not_called()


def test_failed_browser_install_keeps_missing_browser_error(
    browser_install, monkeypatch
):
    from aniworld.playwright import captcha

    browser_install.install.side_effect = subprocess.CalledProcessError(1, "install")
    monkeypatch.setattr(autodeps, "_ensure_xvfb", Mock())
    with (
        pytest.raises(RuntimeError, match="python -m patchright install chromium"),
        captcha._browser("https://example.test/challenge"),
    ):
        pytest.fail("missing browser must not be usable")
    browser_install.install.assert_called_once()
    browser_install.runtime.chromium.launch.assert_not_called()


def test_custom_browser_and_node_paths_are_preserved(
    browser_install, monkeypatch, tmp_path
):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright")
    monkeypatch.setenv("PLAYWRIGHT_NODEJS_PATH", "/custom/node")
    browser_install.executable.touch()
    autodeps.ensure_patchright_chromium()
    import os

    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == "/ms-playwright"
    assert os.environ["PLAYWRIGHT_NODEJS_PATH"] == "/custom/node"
    browser_install.install.assert_not_called()
