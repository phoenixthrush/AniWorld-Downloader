import time

try:
    from ..config import GLOBAL_SESSION, logger
except ImportError:
    from aniworld.config import GLOBAL_SESSION, logger

JIKAN_SEARCH_URL = "https://api.jikan.moe/v4/anime"
JIKAN_ANIME_URL = "https://api.jikan.moe/v4/anime/{id}"
JIKAN_RELATIONS_URL = "https://api.jikan.moe/v4/anime/{id}/relations"

# Rate limiting delay
API_DELAY = 0.8


def search_jikan(query, sfw=False, limit=5):
    """Search Jikan API for TV anime."""
    params = {
        "q": query,
        "type": "tv",
        "sfw": str(sfw).lower(),
        "limit": limit,
        "order_by": "popularity",
        "sort": "asc",  # earliest / most popular first
    }
    # Jikan is a community-run mirror and regularly answers 5xx under load;
    # one retry rescues most lookups.
    for attempt in range(2):
        try:
            logger.debug(
                f"Searching Jikan API URL: {JIKAN_SEARCH_URL} with params: {params}"
            )
            res = GLOBAL_SESSION.get(JIKAN_SEARCH_URL, params=params)
            res.raise_for_status()
            return res.json().get("data", [])
        except Exception as e:
            if attempt == 0:
                logger.debug(f"Jikan search failed ({e}); retrying once...")
                time.sleep(2)
                continue
            logger.error(f"Error searching Jikan API for query '{query}': {e}")
    return []


# Caches to avoid repeated API calls
_type_cache = {}
_relations_cache = {}


def is_tv_series(mal_id):
    """Check if an anime is a TV series using caching."""
    if mal_id in _type_cache:
        return _type_cache[mal_id]

    try:
        logger.debug(f"Fetching anime type for MAL ID: {mal_id}")
        res = GLOBAL_SESSION.get(JIKAN_ANIME_URL.format(id=mal_id))
        res.raise_for_status()
        anime_type = res.json().get("data", {}).get("type")
        is_tv = anime_type == "TV"
        _type_cache[mal_id] = is_tv
        logger.debug(f"Waiting to respect Jikan API rate limits... {API_DELAY}s")
        time.sleep(API_DELAY)
        return is_tv
    except Exception as e:
        logger.error(f"Error checking anime type for MAL ID {mal_id}: {e}")
        _type_cache[mal_id] = False
        return False


def get_anime_relations_cached(mal_id):
    """Get anime relations with caching."""
    if mal_id in _relations_cache:
        return _relations_cache[mal_id]

    try:
        logger.debug(f"Fetching relations for MAL ID: {mal_id}")
        res = GLOBAL_SESSION.get(JIKAN_RELATIONS_URL.format(id=mal_id))
        res.raise_for_status()
        relations = res.json().get("data", [])
        _relations_cache[mal_id] = relations
        logger.debug(f"Waiting to respect Jikan API rate limits... {API_DELAY}s")
        time.sleep(API_DELAY)
        return relations
    except Exception as e:
        logger.error(f"Error fetching relations for MAL ID {mal_id}: {e}")
        _relations_cache[mal_id] = []
        return []


def get_all_related_ids(season1_id):
    """Iteratively fetch all related anime IDs starting from season1_id."""
    collected = set()
    stack = [season1_id]

    while stack:
        mal_id = stack.pop()
        if mal_id in collected:
            continue
        collected.add(mal_id)

        for rel in get_anime_relations_cached(mal_id):
            if rel.get("relation") in {
                "Sequel",
                "Prequel",
                "Parent story",
                "Side story",
            }:
                for entry in rel.get("entry", []):
                    anime_id = entry.get("mal_id")
                    if (
                        anime_id
                        and is_tv_series(anime_id)
                        and anime_id not in collected
                    ):
                        stack.append(anime_id)

    return collected


def get_anime_titles(mal_id):
    """Return the known titles of a MAL anime, most canonical first.

    The romaji "Default" title comes first because scene releases
    (e.g. Erai-raws) name their files after it; English and synonym titles
    follow as search fallbacks.
    """
    try:
        logger.debug(f"Fetching titles for MAL ID: {mal_id}")
        res = GLOBAL_SESSION.get(JIKAN_ANIME_URL.format(id=mal_id))
        res.raise_for_status()
        data = res.json().get("data", {})
        titles = []
        for wanted in ("Default", "English", "Synonym"):
            for entry in data.get("titles", []):
                title = (entry.get("title") or "").strip()
                if entry.get("type") == wanted and title and title not in titles:
                    titles.append(title)
        logger.debug(f"Waiting to respect Jikan API rate limits... {API_DELAY}s")
        time.sleep(API_DELAY)
        return titles
    except Exception as e:
        logger.error(f"Error fetching titles for MAL ID {mal_id}: {e}")
        return []


def get_all_seasons_by_query(query="love is war"):
    """Fetch all seasons starting from Season 1 and follow sequels/prequels."""
    seasons = search_jikan(query)
    if not seasons:
        logger.warning(f"No TV seasons found for query: {query}")
        return []

    # Use the most popular TV series
    season1_id = next((s["mal_id"] for s in seasons if s.get("type") == "TV"), None)
    if not season1_id:
        logger.warning(f"No TV seasons found in search results for query: {query}")
        return []

    all_ids = get_all_related_ids(season1_id)
    logger.debug(f"All related MAL IDs found: {all_ids}")
    return sorted(all_ids)


if __name__ == "__main__":
    print(get_all_seasons_by_query())
