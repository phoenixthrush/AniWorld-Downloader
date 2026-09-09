"""Library endpoints. Each one loads exactly one level of the tree.

Streaming is a plain file response with Range support: the browser gets the
bytes as they are on disk and does any repackaging itself (static/mkv-remux.js
turns Matroska into fragmented MP4 for Media Source Extensions, and, where the
codec needs it, re-encodes with WebCodecs on the viewer's own GPU). The server
never runs ffmpeg for playback.
"""

from flask import abort, jsonify, request, send_file

from ...logger import get_logger
from .. import db, library
from ..auth import current_username
from ..settings_store import library_enabled

logger = get_logger(__name__)


def register(bp):
    bp.add_url_rule("/library/locations", view_func=library_locations)
    bp.add_url_rule("/library/titles", view_func=library_titles)
    bp.add_url_rule("/library/title", view_func=library_title)
    bp.add_url_rule("/library/cards", view_func=library_cards)
    bp.add_url_rule("/library/continue", view_func=library_continue)
    bp.add_url_rule("/library/file", view_func=library_file)
    bp.add_url_rule("/library/thumbnail", view_func=library_thumbnail)
    bp.add_url_rule(
        "/library/thumbnail", view_func=store_thumbnail, methods=["POST"]
    )
    bp.add_url_rule("/library/progress", view_func=update_progress, methods=["POST"])
    bp.add_url_rule("/library/delete", view_func=delete_library_item, methods=["POST"])


def _guard():
    if not library_enabled():
        abort(404)


def _location_args(source=None):
    source = request.args if source is None else source
    path_id = str(source.get("path_id") or source.get("custom_path_id") or "").strip()
    lang_folder = str(source.get("lang_folder") or "").strip() or None
    return (int(path_id) if path_id.isdigit() else None), lang_folder


def _username():
    """Whose progress this is. Without accounts everyone shares one row set."""
    try:
        return current_username() or ""
    except Exception:
        return ""


def library_locations():
    _guard()
    return jsonify(library.list_locations())


def library_titles():
    _guard()
    path_id, lang_folder = _location_args()
    try:
        return jsonify({"titles": library.list_titles_with_meta(path_id, lang_folder)})
    except library.LibraryError as exc:
        return jsonify({"error": str(exc)}), 400


def library_title():
    _guard()
    path_id, lang_folder = _location_args()
    folder = request.args.get("folder", "").strip()
    if not folder:
        return jsonify({"error": "folder is required"}), 400
    try:
        return jsonify(
            library.read_title(folder, path_id, lang_folder, username=_username())
        )
    except library.LibraryError as exc:
        return jsonify({"error": str(exc)}), 400


def library_cards():
    _guard()
    path_id, lang_folder = _location_args()
    try:
        cards = library.list_cards(path_id, lang_folder, username=_username())
    except library.LibraryError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"cards": cards})


def library_continue():
    _guard()
    return jsonify({"items": library.continue_watching(_username())})


def _file_args():
    path_id, lang_folder = _location_args()
    folder = request.args.get("folder", "").strip()
    path = request.args.get("path", "").strip()
    if not folder or not path:
        abort(400)
    return folder, path, path_id, lang_folder


def library_file():
    """The video bytes, with Range support so the player can seek."""
    _guard()
    folder, path, path_id, lang_folder = _file_args()
    try:
        _, file = library.resolve_file(folder, path, path_id, lang_folder)
    except library.LibraryError:
        abort(404)
    response = send_file(
        file,
        mimetype=library.mime_type(file),
        conditional=True,
        max_age=0,
    )
    response.headers["Accept-Ranges"] = "bytes"
    # The API default is no-store; a media element re-requests ranges while
    # seeking, letting the browser keep what it already fetched is the point.
    response.headers["Cache-Control"] = "private, max-age=0"
    return response


def library_thumbnail():
    _guard()
    path_id, lang_folder = _location_args()
    folder = request.args.get("folder", "").strip()
    path = request.args.get("path", "").strip()
    stem = request.args.get("stem", "").strip()
    if not folder or not (path or stem):
        abort(400)
    try:
        if path:
            thumb = library.thumbnail_file(folder, path, path_id, lang_folder)
        else:
            thumb = library.thumbnail_by_stem(folder, stem, path_id, lang_folder)
    except library.LibraryError:
        abort(404)
    if thumb is None:
        abort(404)
    response = send_file(thumb, mimetype="image/jpeg", conditional=True, max_age=0)
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response


def store_thumbnail():
    """A cover frame the browser rendered from the episode, kept for everyone."""
    _guard()
    data = request.get_json(silent=True) or {}
    folder = str(data.get("folder") or "").strip()
    path = str(data.get("path") or "").strip()
    if not folder or not path:
        return jsonify({"error": "folder and path are required"}), 400
    path_id, lang_folder = _location_args(data)
    try:
        raw = library.decode_thumbnail(data.get("image"))
        stored = library.store_thumbnail(folder, path, raw, path_id, lang_folder)
    except library.LibraryError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "stored": stored})


def update_progress():
    """Where the viewer is in an episode; also the "mark as seen" toggle."""
    _guard()
    data = request.get_json(silent=True) or {}
    folder = str(data.get("folder") or "").strip()
    path = str(data.get("path") or "").strip()
    if not folder or not path:
        return jsonify({"error": "folder and path are required"}), 400
    path_id, lang_folder = _location_args(data)
    try:
        library.resolve_file(folder, path, path_id, lang_folder)
    except library.LibraryError as exc:
        return jsonify({"error": str(exc)}), 404

    watched = data.get("watched")
    try:
        position = float(data.get("position") or 0)
        duration = float(data.get("duration") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "position and duration must be numbers"}), 400
    if watched is not None:
        watched = bool(watched)
        if not watched:
            position = 0.0

    progress = db.set_watch_progress(
        _username(),
        db.location_key(path_id, lang_folder),
        folder,
        path,
        position=position,
        duration=duration,
        watched=watched,
    )
    return jsonify({"ok": True, "progress": progress})


def delete_library_item():
    _guard()
    data = request.get_json(silent=True) or {}
    folder = data.get("folder", "")
    if not folder:
        return jsonify({"error": "folder is required"}), 400

    try:
        deleted = library.delete(
            folder,
            season=data.get("season"),
            episode=data.get("episode"),
            custom_path_id=data.get("custom_path_id"),
            lang_folder=data.get("lang_folder"),
        )
    except library.LibraryError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "deleted": deleted})
