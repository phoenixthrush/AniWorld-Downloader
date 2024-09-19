#!/usr/bin/env python
# encoding: utf-8

import argparse
import os
import sys
import re
import logging

import npyscreen

from aniworld.search import search_anime
from aniworld import execute, globals
from aniworld.common import (
    clear_screen,
    clean_up_leftovers,
    get_season_data,
    set_terminal_size,
    get_version_from_pyproject
)

def format_anime_title(anime_slug):
    logging.debug(f"Formatting anime title for slug: {anime_slug}")
    try:
        formatted_title = anime_slug.replace("-", " ").title()
        logging.debug(f"Formatted title: {formatted_title}")
        return formatted_title
    except AttributeError:
        logging.debug("AttributeError encountered in format_anime_title")
        sys.exit()

class CustomTheme(npyscreen.ThemeManager):
    default_colors = {
        'DEFAULT'     : 'WHITE_BLACK',
        'FORMDEFAULT' : 'MAGENTA_BLACK',  # Form border
        'NO_EDIT'     : 'BLUE_BLACK',
        'STANDOUT'    : 'CYAN_BLACK',
        'CURSOR'      : 'WHITE_BLACK',  # Text (focused)
        'CURSOR_INVERSE': 'BLACK_WHITE',
        'LABEL'       : 'CYAN_BLACK',  # Form labels
        'LABELBOLD'   : 'CYAN_BLACK',  # Form labels (focused)
        'CONTROL'     : 'GREEN_BLACK',  # Items in form
        'IMPORTANT'   : 'GREEN_BLACK',
        'SAFE'        : 'GREEN_BLACK',
        'WARNING'     : 'YELLOW_BLACK',
        'DANGER'      : 'RED_BLACK',
        'CRITICAL'    : 'BLACK_RED',
        'GOOD'        : 'GREEN_BLACK',
        'GOODHL'      : 'GREEN_BLACK',
        'VERYGOOD'    : 'BLACK_GREEN',
        'CAUTION'     : 'YELLOW_BLACK',
        'CAUTIONHL'   : 'BLACK_YELLOW',
    }

