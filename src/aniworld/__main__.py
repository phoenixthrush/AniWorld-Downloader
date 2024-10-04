#!/usr/bin/env python
# encoding: utf-8

import argparse
import os
import sys
import re
import logging
import subprocess
import platform

import npyscreen

from aniworld.search import search_anime
from aniworld import execute, globals as aniworld_globals
from aniworld.common import (
    clear_screen,
    clean_up_leftovers,
    get_season_data,
    set_terminal_size,
    get_version_from_pyproject,
    get_language_code,
    is_tail_running,
    get_season_and_episode_numbers,
    setup_anime4k,
    is_version_outdated,
    read_episode_file,
    check_package_installation,
    self_uninstall,
    update_component,
    get_anime_season_title
)


def format_anime_title(anime_slug):
    logging.debug("Formatting anime title for slug: %s", anime_slug)
    try:
        formatted_title = anime_slug.replace("-", " ").title()
        logging.debug("Formatted title: %s", formatted_title)
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
        'CURSOR'      : 'WHITE_BLACK',    # Text (focused)
        'CURSOR_INVERSE': 'BLACK_WHITE',
        'LABEL'       : 'CYAN_BLACK',     # Form labels
        'LABELBOLD'   : 'CYAN_BLACK',     # Form labels (focused)
        'CONTROL'     : 'GREEN_BLACK',    # Items in form
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
    # pylint: disable=too-many-ancestors
    def create(self):
        logging.debug("Creating EpisodeForm")
        anime_slug = self.parentApp.anime_slug
        logging.debug("Anime slug: %s", anime_slug)
        anime_title = format_anime_title(anime_slug)
        logging.debug("Anime title: %s", anime_title)
        season_data = get_season_data(anime_slug)
        logging.debug("Season data: %s", season_data)

        # TODO in get_anime_season_title() common.py
        anime_season_title = get_anime_season_title(slug=anime_slug, season=1)

        season_episode_map = {
            f"{anime_season_title} - Season {season} - Episode {episode}"
            if season > 0
            else f"{anime_season_title} - Movie {episode}": url
            for url in season_data
            for season, episode in [get_season_and_episode_numbers(url)]
        }

        self.episode_map = season_episode_map

        episode_list = list(self.episode_map.keys())
        logging.debug("Episode list: %s", episode_list)

        self.action_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Action",
            values=["Watch", "Download", "Syncplay"],
            max_height=4,
            value=[["Watch", "Download", "Syncplay"].index(aniworld_globals.DEFAULT_ACTION)],
            scroll_exit=True
        )
        logging.debug("Action selector created")

        self.aniskip_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Aniskip",
            values=["Enable", "Disable"],
            max_height=3,
            value=[0 if aniworld_globals.DEFAULT_ANISKIP else 1],
            scroll_exit=True
        )
        logging.debug("Aniskip selector created")

        self.directory_field = self.add(
            npyscreen.TitleFilenameCombo,
            name="Directory:",
            value=aniworld_globals.DEFAULT_DOWNLOAD_PATH
        )
        logging.debug("Directory field created")

        self.language_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Language",
            values=["German Dub", "English Sub", "German Sub"],
            max_height=4,
            value=[
                ["German Dub", "English Sub", "German Sub"].index(
                    aniworld_globals.DEFAULT_LANGUAGE
                )
            ],
            scroll_exit=True
        )
        logging.debug("Language selector created")

        self.provider_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Provider",
            values=["Vidoza", "Streamtape", "VOE"],  # Doodstream broken
            max_height=3,  # 4 with Doodstream
            value=[["Vidoza", "Streamtape", "VOE"].index(aniworld_globals.DEFAULT_PROVIDER)],
            scroll_exit=True
        )
        logging.debug("Provider selector created")

        self.add(npyscreen.FixedText, value="", editable=False)  # new line
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
        logging.debug("Selected action: %s", selected_action)
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
        logging.debug("Output directory: %s", output_directory)
        if not output_directory and not self.directory_field.hidden:
            logging.debug("No output directory provided")
            npyscreen.notify_confirm("Please provide a directory.", title="Error")
            return

        selected_episodes = self.episode_selector.get_selected_objects()
        action_selected = self.action_selector.get_selected_objects()
        language_selected = self.language_selector.get_selected_objects()
        provider_selected = self.provider_selector.get_selected_objects()
        aniskip_selected = self.aniskip_selector.get_selected_objects()[0] == "Enable"

        logging.debug("Selected episodes: %s", selected_episodes)
        logging.debug("Action selected: %s", action_selected)
        logging.debug("Language selected: %s", language_selected)
        logging.debug("Provider selected: %s", provider_selected)
        logging.debug("Aniskip selected: %s", aniskip_selected)

        if not (selected_episodes and action_selected and language_selected):
            logging.debug("No episodes or action or language selected")
            npyscreen.notify_confirm("No episodes selected.", title="Selection")
            return

        lang = self.get_language_code(language_selected[0])
        logging.debug("Language code: %s", lang)
        provider_selected = self.validate_provider(provider_selected)
        logging.debug("Validated provider: %s", provider_selected)

        selected_urls = [self.episode_map[episode] for episode in selected_episodes]
        selected_str = "\n".join(selected_episodes)
        logging.debug("Selected URLs: %s", selected_urls)
        npyscreen.notify_confirm(f"Selected episodes:\n{selected_str}", title="Selection")

        if not self.directory_field.hidden:
            anime_title = format_anime_title(self.parentApp.anime_slug)
            output_directory = os.path.join(output_directory, anime_title)
            os.makedirs(output_directory, exist_ok=True)
            logging.debug("Output directory created: %s", output_directory)

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

            logging.debug("Executing with params: %s", params)
            execute(params)

        if not self.directory_field.hidden:
            logging.debug("Cleaning up leftovers in: %s", output_directory)
            clean_up_leftovers(output_directory)

        self.parentApp.setNextForm(None)
        self.parentApp.switchFormNow()

    def get_language_code(self, language):
        logging.debug("Getting language code for: %s", language)
        return {
            'German Dub': "1",
            'English Sub': "2",
            'German Sub': "3"
        }.get(language, "")

    def validate_provider(self, provider_selected):
        logging.debug("Validating provider: %s", provider_selected)
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
        logging.debug("Initializing AnimeApp with slug: %s", anime_slug)
        super().__init__()
        self.anime_slug = anime_slug

    def onStart(self):
        logging.debug("Starting AnimeApp")
        npyscreen.setTheme(CustomTheme)
        version = get_version_from_pyproject()
        update_notice = " (Update Available)" if is_version_outdated() else ""
        name = f"AniWorld-Downloader{version}{update_notice}"
        self.addForm(
            "MAIN", EpisodeForm,
            name=name
        )


