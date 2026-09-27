"""Site search plumbing shared by the web search API and the Discord bot.

Each site's search returns a slightly different shape, this normalises them all
to {title, url} and filters out season/episode links so only series-level hits
come back.
"""

import re

from ..extractors.provider.hanime_tv import fetch_hanime_genres, search_hanime
from ..logger import get_logger
from ..models.mangafire_to.series import fetch_mangafire_genres
from ..models.mangafire_to.series import search_series as query_mangafire
from ..search import (
    query as query_aniworld,
)
from ..search import (
    fetch_burningseries_genres,
    fetch_filmo_genres,
    fetch_filmpalast_genres,
    fetch_genres as fetch_aniworld_genres,
    fetch_kinox_genres,
    fetch_megakino_genres,
    fetch_s_to_genres,
    query_burningseries,
    query_cineby,
    query_filmo,
    query_filmpalast,
    query_kinox,
    query_megakino,
    query_moflix,
    query_s_to,
)

logger = get_logger(__name__)

SITE_SEARCH = {
    "moflix": query_moflix,
    "aniworld": query_aniworld,
    "sto": query_s_to,
    "megakino": query_megakino,
    "kinox": query_kinox,
    "filmpalast": query_filmpalast,
    "filmo": query_filmo,
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

# hanime results are identified by a slug instead of a link of any kind.
_SLUG_URLS = {"htv": "https://hanime.tv/videos/hentai/{slug}"}

# Sites checked for a Discord request, in priority order. Kinox and Cineby carry
# both movies and series, so they appear in both lists.
SERIES_SITES = ("sto", "burningseries", "aniworld", "kinox", "cineby", "moflix")
MOVIE_SITES = ("megakino", "cineby", "filmpalast", "filmo", "kinox", "moflix")


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


def _normalise(site, raw, fallback=""):
    """Turn one site's raw hits into [{title, url, poster}], dropping the rest."""
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
                "title": _clean_title(item.get("title") or item.get("name"), fallback),
                "url": url,
                "poster": _poster(item),
            }
        )
    return results


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
    return _normalise(site, raw, keyword)


def _resolve_url(site, item):
    slug_url = _SLUG_URLS.get(site)
    if slug_url and item.get("slug"):
        return slug_url.format(slug=item["slug"])

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


def _hanime_genres():
    """hanime browses by plain tag names, so the label is also the slug."""
    return [{"name": tag, "slug": tag} for tag in fetch_hanime_genres()]


def _mangafire_genres():
    """MangaFire filters by the numeric genre ID its own filters are built on."""
    return [
        {"name": item["name"], "slug": str(item["id"])}
        for item in fetch_mangafire_genres()
    ]


# Every site whose genre listing the Web UI can offer. Cineby and Moflix have no
# genre pages of their own, so they are simply absent.
GENRE_LISTS = {
    "aniworld": fetch_aniworld_genres,
    "sto": fetch_s_to_genres,
    "burningseries": fetch_burningseries_genres,
    "megakino": fetch_megakino_genres,
    "kinox": fetch_kinox_genres,
    "filmpalast": fetch_filmpalast_genres,
    "filmo": fetch_filmo_genres,
    "htv": _hanime_genres,
    "mangafire": _mangafire_genres,
}

GENRE_SITES = tuple(GENRE_LISTS)

# AniWorld is missing here on purpose: the site pages its own genre listing, so
# it goes through fetch_genre_animes(). Everything else returns one flat list
# that limit cuts off, and the caller slices it into pages.
GENRE_QUERIES = {
    "sto": lambda genre, limit: query_s_to(genre=genre, limit=limit),
    "burningseries": lambda genre, limit: query_burningseries(genre=genre, limit=limit),
    "megakino": lambda genre, limit: query_megakino(genre=genre, limit=limit),
    "kinox": lambda genre, limit: query_kinox(genre=genre, limit=limit),
    "filmpalast": lambda genre, limit: query_filmpalast(genre=genre, limit=limit),
    "filmo": lambda genre, limit: query_filmo(genre_id=genre, limit=limit),
    "htv": lambda genre, limit: search_hanime(genre=genre, limit=limit),
    "mangafire": lambda genre, limit: query_mangafire(genre=genre, limit=limit),
}


def genres(site):
    """The genre chips for a site, as [{name, slug}]."""
    fetch = GENRE_LISTS.get(site)
    return fetch() if fetch else []


def genre_results(site, genre, limit):
    """Browse one site's genre, normalised like a search result.

    Returns (results, has_more). The flag counts the site's own hits, before
    normalising drops the ones the app cannot open afterwards: serienstream
    lists the odd title under a slug no provider pattern accepts, and a single
    one of those would otherwise read as the end of the listing.

    Failures propagate on purpose: an empty genre is worth telling apart from a
    site that would not answer, which a browse row cannot do.
    """
    query = GENRE_QUERIES.get(site)
    if not query:
        return [], False
    raw = query(genre, limit) or []
    if isinstance(raw, dict):
        raw = [raw]
    return _normalise(site, raw), len(raw) >= limit


def aggregate(title, media_type, per_site=8, limit=25):
    """Search every site of a media type and return combined, site-tagged hits."""
    combined = []
    for site in sites_for(media_type):
        for item in search(site, title)[:per_site]:
            combined.append({**item, "site": site})
            if len(combined) >= limit:
                return combined
    return combined
