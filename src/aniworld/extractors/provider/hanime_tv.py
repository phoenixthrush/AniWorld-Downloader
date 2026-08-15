import base64
import json
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import unescape
from urllib.parse import unquote, urljoin, urlparse

import niquests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    from ...config import DEFAULT_USER_AGENT, GLOBAL_SESSION, logger
    from ...playwright.captcha import (
        is_captcha_page,
        playwright_get_hanime_manifest_token,
        solve_captcha,
    )
except ImportError:
    from aniworld.config import DEFAULT_USER_AGENT, GLOBAL_SESSION, logger
    from aniworld.playwright.captcha import (
        is_captcha_page,
        playwright_get_hanime_manifest_token,
        solve_captcha,
    )


HANIME_BASE_URL = "https://hanime.tv"
HANIME_VIDEO_URL = f"{HANIME_BASE_URL}/videos/hentai/{{slug}}"
HANIME_SITEMAP_URL = f"{HANIME_BASE_URL}/sitemap.xml"
HANIME_TRENDING_URL = f"{HANIME_BASE_URL}/browse/trending"

_HANIME_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Referer": f"{HANIME_BASE_URL}/",
    "Accept-Encoding": "gzip, deflate",
}
_HANIME_AES_KEY = bytes.fromhex(
    "5d657a4dcb0bad1c637ff2e221059b10ff17ae39fe855003e846918941f4ebe3"
)
_HANIME_AES_HEADER = bytes.fromhex("6874762d696e7365637572652d7631")
_HANIME_REQUEST_ATTEMPTS = 3
_HANIME_SITEMAP_TTL = 15 * 60
_sitemap_cache = {"expires": 0.0, "slugs": ()}
_sitemap_lock = threading.Lock()


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
    """Turn a video slug into a franchise title."""
    if not slug:
        return ""
    title = re.sub(r"-\d+$", "", slug).replace("-", " ").strip()
    return title.title()


def _slug_to_video_title(slug):
    if not slug:
        return ""
    return slug.replace("-", " ").strip().title()


def _attribute(tag, name):
    match = re.search(
        rf"\b{re.escape(name)}\s*=\s*([\"'])(.*?)\1", tag, re.IGNORECASE | re.DOTALL
    )
    return unescape(match.group(2).strip()) if match else ""


def _meta_content(html, key, attribute="property"):
    for tag in re.findall(r"<meta\b[^>]*>", html, re.IGNORECASE):
        if _attribute(tag, attribute).lower() == key.lower():
            return _attribute(tag, "content")
    return ""


