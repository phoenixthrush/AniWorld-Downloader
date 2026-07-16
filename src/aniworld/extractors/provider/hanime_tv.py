import json
import re
import threading
import time
from datetime import datetime, timezone

import niquests

try:
    from ...config import DEFAULT_USER_AGENT, logger
    from ...playwright.captcha import (
        playwright_get_hanime_page_html,
        playwright_get_hanime_search_db,
        playwright_get_hanime_stream_url,
    )
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, logger
    from aniworld.playwright.captcha import (
        playwright_get_hanime_page_html,
        playwright_get_hanime_search_db,
        playwright_get_hanime_stream_url,
    )


HANIME_VIDEO_URL = "https://hanime.tv/videos/hentai/{slug}"
_HANIME_HEADERS = {"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://hanime.tv/"}

# hanime.tv ships its whole video catalogue (one JSON array, ~4 MB) to the
# browser and searches it client-side; this is that endpoint. The old
# search.htv-services.com API this project used no longer exists (its DNS
# records are gone).
HANIME_SEARCH_DB_URL = "https://guest.freeanimehentai.net/api/v11/search_hvs"
_SEARCH_DB_TTL_SECONDS = 6 * 60 * 60
_SEARCH_DB_RETRY_SECONDS = 5 * 60

_search_db_lock = threading.Lock()
_search_db_cache = {"videos": None, "by_slug": {}, "fetched_at": 0.0, "failed_at": 0.0}


def _parse_search_db(raw):
    """Validate/parse the search database payload into a list of video dicts."""
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
    if not isinstance(raw, list):
        return None
    videos = [v for v in raw if isinstance(v, dict) and v.get("slug")]
    return videos or None


def fetch_hanime_search_db(allow_browser=True):
    """Return hanime.tv's full video database (list of dicts), cached in memory.

    Tries a plain HTTP GET first (works for normal clients); when that is
    blocked and ``allow_browser`` is set, captures the payload with Patchright
    from the real search page. Failed refreshes are retried after a short
    cooldown and return the last good (possibly stale) copy, or None when the
    database was never fetched.
    """
    now = time.time()
    with _search_db_lock:
        cached = _search_db_cache["videos"]
        if cached is not None and now - _search_db_cache["fetched_at"] < _SEARCH_DB_TTL_SECONDS:
            return cached
        if now - _search_db_cache["failed_at"] < _SEARCH_DB_RETRY_SECONDS:
            return cached

        videos = None
        try:
            resp = niquests.get(
                HANIME_SEARCH_DB_URL,
                headers={
                    **_HANIME_HEADERS,
                    "Accept": "application/json",
                    "Origin": "https://hanime.tv",
                },
                timeout=20,
            )
            resp.raise_for_status()
            videos = _parse_search_db(resp.json())
        except Exception as exc:  # noqa: BLE001 - fall through to the browser
            logger.debug(f"Direct hanime search-db fetch failed: {exc}")

        if videos is None and allow_browser:
            logger.warning(
                "Hanime rejected the direct search-database request; "
                "retrying with Patchright"
            )
            try:
                videos = _parse_search_db(playwright_get_hanime_search_db())
            except Exception as exc:  # noqa: BLE001 - keep the stale copy
                logger.warning(f"Patchright hanime search-db capture failed: {exc}")

        if videos is None:
            _search_db_cache["failed_at"] = now
            return _search_db_cache["videos"]

        _search_db_cache["videos"] = videos
        _search_db_cache["by_slug"] = {v["slug"]: v for v in videos}
        _search_db_cache["fetched_at"] = now
        _search_db_cache["failed_at"] = 0.0
        return videos


def _search_db_entry(slug):
    """Return the cached database entry for a slug, or None. Best-effort."""
    try:
        if fetch_hanime_search_db(allow_browser=False) is None:
            return None
    except Exception:  # noqa: BLE001 - enrichment must never break scraping
        return None
    return _search_db_cache["by_slug"].get(slug)


