from typing import List, Set
import time
from niquests.exceptions import HTTPError
from fake_useragent import UserAgent
import random

try:
    from ..config import GLOBAL_SESSION, logger
    from ..networking import create_pooled_session, get_retry_strategy
except ImportError:
    from aniworld.config import GLOBAL_SESSION, logger
    from aniworld.networking import create_pooled_session, get_retry_strategy

JIKAN_SEARCH_URL = "https://api.jikan.moe/v4/anime"
RATE_LIMIT_DELAY = 1  # Delay between requests in seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # Initial retry delay in seconds

# Lazy user agent generator (initialized on first use)
_ua = None

# Lazy Jikan session with connection pooling (initialized on first use)
_jikan_session = None

# Common referrer patterns for anime/manga sites
REFERRERS = [
    "https://www.google.com/search?q=",
    "https://www.bing.com/search?q=",
    "https://duckduckgo.com/?q=",
    "https://myanimelist.net/",
    "https://anilist.co/",
    "https://www.crunchyroll.com/",
    "https://www.netflix.com/",
]

# Accept-Language variations
ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "de-DE,de;q=0.9,en-US;q=0.8",
    "en-GB,en;q=0.8,de;q=0.6",
    "ja-JP,ja;q=0.9,en;q=0.8",
    "en-US,en;q=0.8,fr;q=0.6",
]


def _get_user_agent():
    """Lazy initialize user agent on first use."""
    global _ua
    if _ua is None:
        _ua = UserAgent()
    return _ua


def _get_jikan_session():
    """
    Lazy initialize Jikan session with optimized connection pooling on first use.
    Uses HTTP connection pooling to reuse connections and improve performance.
    Includes automatic retry strategy for API resilience.
    """
    global _jikan_session
    if _jikan_session is None:
        # Create retry strategy that automatically retries on 429 and 5xx errors
        retry_strategy = get_retry_strategy(
            retries=2,
            backoff_factor=1.0,  # 1s, 2s exponential backoff
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        _jikan_session = create_pooled_session(
            resolver=["doh+google://"],
            pool_connections=10,
            pool_maxsize=20,
            retry_strategy=retry_strategy,
            timeout=30,
        )
    
    return _jikan_session


def get_unique_headers() -> dict:
    """
    Generate unique request headers for each API call.
    Uses random user agents and referrers to avoid rate limiting detection.
    Lazy loads user agent on first call.
    """
    ua = _get_user_agent()
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": random.choice(ACCEPT_LANGUAGES),
        "User-Agent": ua.random,
        "Referer": random.choice(REFERRERS),
        "Sec-Fetch-Site": random.choice(["cross-site", "same-origin", "none"]),
        "Sec-Fetch-Mode": random.choice(["cors", "navigate", "no-cors"]),
        "Sec-Fetch-Dest": random.choice(["empty", "document", "iframe"]),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": random.choice(["1", "null"]),
    }
    return headers


def search_jikan(
    query: str, sfw: bool = False, page: int = 1, limit: int = 10
) -> List[dict]:
    """
    Search for anime using Jikan API v4, filtering by TV type.
    Returns a list of anime dictionaries (only type 'TV').
    Uses unique headers for each request to avoid detection.
    Uses connection pooling for efficiency.
    """
    params = {
        "q": query,
        "type": "tv",
        "sfw": str(sfw).lower(),
        "page": page,
        "limit": limit,
        "order_by": "popularity",
        "sort": "desc",
    }

    headers = get_unique_headers()
    session = _get_jikan_session()

    try:
        res = session.get(JIKAN_SEARCH_URL, params=params, headers=headers)
        res.raise_for_status()
        data = res.json().get("data", [])
        time.sleep(RATE_LIMIT_DELAY)  # Respect rate limits
        # Filter for TV type just in case
        return [anime for anime in data if anime.get("type") == "TV"]
    except Exception as e:
        logger.error(f"Error searching Jikan API for query '{query}': {e}")
        return []


def get_anime_full_by_id(mal_id: int) -> dict:
    """
    Fetch full anime data from Jikan API for a given MAL ID.
    Includes all related entries in one request.
    Implements retry logic with exponential backoff for rate limiting.
    Uses unique headers for each request to avoid detection.
    Uses connection pooling for efficiency.
    """
    url = f"https://api.jikan.moe/v4/anime/{mal_id}/full"
    session = _get_jikan_session()
    
    for attempt in range(MAX_RETRIES):
        try:
            headers = get_unique_headers()
            res = session.get(url, headers=headers)
            res.raise_for_status()
            time.sleep(RATE_LIMIT_DELAY)  # Respect rate limits
            return res.json().get("data", {})
        except HTTPError as e:
            if e.response.status_code == 429:  # Too Many Requests
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Rate limited for MAL ID {mal_id}. Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Max retries exceeded for MAL ID {mal_id}. Skipping.")
                    return {}
            else:
                logger.error(f"Error fetching anime data for MAL ID {mal_id}: {e}")
                return {}
        except Exception as e:
            logger.error(f"Error fetching anime data for MAL ID {mal_id}: {e}")
            return {}


def get_all_related_from_full(mal_id: int) -> List[int]:
    """
    Extract all related MAL IDs from the full anime data.
    Only includes relevant anime types (Sequel, Prequel, Side story, Parent story).
    """
    anime_data = get_anime_full_by_id(mal_id)
    
    if not anime_data:
        return [mal_id]
    
    relations = anime_data.get("relations", [])
    all_ids: Set[int] = {mal_id}

    for rel in relations:
        if rel.get("relation") in {"Sequel", "Prequel", "Parent story", "Side story"}:
            for entry in rel.get("entry", []):
                if entry.get("type") == "anime":
                    all_ids.add(entry["mal_id"])

    return list(all_ids)


def get_all_seasons_by_query(query: str) -> List[int]:
    """
    Return a list of all MAL IDs for all anime seasons related to the query.
    Uses the full endpoint to avoid recursive API calls.
    """
    seasons = search_jikan(query)
    if not seasons:
        logger.warning(f"No TV seasons found for query: {query}")
        return []

    all_ids: Set[int] = set()
    for season in seasons:
        mal_id = season["mal_id"]
        all_ids.update(get_all_related_from_full(mal_id))

    logger.info(f"All season MAL IDs found: {all_ids}")
    return list(all_ids)


if __name__ == "__main__":
    query = "love is war"
    all_seasons = get_all_seasons_by_query(query)
    print(all_seasons)
