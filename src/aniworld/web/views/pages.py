"""HTML pages."""

import platform
from pathlib import Path

from flask import Blueprint, abort, current_app, render_template, send_from_directory

from ...config import ANIWORLD_CONFIG_DIR, LANG_LABELS
from .. import settings_store
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
    )


@bp.route("/library")
def library():
    if not settings_store.library_enabled():
        abort(404)
    return render_template("library.html")


@bp.route("/autosync")
def autosync():
    if not settings_store.autosync_enabled():
        abort(404)
    return render_template("autosync.html")


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