def _regex_group(pattern, text, *, flags=0, group=1, default=""):
    match = re.search(pattern, text, flags)
    return match.group(group).strip() if match else default


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _dedupe_preserve_order(values):
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _episode_sort_key(slug):
    match = re.search(r"-(\d+)$", slug or "")
    return (int(match.group(1)) if match else 0, slug or "")


def _slug_to_title(slug):
    if not slug:
        return ""
    title = re.sub(r"-\d+$", "", slug).replace("-", " ").strip()
    return title.title()


def _slug_to_episode_title(slug):
    """Readable per-episode title, keeping the trailing episode number."""
    if not slug:
        return ""
    return slug.replace("-", " ").strip().title()


def _build_synthetic_payload(slug, html):
    title_text = _regex_group(
        r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
        html,
    )
    title_match = re.match(r"^Watch\s+(.+?)\s+Hentai Video", title_text, re.IGNORECASE)
    video_title = title_match.group(1).strip() if title_match else _slug_to_title(slug)

    # The real synopsis is server-rendered inside an expandable panel; the
    # og:description is only generic SEO boilerplate ("Watch X latest hentai
    # online free...") and is kept as fallback.
    description = _regex_group(
        r"data-expand-content[^>]*>\s*<span>(.*?)</span>",
        html,
        flags=re.DOTALL,
    )
    if not description:
        description = _regex_group(
            r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']',
            html,
        )
    poster_url = _regex_group(
        r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
        html,
    )

    ldjson = {}
    for raw in re.findall(
        r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>',
        html,
        re.DOTALL,
    ):
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("@type") == "VideoObject":
            ldjson = parsed
            break

    upload_date = ldjson.get("uploadDate") or ""
    upload_dt = _parse_iso_datetime(upload_date)

    brand_link_match = re.search(
        r'<a\s+href=["\'](/(?:browse/)?brands/[^"\']+)["\'][^>]*>'
        r".*?<strong[^>]*>([^<]+)</strong>",
        html,
        re.DOTALL,
    )
    brand_name = brand_link_match.group(2).strip() if brand_link_match else ""
    brand_slug = (
        brand_link_match.group(1).rstrip("/").split("/")[-1] if brand_link_match else ""
    )

    tag_texts = [
        match.group(1).strip()
        for match in re.finditer(
            r'<a\s+href=["\']/(?:browse/)?tags/[^"\']+["\'][^>]*>([^<]+)</a>',
            html,
            re.DOTALL,
        )
    ]
    tags = _dedupe_preserve_order([tag for tag in tag_texts if tag])

    # Franchise episodes live in the "More from <franchise>" section. Only
    # links inside that section count — the page also renders recommendation
    # links to unrelated videos elsewhere, which must not become episodes.
    related_heading = re.search(r"More from\s+([^<]+)</h2>", html, re.IGNORECASE)
    franchise_title = related_heading.group(1).strip() if related_heading else ""
    if not franchise_title:
        franchise_title = re.sub(r"\s*\d+$", "", video_title).strip() or video_title

    episode_html = ""
    if related_heading:
        section_end = html.find("</section>", related_heading.end())
        episode_html = html[
            related_heading.end(): section_end if section_end != -1 else len(html)
        ]

    episode_slugs = _dedupe_preserve_order(
        match.group(1).strip()
        for match in re.finditer(
            r'<a\s+href=["\']/videos/hentai/([^"\'/]+)/?["\']',
            episode_html,
        )
    )
    if slug not in episode_slugs:
        episode_slugs.append(slug)
    episode_slugs = sorted(episode_slugs, key=_episode_sort_key)
    episode_urls = [HANIME_VIDEO_URL.format(slug=s) for s in episode_slugs]

    tag_objects = [
        {
            "id": None,
            "slug": re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-"),
            "text": tag,
        }
        for tag in tags
    ]

    return {
        "hentai_video": {
            "id": None,
            "slug": slug,
            "name": video_title,
            "description": description,
            "cover_url": poster_url,
            "poster_url": poster_url,
            "released_at": upload_date,
            "released_at_unix": int(upload_dt.timestamp()) if upload_dt else None,
            "brand": brand_name,
            "hentai_tags": tag_objects,
        },
        "hentai_franchise": {
            "id": None,
            "slug": re.sub(r"-\d+$", "", slug),
            "title": franchise_title,
            "name": franchise_title,
        },
        "hentai_franchise_hentai_videos": [
            {"slug": s, "name": _slug_to_episode_title(s)} for s in episode_slugs
        ],
        "brand": {
            "id": None,
            "slug": brand_slug,
            "title": brand_name,
        },
        "tags": tag_objects,
        "videos_manifest": {},
    }


