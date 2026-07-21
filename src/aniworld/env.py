import os
import re
import shutil
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

# match lines like KEY=VALUE, ignoring comments and blank lines
ENV_LINE_RE = re.compile(r"^([^#\n=]+?)=(.*)$")


def initialize_app_env(example_path: Path, default_dir: Path) -> Path:
    """Resolve the app directory and load its .env file.

    The default .env doubles as the pointer to a relocated app directory. On
    first relocation, copy the existing file so user settings move with it.
    """
    default_dir = Path(default_dir).expanduser().resolve()
    default_env_path = default_dir / ".env"

    configured_dir = os.environ.get("ANIWORLD_INSTALL_FOLDER")
    if configured_dir is None and default_env_path.exists():
        configured_dir = dotenv_values(default_env_path).get("ANIWORLD_INSTALL_FOLDER")

    app_dir = Path(configured_dir or default_dir).expanduser()
    if not app_dir.is_absolute():
        app_dir = Path.home() / app_dir
    app_dir = app_dir.resolve()

    env_path = app_dir / ".env"
    if (
        env_path != default_env_path
        and not env_path.exists()
        and default_env_path.exists()
    ):
        app_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(default_env_path, env_path)

    merge_env(example_path, env_path)
    return app_dir


def merge_env(example_path: Path, env_path: Path):
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if not example_path.exists():
        if env_path.exists():
            load_dotenv(env_path)
        return

    example_lines = example_path.read_text().splitlines()

    # Load existing values from old env
    existing_values = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            m = ENV_LINE_RE.match(line)
            if m:
                existing_values[m.group(1).strip()] = m.group(2).strip()

    merged_lines = []
    for line in example_lines:
        m = ENV_LINE_RE.match(line)
        if not m:
            # keep comments, blank lines, formatting exactly
            merged_lines.append(line)
            continue

        key = m.group(1).strip()
        default_value = m.group(2)

        # replace value if user has one
        if key in existing_values:
            merged_lines.append(f"{key}={existing_values[key]}")
        else:
            merged_lines.append(f"{key}={default_value}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(merged_lines) + "\n")

    # Load the merged env file
    load_dotenv(env_path)


def persist_env_values(env_path: Path, updates: dict):
    """Write specific KEY=VALUE pairs into the .env file, preserving the rest.

    Only the given keys are touched: existing lines (comments, other keys,
    formatting) are kept as-is, matching keys are rewritten in place, and any
    missing keys are appended at the end. Used to persist settings that must
    survive a restart (e.g. the Discord bot config) while every other web-UI
    setting stays session-only.
    """
    env_path = Path(env_path)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text().splitlines() if env_path.exists() else []

    remaining = dict(updates)
    out = []
    for line in lines:
        m = ENV_LINE_RE.match(line)
        key = m.group(1).strip() if m else None
        if key is not None and key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)

    for key, value in remaining.items():
        out.append(f"{key}={value}")

    env_path.write_text("\n".join(out) + "\n")
