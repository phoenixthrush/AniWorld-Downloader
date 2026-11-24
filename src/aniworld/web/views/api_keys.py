"""API key management and the /api/ping identity check."""

from flask import current_app, jsonify, request

from ...logger import get_logger
from .. import apikeys, db
from ..version import get_version

logger = get_logger(__name__)

MAX_EXPIRY_DAYS = 3650


def register(bp):
    bp.add_url_rule("/ping", view_func=ping)
    bp.add_url_rule("/keys", view_func=list_api_keys)
    bp.add_url_rule("/keys", view_func=create_api_key, methods=["POST"])
    bp.add_url_rule("/keys/<int:key_id>", view_func=delete_api_key, methods=["DELETE"])


def _identity():
    """Who is calling and what they may do, for /api/ping."""
    key = apikeys.current()
    if key:
        return {"method": "api_key", "name": key["name"], "scope": key["scope"]}
    if not current_app.config.get("AUTH_ENABLED", False):
        return {"method": "open", "name": None, "scope": "admin"}

    from ..auth import get_current_user

    user = get_current_user()
    if not user:
        return {"method": "none", "name": None, "scope": "read"}
    return {
        "method": "session",
        "name": user["username"],
        "scope": "admin" if user["role"] == "admin" else "write",
    }


def ping():
    """Lets a client confirm its key works and see what it is allowed to do."""
    return jsonify(
        {
            "ok": True,
            "version": get_version(),
            "auth_enabled": current_app.config.get("AUTH_ENABLED", False),
            **_identity(),
        }
    )


def _created_by():
    if not current_app.config.get("AUTH_ENABLED", False):
        return None
    from ..auth import current_username

    return current_username()


def list_api_keys():
    return jsonify({"keys": db.list_api_keys(), "scopes": list(apikeys.SCOPES)})


def _expiry_days(raw):
    """Returns (days, error). Empty, 0 or missing means the key never expires."""
    if raw in (None, "", 0, "0"):
        return None, None
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return None, "expires_days must be a number"
    if days < 1 or days > MAX_EXPIRY_DAYS:
        return None, f"expires_days must be between 1 and {MAX_EXPIRY_DAYS}"
    return days, None


def create_api_key():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    scope = (data.get("scope") or "write").strip()

    if not name:
        return jsonify({"error": "name is required"}), 400
    if len(name) > 64:
        return jsonify({"error": "name must be at most 64 characters"}), 400
    if scope not in apikeys.SCOPES:
        return jsonify({"error": "scope must be read, write or admin"}), 400

    days, error = _expiry_days(data.get("expires_days"))
    if error:
        return jsonify({"error": error}), 400

    raw = apikeys.generate()
    key_id = db.create_api_key(
        name=name,
        key_hash=apikeys.hash_key(raw),
        prefix=raw[: len(apikeys.KEY_PREFIX) + 6],
        scope=scope,
        created_by=_created_by(),
        expires_days=days,
    )
    logger.info("Created API key '%s' (%s)", name, scope)

    # The only time the plain key leaves the server, after this only the hash exists
    return jsonify({"id": key_id, "name": name, "scope": scope, "key": raw})


def delete_api_key(key_id):
    if not db.delete_api_key(key_id):
        return jsonify({"error": "Key not found"}), 404
    return jsonify({"ok": True})