def _enrich_payload_from_db(payload, slug):
    """Fill page-scrape gaps from the search database. Strictly best-effort.

    The database carries fields the page markup lacks or garbles: exact video
    titles (episode names would otherwise be reconstructed from slugs), the
    full description, brand, tags and release dates.
    """
    entry = _search_db_entry(slug)
    if entry:
        hv = payload["hentai_video"]
        hv["id"] = entry.get("id")
        for src_key, dst_key in (
            ("name", "name"),
            ("description", "description"),
            ("cover_url", "cover_url"),
            ("poster_url", "poster_url"),
            ("released_at", "released_at"),
            ("released_at_unix", "released_at_unix"),
            ("brand", "brand"),
        ):
            if entry.get(src_key):
                hv[dst_key] = entry[src_key]

        tag_names = [t for t in entry.get("tags") or [] if isinstance(t, str)]
        if tag_names:
            tag_objects = [
                {
                    "id": None,
                    "slug": re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-"),
                    "text": tag,
                }
                for tag in tag_names
            ]
            hv["hentai_tags"] = tag_objects
            payload["tags"] = tag_objects

        if entry.get("brand"):
            payload["brand"]["title"] = payload["brand"]["title"] or entry["brand"]
        if entry.get("brand_id"):
            payload["brand"]["id"] = entry["brand_id"]

    for video in payload.get("hentai_franchise_hentai_videos") or []:
        db_video = _search_db_entry(video.get("slug"))
        if db_video and db_video.get("name"):
            video["name"] = db_video["name"]

    return payload


def fetch_hanime_api_data(slug):
    """Fetch Hanime metadata, using Patchright when its HTTP endpoint blocks us."""
    page_url = HANIME_VIDEO_URL.format(slug=slug)
    logger.debug(f"scraping hanime page ({page_url})...")
    try:
        resp = niquests.get(page_url, headers=_HANIME_HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except niquests.exceptions.RequestException as exc:
        logger.warning(
            "Hanime rejected the direct metadata request; retrying with Patchright"
        )
        html = playwright_get_hanime_page_html(page_url)
        if not html:
            raise RuntimeError(
                "Could not retrieve the Hanime page through HTTP or Patchright"
            ) from exc

    return _enrich_payload_from_db(_build_synthetic_payload(slug, html), slug)


def get_direct_link_from_hanime_tv(api_data):
    """Extract the best-quality stream URL from hanime.tv API data."""
    manifest = api_data.get("videos_manifest") or {}
    servers = manifest.get("servers") or []

    best_url = None
    best_height = 0

    for server in servers:
        for stream in server.get("streams") or []:
            url = stream.get("signed_url") or stream.get("url") or ""
            if not url:
                continue
            height = int(stream.get("height") or 0)
            if height > best_height:
                best_height = height
                best_url = url

    if not best_url:
        video_slug = (api_data.get("hentai_video") or {}).get("slug") or ""
        if video_slug:
            best_url = playwright_get_hanime_stream_url(
                HANIME_VIDEO_URL.format(slug=video_slug)
            )

    if not best_url:
        raise ValueError("No stream URL found in hanime API data")

    return best_url


def get_download_url_from_hanime_tv(api_data):
    """Extract the direct download URL from hanime.tv API data (pixeldrain etc)."""
    dl_url = api_data.get("dl_url") or ""
    if not dl_url:
        return None
    if "pixeldrain.com/d/" in dl_url:
        file_id = dl_url.rstrip("/").split("/")[-1]
        return f"https://pixeldrain.com/api/filesystem/{file_id}"
    return dl_url
