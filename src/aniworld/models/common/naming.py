"""Shared movie, series, and manga naming."""

import os
import re
from pathlib import Path

from .common import clean_title, movie_folder_enabled


def template_path(
    root,
    template,
    values,
    *,
    is_series,
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
    if not is_series:
        parts = [part for part in parts[:-1] if "{season}" not in part] + parts[-1:]
        parts[-1] = parts[-1].replace("{title} S{season}E{episode}", "{title} ({year})")
        parts[-1] = parts[-1].replace("S{season}E{episode}", "")
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


class TemplatePaths:
    """Opt-in templates; retain each site's existing paths for old downloads."""

    _template_kind = "series"
    _template_filename_title = None

    @property
    def _naming_template(self):
        return os.getenv(f"ANIWORLD_{self._template_kind.upper()}_NAMING_TEMPLATE")

    @property
    def _template_path(self):
        template = self._naming_template
        if not template:
            return None
        path = template_path(
            self.selected_path,
            template,
            self._template_values,
            is_series=self._template_kind == "series",
            movie_folder=movie_folder_enabled(),
            filename_title=self._template_filename_title,
        )
        if path.suffix.lower() not in {".mkv", ".mp4"}:
            raise ValueError("Video naming templates must use .mkv or .mp4")
        return path

    @property
    def _episode_path(self):
        path = self._template_path
        if path is None:
            return self._legacy_episode_path
        if path.exists():
            return path
        legacy = self._legacy_episode_path
        return legacy if legacy.exists() else path

    @property
    def _base_folder(self):
        if not self._naming_template:
            return self._legacy_base_folder
        root = Path(self.selected_path)
        relative = self._episode_path.relative_to(root)
        return root / relative.parts[0] if len(relative.parts) > 1 else root

    @property
    def _folder_path(self):
        return self._episode_path.parent

    @property
    def _file_name(self):
        return self._episode_path.stem

    @property
    def _file_extension(self):
        return self._episode_path.suffix.lstrip(".")
