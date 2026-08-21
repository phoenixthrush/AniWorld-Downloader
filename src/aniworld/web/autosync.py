"""AutoSync.

On a schedule it pulls aniworld's newest-episodes list and looks for titles you
already have on disk. A hit queues the missing episodes of that series, so a
series you started stays complete without tracking it by hand.

The schedule is either an interval (every 24 hours by default) or fixed times
in cron form ("every monday and friday at 22:00"). See schedule.py.

Nothing is tracked explicitly: the library is the whitelist and the exclusion
list is the only opt-out.

By default a hit queues everything the series is missing, so one episode on disk
is enough to pull the rest in. The "only new episodes" setting narrows that to
the episodes the feed actually announced, for people who have gaps on purpose.
"""

import re
import threading
import time
from datetime import datetime, timedelta, timezone

from ..config import LANG_CODE_MAP, LANG_KEY_MAP, LANG_LABELS
from ..logger import get_logger
from ..providers import resolve_provider
from ..search import fetch_new_episodes
from . import db, paths, schedule
from .media import BADGE_ORDER, folder_matches_title
from .settings_store import (
    autosync_cron_schedule,
    autosync_enabled,
    autosync_interval_seconds,
    autosync_mode,
    autosync_new_only,
    autosync_schedule_description,
)

logger = get_logger(__name__)

# How long the thread sleeps at most. A run that is due sooner shortens the nap
# so a fixed time is hit on the minute, and waking up regardless keeps a
# schedule changed in the settings from needing a restart.
TICK_SECONDS = 300
MIN_TICK_SECONDS = 5

# How far ahead of now a stored "last run" may be before it is treated as junk
_CLOCK_SLACK = timedelta(minutes=5)

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

# Set the first time the schedule is looked at, see _anchor()
_anchored_at = None


def _now():
    return datetime.now(timezone.utc)


def _local(moment):
    """A UTC instant as naive local wall-clock time, which is what cron means."""
    return moment.astimezone().replace(tzinfo=None)


def _utc(wall_clock):
    """Naive local wall-clock time back to UTC."""
    return wall_clock.astimezone(timezone.utc)


def _parse(value):
    try:
        parsed = datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None
    if parsed is not None and parsed.tzinfo is None:
        # Hand-edited, or written by a version that stored it without one.
        # Everything else here is UTC, and comparing the two kinds raises.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


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
    return min(labels, key=lambda label: order.get(label, len(order)))


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def _library_folders():
    """Every title folder on disk with the root and language folder it sits in."""
    separated = paths.lang_separation_enabled()
    entries = []

    for root_name, path_id, root in paths.download_roots():
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
                    entries.append((folder, path_id, lang_folder, root_name))
    return entries


def _where(candidate):
    """Human label for one copy, so a report row says which one it is about."""
    parts = [candidate["root_name"]]
    if candidate["lang_folder"]:
        parts.append(candidate["lang_folder"])
    return " / ".join(parts)


def _series_url(episode_url):
    """Strip an episode URL back to its series page."""
    marker = "/staffel-"
    return episode_url.split(marker)[0] if marker in episode_url else episode_url


_EPISODE_NUMBERS = re.compile(r"/staffel-(\d+)/episode-(\d+)")


def _numbers(episode_url):
    """(season, episode) read straight off the URL, or None if it has neither."""
    match = _EPISODE_NUMBERS.search(episode_url)
    return (int(match.group(1)), int(match.group(2))) if match else None


