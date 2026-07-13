import json
import os
import re
import threading
import time

import requests
from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFProtect

from ..config import (
    LANG_KEY_MAP,
    LANG_LABELS,
    SUPPORTED_PROVIDERS,
    get_provider_fallback_order,
    parse_provider_order,
)
from ..extractors import provider_functions
from ..logger import get_logger
from ..models.mangafire_to.series import search_series as query_mangafire
from ..providers import resolve_provider
from ..search import (
    fetch_burningseries_series,
    fetch_cineby_movies,
    fetch_filmpalast_movies,
    fetch_kinox_movies,
    fetch_new_animes,
    fetch_new_series,
    fetch_popular_animes,
    fetch_popular_movies,
    fetch_popular_series,
    query_burningseries,
    query_cineby,
    query_filmpalast,
    query_kinox,
    query_megakino,
    query_s_to,
    random_anime,
)
from ..search import query as aniworld_query
from .db import (
    add_autosync_job,
    add_custom_path,
    update_custom_path,
    add_to_queue,
    cancel_queue_item,
    clear_captcha_url,
    clear_completed,
    find_autosync_by_url,
    get_autosync_job,
    get_autosync_jobs,
    get_custom_path_by_id,
    get_custom_paths,
    get_general_stats,
    get_next_queued,
    get_queue,
    get_queue_stats,
    get_running,
    get_sync_stats,
    add_planned_job,
    get_planned_job,
    get_planned_jobs,
    remove_planned_job,
    init_autosync_db,
    init_custom_paths_db,
    init_planned_db,
    init_queue_db,
    is_queue_cancelled,
    is_series_queued_or_running,
    move_queue_item,
    remove_autosync_job,
    remove_custom_path,
    remove_from_queue,
    requeue_item,
    set_captcha_url,
    set_queue_status,
    update_autosync_job,
    update_queue_errors,
    update_queue_progress,
)

logger = get_logger(__name__)


def _get_working_providers():
    """Return only providers whose extractors are actually implemented."""
    working = []
    for p in SUPPORTED_PROVIDERS:
        func_name = f"get_direct_link_from_{p.lower()}"
        if func_name not in provider_functions:
            continue
        try:
            provider_functions[func_name]("")
        except NotImplementedError:
            continue
        except Exception:
            working.append(p)
    return tuple(working)


WORKING_PROVIDERS = _get_working_providers()
WORKING_PROVIDER_LOOKUP = {provider.lower(): provider for provider in WORKING_PROVIDERS}

# Site keys the front-end uses; custom paths can be the default for any of them
SITE_KEYS = (
    "aniworld",
    "sto",
    "megakino",
    "mangafire",
    "htv",
    "kinox",
    "burningseries",
    "filmpalast",
    "cineby",
)


def _normalize_default_sites(value):
    """Validate a default_sites value into a clean CSV of known site keys."""
    if isinstance(value, (list, tuple)):
        raw = value
    else:
        raw = str(value or "").split(",")
    seen = []
    for item in raw:
        key = str(item).strip().lower()
        if key in SITE_KEYS and key not in seen:
            seen.append(key)
    return ",".join(seen)


# Languages the web interface itself can be displayed in
SUPPORTED_UI_LANGUAGES = ("en", "de")

# Containers the downloader can write
SUPPORTED_OUTPUT_FORMATS = ("mkv", "mp4")

# Discord bot settings that live in the .env file
DISCORD_ENV_KEYS = {
    "enabled": "ANIWORLD_DISCORD_BOT_ENABLED",
    "token": "ANIWORLD_DISCORD_TOKEN",
    "owner_id": "ANIWORLD_DISCORD_OWNER_ID",
    "mode": "ANIWORLD_DISCORD_MODE",
    "request_role_id": "ANIWORLD_DISCORD_REQUEST_ROLE_ID",
    "guild_id": "ANIWORLD_DISCORD_GUILD_ID",
    "language": "ANIWORLD_DISCORD_LANGUAGE",
    "announce_channel_id": "ANIWORLD_DISCORD_ANNOUNCE_CHANNEL_ID",
}
DISCORD_LANGUAGES = ("en", "de")

DISCORD_MODES = ("standard", "advanced")

# Placeholder shown instead of the real token so it never leaves the server
SECRET_PLACEHOLDER = "••••••••"


def _current_naming_template():
    from ..config import NAMING_TEMPLATE

    return os.environ.get("ANIWORLD_NAMING_TEMPLATE", NAMING_TEMPLATE)


def _naming_template_extension():
    """Return the output container implied by the naming template."""
    last_segment = _current_naming_template().rstrip('"').split("/")[-1]
    if "." in last_segment:
        ext = last_segment.rsplit(".", 1)[1].strip().strip('"').lower()
        if ext:
            return ext
    return "mkv"


def _naming_template_with_extension(extension):
    """Rewrite the naming template so it ends in `.<extension>`."""
    template = _current_naming_template()
    quoted = template.startswith('"') and template.endswith('"')
    if quoted:
        template = template[1:-1]

    parts = template.split("/")
    last = parts[-1]
    if "." in last:
        last = last.rsplit(".", 1)[0]
    parts[-1] = f"{last}.{extension}"
    rebuilt = "/".join(parts)
    return f'"{rebuilt}"' if quoted else rebuilt


def _discord_settings():
    """Read the current Discord bot configuration from the environment."""
    return {
        "enabled": os.environ.get(DISCORD_ENV_KEYS["enabled"], "0") == "1",
        "token_set": bool(os.environ.get(DISCORD_ENV_KEYS["token"], "").strip()),
        "owner_id": os.environ.get(DISCORD_ENV_KEYS["owner_id"], ""),
        "mode": os.environ.get(DISCORD_ENV_KEYS["mode"], "standard"),
        "request_role_id": os.environ.get(DISCORD_ENV_KEYS["request_role_id"], ""),
        "guild_id": os.environ.get(DISCORD_ENV_KEYS["guild_id"], ""),
        "language": os.environ.get(DISCORD_ENV_KEYS["language"], "en"),
        "announce_channel_id": os.environ.get(
            DISCORD_ENV_KEYS["announce_channel_id"], ""
        ),
    }


def _apply_discord_settings(payload, env_updates):
    """Validate a Discord settings payload into `env_updates`.

    Returns an error string on failure, otherwise None.
    """
    if not isinstance(payload, dict):
        return "discord must be an object"

    if "enabled" in payload:
        env_updates[DISCORD_ENV_KEYS["enabled"]] = "1" if payload["enabled"] else "0"

    if "token" in payload:
        token = str(payload["token"]).strip()
        # The UI sends the placeholder back when the field was left untouched
        if token != SECRET_PLACEHOLDER:
            env_updates[DISCORD_ENV_KEYS["token"]] = token

    if "mode" in payload:
        mode = str(payload["mode"]).strip().lower()
        if mode not in DISCORD_MODES:
            return f"Invalid discord mode: {mode}"
        env_updates[DISCORD_ENV_KEYS["mode"]] = mode

    if "language" in payload:
        language = str(payload["language"]).strip().lower()
        if language not in DISCORD_LANGUAGES:
            return f"Invalid discord language: {language}"
        env_updates[DISCORD_ENV_KEYS["language"]] = language

    for field in ("owner_id", "request_role_id", "guild_id", "announce_channel_id"):
        if field in payload:
            value = str(payload[field]).strip()
            if value and not value.isdigit():
                return f"Invalid discord {field}: must be a numeric ID"
            env_updates[DISCORD_ENV_KEYS[field]] = value

    return None


def _persist_discord_env(env_updates):
    """Persist only the Discord bot keys to ~/.aniworld/.env.

    Every other web-UI setting is intentionally in-memory only (see
    api_settings_update). The bot config is the one exception: a token that
    vanished on restart would be useless, so the ANIWORLD_DISCORD_* keys are
    written through to the .env file. They live in .env.example too, so the
    startup merge_env keeps them across restarts.
    """
    discord_keys = set(DISCORD_ENV_KEYS.values())
    subset = {k: v for k, v in env_updates.items() if k in discord_keys}
    if not subset:
        return
    try:
        from pathlib import Path

        from ..env import persist_env_values

        env_path = Path.home() / ".aniworld" / ".env"
        persist_env_values(env_path, subset)
    except Exception as exc:
        logger.warning(f"Could not persist Discord settings to .env: {exc}")


def _notify_discord_completed(item):
    """Tell the Discord bot a requested download finished (DM + optional announce)."""
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
        logger.info(f"Discord completion notice skipped: {exc}")


def _reconcile_discord_bot():
    """Start/stop/restart the Discord bot after a settings change."""
    try:
        from .discord_bot import reconcile
    except ImportError as exc:
        logger.warning(f"Discord bot unavailable: {exc}")
        return
    try:
        reconcile()
    except Exception as exc:
        logger.error(f"Discord bot reconcile failed: {exc}", exc_info=True)


ANIWORLD_LANGUAGE_BADGE_ORDER = (
    "German Dub",
    "German Sub",
    "English Dub",
    "English Sub",
)

STO_LANGUAGE_BADGE_ORDER = (
    "German Dub",
    "English Dub",
)


def _episode_language_labels(provider_data):
    labels = []
    seen = set()

    if hasattr(provider_data, "_data"):
        lang_tuple_to_label = {}
        for key, (audio, subtitles) in LANG_KEY_MAP.items():
            label = LANG_LABELS.get(key)
            if label:
                lang_tuple_to_label[(audio.value, subtitles.value)] = label

        for (audio, subtitles), providers in provider_data._data.items():
            label = lang_tuple_to_label.get((audio.value, subtitles.value))
            if not label or label in seen or not providers:
                continue
            labels.append(label)
            seen.add(label)

        order = ANIWORLD_LANGUAGE_BADGE_ORDER
    else:
        sto_label_map = {
            ("German", "None"): "German Dub",
            ("English", "None"): "English Dub",
        }
        for (audio, subtitles), providers in provider_data.items():
            label = sto_label_map.get((audio.value, subtitles.value))
            if not label or label in seen or not providers:
                continue
            labels.append(label)
            seen.add(label)

        order = STO_LANGUAGE_BADGE_ORDER

    sort_order = {label: index for index, label in enumerate(order)}
    labels.sort(key=lambda label: (sort_order.get(label, len(sort_order)), label))
    return labels


def _is_megakino_url(url: str) -> bool:
    return bool(re.match(r"^https?://(?:www\.)?megakino[\w-]*\.[^/]+/", url))


# Only match series-level links: /anime/stream/<slug> (no season/episode)
_SERIES_LINK_PATTERN = re.compile(r"^/anime/stream/[a-zA-Z0-9\-]+/?$", re.IGNORECASE)

# Only match serienstream.to series-level links: /serie/<slug> (no season/episode)
_STO_SERIES_LINK_PATTERN = re.compile(
    r"^/serie/(stream/)?[a-zA-Z0-9\-]+/?$", re.IGNORECASE
)


