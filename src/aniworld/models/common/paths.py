import os
from pathlib import Path


def resolve_download_path(selected_path: str | Path | None = None) -> Path:
    """Expand model paths beneath home; CLI output paths arrive absolute."""
    value = selected_path
    if not value or (isinstance(value, str) and not value.strip()):
        value = os.getenv("ANIWORLD_DOWNLOAD_PATH", "").strip() or "Downloads"
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path.home() / path
