"""Template paths for movie and series models."""

import re
from pathlib import Path

from .common import clean_title


def template_path(root, template, values, *, is_series, movie_folder=True):
    """Format all path components, keeping metadata inside each component."""
    for key in values:
        template = template.replace(f"%{key}%", f"{{{key}}}")
    values = {key: clean_title(str(value or "")) for key, value in values.items()}
    parts = template.split("/")
    if not is_series:
        parts = [part for part in parts[:-1] if "{season}" not in part] + parts[-1:]
        parts[-1] = parts[-1].replace("{title} S{season}E{episode}", "{title} ({year})")
        parts[-1] = parts[-1].replace("S{season}E{episode}", "")
        if not movie_folder:
            parts = parts[-1:]
    formatted = []
    for part in parts:
        part = part.format(**values)
        part = re.sub(r"\s*\[imdbid-\]\s*", " ", part)
        part = part.replace("()", "")
        part = clean_title(part)
        part = re.sub(r"\s+", " ", part).strip(" .")
        if part in {"", ".", ".."}:
            continue
        formatted.append(part)
    if not formatted:
        raise ValueError("Naming template does not produce a filename")
    path = Path(root).joinpath(*formatted)
    return path if Path(parts[-1]).suffix else Path(f"{path}.mkv")
