"""Search, browse and the series/season/episode endpoints."""

import re
import time

from flask import Response, jsonify, request

from ...config import DEFAULT_USER_AGENT, GLOBAL_SESSION
from ...extractors.provider.hanime_tv import fetch_hanime_trending
from ...logger import get_logger
from ...models.mangafire_to.series import _get as get_mangafire
from ...providers import resolve_provider
from ...search import (
    fetch_burningseries_series,
    fetch_cineby_movies,
    fetch_filmpalast_movies,
    fetch_genre_animes,
    fetch_genres,
    fetch_kinox_movies,
    fetch_new_animes,
    fetch_new_series,
    fetch_popular_animes,
    fetch_popular_movies,
    fetch_popular_series,
    random_anime,
)
from .. import media, sitesearch
from ..settings_store import english_sub_disabled

logger = get_logger(__name__)

# Browse rows change slowly, so cache them for an hour per process.
BROWSE_TTL = 3600
_browse_cache = {}

# Sites that list one movie per page instead of seasons.
SINGLE_PAGE_SITES = ("MegaKino", "FilmPalast")

# These resolve their stream per episode, so the language is read once at the
# season level instead of probing every episode.
SEASON_LEVEL_LANGUAGE_SITES = ("Kinox", "BurningSeries", "Cineby")


def register(bp):
    bp.add_url_rule("/search", view_func=search, methods=["POST"])
    bp.add_url_rule("/series", view_func=series)
    bp.add_url_rule("/seasons", view_func=seasons)
    bp.add_url_rule("/episodes", view_func=episodes)
    bp.add_url_rule("/providers", view_func=providers)
    bp.add_url_rule("/random", view_func=random_title)
    bp.add_url_rule("/proxy-image", view_func=proxy_image)
    bp.add_url_rule("/downloaded-folders", view_func=downloaded_folders)
    bp.add_url_rule("/genres", view_func=genres)
    bp.add_url_rule("/genre", view_func=genre)
    for path, key, fetch in _BROWSE_ROWS:
        bp.add_url_rule(
            path,
            endpoint=f"browse_{key}",
            view_func=_make_browse_view(key, fetch),
        )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def search():
    data = request.get_json(silent=True) or {}
    keyword = (data.get("keyword") or "").strip()
    site = (data.get("site") or "aniworld").strip()
    if not keyword:
        return jsonify({"error": "keyword is required"}), 400

    if site == "htv":
        results = _search_hanime(keyword)
    else:
        results = [
            {
                "title": item["title"],
                "url": item["url"],
                "poster_url": media.proxy_image(item["poster"]),
            }
            for item in sitesearch.search(site, keyword)
        ]
    return jsonify({"results": results})


def _search_hanime(keyword):
    """hanime groups sequels under one slug family, show one card per franchise."""
    from ...extractors.provider.hanime_tv import search_hanime

    try:
        hits = search_hanime(keyword) or []
    except Exception as exc:
        logger.warning("HTV search failed: %s", exc)
        return []

    results = []
    seen = set()
    for hit in hits:
        slug = hit.get("slug", "")
        if not slug:
            continue
        franchise = re.sub(r"-\d+$", "", slug)
        if franchise in seen:
            continue
        seen.add(franchise)
        results.append(
            {
                "title": re.sub(r"\s+\d+$", "", hit.get("name", "")).strip(),
                "url": f"https://hanime.tv/videos/hentai/{slug}",
                "poster_url": media.proxy_image(
                    hit.get("cover_url") or hit.get("poster_url") or ""
                ),
            }
        )
    return results


# ---------------------------------------------------------------------------
# Series / seasons / episodes
# ---------------------------------------------------------------------------
def _requested_url():
    url = request.args.get("url", "").strip()
    return url or None


def _hanime_fallback_title(url):
    slug = url.rstrip("/").split("/")[-1]
    title = re.sub(r"-\d+$", "", slug).replace("-", " ").strip()
    return title.title() if title else slug


def series():
    url = _requested_url()
    if not url:
        return jsonify({"error": "url is required"}), 400

    provider = None
    try:
        provider = resolve_provider(url)
        found = provider.series_cls(url=url)
        return jsonify(
            {
                "title": found.title,
                "poster_url": media.proxy_image(
                    media.absolute_poster(getattr(found, "poster_url", ""), url)
                ),
                "description": getattr(found, "description", ""),
                "genres": getattr(found, "genres", []),
                "release_year": getattr(found, "release_year", ""),
            }
        )
    except Exception as exc:
        # hanime pages often fail to parse; a title from the slug still works
        if provider is not None and provider.name == "HanimeTV":
            logger.warning("Hanime series fallback for %s: %s", url, exc)
            return jsonify(
                {
                    "title": _hanime_fallback_title(url),
                    "poster_url": "",
                    "description": "",
                    "genres": [],
                    "release_year": "",
                }
            )
        logger.exception("Series fetch failed")
        return jsonify({"error": str(exc)}), 500


