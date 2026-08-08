"""Global custom CSS.

One stylesheet for the whole instance, stored next to the .env so it can be
edited by hand or mounted into a container. It is served as a real stylesheet
rather than inlined into the page, which keeps a stray </style> in someone's
CSS from breaking out of the tag.
"""

import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from ..config import ANIWORLD_CONFIG_DIR
from ..logger import get_logger

logger = get_logger(__name__)

# Big enough for any hand written theme, small enough that a paste accident
# cannot fill the disk.
MAX_BYTES = 512 * 1024

# CSS only honours @import before any other rule, so a theme pasted below a
# tweak would be dropped without a word. We hoist them instead of explaining it.
_IMPORT = re.compile(r"^[ \t]*@import\b[^;]*;[ \t]*$", re.MULTILINE)


class CSSTooLarge(ValueError):
    """Raised when the submitted stylesheet is over the size limit."""


# A browser only applies a stylesheet that arrives as text/css. These hosts send
# text/plain with nosniff, so the import is fetched and then thrown away without
# a word, not even a console warning. Worth catching before someone spends an
# evening on it.
PLAIN_TEXT_HOSTS = (
    "pastebin.com",
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
)

_IMPORT_URL = re.compile(r"@import\s+(?:url\(\s*)?['\"]?([^'\")\s;]+)")
_GITHUB_RAW = re.compile(
    r"^https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$"
)


# A fragment shader is a lot smaller than a stylesheet, and a huge one would
# only mean a huge GPU program.
MAX_SHADER_BYTES = 64 * 1024


def css_path():
    return Path(ANIWORLD_CONFIG_DIR) / "custom.css"


def shader_path():
    return Path(ANIWORLD_CONFIG_DIR) / "custom.frag"


def _jsdelivr_equivalent(url):
    """The same GitHub file through a CDN that sends it as text/css."""
    match = _GITHUB_RAW.match(url)
    if not match:
        return None
    user, repo, ref, path = match.groups()
    return f"https://cdn.jsdelivr.net/gh/{user}/{repo}@{ref}/{path}"


def import_warnings(css):
    """Imports the browser will silently refuse to apply."""
    found = []
    for url in _IMPORT_URL.findall(str(css)):
        host = (urlparse(url).hostname or "").lower()
        if host not in PLAIN_TEXT_HOSTS:
            continue
        found.append(
            {"url": url, "host": host, "suggestion": _jsdelivr_equivalent(url)}
        )
    return found


def normalise(css):
    """Trim, and lift any @import to the top where the browser will obey it."""
    text = str(css).replace("\r\n", "\n").strip()
    if not text:
        return ""

    imports = [line.strip() for line in _IMPORT.findall(text)]
    if not imports:
        return text + "\n"

    rest = _IMPORT.sub("", text).strip()
    # dedupe but keep the order they were written in
    seen, ordered = set(), []
    for line in imports:
        if line not in seen:
            seen.add(line)
            ordered.append(line)

    body = "\n".join(ordered)
    return f"{body}\n\n{rest}\n" if rest else body + "\n"


def _read_file(path, label):
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.warning("Could not read %s: %s", label, exc)
        return ""


def _write_file(path, text):
    """Write atomically, or delete when there is nothing to store."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text:
        path.unlink(missing_ok=True)
        return ""

    # Via a temp file in the same folder so a crash mid write cannot leave half
    # a file behind for every page load to trip over.
    handle, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return text


def read():
    """The stored stylesheet, or an empty string when there is none."""
    return _read_file(css_path(), "custom CSS")


def write(css):
    """Store the stylesheet. Returns the text as it was written."""
    text = normalise(css)
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise CSSTooLarge(f"Custom CSS must stay under {MAX_BYTES // 1024} KB")

    return _write_file(css_path(), text)


def version():
    """Short content hash, used to bust the browser cache after a save."""
    return _hash(read())


def _hash(text):
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Fragment shader
#
# Only GLSL is accepted, never JavaScript. A fragment shader runs on the GPU
# with no DOM, no cookies, no network and no filesystem, so a hostile one can
# draw something ugly but cannot reach anything. That is the whole reason this
# is a shader field and not a script field.
# ---------------------------------------------------------------------------
class ShaderTooLarge(ValueError):
    """Raised when the submitted shader is over the size limit."""


def read_shader():
    return _read_file(shader_path(), "custom shader")


def write_shader(source):
    """Store the fragment shader. Returns the text as it was written."""
    text = str(source).replace("\r\n", "\n").strip()
    if text:
        text += "\n"
    if len(text.encode("utf-8")) > MAX_SHADER_BYTES:
        raise ShaderTooLarge(f"Shader must stay under {MAX_SHADER_BYTES // 1024} KB")
    return _write_file(shader_path(), text)


def shader_version():
    return _hash(read_shader())
