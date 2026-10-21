"""Shared movie, series, and manga naming."""

import os
import re
from pathlib import Path

from ...config import NAMING_TEMPLATES
from .common import clean_title, movie_folder_enabled


def template_path(
    root,
    template,
    values,
    *,
    movie_folder=True,
    extension="mkv",
    filename_title=None,
):
    """Format all path components, keeping metadata inside each component."""
    for key in values:
        template = template.replace(f"%{key}%", f"{{{key}}}")
    values = {
        key: clean_title(str(value if value is not None else ""))
        for key, value in values.items()
    }
    parts = template.split("/")
    if not movie_folder:
        parts = parts[-1:]
    formatted = []
    for index, part in enumerate(parts):
        part_values = values
        if index == len(parts) - 1 and filename_title is not None:
            part_values = dict(values, title=clean_title(filename_title))
        part = part.format(**part_values)
        part = re.sub(r"\s*\[imdbid-\]\s*", " ", part)
        part = part.replace("()", "")
        part = part.replace("[]", "")
        part = clean_title(part)
        part = re.sub(r"\s+", " ", part).strip(" .")
        if "{chapter_title}" in parts[index] and not values.get("chapter_title"):
            part = re.sub(r"\s+-\s*$", "", part)
        if part in {"", ".", ".."}:
            if index == len(parts) - 1:
                raise ValueError("Naming template does not produce a filename")
            continue
        formatted.append(part)
    if not formatted:
        raise ValueError("Naming template does not produce a filename")
    path = Path(root).joinpath(*formatted)
    return (
        path if not extension or Path(parts[-1]).suffix else Path(f"{path}.{extension}")
    )


def naming_template(kind):
    """Return the media type's template, using its default when empty/unset."""
    return (
        os.getenv(f"ANIWORLD_{kind.upper()}_NAMING_TEMPLATE") or NAMING_TEMPLATES[kind]
    )


def media_path(root, kind, values, *, filename_title=None):
    """Build one deterministic path from provider metadata and a media template."""
    path = template_path(
        root,
        naming_template(kind),
        values,
        movie_folder=kind != "movie" or movie_folder_enabled(),
        extension="" if kind == "manga" else "mkv",
        filename_title=filename_title,
    )
    if kind != "manga" and path.suffix.lower() not in {".mkv", ".mp4"}:
        raise ValueError("Video naming templates must use .mkv or .mp4")
    return path


def base_folder(root, path):
    """Return the first template directory, or the root for a flat template."""
    root = Path(root)
    relative = path.relative_to(root)
    return root / relative.parts[0] if len(relative.parts) > 1 else root
