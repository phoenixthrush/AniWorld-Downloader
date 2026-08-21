"""Settings, custom paths and Discord bot status."""

from flask import jsonify, request

from ...logger import get_logger
from .. import db, schedule, settings_store, theming
from ..media import normalize_default_sites

logger = get_logger(__name__)


def register(bp):
    bp.add_url_rule("/settings", view_func=get_settings)
    bp.add_url_rule("/settings", view_func=update_settings, methods=["PUT"])
    bp.add_url_rule("/settings/public-ip", view_func=public_ip)
    bp.add_url_rule(
        "/settings/schedule-preview", view_func=preview_schedule, methods=["POST"]
    )
    bp.add_url_rule("/custom-css", view_func=get_custom_css)
    bp.add_url_rule("/custom-css", view_func=update_custom_css, methods=["PUT"])
    bp.add_url_rule("/custom-shader", view_func=get_custom_shader)
    bp.add_url_rule("/custom-shader", view_func=update_custom_shader, methods=["PUT"])
    bp.add_url_rule("/discord/status", view_func=discord_status)
    bp.add_url_rule("/custom-paths", view_func=list_custom_paths)
    bp.add_url_rule("/custom-paths", view_func=add_custom_path, methods=["POST"])
    bp.add_url_rule(
        "/custom-paths/<int:path_id>", view_func=update_custom_path, methods=["PUT"]
    )
    bp.add_url_rule(
        "/custom-paths/<int:path_id>", view_func=delete_custom_path, methods=["DELETE"]
    )


def get_settings():
    return jsonify(settings_store.read_settings())


def update_settings():
    data = request.get_json(silent=True) or {}
    try:
        discord_changed = settings_store.update_settings(data)
    except settings_store.SettingsError as exc:
        return jsonify({"error": str(exc)}), 400

    if discord_changed:
        _reconcile_discord()
    return jsonify({"ok": True})


def preview_schedule():
    """What an Auto-Sync schedule would mean, for the hint under the fields.

    Takes the same fields as PUT /settings, so the page can ask about what is
    on screen before anything is saved. This only reads: nothing is stored and
    saving stays a separate request.
    """
    data = request.get_json(silent=True) or {}
    language = settings_store.ui_language()

    if "autosync_interval" in data:
        try:
            seconds = schedule.parse_interval(data["autosync_interval"])
        except schedule.ScheduleError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(
            {
                "interval": schedule.format_interval(seconds),
                "description": schedule.describe_interval(seconds, language),
            }
        )

    try:
        parsed = schedule.parse(str(data.get("autosync_cron", "")))
    except schedule.ScheduleError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {"cron": parsed.expression, "description": parsed.describe(language)}
    )


def _reconcile_discord():
    try:
        from ..discord_bot import reconcile
    except ImportError as exc:
        logger.warning("Discord bot unavailable: %s", exc)
        return
    try:
        reconcile()
    except Exception:
        logger.exception("Discord bot reconcile failed")


# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
def get_custom_css():
    css = theming.read()
    return jsonify(
        {
            "css": css,
            "max_bytes": theming.MAX_BYTES,
            "warnings": theming.import_warnings(css),
        }
    )


def update_custom_css():
    data = request.get_json(silent=True) or {}
    css = data.get("css", "")
    if not isinstance(css, str):
        return jsonify({"error": "css must be a string"}), 400

    try:
        stored = theming.write(css)
    except theming.CSSTooLarge as exc:
        return jsonify({"error": str(exc)}), 413
    except OSError as exc:
        logger.error("Could not save custom CSS: %s", exc)
        return jsonify({"error": "Could not write the stylesheet"}), 500

    # The page reloads its own stylesheet against this, so a save shows up
    # without the browser serving the previous theme from cache.
    return jsonify(
        {
            "ok": True,
            "css": stored,
            "version": theming.version(),
            "warnings": theming.import_warnings(stored),
        }
    )


def get_custom_shader():
    return jsonify(
        {"shader": theming.read_shader(), "max_bytes": theming.MAX_SHADER_BYTES}
    )


def update_custom_shader():
    """Store a fragment shader. It is never compiled or run here, only served.

    GLSL cannot reach the DOM, cookies, the network or the filesystem, so the
    blast radius of a bad one is a wrong looking background.
    """
    data = request.get_json(silent=True) or {}
    source = data.get("shader", "")
    if not isinstance(source, str):
        return jsonify({"error": "shader must be a string"}), 400

    try:
        stored = theming.write_shader(source)
    except theming.ShaderTooLarge as exc:
        return jsonify({"error": str(exc)}), 413
    except OSError as exc:
        logger.error("Could not save custom shader: %s", exc)
        return jsonify({"error": "Could not write the shader"}), 500

    return jsonify({"ok": True, "shader": stored, "version": theming.shader_version()})


def public_ip():
    """Only called when the user presses reveal, never on page load."""
    try:
        return jsonify({"ok": True, **settings_store.fetch_public_ip()})
    except RuntimeError as exc:
        logger.warning("Failed to resolve public IP: %s", exc)
        return jsonify({"ok": False, "error": "Failed to fetch public IP"}), 502


def discord_status():
    try:
        from ..discord_bot import get_status

        return jsonify(get_status())
    except Exception as exc:
        return jsonify({"running": False, "error": str(exc)[:120]})


# ---------------------------------------------------------------------------
# Custom paths
# ---------------------------------------------------------------------------
def list_custom_paths():
    return jsonify({"paths": db.get_custom_paths()})


def add_custom_path():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    path = (data.get("path") or "").strip()
    if not name or not path:
        return jsonify({"error": "name and path are required"}), 400

    try:
        path_id = db.add_custom_path(
            name, path, normalize_default_sites(data.get("default_sites"))
        )
    except Exception:
        return jsonify({"error": "A path with that name already exists"}), 409
    return jsonify({"ok": True, "id": path_id})


def update_custom_path(path_id):
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    path = data.get("path")

    # Blanking either is refused the same way creating one blank is. An empty
    # path resolves to the home directory, so downloads would land loose in it.
    for field, value in (("name", name), ("path", path)):
        if isinstance(value, str) and not value.strip():
            return jsonify({"error": f"{field} cannot be empty"}), 400

    db.update_custom_path(
        path_id,
        name=name.strip() if isinstance(name, str) else None,
        path=path.strip() if isinstance(path, str) else None,
        default_sites=normalize_default_sites(data["default_sites"])
        if "default_sites" in data
        else None,
    )
    return jsonify({"ok": True})


def delete_custom_path(path_id):
    db.remove_custom_path(path_id)
    return jsonify({"ok": True})