def parse_arguments():
    logging.debug("Parsing command line arguments")
    parser = argparse.ArgumentParser(
        description="Parse optional command line arguments."
    )
    parser.add_argument(
        '--slug', type=str,
        help='Search query - E.g. demon-slayer-kimetsu-no-yaiba'
    )
    parser.add_argument(
        '--link', type=str,
        help='Search query - E.g. https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba'
    )
    parser.add_argument(
        '--query', type=str,
        help='Search query input - E.g. demon'
    )
    parser.add_argument(
        '--episode', type=str, nargs='+',
        help='List of episode URLs'
    )
    parser.add_argument(
        '--episode-file', type=str,
        help='File path containing a list of episode URLs'
    )
    parser.add_argument(
        '--action', type=str, choices=['Watch', 'Download', 'Syncplay'],
        default=aniworld_globals.DEFAULT_ACTION,
        help='Action to perform'
    )
    parser.add_argument(
        '--output', type=str,
        default=aniworld_globals.DEFAULT_DOWNLOAD_PATH,
        help='Download directory'
    )
    parser.add_argument(
        '--language', type=str,
        choices=['German Dub', 'English Sub', 'German Sub'],
        default=aniworld_globals.DEFAULT_LANGUAGE,
        help='Language choice'
    )
    parser.add_argument(
        '--provider', type=str,
        choices=['Vidoza', 'Streamtape', 'VOE', 'Doodstream'],
        default=aniworld_globals.DEFAULT_PROVIDER,
        help='Provider choice'
    )
    parser.add_argument(
        '--aniskip', action='store_true',
        default=aniworld_globals.DEFAULT_ANISKIP,
        help='Skip intro and outro'
    )
    parser.add_argument(
        '--keep-watching', action='store_true',
        default=aniworld_globals.DEFAULT_KEEP_WATCHING,
        help='Continue watching'
    )
    parser.add_argument(
        '--anime4k', type=str,
        choices=['High', 'Low', 'Remove'],
        help=('Set Anime4K optimised mode (High Eg.: GTX 1080, RTX 2070, '
              'RTX 3060, RX 590, Vega 56, 5700XT, 6600XT; Low Eg.: GTX 980, '
              'GTX 1060, RX 570, or Remove). This only needs to be run once '
              'to set or remove as the changes are persistent.')
    )
    parser.add_argument(
        '--syncplay-password', type=str, nargs='+',
        help='Set a syncplay room password'
    )
    parser.add_argument(
        '--only-direct-link', action='store_true',
        default=aniworld_globals.DEFAULT_ONLY_DIRECT_LINK,
        help='Output direct link'
    )
    parser.add_argument(
        '--only-command', action='store_true',
        default=aniworld_globals.DEFAULT_ONLY_COMMAND,
        help='Output command'
    )
    parser.add_argument(
        '--proxy', type=str,
        default=aniworld_globals.DEFAULT_PROXY,
        help='Set HTTP Proxy - E.g. http://0.0.0.0:8080'
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable debug mode'
    )
    parser.add_argument(
        '--version', action='store_true',
        help='Print version info'
    )
    parser.add_argument(
        '--update', type=str,
        choices=['mpv', 'yt-dlp', 'syncplay', 'all'],
        help='Update mpv, yt-dlp, syncplay, or all.'
    )
    parser.add_argument(
        '--uninstall', action='store_true',
        help='Self uninstall'
    )

    args = parser.parse_args()

    if args.version:
        banner = fR"""
 ____________________________________
< Installed aniworld{get_version_from_pyproject()} via {check_package_installation()}{" (Update Available)" if is_version_outdated() else ""}. >
 ------------------------------------
        \   ^__^
         \  (oo)\_______
            (__)\       )\/\
                ||----w |
                ||     ||
        """

        print(banner)
        sys.exit()

    if args.episode and args.episode_file:
        msg = "Cannot specify both --episode and --episode-file."
        logging.critical(msg)
        print(msg)
        sys.exit()

    if args.debug:
        os.environ['IS_DEBUG_MODE'] = '1'
        aniworld_globals.IS_DEBUG_MODE = True
        logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("Debug mode enabled")

        if platform.system() == "Darwin":
            if not is_tail_running():
                try:
                    subprocess.run(
                        [
                            "osascript",
                            "-e",
                            'tell application "Terminal" to do script "'
                            'trap exit SIGINT; '
                            'tail -f $TMPDIR/aniworld.log" '
                            'activate'
                        ],
                        check=True
                    )
                    logging.debug("Started tailing the log file in a new Terminal window.")
                except subprocess.CalledProcessError as e:
                    logging.error("Failed to start tailing the log file: %s", e)
        elif platform.system() == "Windows":
            try:
                command = 'start cmd /k "powershell -c "Get-Content -Wait $env:TEMP\\aniworld.log""'
                subprocess.run(command, check=True)
                logging.debug("Started tailing the log file in a new Terminal window.")
            except subprocess.CalledProcessError as e:
                logging.error("Failed to start tailing the log file: %s", e)

    if args.uninstall:
        self_uninstall()

    if args.update:
        update_component(args.update)
        sys.exit()

    if args.proxy:
        os.environ['HTTP_PROXY'] = args.proxy
        os.environ['HTTPS_PROXY'] = args.proxy
        aniworld_globals.DEFAULT_PROXY = args.proxy
        logging.debug("Proxy set to: %s", args.proxy)

    if args.anime4k:
        setup_anime4k(args.anime4k)

    if args.syncplay_password:
        os.environ['SYNCPLAY_PASSWORD'] = args.syncplay_password[0]
        logging.debug("Syncplay password set.")

    return args


