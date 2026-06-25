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
from ..providers import resolve_provider
from ..search import (
    fetch_new_animes,
    fetch_new_series,
    fetch_popular_animes,
    fetch_popular_series,
    query_s_to,
    random_anime,
)
from ..search import query as aniworld_query
from .db import (
    add_autosync_job,
    add_custom_path,
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
    init_autosync_db,
    init_custom_paths_db,
    init_queue_db,
    is_queue_cancelled,
    is_series_queued_or_running,
    move_queue_item,
    remove_autosync_job,
    remove_custom_path,
    remove_from_queue,
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


# Only match series-level links: /anime/stream/<slug> (no season/episode)
_SERIES_LINK_PATTERN = re.compile(r"^/anime/stream/[a-zA-Z0-9\-]+/?$", re.IGNORECASE)

# Only match s.to series-level links: /serie/<slug> (no season/episode)
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
                        set_queue_status(item["id"], "running")

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
                update_queue_progress(item["id"], i, ep_url)
                try:
                    prov = resolve_provider(ep_url)
                    ep_kwargs = {
                        "url": ep_url,
                        "selected_language": item["language"],
                        "selected_provider": item["provider"],
                    }
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
                    errors.append({"url": ep_url, "error": str(e)})
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

        except Exception as e:
            logger.error(f"Queue worker error: {e}", exc_info=True)
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
                    for folder in base.iterdir():
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

            time.sleep(10)
        except Exception as e:
            logger.error("Auto-sync worker error: %s", e, exc_info=True)
            time.sleep(30)


def _ensure_autosync_worker():
    """Start the auto-sync worker thread once."""
    global _autosync_worker_started
    if _autosync_worker_started:
        return
    _autosync_worker_started = True
    thread = threading.Thread(target=_autosync_worker, daemon=True)
    thread.start()


def _get_version():
    try:
        from importlib.metadata import version

        return version("aniworld")
    except Exception:
        return ""


def _proxy_image_url(url: str) -> str:
    if not url:
        return url
    from urllib.parse import quote

    return f"/api/proxy-image?url={quote(url, safe='')}"


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

    # Initialize download queue, custom paths and autosync (works with or without auth)
    init_queue_db()
    init_custom_paths_db()
    init_autosync_db()

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
        default_web_language = os.environ.get("ANIWORLD_LANGUAGE", "German Dub")
        if default_web_language not in LANG_LABELS.values():
            default_web_language = "German Dub"
        htv_enabled = os.environ.get("ANIWORLD_ENABLE_HTV", "0") == "1"
        return render_template(
            "index.html",
            lang_labels=LANG_LABELS,
            sto_lang_labels=sto_lang_labels,
            supported_providers=WORKING_PROVIDERS,
            default_web_language=default_web_language,
            htv_enabled=htv_enabled,
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
                        "poster_url": _proxy_image_url(poster),
                    }
                )
        elif site == "sto":
            # s.to search
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
                            "url": f"https://s.to{link}",
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
            # s.to returns relative poster paths - make them absolute
            if poster and poster.startswith("/"):
                from urllib.parse import urlparse

                parsed = urlparse(url)
                poster = f"{parsed.scheme}://{parsed.netloc}{poster}"
            return jsonify(
                {
                    "title": series.title,
                    "poster_url": _proxy_image_url(poster),
                    "description": getattr(series, "description", ""),
                    "genres": getattr(series, "genres", []),
                    "release_year": getattr(series, "release_year", ""),
                }
            )
        except Exception as e:
            logger.error(f"Series fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/seasons")
    def api_seasons():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)
            series = prov.series_cls(url=url)
            seasons_data = []
            for season in series.seasons:
                seasons_data.append(
                    {
                        "url": season.url,
                        "season_number": season.season_number,
                        "episode_count": season.episode_count,
                        "are_movies": getattr(season, "are_movies", False),
                    }
                )
            return jsonify({"seasons": seasons_data})
        except Exception as e:
            logger.error(f"Seasons fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/episodes")
    def api_episodes():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)

            # HTV: season URL is empty; use the series URL to get episodes
            if prov.name == "HanimeTV":
                series_url = request.args.get("series_url", "").strip() or url
                series = prov.series_cls(url=series_url)
                season = series.seasons[0] if series.seasons else None
                if not season:
                    return jsonify({"episodes": []})
            else:
                # Pass series to avoid broken series URL reconstruction in s.to
                # season model (its fallback splits on "-" which fails)
                series_url = re.sub(r"/staffel-\d+/?$", "", url)
                series_url = re.sub(r"/filme/?$", "", series_url)
                try:
                    series = prov.series_cls(url=series_url)
                except Exception:
                    series = None
                season = prov.season_cls(url=url, series=series)

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
                        for folder in base.iterdir():
                            if (
                                not folder.is_dir()
                                or not folder.name.lower().startswith(title_clean)
                            ):
                                continue
                            for f in folder.rglob("*"):
                                if f.is_file():
                                    m = ep_re.search(f.name)
                                    if m:
                                        downloaded_eps.add(
                                            (int(m.group(1)), int(m.group(2)))
                                        )
            except Exception:
                pass

            episodes_data = []
            for ep in season.episodes:
                downloaded = (
                    ep.season.season_number,
                    ep.episode_number,
                ) in downloaded_eps
                available_languages = _episode_language_labels(ep.provider_data)

                episodes_data.append(
                    {
                        "url": ep.url,
                        "episode_number": ep.episode_number,
                        "title_de": getattr(ep, "title_de", ""),
                        "title_en": getattr(ep, "title_en", ""),
                        "downloaded": downloaded,
                        "available_languages": available_languages,
                    }
                )
            return jsonify({"episodes": episodes_data})
        except Exception as e:
            logger.error(f"Episodes fetch failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/providers")
    def api_providers():
        url = request.args.get("url", "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        try:
            prov = resolve_provider(url)
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
                    working = [p for p in providers.keys() if p in WORKING_PROVIDERS]
                    if working:
                        provider_info[label] = working
            else:
                # s.to: plain dict with (Audio, Subtitles) enum tuple keys
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
            return jsonify({"error": "Random is not available for S.TO"}), 400
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
                for entry in base.iterdir():
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
        return jsonify(
            {
                "download_path": resolved,
                "lang_separation": lang_separation,
                "disable_english_sub": disable_english_sub,
                "enable_htv": enable_htv,
                "sync_schedule": sync_schedule,
                "sync_language": sync_language,
                "sync_provider": sync_provider,
                "provider_fallback_order": provider_fallback_order,
                "available_providers": list(WORKING_PROVIDERS),
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
        if "download_path" in data:
            os.environ["ANIWORLD_DOWNLOAD_PATH"] = str(data["download_path"]).strip()
        if "lang_separation" in data:
            os.environ["ANIWORLD_LANG_SEPARATION"] = (
                "1" if data["lang_separation"] else "0"
            )
        if "disable_english_sub" in data:
            os.environ["ANIWORLD_DISABLE_ENGLISH_SUB"] = (
                "1" if data["disable_english_sub"] else "0"
            )
        if "sync_schedule" in data:
            sched = str(data["sync_schedule"])
            if sched != "0" and sched not in SYNC_SCHEDULE_MAP:
                return jsonify({"error": f"Invalid sync_schedule: {sched}"}), 400
            os.environ["ANIWORLD_SYNC_SCHEDULE"] = sched
        if "sync_language" in data:
            lang = str(data["sync_language"])
            valid_langs = set(LANG_LABELS.values()) | {"All Languages"}
            if lang not in valid_langs:
                return jsonify({"error": f"Invalid sync_language: {lang}"}), 400
            os.environ["ANIWORLD_SYNC_LANGUAGE"] = lang
        if "sync_provider" in data:
            prov = str(data["sync_provider"])
            if prov not in WORKING_PROVIDERS:
                return jsonify({"error": f"Invalid sync_provider: {prov}"}), 400
            os.environ["ANIWORLD_SYNC_PROVIDER"] = prov
        if "enable_htv" in data:
            os.environ["ANIWORLD_ENABLE_HTV"] = "1" if data["enable_htv"] else "0"
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

            os.environ["ANIWORLD_PROVIDER_FALLBACK_ORDER"] = ",".join(
                parse_provider_order(
                    ",".join(requested_order),
                    allowed_providers=WORKING_PROVIDERS,
                )
            )
        return jsonify({"ok": True})

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
        path_id = add_custom_path(name, path)
        return jsonify({"ok": True, "id": path_id})

    @app.route("/api/custom-paths/<int:path_id>", methods=["DELETE"])
    def api_custom_paths_delete(path_id):
        remove_custom_path(path_id)
        return jsonify({"ok": True})

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
            for folder in base.iterdir():
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
            "api_library_delete",
            "api_custom_paths_add",
            "api_custom_paths_delete",
            "api_autosync_create",
            "api_autosync_update",
            "api_autosync_delete",
            "api_autosync_trigger",
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
