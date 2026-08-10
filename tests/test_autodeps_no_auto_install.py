"""ANIWORLD_NO_AUTO_INSTALL blocks every unattended download/install."""

import subprocess

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
