"""Platform config/cache roots stay absolute and independent of the working directory."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aniworld import autodeps, config

INVALID_BASES = [None, "", " \t ", "relative/cache", "../cache", "~/cache"]


@pytest.fixture
def home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    for name in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
        monkeypatch.delenv(name, raising=False)
    return home


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("value", INVALID_BASES)
def test_mpv_invalid_directory_uses_platform_default(home, monkeypatch, windows, value):
    # Replacing only config's OS view leaves pathlib on the real host platform.
    monkeypatch.setattr(
        config,
        "os",
        SimpleNamespace(name="nt" if windows else "posix", environ=os.environ),
    )
    name = "APPDATA" if windows else "XDG_CONFIG_HOME"
    if value is not None:
        monkeypatch.setenv(name, value)

    expected = home / "AppData" / "Roaming" if windows else home / ".config"
    assert config._mpv_config_dir() == expected / "mpv"


@pytest.mark.parametrize("windows", [False, True])
def test_mpv_uses_absolute_directory_with_spaces(home, monkeypatch, tmp_path, windows):
    monkeypatch.setattr(
        config,
        "os",
        SimpleNamespace(name="nt" if windows else "posix", environ=os.environ),
    )
    name = "APPDATA" if windows else "XDG_CONFIG_HOME"
    other = "XDG_CONFIG_HOME" if windows else "APPDATA"
    directory = tmp_path / "custom config" / "nested"
    monkeypatch.setenv(name, str(directory))
    monkeypatch.setenv(other, str(tmp_path / "ignored"))

    assert config._mpv_config_dir() == directory / "mpv"
    assert os.environ[name] == str(directory)
    assert not directory.exists()


@pytest.mark.parametrize("value", [" \t ", "relative/config", "~/config"])
def test_mpv_children_receive_the_same_config_base(home, monkeypatch, value):
    monkeypatch.setattr(config, "os", SimpleNamespace(name="posix", environ=os.environ))
    monkeypatch.setenv("XDG_CONFIG_HOME", value)

    directory = config._mpv_config_dir()
    child = subprocess.run(
        [sys.executable, "-c", "import os; print(os.environ['XDG_CONFIG_HOME'])"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert directory == home / ".config" / "mpv"
    assert child.stdout.strip() == str(directory.parent)


@pytest.mark.parametrize("custom", [False, True])
def test_config_initialization_sets_mpv_and_script_directories(
    home, monkeypatch, tmp_path, custom
):
    monkeypatch.setenv("ANIWORLD_INSTALL_FOLDER", str(tmp_path / "app"))
    monkeypatch.setattr("niquests.Session", Mock())
    if custom:
        roaming = tmp_path / "roaming data"
        xdg = tmp_path / "xdg config"
        monkeypatch.setenv("APPDATA", str(roaming))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        expected = roaming if os.name == "nt" else xdg
    else:
        expected = home / "AppData" / "Roaming" if os.name == "nt" else home / ".config"
    spec = importlib.util.spec_from_file_location(
        "aniworld._test_platform_config", config.__file__
    )
    loaded = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(loaded)

    assert loaded.MPV_CONFIG_DIR == expected / "mpv"
    assert loaded.MPV_SCRIPTS_DIR == expected / "mpv" / "scripts"
    assert not loaded.MPV_CONFIG_DIR.exists()


@pytest.mark.parametrize("platform", ["Linux", "Windows"])
@pytest.mark.parametrize("value", INVALID_BASES)
def test_browser_invalid_directory_uses_platform_default(
    home, monkeypatch, platform, value
):
    monkeypatch.setattr(autodeps, "PLATFORM", platform)
    name = "LOCALAPPDATA" if platform == "Windows" else "XDG_CACHE_HOME"
    if value is not None:
        monkeypatch.setenv(name, value)

    expected = home / "AppData" / "Local" if platform == "Windows" else home / ".cache"
    assert autodeps._default_playwright_browsers_path() == expected / "ms-playwright"


@pytest.mark.parametrize("platform", ["Linux", "Windows"])
def test_browser_uses_absolute_directory_with_spaces(
    home, monkeypatch, tmp_path, platform
):
    monkeypatch.setattr(autodeps, "PLATFORM", platform)
    name = "LOCALAPPDATA" if platform == "Windows" else "XDG_CACHE_HOME"
    other = "XDG_CACHE_HOME" if platform == "Windows" else "LOCALAPPDATA"
    directory = tmp_path / "custom cache" / "nested"
    monkeypatch.setenv(name, str(directory))
    monkeypatch.setenv(other, str(tmp_path / "ignored"))

    assert autodeps._default_playwright_browsers_path() == directory / "ms-playwright"
    assert not directory.exists()


def test_macos_browser_cache_uses_library_directory(home, monkeypatch, tmp_path):
    monkeypatch.setattr(autodeps, "PLATFORM", "Darwin")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "ignored-windows"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "ignored-linux"))

    assert (
        autodeps._default_playwright_browsers_path()
        == home / "Library" / "Caches" / "ms-playwright"
    )
