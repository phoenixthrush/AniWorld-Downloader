"""Site search plumbing shared by the web search API and the Discord bot.

Each site's search returns a slightly different shape, this normalises them all
to {title, url} and filters out season/episode links so only series-level hits
come back.
"""

import re

from ..logger import get_logger
from ..models.mangafire_to.series import search_series as query_mangafire
from ..search import (
    query as query_aniworld,
)
from ..search import (
    query_burningseries,
    query_cineby,
    query_filmpalast,
    query_kinox,
    query_megakino,
    query_s_to,
)

logger = get_logger(__name__)

SITE_SEARCH = {
    "aniworld": query_aniworld,
    "sto": query_s_to,
    "megakino": query_megakino,
    "kinox": query_kinox,
    "filmpalast": query_filmpalast,
    "burningseries": query_burningseries,
    "cineby": query_cineby,
    "mangafire": query_mangafire,
}

# aniworld/serienstream return relative `/.../<slug>` links, everything else
# returns an absolute `url`. These two also need series-only filtering.
_RELATIVE_SITES = {
    "aniworld": (
        "https://aniworld.to",
        re.compile(r"^/anime/stream/[a-zA-Z0-9\-]+/?$", re.IGNORECASE),
    ),
    "sto": (
        "https://serienstream.to",
        re.compile(r"^/serie/(stream/)?[a-zA-Z0-9\-]+/?$", re.IGNORECASE),
    ),
}

_ABSOLUTE_BASES = {"mangafire": "https://mangafire.to"}

# Sites checked for a Discord request, in priority order. Kinox and Cineby carry
# both movies and series, so they appear in both lists.
SERIES_SITES = ("sto", "burningseries", "aniworld", "kinox", "cineby")
MOVIE_SITES = ("megakino", "filmpalast", "kinox", "cineby")


def sites_for(media_type):
    return MOVIE_SITES if media_type == "movie" else SERIES_SITES


def _clean_title(value, fallback=""):
    title = value or fallback or "Unknown"
    return title.replace("<em>", "").replace("</em>", "").strip()


def _poster(item):
    for key in ("poster_url", "cover_url", "image", "poster"):
        value = item.get(key)
        if value:
            return value
    return ""


def search(site, keyword):
    """Run one site's search and return normalised [{title, url, poster}]."""
    query = SITE_SEARCH.get(site)
    if not query:
        return []

    try:
        raw = query(keyword) or []
    except Exception as exc:
        logger.warning("Search on %s failed for '%s': %s", site, keyword, exc)
        return []
    if isinstance(raw, dict):
        raw = [raw]

    results = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = _resolve_url(site, item)
        if not url:
            continue
        results.append(
            {
                "title": _clean_title(item.get("title") or item.get("name"), keyword),
                "url": url,
                "poster": _poster(item),
            }
        )
    return results


def _resolve_url(site, item):
    url = item.get("url")
    if url:
        base = _ABSOLUTE_BASES.get(site)
        if base and not url.startswith("http"):
            return base + url
        return url

    link = item.get("link")
    if not link:
        return None
    base, pattern = _RELATIVE_SITES.get(site, (None, None))
    if base is None:
        return link
    # Skip season/episode links, only series pages belong in results
    return base + link if pattern.match(link) else None


def aggregate(title, media_type, per_site=8, limit=25):
    """Search every site of a media type and return combined, site-tagged hits."""
    combined = []
    for site in sites_for(media_type):
        for item in search(site, title)[:per_site]:
            combined.append({**item, "site": site})
            if len(combined) >= limit:
                return combined
    return combined