def handle_query(args):
    logging.debug("Handling query with args: %s", args)
    if args.query and not args.episode:
        slug = search_anime(query=args.query)
        logging.debug("Found slug: %s", slug)
        season_data = get_season_data(anime_slug=slug)
        logging.debug("Season data: %s", season_data)
        episode_list = list(season_data)
        logging.debug("Episode list: %s", episode_list)

        user_input = input("Please enter the episode (e.g., S1E2): ")
        logging.debug("User input: %s", user_input)
        match = re.match(r"S(\d+)E(\d+)", user_input)
        if match:
            s = int(match.group(1))
            e = int(match.group(2))
            logging.debug("Parsed season: %d, episode: %d", s, e)

        args.episode = [f"https://aniworld.to/anime/stream/{slug}/staffel-{s}/episode-{e}"]
        logging.debug("Set episode URL: %s", args.episode)


def get_anime_title(args):
    logging.debug("Getting anime title from args: %s", args)
    if args.link:
        title = args.link.split('/')[-1]
        logging.debug("Anime title from link: %s", title)
        return title
    if args.slug:
        logging.debug("Anime title from slug: %s", args.slug)
        return args.slug
    if args.episode:
        title = args.episode[0].split('/')[5]
        logging.debug("Anime title from episode URL: %s", title)
        return title
    return None


