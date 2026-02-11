import json
import html
import webbrowser
from urllib.parse import quote
import logging
import re
from typing import List, Dict, Optional, Union
from functools import lru_cache

from bs4 import BeautifulSoup

import curses
import requests

from .ascii_art import display_ascii_art
from .config import DEFAULT_REQUEST_TIMEOUT, ANIWORLD_TO


# Constants for better maintainability
KONAMI_CODE = ["UP", "UP", "DOWN", "DOWN", "LEFT", "RIGHT", "LEFT", "RIGHT", "b", "a"]
EASTER_EGG_URL = "https://www.youtube.com/watch?v=PDJLvF1dUek"

# Forbidden search patterns (case-insensitive)
FORBIDDEN_SEARCHES = ["boku no piko", "boku no pico", "pico boku", "piko boku"]

# Key mapping for menu navigation
KEY_MAP = {
    curses.KEY_UP: "UP",
    curses.KEY_DOWN: "DOWN",
    curses.KEY_LEFT: "LEFT",
    curses.KEY_RIGHT: "RIGHT",
    ord("b"): "b",
    ord("a"): "a",
}


def _validate_keyword(keyword: str) -> str:
    """
    Validate and sanitize the search keyword.

    Args:
        keyword: Raw keyword input

    Returns:
        str: Cleaned keyword

    Raises:
        ValueError: If keyword is forbidden or invalid
    """
    if not keyword or not keyword.strip():
        raise ValueError("Search keyword cannot be empty")

    cleaned_keyword = keyword.strip().lower()

    # Check against forbidden search patterns
    for forbidden in FORBIDDEN_SEARCHES:
        if forbidden in cleaned_keyword:
            raise ValueError("Really? This is not on AniWorld...")

    return keyword.strip()  # Return original case but trimmed


def _get_user_input() -> str:
    """Get search keyword from user input."""
    logging.debug("Prompting user for search.")
    keyword = input("Search for a series: ").strip()
    return _validate_keyword(keyword)


