import os
import re
from pathlib import Path

from dotenv import load_dotenv

# match lines like KEY=VALUE, ignoring comments and blank lines
ENV_LINE_RE = re.compile(r"^([^#\n=]+?)=(.*)$")

# Default location of the user's .env file
DEFAULT_ENV_PATH = Path.home() / ".aniworld" / ".env"


def merge_env(example_path: Path, env_path: Path):
    env_path.parent.mkdir(parents=True, exist_ok=True)
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


def format_env_value(value) -> str:
    """Quote a value so dotenv reads it back unchanged."""
    text = "" if value is None else str(value)
    if text == "":
        return ""
    needs_quotes = any(c in text for c in ' \t#"\'') or text != text.strip()
    if not needs_quotes:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def update_env_values(updates: dict, env_path: Path = None) -> None:
    """Persist KEY=VALUE pairs into the user's .env file.

    Existing keys are rewritten in place so comments, blank lines and the
    ordering of the file survive. Unknown keys are appended at the end.
    Also updates os.environ so the change takes effect immediately.
    """
    if not updates:
        return

    env_path = Path(env_path or DEFAULT_ENV_PATH)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines = env_path.read_text().splitlines() if env_path.exists() else []
    remaining = dict(updates)
    new_lines = []

    for line in lines:
        m = ENV_LINE_RE.match(line)
        if m:
            key = m.group(1).strip()
            if key in remaining:
                new_lines.append(f"{key}={format_env_value(remaining.pop(key))}")
                continue
        new_lines.append(line)

    for key, value in remaining.items():
        new_lines.append(f"{key}={format_env_value(value)}")

    env_path.write_text("\n".join(new_lines) + "\n")

    for key, value in updates.items():
        os.environ[key] = "" if value is None else str(value)


def read_env_file(env_path: Path = None) -> str:
    """Return the raw contents of the user's .env file."""
    env_path = Path(env_path or DEFAULT_ENV_PATH)
    if not env_path.exists():
        return ""
    return env_path.read_text()


def write_env_file(content: str, env_path: Path = None) -> None:
    """Overwrite the user's .env file and reload it into the process."""
    env_path = Path(env_path or DEFAULT_ENV_PATH)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    env_path.write_text(normalized)

    load_dotenv(env_path, override=True)