class EpisodeForm(npyscreen.ActionForm):
    def create(self):
        logging.debug("Creating EpisodeForm")
        anime_slug = self.parentApp.anime_slug
        logging.debug(f"Anime slug: {anime_slug}")
        anime_title = format_anime_title(anime_slug)
        logging.debug(f"Anime title: {anime_title}")
        season_data = get_season_data(anime_slug)
        logging.debug(f"Season data: {season_data}")

        self.episode_map = {
            f"{anime_title} - Season {season} - Episode {idx + 1}": url
            for season, episodes in season_data.items()
            for idx, url in enumerate(episodes)
        }
        episode_list = list(self.episode_map.keys())
        logging.debug(f"Episode list: {episode_list}")

        self.action_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Action",
            values=["Watch", "Download", "Syncplay"],
            max_height=4,
            value=[["Watch", "Download", "Syncplay"].index(globals.DEFAULT_ACTION)],
            scroll_exit=True
        )
        logging.debug("Action selector created")

        self.aniskip_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Aniskip",
            values=["Enable", "Disable"],
            max_height=3,
            value=[0 if globals.DEFAULT_ANISKIP else 1],
            scroll_exit=True
        )
        logging.debug("Aniskip selector created")

        self.directory_field = self.add(
            npyscreen.TitleFilenameCombo,
            name="Directory:",
            value=globals.DEFAULT_DOWNLOAD_PATH
        )
        logging.debug("Directory field created")

        self.language_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Language",
            values=["German Dub", "English Sub", "German Sub"],
            max_height=4,
            value=[["German Dub", "English Sub", "German Sub"].index(globals.DEFAULT_LANGUAGE)],
            scroll_exit=True
        )
        logging.debug("Language selector created")

        self.provider_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Provider",
            values=["Vidoza", "Streamtape", "VOE", "Doodstream"],
            max_height=4,
            value=[["Vidoza", "Streamtape", "VOE", "Doodstream"].index(globals.DEFAULT_PROVIDER)],
            scroll_exit=True
        )
        logging.debug("Provider selector created")

        self.add(npyscreen.FixedText, value="")  # new line
        self.episode_selector = self.add(
            npyscreen.TitleMultiSelect,
            name="Episode Selection",
            values=episode_list,
            max_height=7,
            scroll_exit=True
        )
        logging.debug("Episode selector created")

        self.action_selector.when_value_edited = self.update_directory_visibility
        logging.debug("Set update_directory_visibility as callback for action_selector")

    def update_directory_visibility(self):
        logging.debug("Updating directory visibility")
        selected_action = self.action_selector.get_selected_objects()
        logging.debug(f"Selected action: {selected_action}")
        if selected_action and selected_action[0] == "Watch" or selected_action[0] == "Syncplay":
            self.directory_field.hidden = True
            self.aniskip_selector.hidden = False
            logging.debug("Directory field hidden, Aniskip selector shown")
        else:
            self.directory_field.hidden = False
            self.aniskip_selector.hidden = True
            logging.debug("Directory field shown, Aniskip selector hidden")
        self.display()

    def on_ok(self):
        logging.debug("OK button pressed")
        npyscreen.blank_terminal()
        output_directory = self.directory_field.value if not self.directory_field.hidden else None
        logging.debug(f"Output directory: {output_directory}")
        if not output_directory and not self.directory_field.hidden:
            logging.debug("No output directory provided")
            npyscreen.notify_confirm("Please provide a directory.", title="Error")
            return

        selected_episodes = self.episode_selector.get_selected_objects()
        action_selected = self.action_selector.get_selected_objects()
        language_selected = self.language_selector.get_selected_objects()
        provider_selected = self.provider_selector.get_selected_objects()
        aniskip_selected = self.aniskip_selector.get_selected_objects()[0] == "Enable"

        logging.debug(f"Selected episodes: {selected_episodes}")
        logging.debug(f"Action selected: {action_selected}")
        logging.debug(f"Language selected: {language_selected}")
        logging.debug(f"Provider selected: {provider_selected}")
        logging.debug(f"Aniskip selected: {aniskip_selected}")

        if not (selected_episodes and action_selected and language_selected):
            logging.debug("No episodes or action or language selected")
            npyscreen.notify_confirm("No episodes selected.", title="Selection")
            return

        lang = self.get_language_code(language_selected[0])
        logging.debug(f"Language code: {lang}")
        provider_selected = self.validate_provider(provider_selected)
        logging.debug(f"Validated provider: {provider_selected}")

        selected_urls = [self.episode_map[episode] for episode in selected_episodes]
        selected_str = "\n".join(selected_episodes)
        logging.debug(f"Selected URLs: {selected_urls}")
        npyscreen.notify_confirm(f"Selected episodes:\n{selected_str}", title="Selection")

        if not self.directory_field.hidden:
            anime_title = format_anime_title(self.parentApp.anime_slug)
            output_directory = os.path.join(output_directory, anime_title)
            os.makedirs(output_directory, exist_ok=True)
            logging.debug(f"Output directory created: {output_directory}")

        for episode_url in selected_urls:
            params = {
                'selected_episodes': [episode_url],
                'provider_selected': provider_selected,
                'action_selected': action_selected[0],
                'aniskip_selected': aniskip_selected,
                'lang': lang,
                'output_directory': output_directory,
                'anime_title': format_anime_title(self.parentApp.anime_slug)
            }

            logging.debug(f"Executing with params: {params}")
            execute(params)

        if not self.directory_field.hidden:
            logging.debug(f"Cleaning up leftovers in: {output_directory}")
            clean_up_leftovers(output_directory)

        self.parentApp.setNextForm(None)
        self.parentApp.switchFormNow()

    def get_language_code(self, language):
        logging.debug(f"Getting language code for: {language}")
        return {
            'German Dub': "1",
            'English Sub': "2",
            'German Sub': "3"
        }.get(language, "")

    def validate_provider(self, provider_selected):
        logging.debug(f"Validating provider: {provider_selected}")
        valid_providers = ["Vidoza", "Streamtape", "VOE"]
        while provider_selected[0] not in valid_providers:
            logging.debug("Invalid provider selected, falling back to Vidoza")
            npyscreen.notify_confirm(
                "Doodstream is currently broken.\nFalling back to Vidoza.",
                title="Provider Error"
            )
            self.provider_selector.value = 0
            provider_selected = ["Vidoza"]
        return provider_selected[0]

    def on_cancel(self):
        logging.debug("Cancel button pressed")
        self.parentApp.setNextForm(None)