def seasons():
    url = _requested_url()
    if not url:
        return jsonify({"error": "url is required"}), 400

    provider = None
    try:
        provider = resolve_provider(url)
        if provider.name in SINGLE_PAGE_SITES:
            return jsonify({"seasons": _single_page_seasons(provider, url)})

        found = provider.series_cls(url=url)
        # burning-series has no per-season count on the series page, reading it
        # here would fetch every season up front. The count fills in when a
        # season is expanded instead.
        defer_counts = provider.name == "BurningSeries"
        return jsonify(
            {
                "seasons": [
                    {
                        "url": season.url,
                        "season_number": season.season_number,
                        "episode_count": None if defer_counts else season.episode_count,
                        "are_movies": getattr(season, "are_movies", False),
                        "chapter_type": getattr(season, "chapter_type", ""),
                    }
                    for season in found.seasons
                ]
            }
        )
    except Exception as exc:
        if provider is not None and provider.name == "HanimeTV":
            logger.warning("Hanime seasons fallback for %s: %s", url, exc)
            return jsonify({"seasons": []})
        logger.exception("Seasons fetch failed")
        return jsonify({"error": str(exc)}), 500


def _single_page_seasons(provider, url):
    """MegaKino serials list every episode on one page, surface them as one season."""
    if provider.name == "MegaKino" and "/serials/" in url.lower():
        try:
            episode = provider.episode_cls(url=url)
            if episode.is_series:
                return [
                    {
                        "url": url,
                        "season_number": 1,
                        "episode_count": len(episode.series_episodes),
                        "are_movies": False,
                    }
                ]
        except Exception as exc:
            logger.warning("MegaKino series detection failed: %s", exc)

    return [{"url": url, "season_number": 1, "episode_count": 1, "are_movies": True}]


def episodes():
    url = _requested_url()
    if not url:
        return jsonify({"error": "url is required"}), 400

    series_url = request.args.get("series_url", "").strip() or None
    provider = None
    try:
        provider = resolve_provider(url)
        if provider.name in SINGLE_PAGE_SITES:
            return jsonify({"episodes": _single_page_episodes(provider, url)})
        if provider.name == "MangaFire":
            return jsonify({"episodes": _mangafire_pages(provider, url, series_url)})
        return jsonify({"episodes": _season_episodes(provider, url, series_url)})
    except Exception as exc:
        if provider is not None and provider.name == "HanimeTV":
            logger.warning("Hanime episodes fallback for %s: %s", url, exc)
            return jsonify({"episodes": []})
        logger.exception("Episodes fetch failed")
        return jsonify({"error": str(exc)}), 500


def _single_page_episodes(provider, url):
    episode = provider.episode_cls(url=url, selected_language="German Dub")

    if provider.name == "MegaKino" and episode.is_series:
        return [
            {
                "url": f"{url}#mkep={entry['number']}",
                "episode_number": entry["number"],
                "title_de": "",
                "title_en": entry["label"] or f"Episode {entry['number']}",
                "downloaded": False,
                "available_languages": ["German Dub"] if entry["providers"] else [],
            }
            for entry in episode.series_episodes
        ]

    try:
        languages = media.language_labels(episode.provider_data)
    except Exception as exc:
        logger.warning("%s language detection failed: %s", provider.name, exc)
        languages = ["German Dub"]

    return [
        {
            "url": url,
            "episode_number": 1,
            "title_de": "",
            "title_en": getattr(episode, "title_cleaned", None)
            or getattr(episode, "title", ""),
            "downloaded": False,
            "available_languages": languages,
        }
    ]


def _resolve_series(provider, url, series_url):
    """Build the series a season belongs to, so the season model has its context."""
    if provider.name == "HanimeTV":
        return provider.series_cls(url=series_url or url)

    if series_url is None:
        # serienstream's own season->series fallback splits on "-" and breaks,
        # so derive the series URL here instead.
        series_url = re.sub(r"/staffel-\d+/?$", "", url)
        series_url = re.sub(r"/filme/?$", "", series_url)
    try:
        return provider.series_cls(url=series_url)
    except Exception:
        return None


