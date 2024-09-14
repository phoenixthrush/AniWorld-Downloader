#!/usr/bin/env python
# encoding: utf-8

import argparse
import os
import sys
import re
import logging

from bs4 import BeautifulSoup
import npyscreen

from aniworld import clear_screen, search, execute, globals
from aniworld.common import fetch_url_content, clean_up_leftovers, get_season_data, set_terminal_size


class AnimeDownloader:
    BASE_URL_TEMPLATE = "https://aniworld.to/anime/stream/{anime}/"

    def __init__(self, anime_slug):
        logging.debug(f"Initializing AnimeDownloader with slug: {anime_slug}")
        self.anime_slug = anime_slug
        self.anime_title = self.format_anime_title(anime_slug)
        self.base_url = self.BASE_URL_TEMPLATE.format(anime=anime_slug)
        self.season_data = get_season_data(anime_slug)
        logging.debug(f"Initialized AnimeDownloader: {self.__dict__}")

    @staticmethod
    def format_anime_title(anime_slug):
        try:
            return anime_slug.replace("-", " ").title()
        except AttributeError:
            sys.exit()


class EpisodeForm(npyscreen.ActionForm):
    def create(self):
        logging.debug("Creating EpisodeForm")
        episode_list = [
            url
            for season, episodes in self.parentApp.anime_downloader.season_data.items()
            for url in episodes
        ]
        logging.debug(f"Episode list: {episode_list}")

        self.action_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Watch, Download or Syncplay",
            values=["Watch", "Download", "Syncplay"],
            max_height=4,
            value=[["Watch", "Download", "Syncplay"].index(globals.DEFAULT_ACTION)],
            scroll_exit=True
        )

        self.aniskip_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Use Aniskip (Skip Intro & Outro)",
            values=["Yes", "No"],
            max_height=3,
            value=[0 if globals.DEFAULT_ANISKIP else 1],
            scroll_exit=True
        )

        self.directory_field = self.add(
            npyscreen.TitleFilenameCombo,
            name="Directory:",
            value=globals.DEFAULT_DOWNLOAD_PATH
        )

        self.language_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Language Options",
            values=["German Dub", "English Sub", "German Sub"],
            max_height=4,
            value=[["German Dub", "English Sub", "German Sub"].index(globals.DEFAULT_LANGUAGE)],
            scroll_exit=True
        )

        self.provider_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Provider Options (VOE recommended for Downloading)",
            values=["Vidoza", "Streamtape", "VOE", "Doodstream"],
            max_height=4,
            value=[["Vidoza", "Streamtape", "VOE", "Doodstream"].index(globals.DEFAULT_PROVIDER)],
            scroll_exit=True
        )

        self.episode_selector = self.add(
            npyscreen.TitleMultiSelect,
            name="Select Episodes",
            values=episode_list,
            max_height=7
        )

        self.action_selector.when_value_edited = self.update_directory_visibility

    def update_directory_visibility(self):
        logging.debug("Updating directory visibility")
        selected_action = self.action_selector.get_selected_objects()
        if selected_action and selected_action[0] == "Watch" or selected_action[0] == "Syncplay":
            self.directory_field.hidden = True
            self.aniskip_selector.hidden = False
        else:
            self.directory_field.hidden = False
            self.aniskip_selector.hidden = True
        self.display()

    def on_ok(self):
        logging.debug("OK button pressed")
        npyscreen.blank_terminal()
        output_directory = self.directory_field.value if not self.directory_field.hidden else None
        if not output_directory and not self.directory_field.hidden:
            npyscreen.notify_confirm("Please provide a directory.", title="Error")
            return

        selected_episodes = self.episode_selector.get_selected_objects()
        action_selected = self.action_selector.get_selected_objects()
        language_selected = self.language_selector.get_selected_objects()
        provider_selected = self.provider_selector.get_selected_objects()
        aniskip_selected = self.aniskip_selector.get_selected_objects()

        if not (selected_episodes and action_selected and language_selected):
            npyscreen.notify_confirm("No episodes selected.", title="Selection")
            return

        lang = self.get_language_code(language_selected[0])
        provider_selected = self.validate_provider(provider_selected)

        selected_str = "\n".join(selected_episodes)
        npyscreen.notify_confirm(f"Selected episodes:\n{selected_str}", title="Selection")

        if not self.directory_field.hidden:
            anime_title = self.parentApp.anime_downloader.anime_title
            output_directory = os.path.join(output_directory, anime_title)
            os.makedirs(output_directory, exist_ok=True)

        params = {
            'selected_episodes': selected_episodes,
            'provider_selected': provider_selected,
            'action_selected': action_selected[0],
            'aniskip_selected': aniskip_selected[0],
            'lang': lang,
            'output_directory': output_directory,
            'anime_title': self.parentApp.anime_downloader.anime_title
        }

        logging.debug(f"Execute using: {params}")
        execute(params)

        if not self.directory_field.hidden:
            clean_up_leftovers(output_directory)

        self.parentApp.setNextForm(None)
        self.parentApp.switchFormNow()

    def get_language_code(self, language):
        return {
            'German Dub': "1",
            'English Sub': "2",
            'German Sub': "3"
        }.get(language, "")

    def validate_provider(self, provider_selected):
        valid_providers = ["Vidoza", "Streamtape", "VOE"]
        while provider_selected[0] not in valid_providers:
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
        super().__init__()
        logging.debug(f"Initializing AnimeApp with slug: {anime_slug}")
        self.anime_downloader = AnimeDownloader(anime_slug)

    def onStart(self):
        logging.debug("Starting AnimeApp")
        self.addForm("MAIN", EpisodeForm, name="Anime Downloader")


