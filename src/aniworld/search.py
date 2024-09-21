import curses
from json import loads
from urllib.parse import quote
import logging

from typing import List, Dict, Optional

from aniworld import globals
from aniworld.common import clear_screen, fetch_url_content


def search_anime(slug: str = None, link: str = None, query: str = None) -> str:
    clear_screen()
    logging.debug("Starting search_anime function")

    not_found = "Die gewünschte Serie wurde nicht gefunden oder ist im Moment deaktiviert."

    if slug:
        url = f"https://aniworld.to/anime/stream/{slug}"
        logging.debug(f"Fetching using slug: {url}")
        response = fetch_url_content(url)
        logging.debug(f"Response: {response}")
        if response and not_found not in response.decode():
            logging.debug(f"Found matching slug: {slug}")
            return slug

    if link:
        try:
            logging.debug(f"Fetching using link: {link}")
            response = fetch_url_content(link, check=False)
            if response and not_found not in response.decode():
                logging.debug(f"Found matching slug: {link.split('/')[-1]}")
                return link.split('/')[-1]
        except ValueError:
            logging.debug("ValueError encountered while fetching link")

    while True:
        clear_screen()
        if not query:
            query = input("Search for a series: ")
        else:
            logging.debug(f"Using provided query: {query}")

        url = f"https://aniworld.to/ajax/seriesSearch?keyword={quote(query)}"
        logging.debug(f"Fetching Anime List with query: {query}")

        json_data = fetch_url_content(url)
        decoded_data = loads(json_data.decode())
        logging.debug(f"Anime JSON List: {decoded_data}")

        if not isinstance(decoded_data, list) or not decoded_data:
            logging.debug("No series found. Prompting user to try again.")
            print("No series found. Try again...")
            query = None  # Reset query to prompt user again
            continue

        if len(decoded_data) == 1:
            logging.debug(f"Only one anime found: {decoded_data[0]}")
            return decoded_data[0].get('link', 'No Link Found')

        selected_slug = curses.wrapper(display_menu, decoded_data)
        logging.debug(f"Found matching slug: {selected_slug}")
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
            logging.debug(f"Selected anime: {items[current_row]}")
            return items[current_row].get('link', 'No Link')
        elif key == ord('q'):
            logging.debug("Exiting menu")
            break

    return None
