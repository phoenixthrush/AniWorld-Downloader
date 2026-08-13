"""Resolve the version string shown in the navbar."""

import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path


def get_version():
    """Installed package version, falling back to pyproject when run from source."""
    try:
        installed = package_version("aniworld")
        if installed:
            return installed
    except PackageNotFoundError:
        pass
    except Exception:
        pass

    for parent in Path(__file__).resolve().parents:
        pyproject = parent / "pyproject.toml"
        if not pyproject.exists():
            continue
        try:
            match = re.search(
                r'^\s*version\s*=\s*"([^"]+)"',
                pyproject.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        except OSError:
            break
        return match.group(1) if match else ""
    return ""
