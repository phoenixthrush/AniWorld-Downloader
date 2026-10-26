"""Startup settings stay discoverable and survive template updates."""

import ast
import os
import re
from pathlib import Path
from unittest.mock import Mock

import pytest
from dotenv import dotenv_values

from aniworld.env import initialize_app_env, merge_env
from aniworld.web.media import SITE_KEYS

SOURCE = Path(__file__).resolve().parents[1] / "src" / "aniworld"


@pytest.mark.parametrize("source", ["environment", "dotenv"])
@pytest.mark.parametrize("value", ["", "   ", "\t \t"])
def test_blank_install_folder_uses_default_directory(
    tmp_path, monkeypatch, source, value
):
    home = tmp_path / "home"
    default_dir = home / ".aniworld"
    default_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    example = tmp_path / "example"
    example.write_text(
        "ANIWORLD_INSTALL_FOLDER=.aniworld\nANIWORLD_LANGUAGE=German Dub\n"
    )
    saved_folder = value if source == "dotenv" else "relocated"
    env_path = default_dir / ".env"
    env_path.write_text(
        f'ANIWORLD_INSTALL_FOLDER="{saved_folder}"\nANIWORLD_LANGUAGE=English Dub\n'
    )
    if source == "environment":
        monkeypatch.setenv("ANIWORLD_INSTALL_FOLDER", value)
    else:
        monkeypatch.delenv("ANIWORLD_INSTALL_FOLDER", raising=False)

    assert initialize_app_env(example, default_dir) == default_dir
    assert dotenv_values(env_path)["ANIWORLD_LANGUAGE"] == "English Dub"
    assert list(home.iterdir()) == [default_dir]


@pytest.mark.parametrize("source", ["environment", "dotenv"])
def test_nonblank_install_folder_preserves_spaces(tmp_path, monkeypatch, source):
    home = tmp_path / "home"
    default_dir = home / ".aniworld"
    default_dir.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    example = tmp_path / "example"
    example.write_text("ANIWORLD_INSTALL_FOLDER=.aniworld\n")
    value = "custom data"
    if source == "environment":
        monkeypatch.setenv("ANIWORLD_INSTALL_FOLDER", value)
    else:
        monkeypatch.delenv("ANIWORLD_INSTALL_FOLDER", raising=False)
        (default_dir / ".env").write_text(f'ANIWORLD_INSTALL_FOLDER="{value}"\n')

    expected_dir = (home / value).resolve()
    assert initialize_app_env(example, default_dir) == expected_dir
    assert (expected_dir / ".env").is_file()


def test_install_folder_resolution_preserves_surrounding_spaces(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    value = "  custom data  "
    monkeypatch.setenv("ANIWORLD_INSTALL_FOLDER", value)
    # Windows cannot reliably create a directory whose name ends in spaces.
    merge = Mock()
    monkeypatch.setattr("aniworld.env.merge_env", merge)
    example = tmp_path / "example"

    expected_dir = (home / value).resolve()
    assert initialize_app_env(example, home / ".aniworld") == expected_dir
    merge.assert_called_once_with(example, expected_dir / ".env")


@pytest.mark.parametrize("default_encoding", ["utf-8", "cp1252"])
def test_template_covers_application_settings(monkeypatch, default_encoding):
    read_text = Path.read_text

    def read_with_default(path, *args, **kwargs):
        kwargs.setdefault("encoding", default_encoding)
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_with_default)
    settings = set(dotenv_values(SOURCE / ".env.example"))
    used = {f"ANIWORLD_ENABLE_{site.upper()}" for site in SITE_KEYS}
    for path in SOURCE.rglob("*.py"):
        used.update(
            node.value
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and re.fullmatch(r"ANIWORLD_[A-Z0-9_]+", node.value)
            and node.value != "ANIWORLD_ENABLE_"
        )
    assert all(key.startswith("ANIWORLD_") for key in settings)
    assert used == settings


def test_mangafire_format_migrates_without_overriding_process_env(
    tmp_path, monkeypatch
):
    example = tmp_path / "example"
    example.write_text("ANIWORLD_MANGAFIRE_FORMAT=jpg\n")
    env = tmp_path / ".env"
    env.write_text("MANGAFIRE_FORMAT=cbz\n")
    monkeypatch.setenv("ANIWORLD_MANGAFIRE_FORMAT", "jpg")
    merge_env(example, env)
    assert dotenv_values(env) == {"ANIWORLD_MANGAFIRE_FORMAT": "cbz"}
    assert os.environ["ANIWORLD_MANGAFIRE_FORMAT"] == "jpg"


def test_explicit_new_format_wins_during_migration(tmp_path, monkeypatch):
    example = tmp_path / "example"
    example.write_text("ANIWORLD_MANGAFIRE_FORMAT=jpg\n")
    env = tmp_path / ".env"
    env.write_text("MANGAFIRE_FORMAT=cbz\nANIWORLD_MANGAFIRE_FORMAT=jpg\n")
    monkeypatch.delenv("ANIWORLD_MANGAFIRE_FORMAT", raising=False)
    merge_env(example, env)
    assert dotenv_values(env) == {"ANIWORLD_MANGAFIRE_FORMAT": "jpg"}


def test_cli_and_filmo_settings_survive_startup(tmp_path, monkeypatch):
    example = SOURCE / ".env.example"
    for key in dotenv_values(example):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    values = {
        "ANIWORLD_NO_MENU": "1",
        "ANIWORLD_MENU_DOWNLOAD_ONLY": "1",
        "ANIWORLD_KEEP_WATCHING": "1",
        "ANIWORLD_ENABLE_FILMO": "0",
    }
    env.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    merge_env(example, env)
    loaded = dotenv_values(env)
    assert {key: loaded[key] for key in values} == values
