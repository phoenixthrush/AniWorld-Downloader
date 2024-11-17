import html
import logging
import os
import webbrowser

from typing import List, Dict, Optional
from json import loads
from json.decoder import JSONDecodeError
from urllib.parse import quote

import curses
from bs4 import BeautifulSoup


from aniworld.common import (
    clear_screen,
    fetch_url_content,
    display_ascii_art,
    show_messagebox
)


def search_anime(slug: str = None, link: str = None, query: str = None) -> str:
    clear_screen()
    logging.debug("Starting search_anime function")

    not_found = "Die gewünschte Serie wurde nicht gefunden oder ist im Moment deaktiviert."

    if slug:
        return fetch_by_slug(slug, not_found)

    if link:
        return fetch_by_link(link, not_found)

    return search_by_query(query)


def fetch_by_slug(slug: str, not_found: str) -> str:
    url = f"https://aniworld.to/anime/stream/{slug}"
    logging.debug("Fetching using slug: %s", url)
    response = fetch_url_content(url)
    if response and not_found not in response.decode():
        logging.debug("Found matching slug: %s", slug)
        return slug
    return None


def fetch_by_link(link: str, not_found: str) -> str:
    try:
        logging.debug("Fetching using link: %s", link)
        response = fetch_url_content(link, check=False)
        if response and not_found not in response.decode():
            logging.debug("Found matching slug: %s", link.split('/')[-1])
            return link.split('/')[-1]
    except ValueError:
        logging.debug("ValueError encountered while fetching link")
    return None


def search_by_query(query: str) -> str:
    while True:
        clear_screen()
        if not query:
            print(display_ascii_art())
            query = input("Search for a series: ")
            if query.lower().strip() == "boku no piko":
                show_messagebox("This is not on aniworld...\nThank god...", "Really?...", "info")
        else:
            logging.debug("Using provided query: %s", query)

        url = f"https://aniworld.to/ajax/seriesSearch?keyword={quote(query)}"
        logging.debug("Fetching Anime List with query: %s", query)

        json_data = fetch_anime_json(url)

        if not json_data:
            print("No series found. Try again...")
            query = None
            continue

        if len(json_data) == 1:
            logging.debug("Only one anime found: %s", json_data[0])
            return json_data[0].get('link', 'No Link Found')

        selected_slug = curses.wrapper(display_menu, json_data)
        logging.debug("Found matching slug: %s", selected_slug)
        return selected_slug


def fetch_anime_json(url: str):
    try:
        if os.getenv("USE_PLAYWRIGHT"):
            page_content = html.unescape(fetch_url_content(url).decode('utf-8'))
            soup = BeautifulSoup(page_content, 'html.parser')
            json_data = soup.find('pre').text
        else:
            json_data = html.unescape(fetch_url_content(url).decode('utf-8'))

        decoded_data = loads(json_data)
        if isinstance(decoded_data, list) and decoded_data:
            return decoded_data
    except (AttributeError, JSONDecodeError):
        logging.debug("Error fetching or decoding the anime data.")
    return None


def display_menu(stdscr: curses.window, items: List[Dict[str, Optional[str]]]) -> Optional[str]:
    logging.debug("Starting display_menu function")
    current_row = 0

    konami_code = ['UP', 'UP', 'DOWN', 'DOWN', 'LEFT', 'RIGHT', 'LEFT', 'RIGHT', 'b', 'a']
    entered_keys = []

    key_map = {
        curses.KEY_UP: 'UP',
        curses.KEY_DOWN: 'DOWN',
        curses.KEY_LEFT: 'LEFT',
        curses.KEY_RIGHT: 'RIGHT',
        ord('b'): 'b',
        ord('a'): 'a'
    }

    while True:
        stdscr.clear()
        for idx, anime in enumerate(items):
            name = anime.get('name', 'No Name')
            year = anime.get('productionYear', 'No Year')
            attr = curses.A_REVERSE if idx == current_row else 0
            stdscr.attron(attr)
            stdscr.addstr(idx, 0, f"{name} {year}")
            stdscr.attroff(attr)

        stdscr.refresh()
        key = stdscr.getch()

        if key in key_map:
            entered_keys.append(key_map[key])
            if len(entered_keys) > len(konami_code):
                entered_keys.pop(0)

            if entered_keys == konami_code:
                konami_code_activated()
                entered_keys.clear()
        else:
            entered_keys.clear()

        if key == curses.KEY_DOWN:
            current_row = (current_row + 1) % len(items)
        elif key == curses.KEY_UP:
            current_row = (current_row - 1 + len(items)) % len(items)
        elif key == ord('\n'):
            logging.debug("Selected anime: %s", items[current_row])
            return items[current_row].get('link', 'No Link')
        elif key == ord('q'):
            logging.debug("Exiting menu")
            break

    return None


def konami_code_activated():
    logging.debug("Konami Code activated!")
    curses.endwin()
    webbrowser.open('https://www.youtube.com/watch?v=PDJLvF1dUek')
