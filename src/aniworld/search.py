import curses
import html as html_module
import os
import random
import re

try:
    from .ascii import display_ascii_art
    from .config import GLOBAL_SESSION, logger
except ImportError:
    from aniworld.ascii import display_ascii_art
    from aniworld.config import GLOBAL_SESSION, logger

SEARCH_URL = "https://aniworld.to/ajax/search"
RANDOM_URL = "https://aniworld.to/ajax/randomGeneratorSeries"
NEW_EPISODES_URL = "https://aniworld.to/neue-episoden"
HOME_URL = "https://aniworld.to"

_homepage_cache = None
_series_html_content = None


def random_anime():
    """Fetch a random anime series from Aniworld and return its URL."""
    data = {"productionStart": "all", "productionEnd": "all", "genres[]": "all"}

    try:
        response = GLOBAL_SESSION.post(RANDOM_URL, data=data)
        response.raise_for_status()
        result = response.json()

        if not result:
            logger.error("Random anime response is empty")
            return None

        # Pick a random anime from the list
        series = random.choice(result)
        link = series.get("link")
        if link:
            return f"https://aniworld.to/anime/stream/{link}"
        else:
            logger.error("No link found in selected random anime")
            return None

    except Exception as e:
        logger.error(f"Failed to fetch random anime: {e}")
        return None


def query(keyword):
    """Send a search request to Aniworld with given keyword."""
    response = GLOBAL_SESSION.post(SEARCH_URL, data={"keyword": keyword})
    try:
        return response.json()  # Returns a list of dicts
    except ValueError:
        return None


def fetch_new_episodes():
    """Fetch the latest episodes from aniworld.to/neue-episoden.

    Returns a deduplicated list of episode dicts (grouped by URL, languages merged),
    or None on error.
    """
    try:
        response = GLOBAL_SESSION.get(NEW_EPISODES_URL)
        response.raise_for_status()
        html = response.text
    except Exception as e:
        logger.error(f"Failed to fetch new episodes: {e}")
        return None

    # Try to narrow scope to the newEpisodeList block
    block_match = re.search(r'class="newEpisodeList">(.*)', html, re.DOTALL)
    search_html = block_match.group(1) if block_match else html

    # Find all episode links with their surrounding context
    episode_pattern = re.compile(
        r'<a\s+href="(/anime/stream/[^"]+/staffel-(\d+)/episode-(\d+))"[^>]*>'
        r"(.*?)</a>"
        r'(.*?(?=<a\s+href="/anime/stream/|$))',
        re.DOTALL,
    )

    seen = {}
    ordered_urls = []

    for m in episode_pattern.finditer(search_html):
        path, season_str, episode_str, inner, after = m.groups()
        url = f"https://aniworld.to{path}"
        season = int(season_str)
        episode = int(episode_str)

        # Extract title from <strong>
        title_match = re.search(r"<strong>(.*?)</strong>", inner)
        title = title_match.group(1).strip() if title_match else ""

        # Extract date from elementFloatRight span or last span
        date_match = re.search(
            r'<span[^>]*class="[^"]*elementFloatRight[^"]*"[^>]*>(.*?)</span>',
            inner,
        )
        date = date_match.group(1).strip() if date_match else ""

        # Extract language from flag image data-src
        context = inner + after
        flag_match = re.search(r'data-src="[^"]*?/(\w[\w-]*)\.svg"', context)
        language = flag_match.group(1) if flag_match else ""

        if url not in seen:
            seen[url] = {
                "title": title,
                "url": url,
                "season": season,
                "episode": episode,
                "date": date,
                "languages": [],
            }
            ordered_urls.append(url)

        if language and language not in seen[url]["languages"]:
            seen[url]["languages"].append(language)

    return [seen[url] for url in ordered_urls]


def _fetch_homepage():
    """Fetch the homepage HTML, using a simple module-level cache."""
    global _homepage_cache
    if _homepage_cache is not None:
        return _homepage_cache

    try:
        response = GLOBAL_SESSION.get(HOME_URL)
        response.raise_for_status()
        _homepage_cache = response.text
        return _homepage_cache
    except Exception as e:
        logger.error(f"Failed to fetch homepage: {e}")
        return None