def _extract_video_cards(html):
    """Extract the server-rendered video cards used by hanime.tv pages."""
    cards = []
    seen = set()
    pattern = re.compile(
        r"<a\b(?P<attrs>[^>]*\bhref\s*=\s*([\"'])"
        r"(?P<href>(?:https?://(?:www\.)?hanime\.tv)?/videos/hentai/[^\"']+)"
        r"\2[^>]*)>(?P<body>.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        href = unescape(match.group("href")).split("?", 1)[0].split("#", 1)[0]
        slug = unquote(href.rstrip("/").split("/")[-1])
        if not re.fullmatch(r"[A-Za-z0-9-]+", slug) or slug in seen:
            continue

        body = match.group("body")
        image_tag = _regex_group(r"(<img\b[^>]*>)", body, flags=re.IGNORECASE)
        poster_url = _attribute(image_tag, "src") or _attribute(image_tag, "data-src")
        title = _attribute(image_tag, "alt")
        title = re.sub(r"\s+thumbnail$", "", title, flags=re.IGNORECASE).strip()
        if not title:
            title = _slug_to_video_title(slug)

        cards.append(
            {
                "slug": slug,
                "name": unescape(title),
                "cover_url": poster_url,
                "poster_url": poster_url,
                "tags": [],
            }
        )
        seen.add(slug)
    return cards


def _synopsis_from_page(html):
    """Extract the Synopsis section rendered on the video page."""
    match = re.search(
        r"<h2\b[^>]*>\s*Synopsis\s*</h2>.*?data-expand-content[^>]*>(.*?)</div>",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    return unescape(match.group(1)).strip() if match else ""


def _more_from_section(html):
    match = re.search(
        r"<section\b[^>]*>\s*<h2\b[^>]*>\s*More\s+from\s+([^<]+)</h2>"
        r"(?P<body>.*?)</section>",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return "", ""
    return unescape(match.group(1).strip()), match.group("body")


def _build_synthetic_payload(slug, html):
    title_text = _meta_content(html, "og:title")
    title_match = re.match(r"^Watch\s+(.+?)\s+Hentai Video", title_text, re.IGNORECASE)

    ldjson = {}
    for raw in re.findall(
        r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            parsed = json.loads(unescape(raw.strip()))
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict) and parsed.get("@type") == "VideoObject":
            ldjson = parsed
            break

    video_title = (
        ldjson.get("name")
        or (title_match.group(1).strip() if title_match else "")
        or _slug_to_video_title(slug)
    )
    description = (
        _synopsis_from_page(html)
        or ldjson.get("description")
        or _meta_content(html, "og:description")
        or ""
    )
    poster_url = ldjson.get("thumbnailUrl") or _meta_content(html, "og:image") or ""

    upload_date = ldjson.get("uploadDate") or ""
    upload_dt = _parse_iso_datetime(upload_date)

    brand_link_match = re.search(
        r"<a\b[^>]*href=[\"'](/(?:browse/)?brands/[^\"']+)[\"'][^>]*>"
        r".*?<strong\b[^>]*>([^<]+)</strong>",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    brand_name = unescape(brand_link_match.group(2).strip()) if brand_link_match else ""
    brand_slug = (
        brand_link_match.group(1).rstrip("/").split("/")[-1] if brand_link_match else ""
    )

    tag_texts = [
        unescape(match.group(1).strip())
        for match in re.finditer(
            r"<a\b[^>]*href=[\"']/(?:browse/)?tags/[^\"']+[\"'][^>]*>([^<]+)</a>",
            html,
            re.IGNORECASE | re.DOTALL,
        )
    ]
    tags = _dedupe_preserve_order([tag for tag in tag_texts if tag])

    franchise_title, section_html = _more_from_section(html)
    related_cards = _extract_video_cards(section_html) if section_html else []
    episode_names = {item["slug"]: item["name"] for item in related_cards}
    episode_names[slug] = video_title
    episode_slugs = sorted(episode_names, key=_episode_sort_key)

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
            {"slug": item_slug, "name": episode_names[item_slug]}
            for item_slug in episode_slugs
        ],
        "brand": {
            "id": None,
            "slug": brand_slug,
            "title": brand_name,
        },
        "tags": tag_objects,
        "videos_manifest": {},
    }


def _request_hanime(url, *, timeout=20):
    last_error = None
    challenged = False
    for attempt in range(_HANIME_REQUEST_ATTEMPTS):
        try:
            headers = {
                **_HANIME_HEADERS,
                "User-Agent": GLOBAL_SESSION.headers.get(
                    "User-Agent", DEFAULT_USER_AGENT
                ),
            }
            response = GLOBAL_SESSION.get(url, headers=headers, timeout=timeout)
            response.encoding = "utf-8"
            body = response.text or ""
            if not challenged and is_captcha_page(body, response.status_code):
                challenged = True
                solve_captcha(url)
                continue
            response.raise_for_status()
            return response
        except Exception as exc:
            last_error = exc
            if attempt < _HANIME_REQUEST_ATTEMPTS - 1:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"Hanime request failed for {url}: {last_error}") from last_error


def fetch_hanime_api_data(slug):
    """Build model data exclusively from the public hanime.tv video page."""
    page_url = HANIME_VIDEO_URL.format(slug=slug)
    logger.debug(f"scraping hanime page ({page_url})...")
    return _build_synthetic_payload(slug, _request_hanime(page_url).text)


def _decode_urlsafe_base64(value):
    if isinstance(value, str):
        value = value.encode("ascii")
    return base64.urlsafe_b64decode(value + b"=" * (-len(value) % 4))


def _parse_hanime_manifest_token(token):
    """Decrypt the official handshake token returned by auth.hanime.tv."""
    try:
        envelope = json.loads(_decode_urlsafe_base64(token))
        ciphertext_and_tag = _decode_urlsafe_base64(
            envelope["data"]
        ) + _decode_urlsafe_base64(envelope["tag"])
        plaintext = AESGCM(_HANIME_AES_KEY).decrypt(
            _decode_urlsafe_base64(envelope["iv"]),
            ciphertext_and_tag,
            _HANIME_AES_HEADER,
        )
        manifest = json.loads(plaintext)
    except Exception as exc:
        raise ValueError("Invalid Hanime handshake token") from exc

    if not isinstance(manifest, dict) or not isinstance(manifest.get("sources"), list):
        raise TypeError("Hanime handshake did not contain video sources")
    return manifest


def fetch_hanime_manifest(slug):
    """Resolve a fresh stream manifest through Hanime's own web player."""
    page_url = HANIME_VIDEO_URL.format(slug=slug)
    try:
        token = playwright_get_hanime_manifest_token(page_url, timeout=15)
        if not token:
            raise TimeoutError("Hanime handshake returned no X-Token")
        return _parse_hanime_manifest_token(token)
    except Exception as exc:
        raise RuntimeError(f"Hanime stream handshake failed: {exc}") from exc


def _manifest_sources(manifest):
    sources = list(manifest.get("sources") or [])
    for server in manifest.get("servers") or []:
        sources.extend(server.get("streams") or [])
    return sources


def get_direct_link_from_hanime_tv(api_data, refresh=False):
    """Return the highest-quality non-premium URL from Hanime's manifest."""
    manifest = api_data.get("videos_manifest") or {}
    if refresh or not _manifest_sources(manifest):
        video_slug = (api_data.get("hentai_video") or {}).get("slug") or ""
        if not video_slug:
            raise ValueError("Hanime video slug is missing")
        manifest = fetch_hanime_manifest(video_slug)
        api_data["videos_manifest"] = manifest

    candidates = []
    for source in _manifest_sources(manifest):
        if source.get("kind", "normal") != "normal":
            continue
        source_url = source.get("src") or source.get("signed_url") or source.get("url")
        if not source_url:
            continue
        try:
            height = int(source.get("height") or 0)
        except (TypeError, ValueError):
            height = 0
        candidates.append((height, urljoin(HANIME_BASE_URL, source_url)))

    if not candidates:
        raise ValueError("No normal stream URL found in Hanime manifest")
    return max(candidates, key=lambda item: item[0])[1]


def get_download_url_from_hanime_tv(api_data):
    """Hanime-only mode deliberately does not use third-party file mirrors."""
    return


def _parse_sitemap_slugs(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError("Invalid Hanime sitemap") from exc

    slugs = []
    for element in root.findall(".//{*}loc"):
        value = (element.text or "").strip()
        parsed = urlparse(value)
        prefix = "/videos/hentai/"
        if parsed.netloc.lower() not in ("hanime.tv", "www.hanime.tv"):
            continue
        if not parsed.path.startswith(prefix):
            continue
        slug = unquote(parsed.path[len(prefix) :].strip("/"))
        if re.fullmatch(r"[A-Za-z0-9-]+", slug):
            slugs.append(slug)
    return tuple(_dedupe_preserve_order(slugs))


def _get_sitemap_slugs():
    now = time.monotonic()
    with _sitemap_lock:
        if _sitemap_cache["slugs"] and now < _sitemap_cache["expires"]:
            return _sitemap_cache["slugs"]

    slugs = _parse_sitemap_slugs(_request_hanime(HANIME_SITEMAP_URL).text)
    with _sitemap_lock:
        _sitemap_cache["slugs"] = slugs
        _sitemap_cache["expires"] = time.monotonic() + _HANIME_SITEMAP_TTL
    return slugs


def _normalize_search_text(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _rank_hanime_slugs(slugs, keyword, limit=24):
    query = _normalize_search_text(keyword)
    if not query:
        return []
    tokens = query.split()
    ranked = []
    for slug in slugs:
        text = _normalize_search_text(slug)
        franchise = re.sub(r"\s+\d+$", "", text)
        if not all(token in text for token in tokens):
            continue
        score = (
            0 if franchise == query else 1,
            0 if franchise.startswith(query) else 1,
            0 if query in franchise else 1,
            sum(text.find(token) for token in tokens),
            abs(len(franchise) - len(query)),
            text,
        )
        ranked.append((score, slug))
    ranked.sort(key=lambda item: item[0])

    results = []
    seen_franchises = set()
    for _, slug in ranked:
        franchise_key = re.sub(r"-\d+$", "", slug)
        if franchise_key in seen_franchises:
            continue
        seen_franchises.add(franchise_key)
        results.append(slug)
        if len(results) >= limit:
            break
    return results


def search_hanime(keyword, limit=24):
    """Search Hanime without a third-party API, using hanime.tv's sitemap."""
    slugs = _rank_hanime_slugs(_get_sitemap_slugs(), keyword, limit=limit)

    def _result(slug):
        fallback = {
            "slug": slug,
            "name": _slug_to_video_title(slug),
            "cover_url": "",
            "poster_url": "",
            "tags": [],
        }
        try:
            # Search must stay responsive even if an individual video page is
            # temporarily slow. Unlike regular model fetches this enrichment is
            # optional, so use one short request and retain the slug fallback.
            response = niquests.get(
                HANIME_VIDEO_URL.format(slug=slug),
                headers=_HANIME_HEADERS,
                timeout=4,
            )
            response.raise_for_status()
            payload = _build_synthetic_payload(slug, response.text)
            video = payload.get("hentai_video") or {}
            fallback.update(
                name=video.get("name") or fallback["name"],
                cover_url=video.get("cover_url") or "",
                poster_url=video.get("poster_url") or "",
                tags=[
                    tag.get("text")
                    for tag in video.get("hentai_tags") or []
                    if isinstance(tag, dict) and tag.get("text")
                ],
            )
        except Exception as exc:
            logger.debug(f"Could not enrich Hanime search result {slug}: {exc}")
        return fallback

    if not slugs:
        return []
    workers = min(12, len(slugs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_result, slugs))


def fetch_hanime_trending(limit=24):
    """Read trending cards directly from Hanime's server-rendered page."""
    return _extract_video_cards(_request_hanime(HANIME_TRENDING_URL).text)[:limit]
