"""Background download worker.

One global thread processes the queue a single item at a time, so downloads
never fight over ffmpeg or the captcha browser.
"""

import json
import threading
import time

from ..logger import get_logger
from ..providers import resolve_provider
from . import db, paths
from .media import mangafire_format

logger = get_logger(__name__)

_started = False
_start_lock = threading.Lock()

# How long to wait before looking at the queue again when it is empty.
IDLE_SECONDS = 3


def ensure_started():
    """Start the worker thread once per process."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    db.reset_stale_running()
    threading.Thread(target=_run, name="aniworld-queue", daemon=True).start()


def _claim_next():
    """Take the next queued item and mark it running, or None if busy/empty."""
    if db.get_running():
        return None
    item = db.get_next_queued()
    if not item:
        return None
    try:
        db.set_queue_status(item["id"], "running")
    except Exception:
        logger.exception("Could not mark queue item %s as running", item["id"])
        return None
    return item


def _run():
    while True:
        item = None
        try:
            item = _claim_next()
            if not item:
                time.sleep(IDLE_SECONDS)
                continue
            _process(item)
        except Exception:
            logger.exception("Queue worker error")
            if item:
                try:
                    db.set_queue_status(item["id"], "failed")
                except Exception:
                    pass
            time.sleep(IDLE_SECONDS)


def _episode_request(entry):
    """Normalise a queued entry into (url, extra episode kwargs)."""
    if not isinstance(entry, dict):
        return str(entry), {}

    url = (entry.get("url") or "").strip()
    extra = {}
    if entry.get("selected_pages") is not None:
        extra["selected_pages"] = entry["selected_pages"]
    if entry.get("series_url"):
        extra["_series_url"] = entry["series_url"]
    extra["_format"] = entry.get("mangafire_format", mangafire_format())
    return url, extra


def _build_episode(url, extra, item, selected_path):
    provider = resolve_provider(url)
    kwargs = {
        "url": url,
        "selected_language": item["language"],
        "selected_provider": item["provider"],
    }

    series = None
    if provider.name == "MangaFire":
        series_url = extra.get("_series_url") or url.rsplit("/chapter/", 1)[0]
        try:
            series = provider.series_cls(url=series_url)
        except Exception:
            series = None
        kwargs["format"] = extra["_format"]

    # MegaKino episodes build their own series context internally
    if series is not None and provider.name != "MegaKino":
        kwargs["series"] = series
    if "selected_pages" in extra:
        kwargs["selected_pages"] = extra["selected_pages"]
    if selected_path:
        kwargs["selected_path"] = selected_path

    return provider, provider.episode_cls(**kwargs)


def _captcha_hint(provider, error):
    """Kinox guards downloads with a captcha every visitor gets.

    Attach the title page so the UI can offer a "solve it, then retry" button.
    """
    try:
        from ..models.kinox.series import KINOX_CAPTCHA_MARKER, kinox_captcha_page_url

        if provider and provider.name == "Kinox" and KINOX_CAPTCHA_MARKER in str(error):
            return kinox_captcha_page_url
    except Exception:
        pass
    return None


def _process(item):
    from ..playwright import captcha

    queue_id = item["id"]
    entries = json.loads(item["episodes"])
    selected_path = paths.target_path(item["language"], item.get("custom_path_id"))
    errors = []

    for index, entry in enumerate(entries):
        url, extra = _episode_request(entry)
        provider = None
        try:
            db.update_queue_progress(queue_id, index, url)
            provider, episode = _build_episode(url, extra, item, selected_path)
            # Tells the captcha module to stream its browser into this queue item
            captcha._local.queue_id = queue_id
            try:
                episode.download()
            finally:
                captcha._local.queue_id = None
        except Exception as exc:
            captcha._local.queue_id = None
            # A force cancel kills the download on purpose. Whatever it raised
            # on the way down is the cancel, not a failure worth showing.
            if db.cancel_flags(queue_id)[1]:
                logger.info("Download of %s stopped by force cancel", url)
            else:
                logger.error("Download failed for %s: %s", url, exc)
                failure = {"url": url, "error": str(exc)}
                page_url = _captcha_hint(provider, exc)
                if page_url:
                    failure["captcha_url"] = page_url(url)
                errors.append(failure)
                db.update_queue_errors(queue_id, errors)

        cancelled, forced = db.cancel_flags(queue_id)
        if cancelled:
            logger.info(
                "Download %s for queue item %s",
                "force cancelled" if forced else "cancelled",
                queue_id,
            )
            # a forced stop killed this episode part way, it does not count
            done = index if forced else index + 1
            db.update_queue_progress(queue_id, done, "")
            # asking to stop after the last episode still leaves everything on disk
            everything_done = not forced and done >= len(entries) and not errors
            db.set_queue_status(
                queue_id, "completed" if everything_done else "cancelled"
            )
            if everything_done and item.get("source") == "discord":
                _notify_discord(item)
            return

    db.update_queue_progress(queue_id, len(entries), "")
    status = "failed" if errors and len(errors) == len(entries) else "completed"
    db.set_queue_status(queue_id, status)

    if status == "completed" and item.get("source") == "discord":
        _notify_discord(item)


def _notify_discord(item):
    try:
        from .discord_bot import notify_completed

        media_type = "movie" if int(item.get("total_episodes") or 1) <= 1 else "series"
        notify_completed(
            item.get("title") or "Unknown",
            media_type,
            item.get("language") or "",
            item.get("discord_user_id"),
        )
    except Exception as exc:
        logger.info("Discord completion notice skipped: %s", exc)