class AnimeApp(npyscreen.NPSAppManaged):
    def __init__(self, anime_slug):
        logging.debug(f"Initializing AnimeApp with slug: {anime_slug}")
        super().__init__()
        self.anime_slug = anime_slug

    def onStart(self):
        logging.debug("Starting AnimeApp")
        npyscreen.setTheme(CustomTheme)
        self.addForm("MAIN", EpisodeForm, name=f"AniWorld-Downloader{get_version_from_pyproject()}")


def parse_arguments():
    logging.debug("Parsing command line arguments")
    parser = argparse.ArgumentParser(description="Parse optional command line arguments.")
    parser.add_argument('--slug', type=str, help='Search query - E.g. demon-slayer-kimetsu-no-yaiba')
    parser.add_argument('--link', type=str, help='Search query - E.g. https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba')
    parser.add_argument('--query', type=str, help='Search query input - E.g. demon')
    parser.add_argument('--episode', type=str, nargs='+', help='List of episode URLs')
    parser.add_argument('--action', type=str, choices=['Watch', 'Download', 'Syncplay'], default=globals.DEFAULT_ACTION, help='Action to perform')
    parser.add_argument('--output', type=str, default=globals.DEFAULT_DOWNLOAD_PATH, help='Download directory')
    parser.add_argument('--language', type=str, choices=['German Dub', 'English Sub', 'German Sub'], default=globals.DEFAULT_LANGUAGE, help='Language choice')
    parser.add_argument('--provider', type=str, choices=['Vidoza', 'Streamtape', 'VOE', 'Doodstream'], default=globals.DEFAULT_PROVIDER, help='Provider choice')
    parser.add_argument('--aniskip', action='store_true', default=globals.DEFAULT_ANISKIP, help='Skip intro and outro')
    parser.add_argument('--keep-watching', action='store_true', default=globals.DEFAULT_KEEP_WATCHING, help='Continue watching')
    parser.add_argument('--only-direct-link', action='store_true', default=globals.DEFAULT_ONLY_DIRECT_LINK, help='Output direct link')
    parser.add_argument('--only-command', action='store_true', default=globals.DEFAULT_ONLY_COMMAND, help='Output command')
    parser.add_argument('--proxy', type=str, default=globals.DEFAULT_PROXY, help='Set HTTP Proxy (not working yet)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    if args.debug:
        os.environ['IS_DEBUG_MODE'] = '1'
        globals.IS_DEBUG_MODE = True
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Debug mode enabled")

    return args


def handle_query(args):
    logging.debug(f"Handling query with args: {args}")
    if args.query and not args.episode:
        slug = search_anime(query=args.query)
        logging.debug(f"Found slug: {slug}")
        season_data = get_season_data(anime_slug=slug)
        logging.debug(f"Season data: {season_data}")
        episode_list = [
            url
            for season, episodes in season_data.items()
            for url in episodes
        ]
        logging.debug(f"Episode list: {episode_list}")

        user_input = input("Please enter the episode (e.g., S1E2): ")
        logging.debug(f"User input: {user_input}")
        match = re.match(r"S(\d+)E(\d+)", user_input)
        if match:
            s = int(match.group(1))
            e = int(match.group(2))
            logging.debug(f"Parsed season: {s}, episode: {e}")

        args.episode = [f"https://aniworld.to/anime/stream/{slug}/staffel-{s}/episode-{e}"]
        logging.debug(f"Set episode URL: {args.episode}")


def get_anime_title(args):
    logging.debug(f"Getting anime title from args: {args}")
    if args.link:
        title = args.link.split('/')[-1]
        logging.debug(f"Anime title from link: {title}")
        return title
    elif args.slug:
        logging.debug(f"Anime title from slug: {args.slug}")
        return args.slug
    elif args.episode:
        title = args.episode[0].split('/')[5]
        logging.debug(f"Anime title from episode URL: {title}")
        return title
    return None


def get_language_code(language):
    logging.debug(f"Getting language code for: {language}")
    return {
        "German Dub": "1",
        "English Sub": "2",
        "German Sub": "3"
    }.get(language, "")

def main():
    logging.debug("============================================")
    logging.debug("Welcome to Aniworld!")
    logging.debug("============================================\n")
    try:
        args = parse_arguments()
        logging.debug(f"Parsed arguments: {args}")

        if args.link:
            if args.link.count('/') == 5:
                logging.debug("Provided link format valid.")
            elif args.link.count('/') == 6 and args.link.endswith('/'):
                logging.debug("Provided link format valid.")
                args.link = args.link.rstrip('/')
            else:
                logging.debug("Provided link invalid.")
                args.link = None

        handle_query(args)

        anime_title = get_anime_title(args)
        logging.debug(f"Anime title: {anime_title}")
        language = get_language_code(args.language)
        logging.debug(f"Language code: {language}")

        updated_list = None
        if args.keep_watching and args.episode:
            season_data = get_season_data(anime_slug=anime_title)
            logging.debug(f"Season data: {season_data}")
            episode_list = [
                url
                for season, episodes in season_data.items()
                for url in episodes
            ]
            logging.debug(f"Episode list: {episode_list}")

            index = episode_list.index(args.episode[0])
            updated_list = episode_list[index:]
            logging.debug(f"Updated episode list: {updated_list}")

        selected_episodes = updated_list if updated_list else args.episode
        logging.debug(f"Selected episodes: {selected_episodes}")

        if args.episode:
            params = {
                'selected_episodes': selected_episodes,
                'provider_selected': args.provider,
                'action_selected': args.action,
                'aniskip_selected': args.aniskip,
                'lang': language,
                'output_directory': args.output,
                'anime_title': anime_title.replace('-', ' ').title(),
                'only_direct_link': args.only_direct_link,
                'only_command': args.only_command,
                'debug': args.debug
            }
            logging.debug(f"Executing with params: {params}")
            execute(params=params)
            logging.debug("Execution complete. Exiting.")
            sys.exit()
    except KeyboardInterrupt:
        logging.debug("KeyboardInterrupt encountered. Exiting.")
        sys.exit()

    def run_app(query):
        logging.debug(f"Running app with query: {query}")
        clear_screen()
        app = AnimeApp(query)
        app.run()

    try:
        try:
            logging.debug("Trying to resize Terminal.")
            set_terminal_size()
            run_app(search_anime(slug=args.slug, link=args.link))
        except npyscreen.wgwidget.NotEnoughSpaceForWidget:
            logging.debug("Not enough space for widget. Asking user to resize terminal.")
            clear_screen()
            print("Please increase your current terminal size.")
            logging.debug("Exiting due to terminal size.")
            sys.exit()
    except KeyboardInterrupt:
        logging.debug("KeyboardInterrupt encountered. Exiting.")
        sys.exit()


if __name__ == "__main__":
    main()