def _extract_cover_list(html, heading):
    """Extract a list of anime cover items from a homepage section.

    Finds the section identified by the <h2> heading text, then extracts
    coverListItem entries until the next section.
    """
    # Find the heading position
    heading_pattern = re.compile(rf"<h2>\s*{re.escape(heading)}\s*</h2>", re.IGNORECASE)
    heading_match = heading_pattern.search(html)
    if not heading_match:
        logger.warning(f"Homepage section '{heading}' not found")
        return []

    # Slice from heading to the next <h2> or end
    start = heading_match.end()
    next_h2 = re.search(r"<h2>", html[start:])
    section_html = html[start : start + next_h2.start()] if next_h2 else html[start:]

    # Extract items — anchor on /anime/stream/ links with cover structure
    item_pattern = re.compile(
        r'<a\s+href="(/anime/stream/[^"]+)"[^>]*title="([^"]*)"[^>]*>'
        r"(.*?)</a>",
        re.DOTALL,
    )

    results = []
    seen_urls = set()

    for m in item_pattern.finditer(section_html):
        path, link_title, inner = m.groups()
        url = f"https://aniworld.to{path}"

        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Title from <h3> (strip inner tags)
        h3_match = re.search(r"<h3>(.*?)</h3>", inner, re.DOTALL)
        title = (
            re.sub(r"<[^>]+>", "", h3_match.group(1)).strip()
            if h3_match
            else link_title
        )

        # Genre from <small>
        small_match = re.search(r"<small>(.*?)</small>", inner, re.DOTALL)
        genre = (
            re.sub(r"<[^>]+>", "", small_match.group(1)).strip() if small_match else ""
        )

        # Poster from data-src on img
        img_match = re.search(r'data-src="([^"]+)"', inner)
        poster_url = ""
        if img_match:
            poster_path = img_match.group(1)
            poster_url = (
                poster_path
                if poster_path.startswith("http")
                else f"https://aniworld.to{poster_path}"
            )

        results.append(
            {
                "title": title,
                "url": url,
                "genre": genre,
                "poster_url": poster_url,
            }
        )

    return results


def fetch_new_animes():
    """Fetch the 'Neue Animes' section from the homepage.

    Returns a list of anime dicts or None on error.
    """
    html = _fetch_homepage()
    if html is None:
        return None
    return _extract_cover_list(html, "Neue Animes")


def fetch_popular_animes():
    """Fetch the 'Derzeit beliebt' section from the homepage.

    Returns a list of anime dicts or None on error.
    """
    html = _fetch_homepage()
    if html is None:
        return None
    return _extract_cover_list(html, "Derzeit beliebt")


def _fetch_series_homepage():
    """Fetch the s.to popular series page, using a simple module-level cache."""
    global _series_html_content
    if _series_html_content is not None:
        return _series_html_content

    try:
        response = GLOBAL_SESSION.get("https://s.to/beliebte-serien")
        response.raise_for_status()
        _series_html_content = response.text
        return _series_html_content
    except Exception as e:
        logger.error(f"Failed to fetch s.to popular series page: {e}")
        return None


