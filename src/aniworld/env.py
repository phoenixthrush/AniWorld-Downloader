import re
from pathlib import Path

from dotenv import load_dotenv

# match lines like KEY=VALUE, ignoring comments and blank lines
ENV_LINE_RE = re.compile(r"^([^#\n=]+?)=(.*)$")


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
