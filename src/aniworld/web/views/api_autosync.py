"""AutoSync status, exclusions and the manual Sync now trigger."""

import threading

from flask import abort, jsonify, request

from ...logger import get_logger
from .. import autosync, db
from ..settings_store import autosync_enabled

logger = get_logger(__name__)


def register(bp):
    bp.add_url_rule("/autosync/status", view_func=autosync_status)
    bp.add_url_rule("/autosync/run", view_func=autosync_run, methods=["POST"])
    bp.add_url_rule("/autosync/exclusions", view_func=list_exclusions)
    bp.add_url_rule("/autosync/exclusions", view_func=add_exclusion, methods=["POST"])
    bp.add_url_rule(
        "/autosync/exclusions/<int:exclusion_id>",
        view_func=delete_exclusion,
        methods=["DELETE"],
    )
    # Used by the download modal, so it stays available to non-admins
    bp.add_url_rule("/autosync/excluded", view_func=exclusion_state)
    bp.add_url_rule(
        "/autosync/excluded", view_func=set_exclusion_state, methods=["POST"]
    )


def _guard():
    if not autosync_enabled():
        abort(404)


def autosync_status():
    _guard()
    return jsonify(autosync.status())


def autosync_run():
    """Kick off a cycle in the background so the request returns immediately."""
    _guard()
    if autosync.is_running():
        return jsonify({"error": "A sync is already running"}), 409

    threading.Thread(
        target=_run_quietly, name="aniworld-autosync-manual", daemon=True
    ).start()
    return jsonify({"ok": True, "started": True})


def _run_quietly():
    try:
        autosync.run_cycle()
    except RuntimeError as exc:
        logger.info("AutoSync manual run skipped: %s", exc)
    except Exception:
        logger.exception("AutoSync manual run failed")


def list_exclusions():
    _guard()
    return jsonify({"exclusions": db.get_autosync_exclusions()})


def add_exclusion():
    _guard()
    data = request.get_json(silent=True) or {}
    series_url = (data.get("series_url") or "").strip()
    if not series_url:
        return jsonify({"error": "series_url is required"}), 400
    db.add_autosync_exclusion(series_url, (data.get("title") or "").strip())
    return jsonify({"ok": True})


def delete_exclusion(exclusion_id):
    _guard()
    db.remove_autosync_exclusion(exclusion_id=exclusion_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Download modal checkbox
# ---------------------------------------------------------------------------
def exclusion_state():
    _guard()
    series_url = (request.args.get("url") or "").strip()
    if not series_url:
        return jsonify({"error": "url is required"}), 400
    return jsonify({"excluded": db.is_autosync_excluded(series_url)})


def set_exclusion_state():
    _guard()
    data = request.get_json(silent=True) or {}
    series_url = (data.get("series_url") or "").strip()
    if not series_url:
        return jsonify({"error": "series_url is required"}), 400

    if data.get("excluded"):
        db.add_autosync_exclusion(series_url, (data.get("title") or "").strip())
    else:
        db.remove_autosync_exclusion(series_url=series_url)
    return jsonify({"ok": True})