_HTV_SEARCH_URL = "https://search.htv-services.com/"


def _search_htv(keyword):
    """Search hanime.tv via their search API."""
    try:
        resp = requests.post(
            _HTV_SEARCH_URL,
            json={
                "search_text": keyword,
                "tags": [],
                "tags_mode": "AND",
                "brands": [],
                "blacklist": [],
                "order_by": "likes",
                "ordering": "desc",
                "page": 0,
            },
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        import json as _json

        hits_raw = data.get("hits", "[]")
        if isinstance(hits_raw, str):
            hits = _json.loads(hits_raw)
        else:
            hits = hits_raw
        return hits
    except Exception as e:
        logger.warning(f"HTV search failed: {e}")
        return []


def _megakino_episode_payload(url, title, episode, season_number=1):
    available_languages = _episode_language_labels(episode.provider_data)
    return {
        "url": url,
        "episode_number": 1,
        "title_de": "",
        "title_en": title,
        "downloaded": False,
        "available_languages": available_languages,
    }


def _fetch_htv_trending():
    """Fetch latest videos from hanime.tv via search API."""
    try:
        resp = requests.post(
            _HTV_SEARCH_URL,
            json={
                "search_text": "",
                "tags": [],
                "tags_mode": "AND",
                "brands": [],
                "blacklist": [],
                "order_by": "created_at",
                "ordering": "desc",
                "page": 0,
            },
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        import json as _json

        hits_raw = data.get("hits", "[]")
        if isinstance(hits_raw, str):
            hits = _json.loads(hits_raw)
        else:
            hits = hits_raw
        results = []
        seen = set()
        for h in hits:
            slug = h.get("slug", "")
            title = h.get("name", "")
            if not slug or not title:
                continue
            franchise_key = re.sub(r"-\d+$", "", slug)
            if franchise_key in seen:
                continue
            seen.add(franchise_key)
            results.append(
                {
                    "title": title,
                    "url": f"https://hanime.tv/videos/hentai/{slug}",
                    "poster_url": h.get("cover_url") or h.get("poster_url") or "",
                    "genre": ", ".join(h.get("tags", [])[:3]),
                }
            )
        return results
    except Exception as e:
        logger.warning(f"HTV trending fetch failed: {e}")
        return None


# Queue worker state
_queue_worker_started = False
_queue_lock = threading.Lock()

# Auto-sync worker state
_autosync_worker_started = False

# Track jobs currently being synced to prevent duplicate runs
_syncing_jobs = set()
_syncing_jobs_lock = threading.Lock()

# Schedule intervals in seconds
SYNC_SCHEDULE_MAP = {
    "1min": 60,
    "30min": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "8h": 28800,
    "12h": 43200,
    "16h": 57600,
    "24h": 86400,
}

_PUBLIC_IP_LOOKUP_URLS = (
    "https://api.ipify.org?format=json",
    "https://ifconfig.me/all.json",
)


def _fetch_public_ip():
    """Resolve the current public IP address of the running container."""
    last_error = None
    headers = {"User-Agent": "AniWorld Downloader"}
    for url in _PUBLIC_IP_LOOKUP_URLS:
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            ip = (data.get("ip") or data.get("ip_addr") or "").strip()
            if ip:
                return {"ip": ip, "source": url}
            last_error = "No IP address returned by upstream service"
        except requests.RequestException as exc:
            last_error = str(exc)
        except ValueError as exc:
            last_error = f"Invalid response: {exc}"
    raise RuntimeError(last_error or "Failed to resolve public IP")


def _queue_worker():
    """Single global worker that processes one download at a time."""
    while True:
        try:
            item = None
            with _queue_lock:
                if not get_running():
                    item = get_next_queued()
                    if item:
                        try:
                            set_queue_status(item["id"], "running")
                        except Exception as e:
                            logger.error(f"Failed to set status to 'running': {e}", exc_info=True)
                            item = None

            if not item:
                time.sleep(3)
                continue

            episodes = json.loads(item["episodes"])
            errors = []

            # Language separation: compute subfolder path if enabled
            import os

            lang_sep = os.environ.get("ANIWORLD_LANG_SEPARATION", "0") == "1"
            if item.get("source") == "sync:all_langs":
                lang_sep = True
            selected_path = None

            from pathlib import Path

            # Determine base path: custom path or default
            custom_path_id = item.get("custom_path_id")
            if custom_path_id:
                cp = get_custom_path_by_id(custom_path_id)
                if cp:
                    base = Path(cp["path"]).expanduser()
                    if not base.is_absolute():
                        base = Path.home() / base
                else:
                    base = None
            else:
                base = None

            if base is None:
                raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
                if raw:
                    base = Path(raw).expanduser()
                    if not base.is_absolute():
                        base = Path.home() / base
                else:
                    base = Path.home() / "Downloads"

            if lang_sep:
                lang_folder_map = {
                    "German Dub": "german-dub",
                    "English Sub": "english-sub",
                    "German Sub": "german-sub",
                    "English Dub": "english-dub",
                }
                lang_folder = lang_folder_map.get(
                    item["language"], item["language"].lower().replace(" ", "-")
                )
                selected_path = str(base / lang_folder)
            elif custom_path_id:
                selected_path = str(base)

            from ..playwright import captcha as _captcha_mod

            for i, ep_url in enumerate(episodes):
                try:
                    selected_pages = None
                    series_url = None
                    series = None
                    chapter_url = ep_url
                    if isinstance(ep_url, dict):
                        chapter_url = (ep_url.get("url") or "").strip()
                        series_url = (ep_url.get("series_url") or "").strip() or None
                        selected_pages = ep_url.get("selected_pages")
                    prov = resolve_provider(chapter_url)
                    if prov.name == "MangaFire":
                        if not series_url:
                            series_url = chapter_url.rsplit("/chapter/", 1)[0]
                        try:
                            series = prov.series_cls(url=series_url)
                        except Exception:
                            series = None
                    update_queue_progress(item["id"], i, chapter_url)
                    ep_kwargs = {
                        "url": chapter_url,
                        "selected_language": item["language"],
                        "selected_provider": item["provider"],
                    }
                    # `series` is only ever populated for MangaFire; passing it
                    # (even as None) to movie models that don't accept the kwarg
                    # would raise, so only forward it when it's real.
                    if prov.name != "MegaKino" and series is not None:
                        ep_kwargs["series"] = series
                    if selected_pages is not None:
                        ep_kwargs["selected_pages"] = selected_pages
                    if selected_path:
                        ep_kwargs["selected_path"] = selected_path
                    episode = prov.episode_cls(**ep_kwargs)
                    _captcha_mod._local.queue_id = item["id"]
                    try:
                        episode.download()
                    finally:
                        _captcha_mod._local.queue_id = None
                except Exception as e:
                    _captcha_mod._local.queue_id = None
                    logger.error(f"Download failed for {ep_url}: {e}")
                    err_entry = {"url": ep_url, "error": str(e)}
                    # kinox (and only kinox) guards each download with a captcha
                    # every visitor gets. Attach the kinox title page so the UI
                    # can offer a "solve on kinox, then retry" button.
                    try:
                        from ..models.kinox.series import (
                            KINOX_CAPTCHA_MARKER,
                            kinox_captcha_page_url,
                        )

                        if (
                            locals().get("prov") is not None
                            and prov.name == "Kinox"
                            and KINOX_CAPTCHA_MARKER in str(e)
                        ):
                            err_entry["captcha_url"] = kinox_captcha_page_url(
                                chapter_url
                            )
                    except Exception:
                        pass
                    errors.append(err_entry)
                    update_queue_errors(item["id"], json.dumps(errors))

                # Check for cancellation after each episode
                if is_queue_cancelled(item["id"]):
                    logger.info(f"Download cancelled for queue item {item['id']}")
                    update_queue_progress(item["id"], i + 1, "")
                    break

            # Only set final status if not already cancelled
            if not is_queue_cancelled(item["id"]):
                update_queue_progress(item["id"], len(episodes), "")
                status = (
                    "failed" if errors and len(errors) == len(episodes) else "completed"
                )
                set_queue_status(item["id"], status)

                # Notify the Discord requester (DM) + optional announce channel.
                if status == "completed" and item.get("source") == "discord":
                    _notify_discord_completed(item)

        except Exception as e:
            logger.error(f"Queue worker error: {e}", exc_info=True)
            if item:
                try:
                    set_queue_status(item["id"], "failed")
                except Exception:
                    pass
            time.sleep(3)


def _ensure_queue_worker():
    """Start the queue worker thread once."""
    global _queue_worker_started
    if _queue_worker_started:
        return
    _queue_worker_started = True

    from .db import get_db

    conn = get_db()
    try:
        conn.execute(
            "UPDATE download_queue SET status = 'queued' WHERE status = 'running'"
        )
        conn.execute("UPDATE download_queue SET captcha_url = NULL")
        conn.commit()
    finally:
        conn.close()

    thread = threading.Thread(target=_queue_worker, daemon=True)
    thread.start()


def _run_autosync_for_job(job):
    """Check a single autosync job for new/missing episodes and queue them."""
    from datetime import datetime
    from pathlib import Path

    job_id = job["id"]
    with _syncing_jobs_lock:
        if job_id in _syncing_jobs:
            logger.info("Auto-sync skipped job %d — already running", job_id)
            return
        _syncing_jobs.add(job_id)

    try:
        prov = resolve_provider(job["series_url"])
        series = prov.series_cls(url=job["series_url"])

        lang_sep = os.environ.get("ANIWORLD_LANG_SEPARATION", "0") == "1"
        # Only use lang_sep for "All Languages" when the global setting is enabled;
        # otherwise scan root directory to avoid phantom missing-episode detection.
        if job.get("language") == "All Languages" and not lang_sep:
            logger.warning(
                "Auto-sync job '%s' uses 'All Languages' but lang_separation is off — scanning root.",
                job.get("title", "?"),
            )

        lang_folder_map = {
            "German Dub": "german-dub",
            "English Sub": "english-sub",
            "German Sub": "german-sub",
            "English Dub": "english-dub",
        }

        target_languages = []
        if job.get("language") == "All Languages":
            disable_eng_sub = os.environ.get("ANIWORLD_DISABLE_ENGLISH_SUB", "0") == "1"
            for lang in lang_folder_map.keys():
                if disable_eng_sub and lang == "English Sub":
                    continue
                target_languages.append(lang)
        else:
            target_languages.append(job["language"])

        total_new_queued = 0
        total_episodes_found = 0

        for target_lang in target_languages:
            job_lang_folder = lang_folder_map.get(
                target_lang, target_lang.lower().replace(" ", "-")
            )

            raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
            if raw:
                dl_base = Path(raw).expanduser()
                if not dl_base.is_absolute():
                    dl_base = Path.home() / dl_base
            else:
                dl_base = Path.home() / "Downloads"

            scan_roots = [dl_base]
            for cp in get_custom_paths():
                cp_path = Path(cp["path"]).expanduser()
                if not cp_path.is_absolute():
                    cp_path = Path.home() / cp_path
                scan_roots.append(cp_path)

            # Build set of downloaded (season, episode) on disk
            downloaded_eps = set()
            title_clean = (
                getattr(series, "title_cleaned", None) or getattr(series, "title", "")
            ).lower()
            if title_clean:
                ep_re = re.compile(r"S(\d{2})E(\d{2,3})", re.IGNORECASE)
                all_bases = []
                for root in scan_roots:
                    if lang_sep:
                        all_bases.append(root / job_lang_folder)
                    else:
                        all_bases.append(root)
                for base in all_bases:
                    if not base.is_dir():
                        continue
                    try:
                        folders = list(base.iterdir())
                    except (PermissionError, OSError):
                        continue
                    for folder in folders:
                        if not folder.is_dir() or not folder.name.lower().startswith(
                            title_clean
                        ):
                            continue
                        for f in folder.rglob("*"):
                            if f.is_file():
                                m = ep_re.search(f.name)
                                if m:
                                    downloaded_eps.add(
                                        (int(m.group(1)), int(m.group(2)))
                                    )

            # Collect all episode URLs that are NOT yet downloaded
            missing_episodes = []
            lang_total_found = 0
            for season in series.seasons:
                season_obj = prov.season_cls(url=season.url, series=series)
                for ep in season_obj.episodes:
                    # Depending on provider, might need to pre-filter by language here
                    # But the downloader expects full episode URLs and it will pick the right language within them.
                    lang_total_found += 1
                    key = (ep.season.season_number, ep.episode_number)
                    if key not in downloaded_eps:
                        missing_episodes.append(ep.url)

            # In "All Languages" mode we want to make sure the specific language is actually
            # available on this episode before downloading? For VOE/Vidoza, it downloads what is chosen.
            # If a language isn't available, the extractor fails, which is fine (handled in queue).
            # But the queue item will contain episodes.

            # We use max of lang_total_found for updating stats (usually they are same across languages)
            if lang_total_found > total_episodes_found:
                total_episodes_found = lang_total_found

            if missing_episodes:
                # Skip if series is already queued or running for THIS language
                if is_series_queued_or_running(job["series_url"], language=target_lang):
                    logger.info(
                        "Auto-sync skipped '%s' (%s) — already queued/running",
                        job["title"],
                        target_lang,
                    )
                    continue

                total_new_queued += len(missing_episodes)
                add_to_queue(
                    title=job["title"],
                    series_url=job["series_url"],
                    episodes=missing_episodes,
                    language=target_lang,
                    provider=job["provider"],
                    username=job.get("added_by"),
                    custom_path_id=job.get("custom_path_id"),
                    source="sync:all_langs"
                    if job.get("language") == "All Languages"
                    else "sync",
                )
                logger.info(
                    "Auto-sync queued %d episodes for '%s' (%s)",
                    len(missing_episodes),
                    job["title"],
                    target_lang,
                )

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        update_fields = {
            "last_check": now_str,
            "episodes_found": total_episodes_found,
        }

        if total_new_queued > 0:
            update_fields["last_new_found"] = now_str

        update_autosync_job(job["id"], **update_fields)
    except Exception as e:
        logger.error("Auto-sync failed for '%s': %s", job.get("title", "?"), e)
        from datetime import datetime

        update_autosync_job(
            job["id"],
            last_check=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )
    finally:
        with _syncing_jobs_lock:
            _syncing_jobs.discard(job_id)


def _autosync_worker():
    """Background thread that periodically syncs all enabled autosync jobs.

    Uses short-polling (every 10 s) and checks each job's last_check
    against the configured interval so that schedule changes take effect
    immediately instead of blocking in a long sleep.
    """
    from datetime import datetime, timedelta

    while True:
        try:
            schedule_key = os.environ.get("ANIWORLD_SYNC_SCHEDULE", "0")
            interval = SYNC_SCHEDULE_MAP.get(schedule_key, 0)
            if not interval:
                time.sleep(10)
                continue

            now = datetime.utcnow()
            jobs = get_autosync_jobs()
            for job in jobs:
                if not job.get("enabled"):
                    continue
                # Per-job check: only run if enough time has elapsed
                last_check = job.get("last_check")
                if last_check:
                    try:
                        last_dt = datetime.strptime(last_check, "%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        last_dt = datetime.min
                    if now < last_dt + timedelta(seconds=interval):
                        continue
                _run_autosync_for_job(job)

            # Planned releases ride the same cadence as auto-sync.
            _run_planned_checks(now, interval)

            time.sleep(10)
        except Exception as e:
            logger.error("Auto-sync worker error: %s", e, exc_info=True)
            time.sleep(30)


def _run_planned_checks(now, interval):
    """Check waiting planned items whose per-item interval has elapsed."""
    from datetime import datetime, timedelta

    from .db import get_planned_jobs
    from .planned import check_planned_job

    for job in get_planned_jobs():
        if job.get("status") != "waiting":
            continue
        last_check = job.get("last_check")
        if last_check:
            try:
                last_dt = datetime.strptime(last_check, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                last_dt = datetime.min
            if now < last_dt + timedelta(seconds=interval):
                continue
        check_planned_job(job)


def _ensure_autosync_worker():
    """Start the auto-sync worker thread once."""
    global _autosync_worker_started
    if _autosync_worker_started:
        return
    _autosync_worker_started = True
    thread = threading.Thread(target=_autosync_worker, daemon=True)
    thread.start()


def _get_version():
    # Prefer the installed package metadata…
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            v = version("aniworld")
            if v:
                return v
        except PackageNotFoundError:
            pass
    except Exception:
        pass
    # …otherwise (running from source) read it from pyproject.toml.
    try:
        import re
        from pathlib import Path

        for parent in Path(__file__).resolve().parents:
            pyproject = parent / "pyproject.toml"
            if pyproject.exists():
                m = re.search(
                    r'^\s*version\s*=\s*"([^"]+)"',
                    pyproject.read_text(encoding="utf-8"),
                    re.MULTILINE,
                )
                if m:
                    return m.group(1)
                break
    except Exception:
        pass
    return ""


def _proxy_image_url(url: str) -> str:
    if not url:
        return url
    from urllib.parse import quote

    if not isinstance(url, str):
        url = getattr(url, "url", None) or getattr(url, "href", None) or str(url)

    return f"/api/proxy-image?url={quote(url, safe='')}"


def _normalize_image_url(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("large", "medium", "small", "url", "href", "src"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for candidate in value.values():
            if isinstance(candidate, str) and candidate:
                return candidate
    return getattr(value, "url", None) or getattr(value, "href", None) or str(value)


def _mangafire_browse_item(item: dict) -> dict:
    """Normalize MangaFire browse/search payloads into homepage card data."""
    poster = _normalize_image_url(item.get("poster", ""))
    url = item.get("url", "") or ""
    if url and not url.startswith("http"):
        url = f"https://mangafire.to{url}"

    genres = item.get("genres") or []
    genre = ", ".join(
        genre_item.get("title", "")
        for genre_item in genres
        if isinstance(genre_item, dict) and genre_item.get("title")
    )

    if not genre:
        status = item.get("status", "")
        year = item.get("year")
        parts = [
            part
            for part in (status.title() if status else "", str(year) if year else "")
            if part
        ]
        genre = " · ".join(parts)

    return {
        "title": item.get("title", "Unknown"),
        "url": url,
        "poster_url": _proxy_image_url(poster),
        "genre": genre,
    }


def _hanime_fallback_title(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    title = re.sub(r"-\d+$", "", slug).replace("-", " ").strip()
    return title.title() if title else slug


def create_app(auth_enabled=False, sso_enabled=False, force_sso=False):

    app = Flask(__name__)
    app_version = _get_version()

    base_url = os.environ.get("ANIWORLD_WEB_BASE_URL", "").strip().rstrip("/")
    if base_url:
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        scheme = parsed.scheme or "https"
        host = parsed.netloc

        # WSGI middleware that overrides scheme/host before Flask sees the request
        _inner_wsgi = app.wsgi_app

        def _proxy_wsgi(environ, start_response):
            environ["wsgi.url_scheme"] = scheme
            if host:
                environ["HTTP_HOST"] = host
            return _inner_wsgi(environ, start_response)

        app.wsgi_app = _proxy_wsgi

    if auth_enabled:
        from .auth import (
            auth_bp,
            get_current_user,
            get_or_create_secret_key,
            init_oidc,
            login_required,
            refresh_session_role,
        )
        from .db import has_any_admin, init_db

        app.secret_key = get_or_create_secret_key()
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
        if base_url.startswith("https"):
            app.config["SESSION_COOKIE_SECURE"] = True
        app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 24 hours

        csrf = CSRFProtect()

        init_db()
        app.register_blueprint(auth_bp)
        csrf.init_app(app)

        if sso_enabled:
            init_oidc(app, force_sso=force_sso)
        else:
            app.config["OIDC_ENABLED"] = False
            app.config["OIDC_DISPLAY_NAME"] = "SSO"
            app.config["OIDC_ADMIN_USER"] = None
            app.config["OIDC_ADMIN_SUBJECT"] = None
            app.config["FORCE_SSO"] = False

        @app.before_request
        def _check_setup():
            if request.endpoint and request.endpoint.startswith("auth."):
                return None
            if request.endpoint == "static":
                return None
            if not app.config.get("FORCE_SSO", False) and not has_any_admin():
                return redirect(url_for("auth.setup"))
            return None

        @app.before_request
        def _refresh_role():
            return refresh_session_role()

        @app.context_processor
        def _inject_auth():
            return {
                "current_user": get_current_user(),
                "auth_enabled": True,
                "oidc_enabled": app.config.get("OIDC_ENABLED", False),
                "oidc_display_name": app.config.get("OIDC_DISPLAY_NAME", "SSO"),
                "force_sso": app.config.get("FORCE_SSO", False),
                "app_version": app_version,
            }
    else:

        @app.context_processor
        def _inject_no_auth():
            return {
                "current_user": None,
                "auth_enabled": False,
                "oidc_enabled": False,
                "oidc_display_name": "SSO",
                "force_sso": False,
                "app_version": app_version,
            }

    @app.context_processor
    def _inject_ui_language():
        lang = os.environ.get("ANIWORLD_UI_LANGUAGE", "en").lower()
        if lang not in SUPPORTED_UI_LANGUAGES:
            lang = "en"
        return {"ui_language": lang}

    # Initialize download queue, custom paths and autosync (works with or without auth)
    init_queue_db()
    init_custom_paths_db()
    init_autosync_db()
    init_planned_db()

    # Wire up captcha hooks so the Playwright module can signal the Web UI
    from ..playwright import captcha as _captcha_mod

    _captcha_mod._on_captcha_start = set_captcha_url
    _captcha_mod._on_captcha_end = clear_captcha_url

    # In debug mode, Flask's reloader runs this in both the parent and child
    # process. Only start workers in the child (actual server) process
    # to avoid duplicate ffmpeg downloads.
    _debug = os.getenv("ANIWORLD_DEBUG_MODE", "0") == "1"
    if not _debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        _ensure_queue_worker()
        _ensure_autosync_worker()
        try:
            from .discord_bot import start_if_enabled

            start_if_enabled()
        except Exception as exc:
            logger.warning(f"Discord bot not started: {exc}")

    @app.after_request
    def _set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        return response

    @app.before_request
    def _enforce_json_content_type():
        """Reject non-JSON POST/PUT/DELETE on API routes to prevent form-based CSRF bypass."""
        if request.method in ("POST", "PUT", "DELETE") and request.path.startswith(
            "/api/"
        ):
            if request.content_length and request.content_length > 0:
                ct = request.content_type or ""
                if not ct.startswith("application/json"):
                    return jsonify(
                        {"error": "Content-Type must be application/json"}
                    ), 415

    @app.route("/")
    def index():
        sto_lang_labels = {"1": "German Dub", "2": "English Dub"}
        megakino_lang_labels = {"1": "German Dub"}
        default_web_language = os.environ.get("ANIWORLD_LANGUAGE", "German Dub")
        if default_web_language not in LANG_LABELS.values():
            default_web_language = "German Dub"
        htv_enabled = os.environ.get("ANIWORLD_ENABLE_HTV", "0") == "1"
        burningseries_enabled = (
            os.environ.get("ANIWORLD_ENABLE_BURNINGSERIES", "0") == "1"
        )
        kinox_enabled = os.environ.get("ANIWORLD_ENABLE_KINOX", "0") == "1"
        return render_template(
            "index.html",
            lang_labels=LANG_LABELS,
            sto_lang_labels=sto_lang_labels,
            megakino_lang_labels=megakino_lang_labels,
            supported_providers=WORKING_PROVIDERS,
            default_web_language=default_web_language,
            htv_enabled=htv_enabled,
            burningseries_enabled=burningseries_enabled,
            kinox_enabled=kinox_enabled,
        )

    @app.route("/api/search", methods=["POST"])
    def api_search():
        data = request.get_json(silent=True) or {}
        keyword = (data.get("keyword") or "").strip()
        site = (data.get("site") or "aniworld").strip()
        if not keyword:
            return jsonify({"error": "keyword is required"}), 400

        results = []

        if site == "htv":
            # hanime.tv search — group by franchise so only one result per series
            htv_results = _search_htv(keyword)
            seen = set()
            for item in htv_results:
                slug = item.get("slug", "")
                if not slug:
                    continue
                franchise_key = re.sub(r"-\d+$", "", slug)
                if franchise_key in seen:
                    continue
                seen.add(franchise_key)
                title = re.sub(r"\s+\d+$", "", item.get("name", "")).strip()
                poster = item.get("cover_url") or item.get("poster_url") or ""
                results.append(
                    {
                        "title": title,
                        "url": f"https://hanime.tv/videos/hentai/{slug}",
                        "poster_url": _proxy_image_url(_normalize_image_url(poster)),
                    }
                )
        elif site in ("megakino", "kinox", "filmpalast", "burningseries", "cineby"):
            query_fn = {
                "megakino": query_megakino,
                "kinox": query_kinox,
                "filmpalast": query_filmpalast,
                "burningseries": query_burningseries,
                "cineby": query_cineby,
            }[site]
            site_results = query_fn(keyword) or []
            for item in site_results:
                url = item.get("url", "")
                if not url:
                    continue
                results.append(
                    {
                        "title": item.get("title", "Unknown"),
                        "url": url,
                        "poster_url": _proxy_image_url(
                            _normalize_image_url(item.get("poster_url", ""))
                        ),
                    }
                )
        elif site == "sto":
            # serienstream.to search
            sto_results = query_s_to(keyword) or []
            if isinstance(sto_results, dict):
                sto_results = [sto_results]
            for item in sto_results:
                link = item.get("link", "")
                if _STO_SERIES_LINK_PATTERN.match(link):
                    title = (
                        item.get("title", "Unknown")
                        .replace("<em>", "")
                        .replace("</em>", "")
                    )
                    results.append(
                        {
                            "title": title,
                            "url": f"https://serienstream.to{link}",
                        }
                    )
        elif site == "mangafire":
            mf_results = query_mangafire(keyword) or []
            if isinstance(mf_results, dict):
                mf_results = [mf_results]
            for item in mf_results:
                url = item.get("url", "")
                if not url:
                    continue
                if not url.startswith("http"):
                    url = f"https://mangafire.to{url}"
                title = item.get("title") or item.get("name") or "Unknown"
                poster = (
                    item.get("poster_url")
                    or item.get("cover_url")
                    or item.get("image")
                    or item.get("poster")
                    or ""
                )
                results.append(
                    {
                        "title": title,
                        "url": url,
                        "poster_url": _proxy_image_url(_normalize_image_url(poster)),
                    }
                )
        else:
            # AniWorld search
            aw_results = aniworld_query(keyword) or []
            if isinstance(aw_results, dict):
                aw_results = [aw_results]
            for item in aw_results:
                link = item.get("link", "")
                if _SERIES_LINK_PATTERN.match(link):
                    title = (
                        item.get("title", "Unknown")
                        .replace("<em>", "")
                        .replace("</em>", "")
                    )
                    results.append(
                        {
                            "title": title,
                            "url": f"https://aniworld.to{link}",
                        }
                    )

        return jsonify({"results": results})

    @app.route("/api/series")
    def api_series():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)
            series = prov.series_cls(url=url)
            poster = getattr(series, "poster_url", None)
            # serienstream.to returns relative poster paths - make them absolute
            if poster and poster.startswith("/"):
                from urllib.parse import urlparse

                parsed = urlparse(url)
                poster = f"{parsed.scheme}://{parsed.netloc}{poster}"
            return jsonify(
                {
                    "title": series.title,
                    "poster_url": _proxy_image_url(_normalize_image_url(poster)),
                    "description": getattr(series, "description", ""),
                    "genres": getattr(series, "genres", []),
                    "release_year": getattr(series, "release_year", ""),
                }
            )
        except Exception as e:
            try:
                prov_name = prov.name if "prov" in locals() else ""
            except Exception:
                prov_name = ""
            if prov_name == "HanimeTV":
                logger.warning(f"Hanime series fetch fallback for {url}: {e}")
                return jsonify(
                    {
                        "title": _hanime_fallback_title(url),
                        "poster_url": "",
                        "description": "",
                        "genres": [],
                        "release_year": "",
                    }
                )
            logger.error(f"Series fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/seasons")
    def api_seasons():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)
            if prov.name in ("MegaKino", "FilmPalast"):
                return jsonify(
                    {
                        "seasons": [
                            {
                                "url": url,
                                "season_number": 1,
                                "episode_count": 1,
                                "are_movies": True,
                            }
                        ]
                    }
                )
            series = prov.series_cls(url=url)
            # burning-series has no per-season episode count on the series page,
            # so reading season.episode_count here would fetch every season page
            # up front (a series with 30+ seasons = 30+ serial requests = the
            # modal "loading…" forever). Skip it: the count fills in lazily as
            # each season is expanded and its episodes load.
            defer_counts = prov.name == "BurningSeries"
            seasons_data = []
            for season in series.seasons:
                seasons_data.append(
                    {
                        "url": season.url,
                        "season_number": season.season_number,
                        "episode_count": None if defer_counts else season.episode_count,
                        "are_movies": getattr(season, "are_movies", False),
                        "chapter_type": getattr(season, "chapter_type", ""),
                    }
                )
            return jsonify({"seasons": seasons_data})
        except Exception as e:
            try:
                prov_name = prov.name if "prov" in locals() else ""
            except Exception:
                prov_name = ""
            if prov_name == "HanimeTV":
                logger.warning(f"Hanime seasons fetch fallback for {url}: {e}")
                return jsonify({"seasons": []})
            logger.error(f"Seasons fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/episodes")
    def api_episodes():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)

            if prov.name in ("MegaKino", "FilmPalast"):
                episode = prov.episode_cls(url=url, selected_language="German Dub")
                title = getattr(episode, "title_cleaned", None) or getattr(
                    episode, "title", ""
                )
                try:
                    available_languages = _episode_language_labels(
                        episode.provider_data
                    )
                except Exception as exc:
                    logger.warning(f"{prov.name} language detection failed: {exc}")
                    available_languages = ["German Dub"]
                episodes_data = [
                    {
                        "url": url,
                        "episode_number": 1,
                        "title_de": "",
                        "title_en": title,
                        "downloaded": False,
                        "available_languages": available_languages,
                    }
                ]
                return jsonify({"episodes": episodes_data})

            # HTV: season URL is empty; use the series URL to get episodes
            if prov.name == "HanimeTV":
                series_url = request.args.get("series_url", "").strip() or url
                series = prov.series_cls(url=series_url)
                season = series.seasons[0] if series.seasons else None
                if not season:
                    return jsonify({"episodes": []})
            else:
                if prov.name == "MangaFire":
                    series_url = request.args.get("series_url", "").strip() or url
                else:
                    # Pass series to avoid broken series URL reconstruction in serienstream.to
                    # season model (its fallback splits on "-" which fails)
                    series_url = re.sub(r"/staffel-\d+/?$", "", url)
                    series_url = re.sub(r"/filme/?$", "", series_url)
                try:
                    series = prov.series_cls(url=series_url)
                except Exception:
                    series = None
                season = prov.season_cls(url=url, series=series)

            if prov.name == "MangaFire":
                from pathlib import Path

                lang_sep = os.environ.get("ANIWORLD_LANG_SEPARATION", "0") == "1"
                lang_folders = [
                    "german-dub",
                    "english-sub",
                    "german-sub",
                    "english-dub",
                ]

                raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
                if raw:
                    dl_base = Path(raw).expanduser()
                    if not dl_base.is_absolute():
                        dl_base = Path.home() / dl_base
                else:
                    dl_base = Path.home() / "Downloads"

                scan_roots = [dl_base]
                for cp in get_custom_paths():
                    cp_path = Path(cp["path"]).expanduser()
                    if not cp_path.is_absolute():
                        cp_path = Path.home() / cp_path
                    scan_roots.append(cp_path)

                all_bases = []
                for root in scan_roots:
                    if lang_sep:
                        all_bases.extend([root / lf for lf in lang_folders])
                    else:
                        all_bases.append(root)

                title_clean = (
                    getattr(series, "title_cleaned", None)
                    or getattr(series, "title", "")
                ).lower()
                episodes_data = []
                chapter_pages = []
                try:
                    chapter_pages = list(getattr(season, "pages", []) or [])
                except Exception:
                    chapter_pages = []

                def _mangafire_page_downloaded(page) -> bool:
                    for base in all_bases:
                        if not base.is_dir():
                            continue
                        try:
                            folders = list(base.iterdir())
                        except (PermissionError, OSError):
                            continue
                        for folder in folders:
                            if (
                                not folder.is_dir()
                                or not folder.name.lower().startswith(title_clean)
                            ):
                                continue
                            if (folder / season.folder_name / page.file_name).exists():
                                return True
                    return False

                total_pages = len(chapter_pages)
                for page in chapter_pages:
                    episodes_data.append(
                        {
                            "url": season.url,
                            "chapter_url": season.url,
                            "episode_number": page.page_number,
                            "page_number": page.page_number,
                            "page_count": total_pages,
                            "title_de": f"Page {page.page_number}",
                            "title_en": f"Page {page.page_number}",
                            "downloaded": _mangafire_page_downloaded(page),
                            "available_languages": ["English Dub"],
                        }
                    )
                return jsonify({"episodes": episodes_data})

            # Scan download directory for downloaded episodes.
            # Uses S##E### filename matching so it works regardless of
            # which NAMING_TEMPLATE was active when files were downloaded.
            from pathlib import Path

            lang_sep = os.environ.get("ANIWORLD_LANG_SEPARATION", "0") == "1"
            lang_folders = ["german-dub", "english-sub", "german-sub", "english-dub"]

            raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
            if raw:
                dl_base = Path(raw).expanduser()
                if not dl_base.is_absolute():
                    dl_base = Path.home() / dl_base
            else:
                dl_base = Path.home() / "Downloads"

            # Collect all scan roots: default + custom paths
            scan_roots = [dl_base]
            for cp in get_custom_paths():
                cp_path = Path(cp["path"]).expanduser()
                if not cp_path.is_absolute():
                    cp_path = Path.home() / cp_path
                scan_roots.append(cp_path)

            # Build set of (season_num, episode_num) found on disk
            downloaded_eps = set()
            downloaded_chapters = set()
            try:
                title_clean = ""
                if series:
                    title_clean = (
                        getattr(series, "title_cleaned", None)
                        or getattr(series, "title", "")
                    ).lower()
                if title_clean:
                    ep_re = re.compile(r"S(\d{2})E(\d{2,3})", re.IGNORECASE)
                    all_bases = []
                    for root in scan_roots:
                        if lang_sep:
                            all_bases.extend([root / lf for lf in lang_folders])
                        else:
                            all_bases.append(root)
                    for base in all_bases:
                        if not base.is_dir():
                            continue
                        try:
                            folders = list(base.iterdir())
                        except (PermissionError, OSError):
                            continue
                        for folder in folders:
                            if (
                                not folder.is_dir()
                                or not folder.name.lower().startswith(title_clean)
                            ):
                                continue
                            if prov.name == "MangaFire":
                                for chapter_folder in folder.iterdir():
                                    if chapter_folder.is_dir():
                                        downloaded_chapters.add(
                                            chapter_folder.name.lower()
                                        )
                            for f in folder.rglob("*"):
                                if f.is_file():
                                    m = ep_re.search(f.name)
                                    if m:
                                        downloaded_eps.add(
                                            (int(m.group(1)), int(m.group(2)))
                                        )
            except Exception:
                pass

            # Kinox / BurningSeries / Cineby resolve their stream per episode, so
            # read the language once at the season level for the listing and skip
            # the per-episode provider_data probe.
            season_lang_labels = None
            if prov.name in ("Kinox", "BurningSeries", "Cineby"):
                try:
                    season_lang_labels = list(getattr(season, "language_labels", []) or [])
                except Exception as exc:
                    logger.warning(f"{prov.name} language detection failed: {exc}")
                    season_lang_labels = ["German Dub"]

            episodes_data = []
            for ep in season.episodes:
                if prov.name == "MangaFire":
                    continue
                downloaded = (
                    ep.season.season_number,
                    ep.episode_number,
                ) in downloaded_eps
                if season_lang_labels is not None:
                    available_languages = season_lang_labels
                else:
                    available_languages = _episode_language_labels(ep.provider_data)
                if prov.name == "HanimeTV" and not available_languages:
                    available_languages = ["Japanese"]

                episodes_data.append(
                    {
                        "url": ep.url,
                        "episode_number": ep.episode_number,
                        "title_de": getattr(ep, "title_de", ""),
                        "title_en": getattr(ep, "title_en", ""),
                        "downloaded": downloaded,
                        "available_languages": available_languages,
                        "page_count": 0,
                    }
                )
            return jsonify({"episodes": episodes_data})
        except Exception as e:
            try:
                prov_name = prov.name if "prov" in locals() else ""
            except Exception:
                prov_name = ""
            if prov_name == "HanimeTV":
                logger.warning(f"Hanime episodes fetch fallback for {url}: {e}")
                return jsonify({"episodes": []})
            logger.error(f"Episodes fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/providers")
    def api_providers():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)
            if prov.name == "MangaFire":
                return jsonify({"providers": {}})
            if prov.name == "Cineby":
                # Single implicit provider, but the audio language varies: the
                # original is always there, German only when the title has a
                # German audio rendition. Probe the given episode to find out.
                labels = ["English Dub"]
                try:
                    episode = prov.episode_cls(url=url)
                    labels = list(episode.available_language_labels) or labels
                except Exception as exc:
                    logger.warning(f"Cineby language detection failed: {exc}")
                return jsonify({"providers": {label: ["Cineby"] for label in labels}})
            if prov.name == "MegaKino":
                episode = prov.episode_cls(url=url, selected_language="German Dub")
            else:
                episode = prov.episode_cls(url=url)
            pd = episode.provider_data

            disable_eng_sub = os.environ.get("ANIWORLD_DISABLE_ENGLISH_SUB", "0") == "1"
            provider_info = {}

            if hasattr(pd, "_data"):
                # AniWorld: ProviderData object
                lang_tuple_to_label = {}
                for key, (audio, subtitles) in LANG_KEY_MAP.items():
                    label = LANG_LABELS.get(key)
                    if label:
                        lang_tuple_to_label[(audio.value, subtitles.value)] = label

                for (audio, subtitles), providers in pd._data.items():
                    label = lang_tuple_to_label.get((audio.value, subtitles.value))
                    if not label:
                        continue
                    if disable_eng_sub and label == "English Sub":
                        continue
                    working = [
                        WORKING_PROVIDER_LOOKUP.get(p.lower(), p)
                        for p in providers.keys()
                        if p.lower() in WORKING_PROVIDER_LOOKUP
                    ]
                    if working:
                        provider_info[label] = working
            else:
                # serienstream.to: plain dict with (Audio, Subtitles) enum tuple keys
                sto_label_map = {
                    ("German", "None"): "German Dub",
                    ("English", "None"): "English Dub",
                }
                for (audio, subtitles), providers in pd.items():
                    label = sto_label_map.get((audio.value, subtitles.value))
                    if not label:
                        continue
                    working = [p for p in providers.keys() if p in WORKING_PROVIDERS]
                    if working:
                        provider_info[label] = working

            return jsonify({"providers": provider_info})
        except Exception as e:
            logger.error(f"Providers fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/download", methods=["POST"])
    def api_download():
        data = request.get_json(silent=True) or {}
        episodes = data.get("episodes", [])
        language = data.get("language", "German Dub")
        provider = data.get("provider", "VOE")
        title = data.get("title", "Unknown")
        series_url = data.get("series_url", "")

        if not episodes:
            return jsonify({"error": "episodes list is required"}), 400

        if (
            language == "English Sub"
            and os.environ.get("ANIWORLD_DISABLE_ENGLISH_SUB", "0") == "1"
        ):
            return jsonify({"error": "English Sub downloads are disabled"}), 403

        username = None
        if auth_enabled:
            user = get_current_user()
            if user:
                username = (
                    user.get("username")
                    if isinstance(user, dict)
                    else getattr(user, "username", None)
                )

        custom_path_id = data.get("custom_path_id")

        queue_id = add_to_queue(
            title,
            series_url,
            episodes,
            language,
            provider,
            username,
            custom_path_id=custom_path_id,
        )
        return jsonify({"queue_id": queue_id})

    @app.route("/api/popular-movies")
    def api_popular_movies():
        try:
            results = fetch_popular_movies() or []
            return jsonify({"results": results})
        except Exception as e:
            logger.error(f"Popular movies fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/queue")
    def api_queue():
        from ..models.common.common import get_ffmpeg_progress

        items = get_queue()
        ffmpeg_pct = get_ffmpeg_progress()
        return jsonify({"items": items, "ffmpeg_progress": ffmpeg_pct})

    @app.route("/api/queue/<int:queue_id>", methods=["DELETE"])
    def api_queue_remove(queue_id):
        ok, err = remove_from_queue(queue_id)
        if not ok:
            return jsonify({"error": err}), 400
        return jsonify({"ok": True})

    @app.route("/api/queue/<int:queue_id>/cancel", methods=["POST"])
    def api_queue_cancel(queue_id):
        ok, err = cancel_queue_item(queue_id)
        if not ok:
            return jsonify({"error": err}), 400
        return jsonify({"ok": True})

    @app.route("/api/queue/<int:queue_id>/move", methods=["POST"])
    def api_queue_move(queue_id):
        data = request.get_json(silent=True) or {}
        direction = data.get("direction", "").strip()
        if direction not in ("up", "down"):
            return jsonify({"error": "direction must be 'up' or 'down'"}), 400
        ok, err = move_queue_item(queue_id, direction)
        if not ok:
            return jsonify({"error": err}), 400
        return jsonify({"ok": True})

    @app.route("/api/queue/completed", methods=["DELETE"])
    def api_queue_clear():
        clear_completed()
        return jsonify({"ok": True})

    @app.route("/api/queue/<int:queue_id>/retry", methods=["POST"])
    def api_queue_retry(queue_id):
        """Re-queue a failed/cancelled item (e.g. after solving the kinox captcha)."""
        if not requeue_item(queue_id):
            return jsonify({"error": "item not found or not retryable"}), 400
        _ensure_queue_worker()
        return jsonify({"ok": True})

    # ── Captcha endpoints ─────────────────────────────────────────────────────

    @app.route("/api/captcha/<int:queue_id>/screenshot")
    def api_captcha_screenshot(queue_id):
        """Return the latest JPEG screenshot of the Playwright captcha page."""
        from flask import Response

        from ..playwright.captcha import _active_sessions, _active_sessions_lock

        with _active_sessions_lock:
            session = _active_sessions.get(queue_id)
        if not session:
            return "", 404
        data = session.get_screenshot()
        if not data:
            return "", 404
        return Response(
            data,
            mimetype="image/jpeg",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )

    @app.route("/api/captcha/<int:queue_id>/click", methods=["POST"])
    def api_captcha_click(queue_id):
        """Forward a click event (x, y) to the Playwright captcha browser."""
        from ..playwright.captcha import _active_sessions, _active_sessions_lock

        data = request.get_json(silent=True) or {}
        x = data.get("x")
        y = data.get("y")
        if x is None or y is None:
            return jsonify({"error": "x and y are required"}), 400
        with _active_sessions_lock:
            session = _active_sessions.get(queue_id)
        if not session:
            return jsonify({"error": "no active captcha session"}), 404
        session.enqueue_click(int(x), int(y))
        return jsonify({"ok": True})

    @app.route("/api/captcha/<int:queue_id>/status")
    def api_captcha_status(queue_id):
        """Return whether a captcha session is active and whether it has been solved."""
        from ..playwright.captcha import _active_sessions, _active_sessions_lock

        with _active_sessions_lock:
            session = _active_sessions.get(queue_id)
        if not session:
            return jsonify({"active": False})
        return jsonify({"active": True, "done": session.done})

    # ─────────────────────────────────────────────────────────────────────────

    @app.route("/library")
    def library_page():
        return render_template("library.html")

    @app.route("/settings")
    def settings_page():
        import platform
        from pathlib import Path

        env_path = Path.home() / ".aniworld" / ".env"
        if platform.system() != "Windows":
            display = "~/.aniworld/.env"
        else:
            display = str(env_path)
        return render_template("settings.html", env_path=display)

    @app.route("/api/random")
    def api_random():
        site = request.args.get("site", "aniworld").strip()
        if site == "sto":
            return jsonify(
                {"error": "Random is not available for serienstream.to"}
            ), 400
        url = random_anime()
        if url:
            return jsonify({"url": url})
        return jsonify({"error": "Failed to fetch random anime"}), 500

    @app.route("/api/proxy-image")
    def api_proxy_image():
        from flask import Response

        target = request.args.get("url", "").strip()
        if not target or not target.startswith(("http://", "https://")):
            return "", 400
        try:
            proxy_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            if "hanime" in target:
                proxy_headers["Referer"] = "https://hanime.tv/"
            resp = requests.get(target, headers=proxy_headers, timeout=10, stream=True)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return Response(
                resp.iter_content(chunk_size=8192),
                content_type=content_type,
                headers={"Cache-Control": "public, max-age=3600"},
            )
        except Exception as e:
            logger.warning(f"Image proxy failed for {target}: {e}")
            return "", 502

    # TTL cache for browse endpoints so long-running instances stay fresh
    import time as _time

    _browse_cache = {}
    _BROWSE_TTL = 3600  # 1 hour

    def _cached_browse(key, fetch_fn):
        now = _time.time()
        entry = _browse_cache.get(key)
        if entry and now - entry[0] < _BROWSE_TTL:
            return entry[1]
        results = fetch_fn()
        if results is not None:
            _browse_cache[key] = (now, results)
        return results

    @app.route("/api/new-animes")
    def api_new_animes():
        results = _cached_browse("new_animes", fetch_new_animes)
        if results is None:
            return jsonify({"error": "Failed to fetch new animes"}), 500
        proxied = [
            {**r, "poster_url": _proxy_image_url(r.get("poster_url", ""))}
            for r in results
        ]
        return jsonify({"results": proxied})

    @app.route("/api/popular-animes")
    def api_popular_animes():
        results = _cached_browse("popular_animes", fetch_popular_animes)
        if results is None:
            return jsonify({"error": "Failed to fetch popular animes"}), 500
        proxied = [
            {**r, "poster_url": _proxy_image_url(r.get("poster_url", ""))}
            for r in results
        ]
        return jsonify({"results": proxied})

    @app.route("/api/new-series")
    def api_new_series():
        results = _cached_browse("new_series", fetch_new_series)
        if results is None:
            return jsonify({"error": "Failed to fetch new series"}), 500
        proxied = [
            {**r, "poster_url": _proxy_image_url(r.get("poster_url", ""))}
            for r in results
        ]
        return jsonify({"results": proxied})

    @app.route("/api/popular-series")
    def api_popular_series():
        results = _cached_browse("popular_series", fetch_popular_series)
        if results is None:
            return jsonify({"error": "Failed to fetch popular series"}), 500
        proxied = [
            {**r, "poster_url": _proxy_image_url(r.get("poster_url", ""))}
            for r in results
        ]
        return jsonify({"results": proxied})

    @app.route("/api/kinox-movies")
    def api_kinox_movies():
        results = _cached_browse("kinox_movies", fetch_kinox_movies)
        if results is None:
            return jsonify({"error": "Failed to fetch kinox movies"}), 500
        proxied = [
            {**r, "poster_url": _proxy_image_url(r.get("poster_url", ""))}
            for r in results
        ]
        return jsonify({"results": proxied})

    @app.route("/api/filmpalast-movies")
    def api_filmpalast_movies():
        results = _cached_browse("filmpalast_movies", fetch_filmpalast_movies)
        if results is None:
            return jsonify({"error": "Failed to fetch filmpalast movies"}), 500
        proxied = [
            {**r, "poster_url": _proxy_image_url(r.get("poster_url", ""))}
            for r in results
        ]
        return jsonify({"results": proxied})

    @app.route("/api/burningseries-series")
    def api_burningseries_series():
        results = _cached_browse("burningseries_series", fetch_burningseries_series)
        if results is None:
            return jsonify({"error": "Failed to fetch burning-series"}), 500
        proxied = [
            {**r, "poster_url": _proxy_image_url(r.get("poster_url", ""))}
            for r in results
        ]
        return jsonify({"results": proxied})

    @app.route("/api/cineby-movies")
    def api_cineby_movies():
        results = _cached_browse("cineby_movies", fetch_cineby_movies)
        if results is None:
            return jsonify({"error": "Failed to fetch cineby"}), 500
        proxied = [
            {**r, "poster_url": _proxy_image_url(r.get("poster_url", ""))}
            for r in results
        ]
        return jsonify({"results": proxied})

    @app.route("/api/htv-trending")
    def api_htv_trending():
        results = _cached_browse("htv_trending", _fetch_htv_trending)
        if results is None:
            return jsonify({"error": "Failed to fetch HTV trending"}), 500
        proxied = [
            {**r, "poster_url": _proxy_image_url(r.get("poster_url", ""))}
            for r in results
        ]
        return jsonify({"results": proxied})

    @app.route("/api/mangafire-trending")
    def api_mangafire_trending():
        def _fetch_mangafire_trending():
            response = requests.get("https://mangafire.to/api/top-titles", timeout=20)
            response.raise_for_status()
            payload = response.json() or {}
            return payload.get("items", [])

        results = _cached_browse("mangafire_trending", _fetch_mangafire_trending)
        if results is None:
            return jsonify({"error": "Failed to fetch MangaFire trending"}), 500
        proxied = [
            _mangafire_browse_item(item) for item in results if isinstance(item, dict)
        ]
        return jsonify({"results": proxied})

    @app.route("/api/downloaded-folders")
    def api_downloaded_folders():
        from pathlib import Path

        raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
        if raw:
            p = Path(raw).expanduser()
            if not p.is_absolute():
                p = Path.home() / p
            dl_path = p
        else:
            dl_path = Path.home() / "Downloads"

        lang_sep = os.environ.get("ANIWORLD_LANG_SEPARATION", "0") == "1"
        lang_folders = ["german-dub", "english-sub", "german-sub", "english-dub"]

        # Collect all paths to scan (default + custom)
        scan_roots = [dl_path]
        for cp in get_custom_paths():
            cp_path = Path(cp["path"]).expanduser()
            if not cp_path.is_absolute():
                cp_path = Path.home() / cp_path
            scan_roots.append(cp_path)

        folders = set()
        for root in scan_roots:
            if lang_sep:
                bases = [root / lf for lf in lang_folders]
            else:
                bases = [root]
            for base in bases:
                if not base.is_dir():
                    continue
                try:
                    entries = list(base.iterdir())
                except (PermissionError, OSError):
                    continue
                for entry in entries:
                    if entry.is_dir():
                        folders.add(entry.name)
        return jsonify({"folders": sorted(folders)})

    @app.route("/api/settings", methods=["GET"])
    def api_settings():
        from pathlib import Path

        raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
        if raw:
            p = Path(raw).expanduser()
            if not p.is_absolute():
                p = Path.home() / p
            resolved = str(p)
        else:
            resolved = str(Path.home() / "Downloads")
        lang_separation = os.environ.get("ANIWORLD_LANG_SEPARATION", "0")
        disable_english_sub = os.environ.get("ANIWORLD_DISABLE_ENGLISH_SUB", "0")
        sync_schedule = os.environ.get("ANIWORLD_SYNC_SCHEDULE", "0")
        sync_language = os.environ.get("ANIWORLD_SYNC_LANGUAGE", "German Dub")
        provider_fallback_order = list(get_provider_fallback_order(WORKING_PROVIDERS))
        sync_provider = os.environ.get(
            "ANIWORLD_SYNC_PROVIDER",
            provider_fallback_order[0] if provider_fallback_order else "VOE",
        )
        if sync_provider not in WORKING_PROVIDERS and provider_fallback_order:
            sync_provider = provider_fallback_order[0]
        enable_htv = os.environ.get("ANIWORLD_ENABLE_HTV", "0")
        movie_folder = os.environ.get("ANIWORLD_MOVIE_FOLDER", "1")
        ui_language = os.environ.get("ANIWORLD_UI_LANGUAGE", "en").lower()
        if ui_language not in SUPPORTED_UI_LANGUAGES:
            ui_language = "en"
        return jsonify(
            {
                "download_path": resolved,
                "lang_separation": lang_separation,
                "disable_english_sub": disable_english_sub,
                "enable_htv": enable_htv,
                "movie_folder": movie_folder,
                "ui_language": ui_language,
                "output_format": _naming_template_extension(),
                "sync_schedule": sync_schedule,
                "sync_language": sync_language,
                "sync_provider": sync_provider,
                "provider_fallback_order": provider_fallback_order,
                "available_providers": list(WORKING_PROVIDERS),
                "available_ui_languages": list(SUPPORTED_UI_LANGUAGES),
                "available_output_formats": list(SUPPORTED_OUTPUT_FORMATS),
                "discord": _discord_settings(),
            }
        )

    @app.route("/api/settings/public-ip", methods=["GET"])
    def api_settings_public_ip():
        try:
            result = _fetch_public_ip()
            return jsonify({"ok": True, **result})
        except RuntimeError as exc:
            logger.warning("Failed to resolve public IP: %s", exc)
            return jsonify({"ok": False, "error": "Failed to fetch public IP"}), 502

    @app.route("/api/settings", methods=["PUT"])
    def api_settings_update():
        data = request.get_json(silent=True) or {}
        env_updates = {}

        if "download_path" in data:
            env_updates["ANIWORLD_DOWNLOAD_PATH"] = str(data["download_path"]).strip()
        if "lang_separation" in data:
            env_updates["ANIWORLD_LANG_SEPARATION"] = (
                "1" if data["lang_separation"] else "0"
            )
        if "disable_english_sub" in data:
            env_updates["ANIWORLD_DISABLE_ENGLISH_SUB"] = (
                "1" if data["disable_english_sub"] else "0"
            )
        if "movie_folder" in data:
            env_updates["ANIWORLD_MOVIE_FOLDER"] = "1" if data["movie_folder"] else "0"
        if "ui_language" in data:
            ui_lang = str(data["ui_language"]).strip().lower()
            if ui_lang not in SUPPORTED_UI_LANGUAGES:
                return jsonify({"error": f"Invalid ui_language: {ui_lang}"}), 400
            env_updates["ANIWORLD_UI_LANGUAGE"] = ui_lang
        if "output_format" in data:
            fmt = str(data["output_format"]).strip().lower().lstrip(".")
            if fmt not in SUPPORTED_OUTPUT_FORMATS:
                return jsonify({"error": f"Invalid output_format: {fmt}"}), 400
            env_updates["ANIWORLD_NAMING_TEMPLATE"] = _naming_template_with_extension(
                fmt
            )
        if "sync_schedule" in data:
            sched = str(data["sync_schedule"])
            if sched != "0" and sched not in SYNC_SCHEDULE_MAP:
                return jsonify({"error": f"Invalid sync_schedule: {sched}"}), 400
            env_updates["ANIWORLD_SYNC_SCHEDULE"] = sched
        if "sync_language" in data:
            lang = str(data["sync_language"])
            valid_langs = set(LANG_LABELS.values()) | {"All Languages"}
            if lang not in valid_langs:
                return jsonify({"error": f"Invalid sync_language: {lang}"}), 400
            env_updates["ANIWORLD_SYNC_LANGUAGE"] = lang
        if "sync_provider" in data:
            prov = str(data["sync_provider"])
            if prov not in WORKING_PROVIDERS:
                return jsonify({"error": f"Invalid sync_provider: {prov}"}), 400
            env_updates["ANIWORLD_SYNC_PROVIDER"] = prov
        if "enable_htv" in data:
            env_updates["ANIWORLD_ENABLE_HTV"] = "1" if data["enable_htv"] else "0"
        if "provider_fallback_order" in data:
            raw_order = data["provider_fallback_order"]
            if isinstance(raw_order, list):
                requested_order = [str(provider).strip() for provider in raw_order]
            else:
                requested_order = [
                    provider.strip() for provider in str(raw_order).split(",")
                ]

            requested_order = [provider for provider in requested_order if provider]
            if not requested_order:
                return jsonify(
                    {"error": "provider_fallback_order cannot be empty"}
                ), 400

            invalid = [
                provider
                for provider in requested_order
                if provider not in WORKING_PROVIDERS
            ]
            if invalid:
                invalid_list = ", ".join(sorted(dict.fromkeys(invalid)))
                return (
                    jsonify(
                        {
                            "error": "Invalid provider_fallback_order entries: "
                            + invalid_list
                        }
                    ),
                    400,
                )

            if len(set(requested_order)) != len(requested_order):
                return jsonify(
                    {"error": "provider_fallback_order contains duplicates"}
                ), 400

            env_updates["ANIWORLD_PROVIDER_FALLBACK_ORDER"] = ",".join(
                parse_provider_order(
                    ",".join(requested_order),
                    allowed_providers=WORKING_PROVIDERS,
                )
            )

        if "discord" in data:
            error = _apply_discord_settings(data["discord"], env_updates)
            if error:
                return jsonify({"error": error}), 400

        # Settings are intentionally in-memory only for the running process.
        # To persist across restarts, users set them in their .env file.
        for key, value in env_updates.items():
            os.environ[key] = value

        if "discord" in data:
            # The Discord bot config is the one setting that must survive a
            # restart, so persist just those keys to .env (see the helper).
            _persist_discord_env(env_updates)
            _reconcile_discord_bot()

        return jsonify({"ok": True})

    @app.route("/api/discord/status")
    def api_discord_status():
        try:
            from .discord_bot import get_status

            return jsonify(get_status())
        except Exception as exc:
            return jsonify({"running": False, "error": str(exc)[:120]})

    @app.route("/api/custom-paths")
    def api_custom_paths():
        paths = get_custom_paths()
        return jsonify({"paths": paths})

    @app.route("/api/custom-paths", methods=["POST"])
    def api_custom_paths_add():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        path = (data.get("path") or "").strip()
        if not name or not path:
            return jsonify({"error": "name and path are required"}), 400
        default_sites = _normalize_default_sites(data.get("default_sites"))
        path_id = add_custom_path(name, path, default_sites)
        return jsonify({"ok": True, "id": path_id})

    @app.route("/api/custom-paths/<int:path_id>", methods=["PUT"])
    def api_custom_paths_update(path_id):
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        path = data.get("path")
        default_sites = (
            _normalize_default_sites(data.get("default_sites"))
            if "default_sites" in data
            else None
        )
        update_custom_path(
            path_id,
            name=name.strip() if isinstance(name, str) else None,
            path=path.strip() if isinstance(path, str) else None,
            default_sites=default_sites,
        )
        return jsonify({"ok": True})

    @app.route("/api/custom-paths/<int:path_id>", methods=["DELETE"])
    def api_custom_paths_delete(path_id):
        remove_custom_path(path_id)
        return jsonify({"ok": True})

    # ===== Planned Releases Page =====

    @app.route("/planned")
    def planned_page():
        return render_template(
            "planned.html",
            available_providers=WORKING_PROVIDERS,
            site_keys=SITE_KEYS,
        )

    @app.route("/api/planned")
    def api_planned_list():
        username, is_admin = _get_current_user_info()
        jobs = get_planned_jobs(added_by=None if is_admin else username)
        return jsonify({"jobs": jobs})

    @app.route("/api/planned", methods=["POST"])
    def api_planned_create():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "title is required"}), 400

        media_type = (data.get("media_type") or "").strip().lower()
        if media_type not in ("movie", "series"):
            return jsonify({"error": "media_type must be 'movie' or 'series'"}), 400

        provider = str(data.get("provider", "VOE"))
        if provider not in WORKING_PROVIDERS:
            provider = WORKING_PROVIDERS[0] if WORKING_PROVIDERS else "VOE"

        username, _ = _get_current_user_info()
        job_id = add_planned_job(
            title=title,
            # No single site any more: the worker scans every site of this type.
            site="any",
            media_type=media_type,
            language=str(data.get("language", "German Dub")),
            provider=provider,
            custom_path_id=data.get("custom_path_id"),
            auto_sync=1 if data.get("auto_sync") else 0,
            added_by=username,
        )
        return jsonify({"ok": True, "id": job_id})

    @app.route("/api/planned/<int:job_id>", methods=["DELETE"])
    def api_planned_delete(job_id):
        ok, err = remove_planned_job(job_id)
        if not ok:
            return jsonify({"error": err}), 404
        return jsonify({"ok": True})

    @app.route("/api/planned/<int:job_id>/check", methods=["POST"])
    def api_planned_check(job_id):
        job = get_planned_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        from .planned import check_planned_job

        found = check_planned_job(job)
        return jsonify({"ok": True, "found": found})

    # ===== Auto-Sync Page =====

    @app.route("/autosync")
    def autosync_page():
        return render_template("autosync.html")

    # ===== Auto-Sync API =====

    def _get_current_user_info():
        """Return (username, is_admin) for the current request."""
        if not auth_enabled:
            return None, True  # no auth → treat as admin
        user = get_current_user()
        if not user:
            return None, False
        username = (
            user.get("username")
            if isinstance(user, dict)
            else getattr(user, "username", None)
        )
        role = (
            user.get("role")
            if isinstance(user, dict)
            else getattr(user, "role", "user")
        )
        return username, role == "admin"

    @app.route("/api/autosync")
    def api_autosync_list():
        username, is_admin = _get_current_user_info()
        # Admins see all jobs; regular users see only their own
        jobs = get_autosync_jobs(username=None if is_admin else username)
        return jsonify({"jobs": jobs})

    @app.route("/api/autosync", methods=["POST"])
    def api_autosync_create():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        series_url = (data.get("series_url") or "").strip()
        language = data.get("language", "German Dub")
        provider = data.get("provider", "VOE")
        custom_path_id = data.get("custom_path_id")

        if not title or not series_url:
            return jsonify({"error": "title and series_url are required"}), 400

        existing = find_autosync_by_url(series_url)
        if existing:
            return jsonify(
                {"error": "A sync job for this series already exists", "job": existing}
            ), 409

        username, _ = _get_current_user_info()
        job_id = add_autosync_job(
            title=title,
            series_url=series_url,
            language=language,
            provider=provider,
            custom_path_id=custom_path_id,
            added_by=username,
        )
        return jsonify({"ok": True, "id": job_id})

    @app.route("/api/autosync/<int:job_id>", methods=["PUT"])
    def api_autosync_update(job_id):
        job = get_autosync_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        username, is_admin = _get_current_user_info()
        if not is_admin and job.get("added_by") != username:
            return jsonify({"error": "Not authorized to edit this job"}), 403
        data = request.get_json(silent=True) or {}
        allowed = {"language", "provider", "enabled", "custom_path_id"}
        filtered = {k: v for k, v in data.items() if k in allowed}
        update_autosync_job(job_id, **filtered)
        return jsonify({"ok": True})

    @app.route("/api/autosync/<int:job_id>", methods=["DELETE"])
    def api_autosync_delete(job_id):
        job = get_autosync_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        username, is_admin = _get_current_user_info()
        if not is_admin and job.get("added_by") != username:
            return jsonify({"error": "Not authorized to delete this job"}), 403
        ok, err = remove_autosync_job(job_id)
        if not ok:
            return jsonify({"error": err}), 404
        return jsonify({"ok": True})

    @app.route("/api/autosync/<int:job_id>/sync", methods=["POST"])
    def api_autosync_trigger(job_id):
        job = get_autosync_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        username, is_admin = _get_current_user_info()
        if not is_admin and job.get("added_by") != username:
            return jsonify({"error": "Not authorized"}), 403
        with _syncing_jobs_lock:
            if job_id in _syncing_jobs:
                return jsonify({"error": "Sync already running for this job"}), 409
        threading.Thread(target=_run_autosync_for_job, args=(job,), daemon=True).start()
        return jsonify({"ok": True, "message": "Sync started"})

    @app.route("/api/autosync/check", methods=["GET"])
    def api_autosync_check():
        """Check if a sync job exists for a given series URL."""
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"exists": False})
        job = find_autosync_by_url(url)
        if not job:
            return jsonify({"exists": False})
        # Only expose job details to the owner or admins
        username, is_admin = _get_current_user_info()
        if not is_admin and job.get("added_by") != username:
            return jsonify({"exists": False})
        return jsonify({"exists": True, "job": job})

    # ===== Stats API =====

    @app.route("/api/stats/sync")
    def api_stats_sync():
        stats = get_sync_stats()
        # Compute next_run_at from last check + schedule interval
        schedule_key = os.environ.get("ANIWORLD_SYNC_SCHEDULE", "0")
        interval = SYNC_SCHEDULE_MAP.get(schedule_key, 0)
        stats["schedule"] = schedule_key
        stats["next_run_at"] = None
        if interval and stats.get("last_check"):
            from datetime import datetime, timedelta

            try:
                last = datetime.strptime(stats["last_check"], "%Y-%m-%d %H:%M:%S")
                nxt = last + timedelta(seconds=interval)
                stats["next_run_at"] = nxt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        return jsonify(stats)

    @app.route("/api/stats/queue")
    def api_stats_queue():
        return jsonify(get_queue_stats())

    @app.route("/api/stats/general")
    def api_stats_general():
        return jsonify(get_general_stats())

    @app.route("/api/library")
    def api_library():
        from pathlib import Path

        raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
        if raw:
            dl_base = Path(raw).expanduser()
            if not dl_base.is_absolute():
                dl_base = Path.home() / dl_base
        else:
            dl_base = Path.home() / "Downloads"

        lang_sep = os.environ.get("ANIWORLD_LANG_SEPARATION", "0") == "1"
        lang_folders = ["german-dub", "english-sub", "german-sub", "english-dub"]
        ep_re = re.compile(r"S(\d{2})E(\d{2,3})", re.IGNORECASE)
        video_exts = {
            ".mkv",
            ".mp4",
            ".avi",
            ".webm",
            ".flv",
            ".mov",
            ".wmv",
            ".m4v",
            ".ts",
        }

        # Build list of (label, custom_path_id, base_path) to scan
        scan_targets = [("Default", None, dl_base)]
        for cp in get_custom_paths():
            cp_base = Path(cp["path"]).expanduser()
            if not cp_base.is_absolute():
                cp_base = Path.home() / cp_base
            scan_targets.append((cp["name"], cp["id"], cp_base))

        def _scan_base(base):
            """Scan a single base directory and return list of title dicts."""
            lang_folder_set = set(lang_folders)
            titles = {}
            if not base.is_dir():
                return []
            try:
                folders = list(base.iterdir())
            except (PermissionError, OSError):
                return []

            for folder in folders:
                if not folder.is_dir():
                    continue
                name = folder.name
                if name in lang_folder_set:
                    continue
                if name not in titles:
                    titles[name] = {"folder": name, "seasons": {}, "total_size": 0}
                entry = titles[name]
                for f in folder.rglob("*"):
                    if not f.is_file() or f.name.startswith(".temp_"):
                        continue
                    m = ep_re.search(f.name)
                    if not m:
                        continue
                    snum = int(m.group(1))
                    enum = int(m.group(2))
                    is_video = f.suffix.lower() in video_exts
                    try:
                        fsize = f.stat().st_size
                    except OSError:
                        fsize = 0
                    skey = str(snum)
                    if skey not in entry["seasons"]:
                        entry["seasons"][skey] = []
                    if not any(
                        e["episode"] == enum and e["file"] == f.name
                        for e in entry["seasons"][skey]
                    ):
                        entry["seasons"][skey].append(
                            {
                                "episode": enum,
                                "file": f.name,
                                "size": fsize,
                                "is_video": is_video,
                            }
                        )
                        entry["total_size"] += fsize

            result = []
            for entry in sorted(titles.values(), key=lambda x: x["folder"].lower()):
                if not any(entry["seasons"].values()):
                    continue
                total_eps = sum(
                    sum(1 for e in eps if e.get("is_video", True))
                    for eps in entry["seasons"].values()
                )
                for skey in entry["seasons"]:
                    entry["seasons"][skey].sort(key=lambda e: e["episode"])
                result.append(
                    {
                        "folder": entry["folder"],
                        "seasons": entry["seasons"],
                        "total_episodes": total_eps,
                        "total_size": entry["total_size"],
                    }
                )
            return result

        locations = []
        for label, cp_id, base_path in scan_targets:
            if lang_sep:
                loc_lang_folders = []
                for lf in lang_folders:
                    lf_titles = _scan_base(base_path / lf)
                    if lf_titles:
                        loc_lang_folders.append(
                            {
                                "name": lf,
                                "titles": lf_titles,
                            }
                        )
                if loc_lang_folders:
                    locations.append(
                        {
                            "label": label,
                            "custom_path_id": cp_id,
                            "lang_folders": loc_lang_folders,
                            "titles": None,
                        }
                    )
            else:
                loc_titles = _scan_base(base_path)
                if loc_titles:
                    locations.append(
                        {
                            "label": label,
                            "custom_path_id": cp_id,
                            "lang_folders": None,
                            "titles": loc_titles,
                        }
                    )

        return jsonify({"lang_sep": lang_sep, "locations": locations})

    @app.route("/api/library/delete", methods=["POST"])
    def api_library_delete():
        import shutil
        from pathlib import Path

        data = request.get_json(silent=True) or {}
        folder = data.get("folder", "")
        season = data.get("season")  # int or null
        episode = data.get("episode")  # int or null
        custom_path_id = data.get("custom_path_id")  # int or null

        # Security: reject dangerous folder names
        if (
            not folder
            or ".." in folder
            or "/" in folder
            or "\\" in folder
            or "\x00" in folder
        ):
            return jsonify({"error": "Invalid folder name"}), 400

        # Resolve base path from custom_path_id or default
        if custom_path_id:
            cp = get_custom_path_by_id(custom_path_id)
            if not cp:
                return jsonify({"error": "Custom path not found"}), 404
            dl_base = Path(cp["path"]).expanduser()
            if not dl_base.is_absolute():
                dl_base = Path.home() / dl_base
        else:
            raw = os.environ.get("ANIWORLD_DOWNLOAD_PATH", "")
            if raw:
                dl_base = Path(raw).expanduser()
                if not dl_base.is_absolute():
                    dl_base = Path.home() / dl_base
            else:
                dl_base = Path.home() / "Downloads"

        lang_sep = os.environ.get("ANIWORLD_LANG_SEPARATION", "0") == "1"
        lang_folders = ["german-dub", "english-sub", "german-sub", "english-dub"]
        lang_folder = data.get("lang_folder")  # str or null

        if lang_sep and lang_folder:
            if lang_folder not in lang_folders:
                return jsonify({"error": "Invalid language folder"}), 400
            bases = [dl_base / lang_folder]
        elif lang_sep:
            bases = [dl_base / lf for lf in lang_folders]
        else:
            bases = [dl_base]

        deleted = 0
        for base in bases:
            title_path = base / folder
            # Verify resolved path is a child of the base
            try:
                title_path.resolve().relative_to(base.resolve())
            except ValueError:
                continue
            if not title_path.is_dir():
                continue

            if season is None and episode is None:
                # Delete entire title
                shutil.rmtree(title_path, ignore_errors=True)
                deleted += 1
            else:
                # Build regex pattern
                if episode is not None:
                    pat = re.compile(
                        rf"S{int(season):02d}E{int(episode):03d}(?!\d)", re.IGNORECASE
                    )
                else:
                    pat = re.compile(rf"S{int(season):02d}E\d{{2,3}}", re.IGNORECASE)

                for f in list(title_path.rglob("*")):
                    if f.is_file() and pat.search(f.name):
                        try:
                            f.unlink()
                            deleted += 1
                        except OSError:
                            pass

                # Cleanup empty directories bottom-up
                for dirpath in sorted(
                    title_path.rglob("*"), key=lambda p: len(p.parts), reverse=True
                ):
                    if dirpath.is_dir():
                        try:
                            dirpath.rmdir()  # only succeeds if empty
                        except OSError:
                            pass
                # Remove title folder itself if empty
                try:
                    title_path.rmdir()
                except OSError:
                    pass

        if deleted == 0:
            return jsonify({"error": "Nothing found to delete"}), 404
        return jsonify({"ok": True, "deleted": deleted})

    if auth_enabled:
        from .auth import admin_required

        # Endpoints that require admin instead of just login
        _admin_only = {
            "settings_page",
            "api_settings",
            "api_settings_public_ip",
            "api_settings_update",
            "api_discord_status",
            "api_library_delete",
            "api_custom_paths_add",
            "api_custom_paths_update",
            "api_custom_paths_delete",
            "api_autosync_create",
            "api_autosync_update",
            "api_autosync_delete",
            "api_autosync_trigger",
            "api_planned_create",
            "api_planned_delete",
            "api_planned_check",
        }

        # Wrap all non-auth, non-static view functions with login_required
        # (admin_required for settings endpoints)
        _exempt = {
            "static",
            "auth.login",
            "auth.logout",
            "auth.setup",
            "auth.oidc_login",
            "auth.oidc_callback",
        }
        for endpoint, view_func in list(app.view_functions.items()):
            if endpoint not in _exempt:
                if endpoint in _admin_only:
                    app.view_functions[endpoint] = admin_required(view_func)
                else:
                    app.view_functions[endpoint] = login_required(view_func)

        # Exempt JSON API routes from CSRF (they use Content-Type: application/json
        # which provides implicit cross-origin protection via CORS preflight)
        for endpoint in list(app.view_functions):
            if endpoint.startswith("api_") or endpoint.startswith("auth.admin_"):
                csrf.exempt(app.view_functions[endpoint])

    return app


