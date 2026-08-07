"""Settings, custom paths and Discord bot status."""

from flask import jsonify, request

from ...logger import get_logger
from .. import db, settings_store
from ..media import normalize_default_sites

logger = get_logger(__name__)


def register(bp):
    bp.add_url_rule("/settings", view_func=get_settings)
    bp.add_url_rule("/settings", view_func=update_settings, methods=["PUT"])
    bp.add_url_rule("/settings/public-ip", view_func=public_ip)
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


def _reconcile_discord():
    try:
        from ..discord_bot import reconcile
    except ImportError as exc:
        logger.warning("Discord bot unavailable: %s", exc)
        return
    try:
        reconcile()
    except Exception as exc:
        logger.error("Discord bot reconcile failed: %s", exc, exc_info=True)


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