def _extract_series_cards(section_html):
    """Extract series cards from an s.to HTML section.

    Parses <a> tags linking to /serie/ paths and extracts title from the
    <img> alt attribute and poster from src/data-src. Deduplicates by slug.
    """
    results = []
    seen_slugs = set()

    # Match <a> tags with /serie/ hrefs — deliberately loose on class to
    # survive class-name changes; we only require the href pattern.
    link_pattern = re.compile(
        r'<a\s[^>]*href="(/serie/[^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    for m in link_pattern.finditer(section_html):
        path, inner = m.groups()

        # Normalise to the base series slug (strip /staffel-N etc.)
        parts = path.strip("/").split("/")
        # Expected: ["serie", "slug"] or ["serie", "slug", "staffel-8"]
        if len(parts) < 2:
            continue
        series_slug = parts[1]

        if series_slug in seen_slugs:
            continue
        seen_slugs.add(series_slug)

        url = f"https://s.to/serie/{series_slug}"

        # --- Title: try img alt, then link title attr, then alt on any tag ---
        title = ""
        for pat in [
            r'<img[^>]+\balt="([^"]+)"',
            r'\btitle="([^"]+)"',
        ]:
            t = re.search(pat, inner)
            if t:
                title = html_module.unescape(t.group(1).strip())
                break

        # --- Poster: try data-src first (lazy-loaded real URL), then src ---
        poster_url = ""
        for pat in [
            r'<img[^>]+\bdata-src="(/[^"]+)"',
            r'<img[^>]+\bsrc="(/[^"]+)"',
            r'<img[^>]+\bsrc="(https?://[^"]+)"',
        ]:
            p = re.search(pat, inner)
            if p:
                raw = p.group(1).strip()
                poster_url = (
                    raw if raw.startswith("http") else f"http://186.2.175.5{raw}"
                )
                break

        if title or poster_url:
            results.append(
                {
                    "title": title,
                    "url": url,
                    "genre": "",
                    "poster_url": poster_url,
                }
            )

    return results


def _find_series_section(full_html, heading_hints, fallback_index):
    """Locate an s.to section and extract its series cards.

    Tries to find the section by heading text patterns first (resilient to
    surrounding markup changes), then falls back to the Nth mb-5 div by
    positional index.
    """
    section_html = None

    # strat 1: find by heading text inside an <h2> (avoids meta tags)
    for hint in heading_hints:
        h2_pattern = re.compile(r"<h2[^>]*>[^<]*" + hint, re.IGNORECASE | re.DOTALL)
        match = h2_pattern.search(full_html)
        if match:
            start = match.start()
            # Grab content from the heading to the next mb-5 section or end
            rest = full_html[start:]
            next_section = re.search(r'<div[^>]*class="[^"]*\bmb-5\b', rest[50:])
            section_html = rest[: next_section.start() + 50] if next_section else rest
            break

    # strat 2: split by mb-5 divs and pick by index
    if section_html is None:
        mb5_starts = [
            m.start() for m in re.finditer(r'<div[^>]*class="[^"]*\bmb-5\b', full_html)
        ]
        if fallback_index < len(mb5_starts):
            start = mb5_starts[fallback_index]
            end = (
                mb5_starts[fallback_index + 1]
                if fallback_index + 1 < len(mb5_starts)
                else len(full_html)
            )
            section_html = full_html[start:end]

    if not section_html:
        return []

    return _extract_series_cards(section_html)


def fetch_new_series():
    """Fetch the 'Neue Staffeln diese Woche' section from s.to.

    Returns a list of series dicts or None on error.
    """
    html = _fetch_series_homepage()
    if html is None:
        return None
    return _find_series_section(
        html,
        heading_hints=[r"Neue\s+Staffeln", r"Neue\s+Serien", r"\U0001f970"],
        fallback_index=0,
    )


def fetch_popular_series():
    """Fetch the 'Meistgesehen gerade' section from s.to.

    Returns a list of series dicts or None on error.
    """
    html = _fetch_series_homepage()
    if html is None:
        return None
    return _find_series_section(
        html,
        heading_hints=[r"Meistgesehen", r"Beliebt", r"\U0001f525"],
        fallback_index=1,
    )


def _curses_menu(stdscr, options):
    """Display a simple curses menu to select an option with scrolling support."""
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)

    selected = 0
    top = 0

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        display_height = h - 2  # leave room for borders

        # Adjust top for scrolling
        if selected < top:
            top = selected
        elif selected >= top + display_height:
            top = selected - display_height + 1

        # Display visible options
        for idx in range(top, min(top + display_height, len(options))):
            option = options[idx]
            title = (
                option.get("title", "Unknown Title")
                .replace("<em>", "")
                .replace("</em>", "")
            )
            title = title[: w - 4]  # clip to width
            y = idx - top + 1
            x = 2
            if idx == selected:
                stdscr.attron(curses.color_pair(1))
                stdscr.addstr(y, x, title)
                stdscr.attroff(curses.color_pair(1))
            else:
                stdscr.addstr(y, x, title)

        stdscr.refresh()
        key = stdscr.getch()

        if key in [curses.KEY_UP, ord("k")]:
            selected = (selected - 1) % len(options)
        elif key in [curses.KEY_DOWN, ord("j")]:
            selected = (selected + 1) % len(options)
        elif key in [curses.KEY_ENTER, ord("\n")]:
            return options[selected]