def start_web_ui(
    host="127.0.0.1",
    port=8080,
    open_browser=True,
    auth_enabled=False,
    sso_enabled=False,
    force_sso=False,
):
    """Start the Flask web UI server."""
    import threading
    import webbrowser

    # Allow env var overrides (Docker-friendly)
    force_sso = force_sso or os.getenv("ANIWORLD_WEB_FORCE_SSO", "0") == "1"
    sso_enabled = sso_enabled or force_sso or os.getenv("ANIWORLD_WEB_SSO", "0") == "1"
    auth_enabled = (
        auth_enabled or force_sso or os.getenv("ANIWORLD_WEB_AUTH", "0") == "1"
    )

    app = create_app(
        auth_enabled=auth_enabled, sso_enabled=sso_enabled, force_sso=force_sso
    )
    display_host = "localhost" if host == "127.0.0.1" else host
    url = f"http://{display_host}:{port}"
    print(f"Starting AniWorld Web UI on {url}")

    debug = os.getenv("ANIWORLD_DEBUG_MODE", "0") == "1"

    # In debug mode, Flask's reloader spawns a child process that re-executes
    # this function. Only open the browser in the parent (reloader) process
    # to avoid opening it twice.
    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if open_browser and not is_reloader_child:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        from waitress import serve

        serve(app, host=host, port=port)