def _season_episodes(provider, url, series_url):
    found = _resolve_series(provider, url, series_url)

    if provider.name == "HanimeTV":
        if not found or not found.seasons:
            return []
        season = found.seasons[0]
    else:
        season = provider.season_cls(url=url, series=found)

    downloaded = media.downloaded_episodes(found) if found else set()

    season_languages = None
    if provider.name in SEASON_LEVEL_LANGUAGE_SITES:
        try:
            season_languages = list(getattr(season, "language_labels", []) or [])
        except Exception as exc:
            logger.warning("%s language detection failed: %s", provider.name, exc)
            season_languages = ["German Dub"]

    results = []
    for episode in season.episodes:
        if season_languages is not None:
            languages = season_languages
        else:
            languages = media.language_labels(episode.provider_data)
        if provider.name == "HanimeTV" and not languages:
            languages = ["Japanese"]

        results.append(
            {
                "url": episode.url,
                "episode_number": episode.episode_number,
                "title_de": getattr(episode, "title_de", ""),
                "title_en": getattr(episode, "title_en", ""),
                "downloaded": (episode.season.season_number, episode.episode_number)
                in downloaded,
                "available_languages": languages,
                "page_count": 0,
            }
        )
    return results


def _mangafire_pages(provider, url, series_url):
    """A MangaFire "season" is a chapter and its episodes are the pages."""
    from .. import paths

    found = _resolve_series(provider, url, series_url or url)
    chapter = provider.season_cls(url=url, series=found)

    title = (
        getattr(found, "title_cleaned", None) or getattr(found, "title", "") or ""
    ).lower()
    bases = [base for base in paths.scan_bases() if base.is_dir()]

    def on_disk(page):
        if not title:
            return False
        for base in bases:
            try:
                entries = list(base.iterdir())
            except OSError:
                continue
            for folder in entries:
                if not folder.is_dir() or not folder.name.lower().startswith(title):
                    continue
                if (folder / chapter.folder_name / page.file_name).exists():
                    return True
        return False

    try:
        pages = list(getattr(chapter, "pages", []) or [])
    except Exception:
        pages = []

    return [
        {
            "url": chapter.url,
            "chapter_url": chapter.url,
            "episode_number": page.page_number,
            "page_number": page.page_number,
            "page_count": len(pages),
            "title_de": f"Page {page.page_number}",
            "title_en": f"Page {page.page_number}",
            "downloaded": on_disk(page),
            "available_languages": ["English Dub"],
        }
        for page in pages
    ]


def providers():
    url = _requested_url()
    if not url:
        return jsonify({"error": "url is required"}), 400

    try:
        provider = resolve_provider(url)
        if provider.name == "MangaFire":
            return jsonify({"providers": {}})
        if provider.name == "Cineby":
            return jsonify({"providers": _cineby_providers(provider, url)})

        kwargs = {"url": url}
        if provider.name == "MegaKino":
            kwargs["selected_language"] = "German Dub"
        episode = provider.episode_cls(**kwargs)
        return jsonify(
            {
                "providers": media.provider_map(
                    episode.provider_data, drop_english_sub=english_sub_disabled()
                )
            }
        )
    except Exception as exc:
        logger.exception("Providers fetch failed")
        return jsonify({"error": str(exc)}), 500


def _cineby_providers(provider, url):
    """Cineby has one implicit hoster, but German audio only for some titles."""
    labels = ["English Dub"]
    try:
        episode = provider.episode_cls(url=url)
        labels = list(episode.available_language_labels) or labels
    except Exception as exc:
        logger.warning("Cineby language detection failed: %s", exc)
    return {label: ["Cineby"] for label in labels}


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
def random_title():
    if request.args.get("site", "aniworld").strip() == "sto":
        return jsonify({"error": "Random is not available for serienstream.to"}), 400
    url = random_anime()
    if url:
        return jsonify({"url": url})
    return jsonify({"error": "Failed to fetch random anime"}), 500