def _normalize_s_to_link(link: str) -> str:
    """
    Normalize s.to links to the canonical form used by our provider patterns:
    - /serie/<slug>
    Also accepts /serie/stream/<slug> and converts it back.
    """
    if not link:
        return link

    link = link.strip()

    # Convert /serie/stream/<slug> -> /serie/<slug>
    if link.startswith("/serie/stream/"):
        slug = link[len("/serie/stream/") :].strip("/")
        return f"/serie/{slug}" if slug else link

    # Keep canonical /serie/<slug>
    if link.startswith("/serie/"):
        # ensure it doesn't include extra path segments
        slug = link[len("/serie/") :].strip("/").split("/", 1)[0]
        return f"/serie/{slug}" if slug else link

    return link


def query_s_to(keyword):
    """Search s.to for the given keyword and return a list of matching series with their URLs."""
    # Use query params to ensure proper URL encoding (spaces, umlauts, etc.)
    url = "https://s.to/api/search/suggest"
    response = GLOBAL_SESSION.get(url, params={"term": keyword})

    data = response.json()
    shows = data.get("shows", []) or []

    results = []
    for show in shows:
        title = show.get("name", "Unknown Title")
        link = _normalize_s_to_link(show.get("url", "") or "")
        if link:
            results.append({"title": title, "link": link})

    return results


def search(is_aniworld=None):
    """Prompt user for a search keyword and return a single series URL using a curses menu."""
    display_ascii_art()

    use_random = os.getenv("ANIWORLD_RANDOM_ANIME", "0") == "1"

    if is_aniworld is None:
        is_aniworld = os.getenv("ANIWORLD_USE_STO_SEARCH", "0") != "1"

    # print(f"Using {'Aniworld' if is_aniworld else 's.to'} for search results.\n")

    base_url = "https://aniworld.to" if is_aniworld else "https://s.to"
    query_fn = query if is_aniworld else query_s_to

    if use_random:
        result = random_anime()
        if result:
            logger.debug(f"Random anime selected: {result}")
            return result
        else:
            logger.error("Failed to get random anime. Please try again.")
            return None

    while True:
        keyword = input("\nSearch for a series: ").strip()
        if not keyword:
            logger.error("No keyword entered, aborting search.")
            return None

        results = query_fn(keyword)

        if not results:
            logger.error("No results found. Please try again.")
            continue

        if isinstance(results, dict):
            results = [results]
        elif isinstance(results, str):
            return results

        logger.debug(results)

        if is_aniworld:
            stream_pattern = re.compile(
                r"^/anime/stream/[a-zA-Z0-9\-]+/?$", re.IGNORECASE
            )
        else:
            stream_pattern = re.compile(
                r"^/serie/(stream/)?[a-zA-Z0-9\-]+/?$", re.IGNORECASE
            )

        stream_results = [
            item for item in results if stream_pattern.match(item.get("link") or "")
        ]

        if not stream_results:
            logger.error("No streamable series found. Please try again.")
            continue

        if len(stream_results) == 1:
            selected_item = stream_results[0]
            title = selected_item.get("title") or selected_item.get(
                "name", "Unknown Title"
            )
            logger.debug(f"Auto-selected: {title}")
            return f"{base_url}{selected_item['link']}"

        def menu_wrapper(stdscr):
            curses.start_color()
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
            selected_item = _curses_menu(stdscr, stream_results)
            return f"{base_url}{selected_item['link']}"

        return curses.wrapper(menu_wrapper)


if __name__ == "__main__":
    print("New series:", fetch_new_series())
    print("Popular series:", fetch_popular_series())
