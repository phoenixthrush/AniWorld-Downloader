import json
import re
from datetime import datetime, timezone

import niquests

try:
    from ...config import DEFAULT_USER_AGENT, logger
    from ...playwright.captcha import playwright_get_hanime_stream_url
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, logger
    from aniworld.playwright.captcha import playwright_get_hanime_stream_url


HANIME_VIDEO_URL = "https://hanime.tv/videos/hentai/{slug}"
_HANIME_HEADERS = {"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://hanime.tv/"}


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


def _build_synthetic_payload(slug, html):
    title_text = _regex_group(
        r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
        html,
    )
    title_match = re.match(r"^Watch\s+(.+?)\s+Hentai Video", title_text, re.IGNORECASE)
    video_title = title_match.group(1).strip() if title_match else _slug_to_title(slug)

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
        r'<a\s+href=["\'](/brands/[^"\']+)["\'][^>]*>.*?<strong[^>]*>([^<]+)</strong>',
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

    video_links = []
    for match in re.finditer(
        r'<a\s+href=["\'](/videos/hentai/[^"\']+)["\']',
        html,
    ):
        href = match.group(1).strip()
        if not href:
            continue
        if href.startswith("/"):
            href = f"https://hanime.tv{href}"
        video_links.append(href)
    episode_urls = _dedupe_preserve_order(video_links)
    episode_slugs = [url.rstrip("/").split("/")[-1] for url in episode_urls]
    episode_slugs = sorted(episode_slugs, key=_episode_sort_key)
    episode_urls = [HANIME_VIDEO_URL.format(slug=s) for s in episode_slugs]
    if slug not in episode_slugs:
        episode_slugs.insert(0, slug)
        episode_urls.insert(0, HANIME_VIDEO_URL.format(slug=slug))

    related_heading = re.search(r"More from\s+([^<]+)</h2>", html, re.IGNORECASE)
    franchise_title = related_heading.group(1).strip() if related_heading else ""
    if not franchise_title:
        franchise_title = re.sub(r"\s*\d+$", "", video_title).strip() or video_title

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
            {"slug": s, "name": _slug_to_title(s)} for s in episode_slugs
        ],
        "brand": {
            "id": None,
            "slug": brand_slug,
            "title": brand_name,
        },
        "tags": tag_objects,
        "videos_manifest": {},
    }


def fetch_hanime_api_data(slug):
    page_url = HANIME_VIDEO_URL.format(slug=slug)
    logger.debug(f"scraping hanime page ({page_url})...")
    resp = niquests.get(page_url, headers=_HANIME_HEADERS, timeout=15)
    resp.raise_for_status()
    return _build_synthetic_payload(slug, resp.text)


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