@lru_cache(maxsize=128)
def _cached_search_request(search_url: str) -> str:
    """
    Cached HTTP request for search results.

    Args:
        search_url: The URL to fetch data from

    Returns:
        str: Raw response text
    """
    response = requests.get(search_url, timeout=DEFAULT_REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text.strip()


def search_anime(
    keyword: Optional[str] = None, only_return: bool = False
) -> Union[str, List[Dict]]:
    """
    Search for anime series on AniWorld.

    Args:
        keyword: Search term (if None, prompts user)
        only_return: If True, returns raw anime list instead of processing

    Returns:
        Union[str, List[Dict]]: Either selected anime link or list of anime

    Raises:
        ValueError: If no anime found or invalid input
    """
    if not only_return:
        print(display_ascii_art())

    if not keyword:
        keyword = _get_user_input()
    else:
        keyword = _validate_keyword(keyword)

    search_url = f"{ANIWORLD_TO}/ajax/seriesSearch?keyword={quote(keyword)}"
    anime_list = fetch_anime_list(search_url)

    if only_return:
        return anime_list

    if len(anime_list) == 1:
        return anime_list[0].get("link", None)

    if not anime_list:
        raise ValueError("Could not get valid anime")

    return curses.wrapper(show_menu, anime_list)


def _clean_json_text(text: str) -> str:
    """
    Clean problematic characters from JSON text.

    Args:
        text: Raw JSON text

    Returns:
        str: Cleaned JSON text
    """
    # Remove BOM and problematic characters
    clean_text = text.encode("utf-8").decode("utf-8-sig")
    # Remove control characters that can break JSON parsing
    clean_text = re.sub(r"[\x00-\x1F\x7F-\x9F]", "", clean_text)
    return clean_text


def fetch_anime_list(url: str) -> List[Dict]:
    """
    Fetch and parse anime list from search API.

    Args:
        url: The search API URL

    Returns:
        List[Dict]: List of anime dictionaries

    Raises:
        ValueError: If unable to fetch or parse anime data
    """
    try:
        clean_text = _cached_search_request(url)
        # First attempt: direct JSON parsing
        try:
            decoded_data = json.loads(html.unescape(clean_text))
            
            # Handle S.TO style response {"shows": [...]}
            if isinstance(decoded_data, dict) and "shows" in decoded_data:
                results = decoded_data["shows"]
                # Normalize S.TO results
                for item in results:
                    if "url" in item and "link" not in item:
                        # Extract slug from url (e.g. /serie/shameless -> shameless)
                        item["link"] = item["url"].split("/")[-1]
                return results

            return decoded_data if isinstance(decoded_data, list) else []
        except json.JSONDecodeError:
            # Second attempt: clean problematic characters
            cleaned_text = _clean_json_text(clean_text)
            try:
                decoded_data = json.loads(cleaned_text)
                
                # Handle S.TO style response {"shows": [...]}
                if isinstance(decoded_data, dict) and "shows" in decoded_data:
                    results = decoded_data["shows"]
                    # Normalize S.TO results
                    for item in results:
                        if "url" in item and "link" not in item:
                            # Extract slug from url (e.g. /serie/shameless -> shameless)
                            item["link"] = item["url"].split("/")[-1]
                    return results

                return decoded_data if isinstance(decoded_data, list) else []
            except json.JSONDecodeError as err:
                logging.error("Failed to parse JSON after cleaning: %s", err)
                raise ValueError("Could not parse anime search results") from err

    except requests.RequestException as err:
        logging.error("Failed to fetch anime list: %s", err)
        raise ValueError("Could not fetch anime data from server") from err


def fetch_popular_and_new_anime() -> Dict[str, List[Dict[str, str]]]:
    """
    Fetch HTML from AniWorld homepage for popular and new anime parsing.

    Extracts anime titles and cover URLs from "Beliebt bei AniWorld" and "Neue Animes" sections.

    Returns:
        Dictionary with 'popular' and 'new' keys containing lists of anime data
    """
    try:
        response = requests.get(ANIWORLD_TO, timeout=DEFAULT_REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        result = {"popular": [], "new": []}

        # Extract popular anime section
        popular_section = soup.find(
            "h2", string=lambda text: text and "beliebt" in text.lower()
        )
        if popular_section:
            popular_carousel = popular_section.find_parent().find_next_sibling(
                "div", class_="previews"
            )
            if popular_carousel:
                result["popular"] = extract_anime_from_carousel(popular_carousel)

        # Extract new anime section
        new_section = soup.find(
            "h2",
            string=lambda text: text
            and "neue" in text.lower()
            and "anime" in text.lower(),
        )
        if new_section:
            new_carousel = new_section.find_parent().find_next_sibling(
                "div", class_="previews"
            )
            if new_carousel:
                result["new"] = extract_anime_from_carousel(new_carousel)

        return result

    except requests.RequestException as err:
        logging.error("Failed to fetch AniWorld homepage: %s", err)
        raise ValueError("Could not fetch homepage data") from err


def extract_anime_from_carousel(carousel_div):
    """
    Extract anime data from a carousel div section.

    Args:
        carousel_div: BeautifulSoup element containing the carousel

    Returns:
        List of dictionaries with 'name' and 'cover' keys
    """
    anime_list = []

    # Find all cover list items
    cover_items = carousel_div.find_all("div", class_="coverListItem")

    for item in cover_items:
        try:
            # Extract name from h3 tag or title attribute
            name = None
            h3_tag = item.find("h3")
            if h3_tag:
                name = h3_tag.get_text(strip=True)
                # Remove any trailing dots or special characters
                name = name.split(" •")[0].strip()

            # Fallback to title attribute from link
            if not name:
                link = item.find("a")
                if link and link.get("title"):
                    title_text = link.get("title")
                    # Extract name before "alle Folgen ansehen" or similar text
                    name = (
                        title_text.split(" alle Folgen")[0]
                        .split(" jetzt online")[0]
                        .strip()
                    )

            # Extract cover URL from img tag
            cover = None
            img_tag = item.find("img")
            if img_tag:
                # Try data-src first (lazy loading), then src
                cover = img_tag.get("data-src") or img_tag.get("src")
                # Make absolute URL if relative
                if cover and cover.startswith("/"):
                    cover = ANIWORLD_TO + cover

            if name and cover:
                anime_list.append({"name": name, "cover": cover})

        except Exception:
            # Skip this item if extraction fails
            continue

    return anime_list


def _handle_konami_code(entered_keys: List[str], key_input: str) -> List[str]:
    """
    Handle Konami code detection and Easter egg activation.

    Args:
        entered_keys: List of previously entered keys
        key_input: Current key input

    Returns:
        List[str]: Updated list of entered keys
    """
    entered_keys.append(key_input)

    # Keep only the last N keys where N is the length of Konami code
    if len(entered_keys) > len(KONAMI_CODE):
        entered_keys.pop(0)

    # Check if Konami code was entered
    if entered_keys == KONAMI_CODE:
        try:
            webbrowser.open(EASTER_EGG_URL)
        except Exception as err:
            logging.debug("Failed to open Easter egg URL: %s", err)
        entered_keys.clear()

    return entered_keys


def _render_menu(stdscr: curses.window, options: List[Dict], current_row: int) -> None:
    """
    Render the anime selection menu.

    Args:
        stdscr: Curses window object
        options: List of anime options
        current_row: Currently selected row index
    """
    stdscr.clear()

    max_y, max_x = stdscr.getmaxyx()

    for idx, anime in enumerate(options):
        if idx >= max_y - 1:  # Prevent drawing beyond screen
            break

        name = anime.get("name", "No Name")
        year = anime.get("productionYear", "Unknown Year")
        display_text = f"{name} {year}"

        # Truncate text if it's too long for the screen
        if len(display_text) >= max_x:
            display_text = display_text[: max_x - 4] + "..."

        highlight = curses.A_REVERSE if idx == current_row else 0

        try:
            stdscr.attron(highlight)
            stdscr.addstr(idx, 0, display_text)
            stdscr.attroff(highlight)
        except curses.error:
            # Handle cases where we can't draw to the screen
            pass

    stdscr.refresh()


def show_menu(stdscr: curses.window, options: List[Dict]) -> Optional[str]:
    """
    Display interactive menu for anime selection.

    Args:
        stdscr: Curses window object
        options: List of anime dictionaries

    Returns:
        Optional[str]: Selected anime link or None if cancelled
    """
    if not options:
        return None

    current_row = 0
    entered_keys = []

    try:
        while True:
            _render_menu(stdscr, options, current_row)
            key = stdscr.getch()

            # Handle Konami code detection
            if key in KEY_MAP:
                entered_keys = _handle_konami_code(entered_keys, KEY_MAP[key])
            else:
                entered_keys.clear()

            # Handle navigation
            if key == curses.KEY_DOWN:
                current_row = (current_row + 1) % len(options)
            elif key == curses.KEY_UP:
                current_row = (current_row - 1 + len(options)) % len(options)
            elif key == ord("\n"):
                return options[current_row].get("link", "No Link")
            elif key == ord("q") or key == 27:  # 'q' or ESC
                break

    except curses.error as err:
        logging.error("Curses error in menu: %s", err)
    except KeyboardInterrupt:
        pass

    return None


if __name__ == "__main__":
    print(search_anime())
