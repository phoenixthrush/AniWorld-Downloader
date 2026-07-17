"""Planned releases.

Watch for movies/series that are not out yet. A background pass searches the
chosen site for each waiting item; once a confident title match appears it is
queued for download (and, for series, optionally kept updated via an auto-sync
job). The title matcher is ported from the PlexDownloader scheduler so a loose
first search hit no longer triggers the wrong download.
"""

import re
from datetime import datetime

from ..logger import get_logger
from ..providers import resolve_provider
from ..search import (
    query,
    query_burningseries,
    query_cineby,
    query_filmpalast,
    query_kinox,
    query_megakino,
    query_s_to,
)
from .db import (
    add_autosync_job,
    add_to_queue,
    get_planned_jobs,
    update_planned_job,
)

logger = get_logger(__name__)

# Which search function backs each site.
SITE_SEARCH = {
    "aniworld": query,
    "sto": query_s_to,
    "megakino": query_megakino,
    "kinox": query_kinox,
    "filmpalast": query_filmpalast,
    "burningseries": query_burningseries,
    "cineby": query_cineby,
}

# Sites checked for a request, in priority order. A planned/requested item is
# grabbed from whichever site has it first. Kinox/Cineby appear in both because
# they carry movies and series; a type check disambiguates their hits.
SERIES_SITE_ORDER = ["sto", "burningseries", "aniworld", "kinox", "cineby"]
MOVIE_SITE_ORDER = ["megakino", "filmpalast", "kinox", "cineby"]

# Sites whose search mixes movies and series and therefore need a type check.
_MIXED_SITES = {"kinox", "cineby"}


# aniworld/s.to searches return relative `/…/<slug>` links; the others return
# absolute `url`s. Normalise them all to {title, url} with series-only links.
_SERIES_LINK = {
    "aniworld": ("https://aniworld.to", re.compile(r"^/anime/stream/[^/]+/?$")),
    "sto": ("https://serienstream.to", re.compile(r"^/serie/[^/]+/?$")),
}


def search_site(site, title):
    """Run the search backing `site` and return normalised {title, url} hits."""
    fn = SITE_SEARCH.get(site)
    if not fn:
        return []
    try:
        raw = fn(title) or []
    except Exception as exc:
        logger.debug("Search on %s failed for '%s': %s", site, title, exc)
        return []
    if isinstance(raw, dict):
        raw = [raw]

    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not url:
            link = item.get("link")
            if not link:
                continue
            base, pattern = _SERIES_LINK.get(site, (None, None))
            if base is not None:
                if not pattern.match(link):
                    continue  # skip episode/season links
                url = base + link
            else:
                url = link
        clean = item.get("title") or item.get("name") or title
        clean = clean.replace("<em>", "").replace("</em>", "").strip()
        out.append({"title": clean, "url": url})
    return out


def sites_for(media_type):
    return MOVIE_SITE_ORDER if media_type == "movie" else SERIES_SITE_ORDER


def _matches_type(url, media_type):
    """For mixed sites, confirm a hit is the requested movie/series kind."""
    try:
        series = resolve_provider(url).series_cls(url=url)
        is_movie = bool(getattr(series, "is_movie", False))
    except Exception:
        return True  # can't tell — don't block
    return is_movie if media_type == "movie" else not is_movie


def _clean_title(title):
    """Normalise a title for comparison (umlauts, punctuation, case)."""
    text = (title or "").lower()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "&": "and",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(title):
    return [t for t in _clean_title(title).split() if t]


def title_matches(wanted, candidate):
    """True when `candidate` is a confident match for `wanted`."""
    want_clean = _clean_title(wanted)
    cand_clean = _clean_title(candidate)
    if not want_clean or not cand_clean:
        return False

    if want_clean == cand_clean:
        return True
    # One fully contained in the other (e.g. "dune" vs "dune part two")
    if want_clean in cand_clean or cand_clean in want_clean:
        return True

    want_tokens = set(_tokens(wanted))
    cand_tokens = set(_tokens(candidate))
    if not want_tokens:
        return False

    # Every digit token in the wanted title must be present (sequels/parts).
    want_digits = {t for t in want_tokens if t.isdigit()}
    if want_digits and not want_digits.issubset(cand_tokens):
        return False

    overlap = len(want_tokens & cand_tokens) / len(want_tokens)
    return overlap >= 0.7


def _best_match(wanted, results):
    for item in results:
        if title_matches(wanted, item.get("title", "")):
            return item
    return None


def _enqueue_series_once(job, series_url):
    """Queue every episode of a found series a single time.

    Episodes already on disk are skipped by the downloader itself, and
    duplicate queue entries are prevented by the queue's own guards.
    """
    prov = resolve_provider(series_url)
    series = prov.series_cls(url=series_url)
    episodes = []
    for season in series.seasons:
        for episode in season.episodes:
            episodes.append(episode.url)
    if not episodes:
        return False
    add_to_queue(
        title=job["title"],
        series_url=series_url,
        episodes=episodes,
        language=job["language"],
        provider=job["provider"],
        username=job.get("added_by"),
        custom_path_id=job.get("custom_path_id"),
        source="planned",
    )
    return True


def find_available(title, media_type):
    """Search every site of `media_type` and return (site, url) of the first
    confident match, or None when the title isn't available anywhere yet."""
    for site in sites_for(media_type):
        match = _best_match(title, search_site(site, title))
        if not match:
            continue
        url = match["url"]
        if site in _MIXED_SITES and not _matches_type(url, media_type):
            continue
        return site, url
    return None


def check_planned_job(job):
    """Run one availability check for a planned item across all matching sites.

    Returns True when the item was found and handled (its status is updated),
    False when it is still unavailable.
    """
    media_type = job.get("media_type", "movie")
    found = find_available(job["title"], media_type)
    update_planned_job(job["id"], last_check=_now())
    if not found:
        return False

    site, found_url = found
    try:
        if media_type == "movie":
            add_to_queue(
                title=job["title"],
                series_url=found_url,
                episodes=[found_url],
                language=job["language"],
                provider=job["provider"],
                username=job.get("added_by"),
                custom_path_id=job.get("custom_path_id"),
                source="planned",
            )
        else:
            _enqueue_series_once(job, found_url)
            if job.get("auto_sync"):
                try:
                    add_autosync_job(
                        title=job["title"],
                        series_url=found_url,
                        language=job["language"],
                        provider=job["provider"],
                        custom_path_id=job.get("custom_path_id"),
                        added_by=job.get("added_by"),
                    )
                except Exception as exc:
                    logger.info("Planned: auto-sync job already exists: %s", exc)
    except Exception as exc:
        logger.error("Planned: failed to queue '%s': %s", job["title"], exc)
        update_planned_job(job["id"], status="error", found_url=found_url)
        return False

    update_planned_job(job["id"], status="found", found_url=found_url)
    logger.info(
        "Planned item '%s' became available on %s: %s", job["title"], site, found_url
    )
    return True


def run_planned_checks():
    """Check every waiting planned item once."""
    for job in get_planned_jobs():
        if job.get("status") != "waiting":
            continue
        check_planned_job(job)


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
