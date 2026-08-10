"""HTML pages."""

import platform
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    render_template,
    send_from_directory,
)

from ...config import ANIWORLD_CONFIG_DIR, LANG_LABELS
from .. import paths, settings_store, theming
from ..media import WORKING_PROVIDERS

bp = Blueprint("pages", __name__)

# Language options per site. AniWorld is the only one with subs.
STO_LANGUAGES = {"1": "German Dub", "2": "English Dub"}
MEGAKINO_LANGUAGES = {"1": "German Dub"}


@bp.route("/favicon.ico")
def favicon():
    return send_from_directory(
        Path(current_app.root_path) / "static", "favicon.png", mimetype="image/png"
    )


@bp.route("/custom.css")
def custom_css():
    """The instance wide theme, served as its own stylesheet.

    Not linked from the login or setup pages, so a theme can never restyle the
    form people type their password into.
    """
    css = theming.read()
    response = Response(css, mimetype="text/css")
    # The link carries a content hash, so a cached copy is always the right one
    # and a save shows up immediately under a new URL.
    response.headers["Cache-Control"] = (
        "public, max-age=31536000, immutable" if css else "no-store"
    )
    return response


@bp.route("/custom.frag")
def custom_shader():
    """The theme's fragment shader. GLSL only, never executed on the server."""
    source = theming.read_shader()
    response = Response(source, mimetype="text/plain")
    response.headers["Cache-Control"] = (
        "public, max-age=31536000, immutable" if source else "no-store"
    )
    return response


@bp.route("/")
def index():
    return render_template(
        "index.html",
        lang_labels=LANG_LABELS,
        sto_lang_labels=STO_LANGUAGES,
        megakino_lang_labels=MEGAKINO_LANGUAGES,
        supported_providers=WORKING_PROVIDERS,
        default_language=settings_store.default_language(),
        htv_enabled=settings_store.htv_enabled(),
        burningseries_enabled=settings_store.burningseries_enabled(),
        kinox_enabled=settings_store.kinox_enabled(),
    )


@bp.route("/queue")
def queue():
    return render_template("queue.html")


@bp.route("/library")
def library():
    if not settings_store.library_enabled():
        abort(404)
    return render_template("library.html")


@bp.route("/autosync")
def autosync():
    if not settings_store.autosync_enabled():
        abort(404)
    return render_template(
        "autosync.html", lang_separation=paths.lang_separation_enabled()
    )


@bp.route("/settings")
def settings():
    return render_template("settings.html", env_path=_display_env_path())


def _display_env_path():
    """Show the .env location, shortened to ~/ where that makes sense."""
    env_path = ANIWORLD_CONFIG_DIR / ".env"
    if platform.system() == "Windows":
        return str(env_path)
    try:
        return f"~/{env_path.relative_to(Path.home())}"
    except ValueError:
        return str(env_path)
