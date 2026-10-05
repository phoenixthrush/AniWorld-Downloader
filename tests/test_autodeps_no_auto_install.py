"""ANIWORLD_NO_AUTO_INSTALL blocks every unattended download/install."""

import subprocess
import zipfile
from unittest.mock import Mock

import pytest

from aniworld import autodeps


@pytest.fixture(autouse=True)
def _no_subprocess(monkeypatch):
    """Fail loudly if anything tries to shell out (apt, sudo, the playwright CLI)."""

    def _boom(*args, **kwargs):
        raise AssertionError(f"unexpected subprocess call: {args!r}")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)


@pytest.mark.parametrize(
    "value,expected",
    [(None, False), ("0", False), ("", False), ("1", True), (" 1 ", True)],
)
def test_auto_install_disabled_reads_env(monkeypatch, value, expected):
    monkeypatch.delenv("ANIWORLD_NO_AUTO_INSTALL", raising=False)
    if value is not None:
        monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", value)
    assert autodeps.auto_install_disabled() is expected


def test_confirm_install_never_prompts(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "1")
    monkeypatch.setattr(
        "builtins.input", lambda *_: pytest.fail("should not prompt the user")
    )
    manager = autodeps.DependencyManager(install_folder=tmp_path)
    assert manager._confirm_install("install mpv?") is False


def test_package_manager_install_is_skipped(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "1")
    manager = autodeps.DependencyManager(install_folder=tmp_path)
    assert manager._install_with_package_manager("mpv") is False


@pytest.fixture
def binary_manager(monkeypatch, tmp_path):
    monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "1")
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(autodeps, "PLATFORM", "Windows")
    monkeypatch.setattr(autodeps.shutil, "which", lambda _: None)
    manager = autodeps.DependencyManager(install_folder=tmp_path)
    manager.deps = {
        "mpv": {
            "Windows": {
                "url": "https://example.com/mpv.zip",
                "binary_names": ["mpv.exe"],
                "package": "mpv.net",
            }
        },
        "7z": {"Windows": {"url": "https://example.com/7zr.exe"}},
    }
    return manager


@pytest.mark.parametrize("prompt_user", [True, False])
@pytest.mark.parametrize("url", [None, "https://example.com/mpv.zip"])
def test_missing_binary_never_installs(binary_manager, monkeypatch, prompt_user, url):
    binary_manager.deps["mpv"]["Windows"]["url"] = url
    for method in (
        "_resolve_download_url",
        "_download_binary",
        "_confirm_install",
        "_install_with_package_manager",
    ):
        monkeypatch.setattr(
            binary_manager, method, lambda *_: pytest.fail("unexpected install attempt")
        )

    with pytest.raises(FileNotFoundError, match="mpv.*ANIWORLD_NO_AUTO_INSTALL=1"):
        binary_manager.fetch_binary("mpv", prompt_user=prompt_user)


@pytest.mark.parametrize("location", ["system", "local"])
def test_installed_binary_remains_usable(
    binary_manager, monkeypatch, tmp_path, location
):
    binary = tmp_path / "tools" / "mpv.exe"
    binary.parent.mkdir()
    binary.touch()
    if location == "system":
        monkeypatch.setattr(autodeps.shutil, "which", lambda _: str(binary))
    monkeypatch.setattr(
        binary_manager,
        "_resolve_download_url",
        lambda *_: pytest.fail("unexpected release lookup"),
    )

    assert binary_manager.fetch_binary("mpv", prompt_user=False) == binary


def test_cached_zip_remains_usable(binary_manager, tmp_path):
    with zipfile.ZipFile(tmp_path / "mpv.zip", "w") as archive:
        archive.writestr("mpv.exe", b"cached executable")

    binary = binary_manager.fetch_binary("mpv", prompt_user=False)

    assert binary == tmp_path / "mpv" / "mpv.exe"
    assert binary.read_bytes() == b"cached executable"


def test_cached_7z_cannot_download_unpacker(binary_manager, tmp_path, monkeypatch):
    binary_manager.deps["mpv"]["Windows"]["url"] = "https://example.com/mpv.7z"
    (tmp_path / "mpv.7z").touch()
    monkeypatch.setattr(
        binary_manager,
        "_download_binary",
        lambda *_: pytest.fail("unexpected helper download"),
    )

    with pytest.raises(FileNotFoundError, match="7z.*ANIWORLD_NO_AUTO_INSTALL=1"):
        binary_manager.fetch_binary("mpv", prompt_user=False)


def test_cached_7z_uses_cached_unpacker(binary_manager, tmp_path, monkeypatch):
    binary_manager.deps["mpv"]["Windows"]["url"] = "https://example.com/mpv.7z"
    (tmp_path / "mpv.7z").touch()
    unpacker = tmp_path / "7zr.exe"
    unpacker.touch()
    binary = tmp_path / "mpv" / "mpv.exe"

    def extract(command, **kwargs):
        assert command[0] == str(unpacker)
        binary.write_bytes(b"cached executable")

    monkeypatch.setattr(subprocess, "run", extract)

    assert binary_manager.fetch_binary("mpv", prompt_user=False) == binary
    assert binary.read_bytes() == b"cached executable"


def test_promptless_download_still_works_when_enabled(
    binary_manager, monkeypatch, tmp_path
):
    monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "0")
    expected = tmp_path / "mpv.exe"
    download = Mock(return_value=expected)
    monkeypatch.setattr(binary_manager, "_download_binary", download)

    assert binary_manager.fetch_binary("mpv", prompt_user=False) == expected
    download.assert_called_once_with(
        "mpv", binary_manager.deps["mpv"]["Windows"], "https://example.com/mpv.zip"
    )


def test_ensure_xvfb_does_not_apt_install(monkeypatch):
    """No DISPLAY, no Xvfb binary - it must warn instead of calling sudo apt-get."""
    monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "1")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(autodeps, "PLATFORM", "Linux")
    monkeypatch.setattr(autodeps.shutil, "which", lambda _: None)

    autodeps._ensure_xvfb()  # _no_subprocess turns any install attempt into a failure


def test_ensure_patchright_chromium_is_skipped(monkeypatch):
    monkeypatch.setenv("ANIWORLD_NO_AUTO_INSTALL", "1")
    monkeypatch.setattr(
        autodeps, "_ensure_xvfb", lambda: pytest.fail("should not touch Xvfb")
    )

    autodeps.ensure_patchright_chromium()