def proxy_image():
    target = request.args.get("url", "").strip()
    if not target.startswith(("http://", "https://")):
        return "", 400
    try:
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        if "hanime" in target:
            headers["Referer"] = "https://hanime.tv/"
        response = GLOBAL_SESSION.get(target, headers=headers, timeout=10)
        response.raise_for_status()
        return Response(
            response.content,
            content_type=response.headers.get("Content-Type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as exc:
        logger.warning("Image proxy failed for %s: %s", target, exc)
        return "", 502


def downloaded_folders():
    return jsonify({"folders": media.downloaded_folder_names()})


# ---------------------------------------------------------------------------
# Genres
# ---------------------------------------------------------------------------
def genres():
    """The aniworld genre list for the discover row."""
    results = _cached("genres", fetch_genres)
    if not results:
        return jsonify({"error": "Failed to fetch genres"}), 500
    return jsonify({"genres": results})


def genre():
    """One page of a genre listing, 30 animes per page."""
    slug = (request.args.get("slug") or "").strip()
    known = {item["slug"] for item in _cached("genres", fetch_genres) or ()}
    if slug not in known:
        return jsonify({"error": "Unknown genre"}), 404

    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        return jsonify({"error": "page must be a number"}), 400

    data = _cached(f"genre:{slug}:{page}", lambda: fetch_genre_animes(slug, page))
    if data is None:
        return jsonify({"error": f"Failed to fetch genre {slug}"}), 500

    return jsonify(
        {
            "results": [
                {**item, "poster_url": media.proxy_image(item.get("poster_url", ""))}
                for item in data["results"]
            ],
            "has_more": data["has_more"],
            "page": page,
        }
    )


# ---------------------------------------------------------------------------
# Browse rows
# ---------------------------------------------------------------------------
def _fetch_hanime_trending():
    """Trending hanime, one card per franchise."""
    try:
        hits = fetch_hanime_trending() or []
    except Exception as exc:
        logger.warning("HTV trending fetch failed: %s", exc)
        return None

    results = []
    seen = set()
    for hit in hits:
        slug, title = hit.get("slug", ""), hit.get("name", "")
        if not slug or not title:
            continue
        franchise = re.sub(r"-\d+$", "", slug)
        if franchise in seen:
            continue
        seen.add(franchise)
        results.append(
            {
                "title": title,
                "url": f"https://hanime.tv/videos/hentai/{slug}",
                "poster_url": hit.get("cover_url") or hit.get("poster_url") or "",
                "genre": ", ".join(hit.get("tags", [])[:3]),
            }
        )
    return results


def _fetch_mangafire_trending():
    response = get_mangafire("https://mangafire.to/api/top-titles", timeout=20)
    items = (response.json() or {}).get("items", [])
    return [_mangafire_card(item) for item in items if isinstance(item, dict)]


def _mangafire_card(item):
    url = item.get("url", "") or ""
    if url and not url.startswith("http"):
        url = f"https://mangafire.to{url}"

    genres = [
        entry.get("title", "")
        for entry in (item.get("genres") or [])
        if isinstance(entry, dict) and entry.get("title")
    ]
    subtitle = ", ".join(genres)
    if not subtitle:
        status = item.get("status", "")
        year = item.get("year")
        parts = [
            part
            for part in (status.title() if status else "", str(year) if year else "")
            if part
        ]
        subtitle = " | ".join(parts)

    return {
        "title": item.get("title", "Unknown"),
        "url": url,
        "poster_url": item.get("poster", ""),
        "genre": subtitle,
    }


_BROWSE_ROWS = (
    ("/new-animes", "new_animes", fetch_new_animes),
    ("/popular-animes", "popular_animes", fetch_popular_animes),
    ("/new-series", "new_series", fetch_new_series),
    ("/popular-series", "popular_series", fetch_popular_series),
    ("/popular-movies", "popular_movies", fetch_popular_movies),
    ("/kinox-movies", "kinox_movies", fetch_kinox_movies),
    ("/filmpalast-movies", "filmpalast_movies", fetch_filmpalast_movies),
    ("/burningseries-series", "burningseries_series", fetch_burningseries_series),
    ("/cineby-movies", "cineby_movies", fetch_cineby_movies),
    ("/htv-trending", "htv_trending", _fetch_hanime_trending),
    ("/mangafire-trending", "mangafire_trending", _fetch_mangafire_trending),
)


def _cached(key, fetch):
    now = time.time()
    entry = _browse_cache.get(key)
    if entry and now - entry[0] < BROWSE_TTL:
        return entry[1]
    try:
        results = fetch()
    except Exception as exc:
        logger.warning("Browse fetch '%s' failed: %s", key, exc)
        return None
    if results is not None:
        _browse_cache[key] = (now, results)
    return results


def _make_browse_view(key, fetch):
    def view():
        results = _cached(key, fetch)
        if results is None:
            return jsonify({"error": f"Failed to fetch {key.replace('_', ' ')}"}), 500
        return jsonify(
            {
                "results": [
                    {
                        **item,
                        "poster_url": media.proxy_image(item.get("poster_url", "")),
                    }
                    for item in results
                ]
            }
        )

    view.__name__ = f"browse_{key}"
    return view
