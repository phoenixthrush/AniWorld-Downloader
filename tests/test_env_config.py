"""Startup settings stay discoverable and survive template updates."""

import ast
import os
import re
from pathlib import Path

from dotenv import dotenv_values

from aniworld.env import merge_env
from aniworld.web.media import SITE_KEYS

SOURCE = Path(__file__).resolve().parents[1] / "src" / "aniworld"


def test_template_covers_application_settings():
    settings = set(dotenv_values(SOURCE / ".env.example"))
    used = {f"ANIWORLD_ENABLE_{site.upper()}" for site in SITE_KEYS}
    for path in SOURCE.rglob("*.py"):
        used.update(
            node.value
            for node in ast.walk(ast.parse(path.read_text()))
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
        "ANIWORLD_KEEP_WATCHING": "1",
        "ANIWORLD_ENABLE_FILMO": "0",
    }
    env.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    merge_env(example, env)
    loaded = dotenv_values(env)
    assert {key: loaded[key] for key in values} == values
