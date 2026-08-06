"""AutoSync.

Once a day it pulls aniworld's newest-episodes list and looks for titles you
already have on disk. A hit queues the missing episodes of that series, so a
series you started stays complete without tracking it by hand.

Nothing is tracked explicitly: the library is the whitelist and the exclusion
list is the only opt-out.
"""

import threading
import time
from datetime import datetime, timedelta, timezone

from ..config import LANG_CODE_MAP, LANG_KEY_MAP, LANG_LABELS
from ..logger import get_logger
from ..providers import resolve_provider
from ..search import fetch_new_episodes
from . import db, paths
from .media import BADGE_ORDER, downloaded_episodes
from .settings_store import autosync_enabled

logger = get_logger(__name__)

INTERVAL_SECONDS = 24 * 60 * 60

# How often the thread wakes to see whether a run is due.
TICK_SECONDS = 300

# aniworld tags each row with the flag graphic of its language
FLAG_TO_LABEL = {
    "german": "German Dub",
    "english": "English Dub",
    "japanese-german": "German Sub",
    "japanese-english": "English Sub",
}

_run_lock = threading.Lock()
_started = False
_start_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc)


def _parse(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------
def _label_lookup():
    """(audio code, subtitle code) -> language label, inverted from the config maps."""
    lookup = {}
    for key, (audio, subtitles) in LANG_KEY_MAP.items():
        label = LANG_LABELS.get(key)
        if label:
            lookup[(LANG_CODE_MAP[audio], LANG_CODE_MAP[subtitles])] = label
    return lookup


def languages_from_probe(episode_path):
    """Language labels a downloaded file actually contains.

    Subtitles are burned into the video stream and the video track carries the
    subtitle language tag, which is the same thing the downloader compares
    against when deciding whether an episode still needs work.
    """
    from ..models.common.common import check_downloaded

    try:
        probe = check_downloaded(episode_path)
    except Exception as exc:
        logger.debug("AutoSync: probe failed for %s: %s", episode_path, exc)
        return set()
    if not probe.get("exists"):
        return set()

    audio_langs = probe.get("audio_langs") or set()
    video_langs = probe.get("video_langs") or set()

    found = set()
    for (audio_code, sub_code), label in _label_lookup().items():
        if audio_code not in audio_langs:
            continue
        # A dub has no burned-in subtitles, any video track will do
        if sub_code is None or sub_code in video_langs:
            found.add(label)
    return found


def _first_video_file(folder):
    from .library import VIDEO_EXTENSIONS

    try:
        for file in sorted(folder.rglob("*")):
            if file.is_file() and file.suffix.lower() in VIDEO_EXTENSIONS:
                return file
    except OSError:
        pass
    return None


def detect_languages(folder, lang_folder=None):
    """Languages a title on disk is held in.

    With language separation on the folder name already says it, otherwise the
    file itself is probed. An empty set means we could not tell.
    """
    if lang_folder:
        for label, name in paths.LANG_FOLDERS.items():
            if name == lang_folder:
                return {label}

    sample = _first_video_file(folder)
    return languages_from_probe(sample) if sample else set()


def _preferred(labels):
    """Pick one label when a title is held in several languages."""
    order = {label: index for index, label in enumerate(BADGE_ORDER)}
    return sorted(labels, key=lambda label: order.get(label, len(order)))[0]


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def _library_folders():
    """Every title folder on disk with the root and language folder it sits in."""
    separated = paths.lang_separation_enabled()
    entries = []

    for _, path_id, root in paths.download_roots():
        bases = (
            [(root / name, name) for name in paths.ALL_LANG_FOLDERS]
            if separated
            else [(root, None)]
        )
        for base, lang_folder in bases:
            if not base.is_dir():
                continue
            try:
                children = list(base.iterdir())
            except OSError:
                continue
            for folder in children:
                if folder.is_dir() and not folder.name.startswith("."):
                    entries.append((folder, path_id, lang_folder))
    return entries


def _series_url(episode_url):
    """Strip an episode URL back to its series page."""
    marker = "/staffel-"
    return episode_url.split(marker)[0] if marker in episode_url else episode_url


def find_candidates():
    """New episodes whose series already has a folder in the library.

    Matching is done on folder names rather than by rendering the naming
    template, so it keeps working after the template changes.
    """
    episodes = fetch_new_episodes()
    if episodes is None:
        raise RuntimeError("Could not fetch the newest episodes from aniworld.to")

    folders = _library_folders()
    excluded = db.excluded_series_urls()

    candidates = {}
    for entry in episodes:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        series_url = _series_url(entry["url"])
        if series_url in excluded or series_url in candidates:
            continue

        key = title.lower()
        match = next(
            (item for item in folders if item[0].name.lower().startswith(key)), None
        )
        if not match:
            continue

        folder, path_id, lang_folder = match
        labels = {
            FLAG_TO_LABEL[flag]
            for flag in entry.get("languages", [])
            if flag in FLAG_TO_LABEL
        }
        candidates[series_url] = {
            "title": title,
            "series_url": series_url,
            "folder": folder,
            "custom_path_id": path_id,
            "lang_folder": lang_folder,
            "new_languages": labels,
        }
    return list(candidates.values())


# ---------------------------------------------------------------------------
# Running a cycle
# ---------------------------------------------------------------------------
def _default_provider():
    from ..config import get_provider_fallback_order
    from .media import WORKING_PROVIDERS

    order = list(get_provider_fallback_order(WORKING_PROVIDERS))
    return order[0] if order else "VOE"


def _missing_episodes(series):
    """Episode URLs of a series that are not on disk yet."""
    have = downloaded_episodes(series)
    missing = []
    for season in series.seasons:
        for episode in season.episodes:
            if (season.season_number, episode.episode_number) not in have:
                missing.append(episode.url)
    return missing


def _handle(candidate, provider_name):
    """Resolve one candidate into a queue entry. Returns a report row."""
    title = candidate["title"]
    series_url = candidate["series_url"]
    report = {"title": title, "series_url": series_url}

    if db.is_series_queued_or_running(series_url):
        return {**report, "status": "skipped", "reason": "already in the queue"}

    have_languages = detect_languages(candidate["folder"], candidate["lang_folder"])
    if not have_languages:
        # Guessing here could pull a whole series in a language you never watch
        return {
            **report,
            "status": "skipped",
            "reason": "could not detect the language of the existing files",
        }

    usable = have_languages & candidate["new_languages"]
    if not usable:
        return {
            **report,
            "status": "skipped",
            "reason": "the new episode is not out in "
            + ", ".join(sorted(have_languages)),
        }

    language = _preferred(usable)
    series = resolve_provider(series_url).series_cls(url=series_url)
    missing = _missing_episodes(series)
    if not missing:
        return {**report, "status": "up-to-date", "language": language}

    queue_id = db.add_to_queue(
        title=series.title or title,
        series_url=series_url,
        episodes=missing,
        language=language,
        provider=provider_name,
        custom_path_id=candidate["custom_path_id"],
        source="autosync",
    )
    return {
        **report,
        "status": "queued",
        "language": language,
        "episodes": len(missing),
        "queue_id": queue_id,
    }


def run_cycle():
    """One full pass. Returns a report dict, also stored for the AutoSync page."""
    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("A sync is already running")

    started = _now()
    try:
        provider_name = _default_provider()
        rows = []
        try:
            candidates = find_candidates()
        except Exception as exc:
            logger.error("AutoSync: %s", exc)
            report = {
                "started_at": started.isoformat(),
                "error": str(exc),
                "checked": 0,
                "queued": 0,
                "results": [],
            }
            db.set_autosync_state(last_run=started.isoformat(), last_report=_dump(report))
            return report

        for candidate in candidates:
            try:
                rows.append(_handle(candidate, provider_name))
            except Exception as exc:
                logger.error("AutoSync failed for %s: %s", candidate["title"], exc)
                rows.append(
                    {
                        "title": candidate["title"],
                        "series_url": candidate["series_url"],
                        "status": "error",
                        "reason": str(exc)[:200],
                    }
                )

        report = {
            "started_at": started.isoformat(),
            "finished_at": _now().isoformat(),
            "checked": len(candidates),
            "queued": sum(1 for row in rows if row["status"] == "queued"),
            "results": rows,
        }
        db.set_autosync_state(last_run=started.isoformat(), last_report=_dump(report))
        logger.info(
            "AutoSync finished: %d matched, %d queued", report["checked"], report["queued"]
        )

        if report["queued"]:
            from . import worker

            worker.ensure_started()
        return report
    finally:
        _run_lock.release()


def _dump(report):
    import json

    return json.dumps(report)


def is_running():
    return _run_lock.locked()


def status():
    """What the AutoSync page shows."""
    import json

    state = db.get_autosync_state()
    last_run = _parse(state.get("last_run"))
    report = None
    if state.get("last_report"):
        try:
            report = json.loads(state["last_report"])
        except ValueError:
            report = None

    return {
        "enabled": autosync_enabled(),
        "running": _run_lock.locked(),
        "interval_hours": INTERVAL_SECONDS // 3600,
        "last_run": last_run.isoformat() if last_run else None,
        "next_run": (last_run + timedelta(seconds=INTERVAL_SECONDS)).isoformat()
        if last_run
        else None,
        "last_report": report,
    }


# ---------------------------------------------------------------------------
# Daily worker
# ---------------------------------------------------------------------------
def _due():
    last_run = _parse(db.get_autosync_state().get("last_run"))
    if last_run is None:
        return True
    return _now() - last_run >= timedelta(seconds=INTERVAL_SECONDS)


def _loop():
    while True:
        try:
            # Re-read the toggle every tick so turning it off takes effect
            if autosync_enabled() and _due():
                run_cycle()
        except Exception as exc:
            logger.error("AutoSync worker error: %s", exc, exc_info=True)
        time.sleep(TICK_SECONDS)


def ensure_started():
    """Start the daily thread once per process."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="aniworld-autosync", daemon=True).start()
