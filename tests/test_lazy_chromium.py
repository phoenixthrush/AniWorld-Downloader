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


@pytest.mark.parametrize("value", ["0", "../custom-cache", "~/custom-cache"])
def test_explicit_browser_cache_semantics_are_preserved(
    browser_install, monkeypatch, value
):
    import os

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", value)
    browser_install.executable.touch()

    autodeps.ensure_patchright_chromium()

    assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == value
    browser_install.install.assert_not_called()


@pytest.fixture
def linux_browser_libraries(browser_install, monkeypatch):
    monkeypatch.setattr(autodeps, "PLATFORM", "Linux")
    monkeypatch.setattr(autodeps.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(autodeps.shutil, "which", lambda name: "/usr/bin/apt-get")
    monkeypatch.setattr(
        autodeps.platform,
        "freedesktop_os_release",
        lambda: {"ID": "debian", "VERSION_ID": "13"},
    )
    monkeypatch.setattr(autodeps.os, "geteuid", lambda: 0, raising=False)
    missing = SimpleNamespace(
        returncode=127,
        stderr="chrome: error while loading shared libraries: libnspr4.so: "
        "cannot open shared object file: No such file or directory",
    )
    browser_install.install.return_value = missing
    return browser_install, missing


@pytest.mark.parametrize(
    ("returncode", "stderr"), [(0, ""), (1, "failed to start Chromium")]
)
def test_chromium_dependency_install_requires_a_loader_error(
    linux_browser_libraries, returncode, stderr
):
    browser, _ = linux_browser_libraries
    browser.install.return_value = SimpleNamespace(returncode=returncode, stderr=stderr)

    autodeps.ensure_chromium_system_dependencies(str(browser.executable))

    (command,), _ = browser.install.call_args
    assert command == [str(browser.executable), "--version"]
    assert browser.install.call_count == 1


def test_chromium_dependency_install_repairs_and_rechecks(linux_browser_libraries):
    browser, missing = linux_browser_libraries
    healthy = SimpleNamespace(returncode=0, stderr="")
    browser.install.side_effect = [missing, None, healthy, healthy]

    autodeps.ensure_chromium_system_dependencies(str(browser.executable))
    autodeps.ensure_chromium_system_dependencies(str(browser.executable))

    probe = [str(browser.executable), "--version"]
    setup = [str(browser.driver), "cli.js", "install-deps", "chromium"]
    assert [call.args[0] for call in browser.install.call_args_list] == [
        probe,
        setup,
        probe,
        probe,
    ]


@pytest.mark.parametrize("reason", ["disabled", "non-interactive", "unsupported"])
def test_chromium_dependency_install_gives_manual_instructions(
    linux_browser_libraries, monkeypatch, reason
):
    browser, _ = linux_browser_libraries
    expected_hint = "python -m patchright install-deps chromium"
    if reason == "disabled":
        monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "1")
    elif reason == "non-interactive":
        monkeypatch.setattr(autodeps.os, "geteuid", lambda: 1000)
        monkeypatch.setattr(autodeps.sys, "stdin", None)
    else:
        monkeypatch.setattr(
            autodeps.platform, "freedesktop_os_release", lambda: {"ID": "arch"}
        )
        expected_hint = "your distribution's package manager"

    with pytest.raises(RuntimeError, match=f"libnspr4.so.*{expected_hint}"):
        autodeps.ensure_chromium_system_dependencies(str(browser.executable))

    assert browser.install.call_count == 1


def test_chromium_dependency_install_reports_a_failed_repair(linux_browser_libraries):
    browser, missing = linux_browser_libraries
    browser.install.side_effect = [
        missing,
        subprocess.CalledProcessError(1, ["install-deps", "chromium"]),
    ]

    with pytest.raises(RuntimeError, match="libnspr4.so.*Dependency setup failed"):
        autodeps.ensure_chromium_system_dependencies(str(browser.executable))

    assert browser.install.call_count == 2


def test_chromium_dependency_install_checks_the_remaining_library(
    linux_browser_libraries,
):
    browser, missing = linux_browser_libraries
    still_missing = SimpleNamespace(
        returncode=127, stderr=missing.stderr.replace("libnspr4.so", "libnss3.so")
    )
    browser.install.side_effect = [missing, None, still_missing]

    with pytest.raises(RuntimeError, match=r"still cannot load libnss3\.so"):
        autodeps.ensure_chromium_system_dependencies(str(browser.executable))

    assert browser.install.call_count == 3
