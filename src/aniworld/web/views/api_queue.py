"""Download queue and captcha endpoints."""

from flask import Response, current_app, jsonify, request

from ...logger import get_logger
from .. import db, worker
from ..media import mangafire_format
from ..settings_store import english_sub_disabled

logger = get_logger(__name__)


def register(bp):
    bp.add_url_rule("/download", view_func=start_download, methods=["POST"])
    bp.add_url_rule("/queue", view_func=list_queue)
    bp.add_url_rule("/queue/counts", view_func=queue_counts)
    bp.add_url_rule("/queue/completed", view_func=clear_completed, methods=["DELETE"])
    bp.add_url_rule("/queue/<int:queue_id>", view_func=remove_item, methods=["DELETE"])
    bp.add_url_rule(
        "/queue/<int:queue_id>/cancel", view_func=cancel_item, methods=["POST"]
    )
    bp.add_url_rule(
        "/queue/<int:queue_id>/force-cancel",
        view_func=force_cancel_item,
        methods=["POST"],
    )
    bp.add_url_rule("/queue/<int:queue_id>/move", view_func=move_item, methods=["POST"])
    bp.add_url_rule(
        "/queue/<int:queue_id>/retry", view_func=retry_item, methods=["POST"]
    )
    bp.add_url_rule("/captcha/<int:queue_id>/screenshot", view_func=captcha_screenshot)
    bp.add_url_rule("/captcha/<int:queue_id>/status", view_func=captcha_status)
    bp.add_url_rule(
        "/captcha/<int:queue_id>/click", view_func=captcha_click, methods=["POST"]
    )


def _current_username():
    if not current_app.config.get("AUTH_ENABLED", False):
        return None
    from ..auth import current_username

    return current_username()


def start_download():
    data = request.get_json(silent=True) or {}
    episodes = data.get("episodes") or []
    if not episodes:
        return jsonify({"error": "episodes list is required"}), 400

    language = data.get("language", "German Dub")
    if language == "English Sub" and english_sub_disabled():
        return jsonify({"error": "English Sub downloads are disabled"}), 403

    provider = data.get("provider", "VOE")
    if provider == "MangaFire":
        episodes = _tag_mangafire(episodes, data.get("mangafire_format"))

    queue_id = db.add_to_queue(
        title=data.get("title", "Unknown"),
        series_url=data.get("series_url", ""),
        episodes=episodes,
        language=language,
        provider=provider,
        username=_current_username(),
        custom_path_id=data.get("custom_path_id"),
    )
    worker.ensure_started()
    return jsonify({"queue_id": queue_id})


def _tag_mangafire(episodes, requested_format):
    """MangaFire needs the output format stored per queued chapter."""
    output = requested_format or mangafire_format()
    tagged = []
    for entry in episodes:
        if isinstance(entry, dict):
            tagged.append({**entry, "mangafire_format": output})
        else:
            tagged.append({"url": entry, "mangafire_format": output})
    return tagged


# What ?status= accepts: a real status, or one of the two groups.
_STATUS_FILTERS = frozenset(
    ("queued", "running", "completed", "failed", "cancelled", "active", "finished")
)
_SORTS = frozenset(("smart", "newest", "oldest", "title"))

# Passing any of these switches the response to a page of the queue.
_PAGE_ARGS = ("limit", "offset", "status", "q", "sort")


def list_queue():
    """The queue, whole or a page of it.

    Without any query parameters this returns every row, which is what the
    documented API has always done and what scripts expect. Pass any of the
    paging parameters and you get one page plus the totals the pager needs.
    Paged rows leave out `episodes`, the largest column by far and one the list
    never displays; fetch the queue unpaged if you need it.
    """
    from ...models.common.common import get_ffmpeg_progress

    args = request.args
    if not any(arg in args for arg in _PAGE_ARGS):
        return jsonify(
            {"items": db.get_queue(), "ffmpeg_progress": get_ffmpeg_progress()}
        )

    status = args.get("status") or None
    if status and status not in _STATUS_FILTERS:
        return jsonify({"error": f"unknown status filter: {status}"}), 400

    sort = args.get("sort") or "smart"
    if sort not in _SORTS:
        return jsonify({"error": f"unknown sort: {sort}"}), 400

    try:
        limit = int(args.get("limit", 25))
        offset = int(args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit and offset must be whole numbers"}), 400
    if limit < 1 or offset < 0:
        return jsonify(
            {"error": "limit must be positive and offset cannot be negative"}
        ), 400

    items, total = db.get_queue_page(
        status=status,
        search=(args.get("q") or "").strip() or None,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return jsonify(
        {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "counts": db.queue_counts(),
            "ffmpeg_progress": get_ffmpeg_progress(),
        }
    )


def queue_counts():
    """Just the numbers, so the nav badge does not pull the whole queue."""
    return jsonify({"counts": db.queue_counts()})


def _result(ok, error, status=400):
    return (jsonify({"ok": True}), 200) if ok else (jsonify({"error": error}), status)


def remove_item(queue_id):
    return _result(*db.remove_from_queue(queue_id))


def cancel_item(queue_id):
    return _result(*db.cancel_queue_item(queue_id))


def force_cancel_item(queue_id):
    return _result(*db.cancel_queue_item(queue_id, force=True))


def move_item(queue_id):
    data = request.get_json(silent=True) or {}
    return _result(*db.move_queue_item(queue_id, (data.get("direction") or "").strip()))


def retry_item(queue_id):
    """Re-queue a failed or cancelled item, e.g. after solving the kinox captcha."""
    if not db.requeue_item(queue_id):
        return jsonify({"error": "Item not found or not retryable"}), 400
    worker.ensure_started()
    return jsonify({"ok": True})


def clear_completed():
    db.clear_completed()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Captcha (the playwright browser is streamed into the queue modal)
# ---------------------------------------------------------------------------
def _captcha_session(queue_id):
    from ...playwright.captcha import _active_sessions, _active_sessions_lock

    with _active_sessions_lock:
        return _active_sessions.get(queue_id)


def captcha_screenshot(queue_id):
    session = _captcha_session(queue_id)
    data = session.get_screenshot() if session else None
    if not data:
        return "", 404
    return Response(
        data,
        mimetype="image/jpeg",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def captcha_status(queue_id):
    session = _captcha_session(queue_id)
    if not session:
        return jsonify({"active": False})
    return jsonify({"active": True, "done": session.done})


def captcha_click(queue_id):
    data = request.get_json(silent=True) or {}
    x, y = data.get("x"), data.get("y")
    if x is None or y is None:
        return jsonify({"error": "x and y are required"}), 400

    session = _captcha_session(queue_id)
    if not session:
        return jsonify({"error": "No active captcha session"}), 404
    session.enqueue_click(int(x), int(y))
    return jsonify({"ok": True})