def parse_arguments():
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

    logging.debug("Parsing Command Line Arguments.")
    return parser.parse_args()


def handle_query(args):
    if args.query and not args.episode:
        logging.debug(f"Handling query: {args.query}")
        slug = search.search_anime(query=args.query)
        season_data = get_season_data(anime_slug=slug)
        episode_list = [
            url
            for season, episodes in season_data.items()
            for url in episodes
        ]

        user_input = input("Please enter the episode (e.g., S1E2): ")
        match = re.match(r"S(\d+)E(\d+)", user_input)
        if match:
            s = int(match.group(1))
            e = int(match.group(2))

        args.episode = [f"https://aniworld.to/anime/stream/{slug}/staffel-{s}/episode-{e}"]


def get_anime_title(args):
    if args.link:
        return args.link.split('/')[-1]
    elif args.slug:
        return args.slug
    elif args.episode:
        return args.episode[0].split('/')[5]
    return None


def get_language_code(language):
    return {
        "German Dub": "1",
        "English Sub": "2",
        "German Sub": "3"
    }.get(language, "")


def main():
    try:
        args = parse_arguments()

        if args.link and args.link.count('/') != 5:
            logging.debug("Provided link invalid.")
            args.link = None

        handle_query(args)

        anime_title = get_anime_title(args)
        language = get_language_code(args.language)

        updated_list = None
        if args.keep_watching and args.episode:
            season_data = get_season_data(anime_slug=anime_title)
            episode_list = [
                url
                for season, episodes in season_data.items()
                for url in episodes
            ]

            if logging.debug:
                logging.debug(f"Episode List: {episode_list}\n")
                logging.debug(args.episode[0])

            index = episode_list.index(args.episode[0])
            updated_list = episode_list[index:]

            if logging.debug:
                logging.debug(f"Updated List: {updated_list}\n")

        selected_episodes = updated_list if updated_list else args.episode

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
            logging.debug(f"Execute using: {params}")
            execute(params=params)
            sys.exit()
    except KeyboardInterrupt:
        sys.exit()

    def run_app(query):
        clear_screen()
        app = AnimeApp(query)
        app.run()

    try:
        try:
            logging.debug("Trying to resize Terminal.")
            set_terminal_size()
            run_app(search.search_anime(slug=args.slug, link=args.link))
        except npyscreen.wgwidget.NotEnoughSpaceForWidget:
            clear_screen()
            print("Please increase your current terminal size.")
            sys.exit()
    except KeyboardInterrupt:
        sys.exit()


if __name__ == "__main__":
    main()