def find_candidates():
    """One candidate per copy of a series that the feed has new episodes for.

    Matching is done on folder names rather than by rendering the naming
    template, so it keeps working after the template changes.

    The same show can sit on disk more than once: twice in different languages,
    or in two libraries. Every copy is its own download with its own language,
    so every copy gets its own candidate rather than the first match standing in
    for all of them.
    """
    episodes = fetch_new_episodes()
    if episodes is None:
        raise RuntimeError("Could not fetch the newest episodes from aniworld.to")

    folders = _library_folders()
    excluded = db.excluded_series_urls()

    # A series shows up once per new episode. Collapse the feed first, keeping
    # every URL so the "only new episodes" mode has the full set, and merging
    # the flags since the episodes are not always out in the same languages.
    announced = {}
    for entry in episodes:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        series_url = _series_url(entry["url"])
        if series_url in excluded:
            continue

        labels = {
            FLAG_TO_LABEL[flag]
            for flag in entry.get("languages", [])
            if flag in FLAG_TO_LABEL
        }
        seen = announced.get(series_url)
        if seen:
            seen["new_episode_urls"].append(entry["url"])
            seen["new_languages"] |= labels
        else:
            announced[series_url] = {
                "title": title,
                "series_url": series_url,
                "new_languages": labels,
                "new_episode_urls": [entry["url"]],
            }

    candidates = []
    for record in announced.values():
        for folder, path_id, lang_folder, root_name in folders:
            if not folder_matches_title(folder.name, record["title"]):
                continue
            candidates.append(
                {
                    **record,
                    "folder": folder,
                    "custom_path_id": path_id,
                    "lang_folder": lang_folder,
                    "root_name": root_name,
                }
            )
    return candidates


# ---------------------------------------------------------------------------
# Running a cycle
# ---------------------------------------------------------------------------
def _default_provider():
    from ..config import get_provider_fallback_order
    from .media import WORKING_PROVIDERS

    order = list(get_provider_fallback_order(WORKING_PROVIDERS))
    return order[0] if order else "VOE"


def episodes_in_folder(folder):
    """(season, episode) numbers sitting in this one copy.

    media.downloaded_episodes() unions every root and language folder, which is
    right for the "already downloaded" badge but wrong here: a German copy would
    look complete because the English copy next to it has the episode, and would
    then never be filled in.
    """
    from .media import EPISODE_RE

    found = set()
    try:
        files = folder.rglob("*")
    except OSError:
        return found

    for file in files:
        try:
            if not file.is_file():
                continue
        except OSError:
            continue
        match = EPISODE_RE.search(file.name)
        if match:
            found.add((int(match.group(1)), int(match.group(2))))
    return found


def _missing_episodes(series, have):
    """Episode URLs of a series that are not in this copy yet."""
    missing = []
    for season in series.seasons:
        for episode in season.episodes:
            if (season.season_number, episode.episode_number) not in have:
                missing.append(episode.url)
    return missing


def _announced_episodes(episode_urls, have):
    """Only the episodes the feed announced, minus whatever this copy has.

    The season and episode number come off the URL, so unlike the fill mode this
    never has to walk the series page for every season.
    """
    return [
        url
        for url in episode_urls
        if (numbers := _numbers(url)) is not None and numbers not in have
    ]