def main():
    logging.debug("============================================")
    logging.debug("Welcome to Aniworld!")
    logging.debug("============================================\n")
    try:
        args = parse_arguments()
        logging.debug("Parsed arguments: %s", args)

        validate_link(args)
        handle_query(args)

        language = get_language_code(args.language)
        logging.debug("Language code: %s", language)

        if args.episode_file:
            animes = read_episode_file(args.episode_file)
            for slug, seasons in animes.items():
                if args.output == aniworld_globals.DEFAULT_DOWNLOAD_PATH:
                    args.output = os.path.join(args.output, slug.replace("-", " ").title())
                execute_with_params(args, seasons, slug, language)
            sys.exit()

        anime_title = get_anime_title(args)
        logging.debug("Anime title: %s", anime_title)

        selected_episodes = get_selected_episodes(args, anime_title)

        logging.debug("Selected episodes: %s", selected_episodes)

        if args.episode:
            execute_with_params(args, selected_episodes, anime_title, language)
            logging.debug("Execution complete. Exiting.")
            sys.exit()
    except KeyboardInterrupt:
        logging.debug("KeyboardInterrupt encountered. Exiting.")
        sys.exit()

    run_app_with_query(args)


def validate_link(args):
    if args.link:
        if args.link.count('/') == 5:
            logging.debug("Provided link format valid.")
        elif args.link.count('/') == 6 and args.link.endswith('/'):
            logging.debug("Provided link format valid.")
            args.link = args.link.rstrip('/')
        else:
            logging.debug("Provided link invalid.")
            args.link = None


def get_selected_episodes(args, anime_title):
    updated_list = None
    if args.keep_watching and args.episode:
        season_data = get_season_data(anime_slug=anime_title)
        logging.debug("Season data: %s", season_data)
        episode_list = list(season_data)
        logging.debug("Episode list: %s", episode_list)

        index = episode_list.index(args.episode[0])
        updated_list = episode_list[index:]
        logging.debug("Updated episode list: %s", updated_list)

    return updated_list if updated_list else args.episode


def execute_with_params(args, selected_episodes, anime_title, language):
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
    logging.debug("Executing with params: %s", params)
    execute(params=params)


def run_app_with_query(args):
    def run_app(query):
        logging.debug("Running app with query: %s", query)
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
