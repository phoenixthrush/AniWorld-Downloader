import curses
from json import loads
from json.decoder import JSONDecodeError
from urllib.parse import quote
import logging

from typing import List, Dict, Optional

from aniworld.common import (
    clear_screen,
    fetch_url_content,
    display_ascii_art
)


def search_anime(slug: str = None, link: str = None, query: str = None) -> str:
    clear_screen()
    logging.debug("Starting search_anime function")

    not_found = "Die gewünschte Serie wurde nicht gefunden oder ist im Moment deaktiviert."

    if slug:
        url = f"https://aniworld.to/anime/stream/{slug}"
        logging.debug("Fetching using slug: %s", url)
        response = fetch_url_content(url)
        logging.debug("Response: %s", response)
        if response and not_found not in response.decode():
            logging.debug("Found matching slug: %s", slug)
            return slug

    if link:
        try:
            logging.debug("Fetching using link: %s", link)
            response = fetch_url_content(link, check=False)
            if response and not_found not in response.decode():
                logging.debug("Found matching slug: %s", link.split('/')[-1])
                return link.split('/')[-1]
        except ValueError:
            logging.debug("ValueError encountered while fetching link")

    while True:
        clear_screen()
        if not query:
            print(display_ascii_art())
            query = input("Search for a series: ")
        else:
            logging.debug("Using provided query: %s", query)

        url = f"https://aniworld.to/ajax/seriesSearch?keyword={quote(query)}"
        logging.debug("Fetching Anime List with query: %s", query)

        json_data = fetch_url_content(url)
        try:
            decoded_data = loads(json_data.decode())
        except JSONDecodeError:
            continue
        logging.debug("Anime JSON List: %s", decoded_data)

        if not isinstance(decoded_data, list) or not decoded_data:
            logging.debug("No series found. Prompting user to try again.")
            print("No series found. Try again...")
            query = None
            continue

        if len(decoded_data) == 1:
            logging.debug("Only one anime found: %s", decoded_data[0])
            return decoded_data[0].get('link', 'No Link Found')

        selected_slug = curses.wrapper(display_menu, decoded_data)
        logging.debug("Found matching slug: %s", selected_slug)
        return selected_slug


def display_menu(stdscr: curses.window, items: List[Dict[str, Optional[str]]]) -> Optional[str]:
    logging.debug("Starting display_menu function")
    current_row = 0

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
