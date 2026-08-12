"""Library endpoints. Each one loads exactly one level of the tree."""

from flask import abort, jsonify, request

from ...logger import get_logger
from .. import library
from ..settings_store import library_enabled

logger = get_logger(__name__)


def register(bp):
    bp.add_url_rule("/library/locations", view_func=library_locations)
    bp.add_url_rule("/library/titles", view_func=library_titles)
    bp.add_url_rule("/library/title", view_func=library_title)
    bp.add_url_rule("/library/delete", view_func=delete_library_item, methods=["POST"])


def _guard():
    if not library_enabled():
        abort(404)


def _location_args():
    path_id = request.args.get("path_id", "").strip()
    lang_folder = request.args.get("lang_folder", "").strip() or None
    return (int(path_id) if path_id.isdigit() else None), lang_folder


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
        return jsonify(library.read_title(folder, path_id, lang_folder))
    except library.LibraryError as exc:
        return jsonify({"error": str(exc)}), 400


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
