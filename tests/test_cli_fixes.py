"""Offline checks for small CLI fixes: search abort, --provider-url, banner, Anime4K remove."""

import importlib
import sys

import pytest

from aniworld import entry, search

# The packages re-export functions that shadow their submodule names.
a4k = importlib.import_module("aniworld.anime4k.anime4k")
ascii_art = importlib.import_module("aniworld.ascii.ascii")


def test_aborted_search_exits_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["aniworld"])
    monkeypatch.setattr(search, "search", lambda: None)
    assert entry.aniworld() == 1
    assert "unexpected error" not in capsys.readouterr().err


def test_provider_url_without_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["aniworld", "--provider-url", "https://voe.sx/e/x"]
    )
    with pytest.raises(SystemExit) as exc:
        entry.parse_args()
    assert exc.value.code == 2


def test_legacy_windows_banner_is_printed(monkeypatch, capsys):
    monkeypatch.setattr(ascii_art.platform, "system", lambda: "Windows")
    monkeypatch.setattr(ascii_art.platform, "release", lambda: "10")
    ascii_art.display_ascii_art()
    assert capsys.readouterr().out.strip()


def test_anime4k_remove_deletes_assets(monkeypatch, tmp_path):
    monkeypatch.setattr(a4k, "ANIWORLD_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(a4k, "MPV_CONFIG_DIR", tmp_path / "mpv")
    assets = tmp_path / "Anime4K" / "GLSL_Windows_High-end"
    assets.mkdir(parents=True)
    a4k.anime4k(mode="remove")
    assert not (tmp_path / "Anime4K").exists()
