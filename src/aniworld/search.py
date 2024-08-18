import curses
from json import loads
from urllib.parse import quote

from typing import List, Dict, Optional

from aniworld.common import clear_screen, fetch_url_content


def search_anime(slug: str = None, link: str = None, query: str = None) -> str:
    """
    Retrieve the anime slug based on either a provided slug or link.
    - Tries using the slug first; if not found, tries using the link.
    - If neither slug nor link is provided, prompts the user to search.

    Args:
        slug (str, optional): The anime slug.
        link (str, optional): The URL containing the anime slug.
        query (str, optional): The anime query.

    Returns:
        str: The anime slug.
    """
    clear_screen()

    not_found = "Die gewünschte Serie wurde nicht gefunden oder ist im Moment deaktiviert."

    if slug:
        response = fetch_url_content(f"https://aniworld.to/anime/stream/{slug}")
        if response and not_found not in response.decode():
            return slug

    if link:
        try:
            response = fetch_url_content(link, check=False)
            if response and not_found not in response.decode():
                return link.split('/')[-1]
        except ValueError:
            pass

    while True:
        clear_screen()
        first_run = True
        if not query and first_run:
            query = input("Search for a series: ")
        else:
            query = input("Search for a series: ")

        url = f"https://aniworld.to/ajax/seriesSearch?keyword={quote(query)}"

        json_data = fetch_url_content(url)
        decoded_data = loads(json_data.decode())

        if not isinstance(decoded_data, list) or not decoded_data:
            print("No series found. Try again...")
            continue

        selected_slug = curses.wrapper(display_menu, decoded_data)
        return selected_slug


def display_menu(stdscr: curses.window, items: List[Dict[str, Optional[str]]]) -> Optional[str]:
    """
    Displays a menu of anime series in a curses window and allows user interaction.

    Args:
        stdscr (curses.window): The curses window object used for drawing.
        items (List[Dict[str, Optional[str]]]): List of dictionaries where each dictionary
            represents an anime series.
            Each dictionary contains optional 'name', 'link', and 'productionYear' fields.

    Returns:
        Optional[str]: The link of the selected anime or None if the menu is exited.
    """
    stdscr.clear()
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
            return items[current_row].get('link', 'No Link')
        elif key == ord('q'):
            break

    return None