def _handle(candidate, provider_name):
    """Resolve one copy into a queue entry. Returns a report row.

    Reasons are shown verbatim on the Auto-Sync page, so they read as sentences.
    """
    title = candidate["title"]
    series_url = candidate["series_url"]
    report = {"title": title, "series_url": series_url, "where": _where(candidate)}

    have_languages = detect_languages(candidate["folder"], candidate["lang_folder"])
    if not have_languages:
        # Guessing here could pull a whole series in a language you never watch
        return {
            **report,
            "status": "skipped",
            "reason": "Could not detect the language of the existing files.",
        }

    usable = have_languages & candidate["new_languages"]
    if not usable:
        return {
            **report,
            "status": "skipped",
            "reason": "This copy is in {have}, and the new episode is only out in {new}.".format(
                have=", ".join(sorted(have_languages)),
                new=", ".join(sorted(candidate["new_languages"])) or "another language",
            ),
        }

    language = _preferred(usable)

    # Per copy, not per series: the same show queued for another language or
    # another library is a different download and must not block this one.
    if db.is_copy_queued_or_running(series_url, language, candidate["custom_path_id"]):
        return {
            **report,
            "status": "skipped",
            "language": language,
            "reason": "This copy is already in the queue.",
        }

    have = episodes_in_folder(candidate["folder"])
    series = resolve_provider(series_url).series_cls(url=series_url)
    if autosync_new_only():
        missing = _announced_episodes(candidate.get("new_episode_urls") or [], have)
    else:
        missing = _missing_episodes(series, have)
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
            db.set_autosync_state(
                last_run=started.isoformat(), last_report=_dump(report)
            )
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
                        "where": _where(candidate),
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
            "AutoSync finished: %d matched, %d queued",
            report["checked"],
            report["queued"],
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

    fixed = _fixed_times()
    interval_seconds = autosync_interval_seconds()
    upcoming = next_run_at()

    return {
        "enabled": autosync_enabled(),
        "new_only": autosync_new_only(),
        "running": _run_lock.locked(),
        "mode": autosync_mode(),
        "interval": schedule.format_interval(interval_seconds),
        "interval_seconds": interval_seconds,
        # Kept for anything that read the status before the schedule was
        # settable, when it was always 24. Whole hours no longer cover it.
        "interval_hours": round(interval_seconds / 3600, 4),
        "cron": fixed.expression if fixed else None,
        "schedule": autosync_schedule_description(),
        "last_run": last_run.isoformat() if last_run else None,
        "next_run": upcoming.isoformat() if upcoming else None,
        "last_report": report,
    }


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------
def _fixed_times():
    """The parsed fixed times, or None for interval mode and a broken schedule."""
    try:
        return autosync_cron_schedule()
    except schedule.ScheduleError as exc:
        # settings_store already falls back to the default, so this is only
        # reachable if that default itself stopped parsing.
        logger.error(
            "AutoSync: unusable schedule, falling back to the interval: %s", exc
        )
        return None


def _anchor():
    """Stands in for "last run" while Auto-Sync has never run.

    Fixed times are counted from the moment Auto-Sync was switched on, so
    turning it on at 23:00 with "every day at 22:00" waits for tomorrow
    instead of queueing a pile of downloads on the spot.
    """
    global _anchored_at
    if _anchored_at is None:
        _anchored_at = _now()
    return _anchored_at


def _reset_anchor():
    """While Auto-Sync is off there is nothing to count from, so the anchor
    follows the clock and freezes at the moment it is switched on."""
    global _anchored_at
    _anchored_at = _now()


def next_run_at():
    """When the next cycle is due, in UTC, or None if the schedule never fires."""
    last_run = _parse(db.get_autosync_state().get("last_run"))
    fixed = _fixed_times()

    if last_run is not None and last_run - _now() > _CLOCK_SLACK:
        # Written while the clock was wrong, a dead CMOS battery say. Counting
        # from it would park the next run in that future and never run again,
        # so ignore it: the next cycle writes a sane one and it heals itself.
        logger.warning(
            "AutoSync: the last run is in the future (%s), ignoring it", last_run
        )
        last_run = None

    if fixed is None:
        # An interval install that has never run is due right away, which is
        # what Auto-Sync did before the schedule was configurable.
        if last_run is None:
            return _anchor()
        return last_run + timedelta(seconds=autosync_interval_seconds())

    upcoming = fixed.next_run(_local(last_run or _anchor()))
    return _utc(upcoming) if upcoming else None


def _due():
    upcoming = next_run_at()
    return upcoming is not None and _now() >= upcoming


def _nap_seconds():
    """How long to sleep: long enough to stay cheap, short enough to be on time."""
    if not autosync_enabled():
        return TICK_SECONDS
    try:
        upcoming = next_run_at()
    except Exception:
        logger.exception("AutoSync: could not work out the next run")
        return TICK_SECONDS
    if upcoming is None:
        return TICK_SECONDS
    seconds = (upcoming - _now()).total_seconds()
    return max(MIN_TICK_SECONDS, min(TICK_SECONDS, seconds))


def _loop():
    while True:
        try:
            # Re-read the settings every tick so a change takes effect
            if autosync_enabled():
                if _due():
                    run_cycle()
            else:
                _reset_anchor()
        except Exception:
            logger.exception("AutoSync worker error")
        time.sleep(_nap_seconds())


def ensure_started():
    """Start the scheduling thread once per process."""
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
    _anchor()
    threading.Thread(target=_loop, name="aniworld-autosync", daemon=True).start()
