#!/usr/bin/env python
# encoding: utf-8

import argparse
import os
import sys
import re
import logging
import subprocess
import platform
import threading
import random
import signal
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed

import npyscreen

from aniworld.search import search_anime
from aniworld import execute, globals as aniworld_globals
from aniworld.common import (
    clear_screen,
    clean_up_leftovers,
    get_season_data,
    set_terminal_size,
    get_version,
    get_language_code,
    is_tail_running,
    get_season_and_episode_numbers,
    setup_anime4k,
    is_version_outdated,
    read_episode_file,
    check_package_installation,
    self_uninstall,
    update_component,
    get_anime_season_title,
    open_terminal_with_command,
    get_random_anime,
    show_messagebox,
    check_internet_connection,
    adventure,
    get_description,
    get_description_with_id
)
from aniworld.extractors import (
    nhentai,
    streamkiste,
    jav,
    hanime
)

from aniworld.globals import DEFAULT_DOWNLOAD_PATH


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
        'DEFAULT': 'WHITE_BLACK',
        'FORMDEFAULT': 'MAGENTA_BLACK',  # Form border
        'NO_EDIT': 'BLUE_BLACK',
        'STANDOUT': 'CYAN_BLACK',
        'CURSOR': 'WHITE_BLACK',  # Text (focused)
        'CURSOR_INVERSE': 'BLACK_WHITE',
        'LABEL': 'CYAN_BLACK',  # Form labels
        'LABELBOLD': 'CYAN_BLACK',  # Form labels (focused)
        'CONTROL': 'GREEN_BLACK',  # Items in form
        'IMPORTANT': 'GREEN_BLACK',
        'SAFE': 'GREEN_BLACK',
        'WARNING': 'YELLOW_BLACK',
        'DANGER': 'RED_BLACK',
        'CRITICAL': 'BLACK_RED',
        'GOOD': 'GREEN_BLACK',
        'GOODHL': 'GREEN_BLACK',
        'VERYGOOD': 'BLACK_GREEN',
        'CAUTION': 'YELLOW_BLACK',
        'CAUTIONHL': 'BLACK_YELLOW',
    }


# pylint: disable=too-many-ancestors, too-many-instance-attributes
class EpisodeForm(npyscreen.ActionForm):
    def create(self):
        logging.debug("Creating EpisodeForm")

        anime_slug = self.parentApp.anime_slug
        logging.debug("Anime slug: %s", anime_slug)

        anime_title = format_anime_title(anime_slug)
        logging.debug("Anime title: %s", anime_title)

        season_data = get_season_data(anime_slug)
        logging.debug("Season data: %s", season_data)

        self.timer = None
        self.start_timer()
        self.setup_signal_handling()

        anime_season_title = get_anime_season_title(slug=anime_slug, season=1)

        def process_url(url):
            logging.debug("Processing URL: %s", url)
            season, episode = get_season_and_episode_numbers(url)
            title = (
                f"{anime_season_title} - Season {season} - Episode {episode}"
                if season > 0
                else f"{anime_season_title} - Movie {episode}"
            )
            return (season, episode, title, url)

        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_url = {executor.submit(process_url, url): url for url in season_data}

            results = []
            for future in as_completed(future_to_url):
                try:
                    result = future.result(timeout=5)  # Timeout for future result
                    results.append(result)
                    logging.debug("Processed result: %s", result)
                except TimeoutError as e:
                    logging.error("Timeout processing %s: %s", future_to_url[future], e)

        sorted_results = sorted(
            results,
            key=lambda x: (x[0] if x[0] > 0 else 999, x[1])
        )

        season_episode_map = {title: url for _, _, title, url in sorted_results}
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
            values=[
                "VOE",
                "Vidmoly",
                "Doodstream",
                "Speedfiles",
                "Vidoza"
            ],
            max_height=6,
            value=[
                [
                    "VOE",
                    "Vidmoly",
                    "Doodstream",
                    "Speedfiles",
                    "Vidoza"
                ].index(aniworld_globals.DEFAULT_PROVIDER)
            ],
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

        self.add(npyscreen.FixedText, value="")

        self.display_text = False

        self.toggle_button = self.add(
            npyscreen.ButtonPress,
            name="Description",
            max_height=1,
            when_pressed_function=self.go_to_second_form,
            scroll_exit=True
        )

        self.action_selector.when_value_edited = self.update_directory_visibility
        logging.debug("Set update_directory_visibility as callback for action_selector")

    def setup_signal_handling(self):
        def signal_handler(_signal_number, _frame):
            try:
                self.parentApp.switchForm(None)
            except AttributeError:
                pass
            self.cancel_timer()
            sys.exit()

        signal.signal(signal.SIGINT, signal_handler)
        logging.debug("Signal handler for SIGINT registered")

    def start_timer(self):
        self.timer = threading.Timer(  # pylint: disable=attribute-defined-outside-init
            random.randint(600, 900),
            self.delayed_message_box
        )
        self.timer.start()

    def cancel_timer(self):
        if self.timer and self.timer.is_alive():
            self.timer.cancel()
            logging.debug("Timer canceled")

    def delayed_message_box(self):
        show_messagebox("Are you still there?", "Uhm...", "info")

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
        self.cancel_timer()
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
            output_directory = os.path.join(output_directory)
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
                'anime_title': format_anime_title(self.parentApp.anime_slug),
                'anime_slug': self.parentApp.anime_slug
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
        valid_providers = ["Vidoza", "Streamtape", "VOE", "Doodstream", "Speedfiles"]
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
        self.cancel_timer()
        self.parentApp.setNextForm(None)

    def go_to_second_form(self):
        self.parentApp.switchForm("SECOND")


# pylint: disable=R0901
class SecondForm(npyscreen.ActionFormV2):
    def create(self):
        anime_slug = self.parentApp.anime_slug
        anime_title = format_anime_title(anime_slug)

        text_content1 = get_description(anime_slug)
        text_content2 = get_description_with_id(anime_title, 1)

        wrapped_text1 = "\n".join(textwrap.wrap(text_content1, width=100))
        wrapped_text2 = "\n".join(textwrap.wrap(text_content2, width=100))

        text_content = f"{wrapped_text1}\n\n{wrapped_text2}"

        self.expandable_text = self.add(
            npyscreen.MultiLineEdit,
            value=text_content,
            max_height=None,
            editable=False
        )

    def on_ok(self):
        self.parentApp.switchForm("MAIN")

    def on_cancel(self):
        self.parentApp.switchForm("MAIN")


class AnimeApp(npyscreen.NPSAppManaged):
    def __init__(self, anime_slug):
        logging.debug("Initializing AnimeApp with slug: %s", anime_slug)
        super().__init__()
        self.anime_slug = anime_slug

    def onStart(self):
        logging.debug("Starting AnimeApp")
        npyscreen.setTheme(CustomTheme)
        version = get_version()
        update_notice = " (Update Available)" if is_version_outdated() else ""
        name = f"AniWorld-Downloader{version}{update_notice}"
        self.addForm(
            "MAIN", EpisodeForm,
            name=name
        )
        self.addForm("SECOND", SecondForm, name="Description")


# pylint: disable=R0912, R0915
def parse_arguments():
    logging.debug("Parsing command line arguments")

    parser = argparse.ArgumentParser(
        description="Parse optional command line arguments."
    )

    # General options
    general_group = parser.add_argument_group('General Options')
    general_group.add_argument(
        '-v', '--version',
        action='store_true',
        help='Print version info'
    )
    general_group.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    general_group.add_argument(
        '-u', '--uninstall',
        action='store_true',
        help='Self uninstall'
    )
    general_group.add_argument(
        '-U', '--update',
        type=str,
        choices=['mpv', 'yt-dlp', 'syncplay', 'all'],
        help='Update mpv, yt-dlp, syncplay, or all.'
    )

    # Search options
    search_group = parser.add_argument_group('Search Options')
    search_group.add_argument(
        '-s', '--slug',
        type=str,
        help='Search query - E.g. demon-slayer-kimetsu-no-yaiba'
    )
    search_group.add_argument(
        '-l', '--link',
        type=str,
        help='Search query - E.g. https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba'
    )
    search_group.add_argument(
        '-q', '--query',
        type=str,
        help='Search query input - E.g. demon'
    )

    # Episode options
    episode_group = parser.add_argument_group('Episode Options')
    episode_group.add_argument(
        '-e', '--episode',
        type=str,
        nargs='+',
        help='List of episode URLs'
    )
    episode_group.add_argument(
        '-f', '--episode-file',
        type=str,
        help='File path containing a list of episode URLs'
    )
    episode_group.add_argument(
        '-lf', '--episode-local',
        action='store_true',
        help='NOT IMPLEMENTED YET - Use local episode files instead of URLs'
    )

    # Action options
    action_group = parser.add_argument_group('Action Options')
    action_group.add_argument(
        '-a', '--action',
        type=str,
        choices=['Watch', 'Download', 'Syncplay'],
        default=aniworld_globals.DEFAULT_ACTION,
        help='Action to perform'
    )
    action_group.add_argument(
        '-o', '--output',
        type=str,
        help='Download directory E.g. /Users/phoenixthrush/Downloads',
        default=DEFAULT_DOWNLOAD_PATH
    )
    action_group.add_argument(
        '-O', '--output-directory',
        type=str,
        help=(
            'Final download directory, e.g., ExampleDirectory. '
            'Defaults to anime name if not specified.'
        )
    )
    action_group.add_argument(
        '-L', '--language',
        type=str,
        choices=['German Dub', 'English Sub', 'German Sub'],
        default=aniworld_globals.DEFAULT_LANGUAGE,
        help='Language choice'
    )
    action_group.add_argument(
        '-p', '--provider',
        type=str,
        choices=['Vidoza', 'Streamtape', 'VOE', 'Doodstream', 'Vidmoly', 'Doodstream', "Speedfiles"],
        help='Provider choice'
    )

    # Anime4K options
    anime4k_group = parser.add_argument_group('Anime4K Options')
    anime4k_group.add_argument(
        '-A', '--anime4k',
        type=str,
        choices=['High', 'Low', 'Remove'],
        help=(
            'Set Anime4K optimised mode (High, e.g., GTX 1080, RTX 2070, RTX 3060, '
            'RX 590, Vega 56, 5700XT, 6600XT; Low, e.g., GTX 980, GTX 1060, RX 570, '
            'or Remove).'
        )
    )

    # Syncplay options
    syncplay_group = parser.add_argument_group('Syncplay Options')
    syncplay_group.add_argument(
        '-sH', '--syncplay-hostname',
        type=str,
        help='Set syncplay hostname'
    )
    syncplay_group.add_argument(
        '-sU', '--syncplay-username',
        type=str,
        help='Set syncplay username'
    )
    syncplay_group.add_argument(
        '-sR', '--syncplay-room',
        type=str,
        help='Set syncplay room'
    )
    syncplay_group.add_argument(
        '-sP', '--syncplay-password',
        type=str,
        nargs='+',
        help='Set a syncplay room password'
    )

    # Miscellaneous options
    misc_group = parser.add_argument_group('Miscellaneous Options')
    misc_group.add_argument(
        '-k', '--aniskip',
        action='store_true',
        help='Skip intro and outro'
    )
    misc_group.add_argument(
        '-K', '--keep-watching',
        action='store_true',
        help='Continue watching'
    )
    misc_group.add_argument(
        '-r', '--random-anime',
        type=str,
        nargs='?',
        const="all",
        help='Select random anime (default genre is "all", Eg.: Drama)'
    )
    misc_group.add_argument(
        '-D', '--only-direct-link',
        action='store_true',
        help='Output direct link'
    )
    misc_group.add_argument(
        '-C', '--only-command',
        action='store_true',
        help='Output command'
    )
    misc_group.add_argument(
        '-x', '--proxy',
        type=str,
        help='Set HTTP Proxy - E.g. http://0.0.0.0:8080'
    )
    misc_group.add_argument(
        '-w', '--use-playwright',
        action='store_true',
        help='Bypass fetching with a headless browser using Playwright instead (EXPERIMENTAL!!!)'
    )

    args = parser.parse_args()

    if not args.provider:
        if args.action == "Download":
            args.provider = aniworld_globals.DEFAULT_PROVIDER
        else:
            args.provider = aniworld_globals.DEFAULT_PROVIDER_WATCH

    if args.version:
        update_status = " (Update Available)" if is_version_outdated() else ""
        divider = "-------------------" if is_version_outdated() else ""
        banner = fR"""
     ____________________________________{divider}
    < Installed aniworld {get_version()} via {check_package_installation()}{update_status}. >
     ------------------------------------{divider}
            \\   ^__^
             \\  (oo)\\_______
                (__)\\       )\\/\\
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
        logging.debug("============================================")
        logging.debug("Welcome to Aniworld!")
        logging.debug("============================================\n")
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
                            'tail -f -n +1 $TMPDIR/aniworld.log" '
                            'activate'
                        ],
                        check=True
                    )
                    logging.debug("Started tailing the log file in a new Terminal window.")
                except subprocess.CalledProcessError as e:
                    logging.error("Failed to start tailing the log file: %s", e)
        elif platform.system() == "Windows":
            try:
                command = ('start cmd /c "powershell -NoExit -c Get-Content '
                           '-Wait \\"$env:TEMP\\aniworld.log\\""')
                subprocess.Popen(command, shell=True)  # pylint: disable=consider-using-with
                logging.debug("Started tailing the log file in a new Terminal window.")
            except subprocess.CalledProcessError as e:
                logging.error("Failed to start tailing the log file: %s", e)
        elif platform.system() == "Linux":
            open_terminal_with_command('tail -f -n +1 /tmp/aniworld.log')

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

    if args.syncplay_hostname:
        os.environ['SYNCPLAY_HOSTNAME'] = args.syncplay_hostname
        logging.debug("Syncplay hostname set.")

    if args.syncplay_username:
        os.environ['SYNCPLAY_USERNAME'] = args.syncplay_username
        logging.debug("Syncplay username set.")

    if args.syncplay_room:
        os.environ['SYNCPLAY_ROOM'] = args.syncplay_room
        logging.debug("Syncplay room set.")

    if args.output_directory:
        os.environ['OUTPUT_DIRECTORY'] = args.output_directory
        logging.debug("Output directory set.")

    if args.use_playwright:
        os.environ['USE_PLAYWRIGHT'] = str(args.use_playwright)
        logging.debug("Playwright set.")

    if not args.slug and args.random_anime:
        args.slug = get_random_anime(args.random_anime)

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
    if not check_internet_connection():
        clear_screen()

        logging.disable(logging.CRITICAL)
        adventure()

        sys.exit()
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
                execute_with_params(args, seasons, slug, language, anime_slug=slug)
            sys.exit()

        anime_title = get_anime_title(args)
        logging.debug("Anime title: %s", anime_title)

        selected_episodes = get_selected_episodes(args, anime_title)

        logging.debug("Selected episodes: %s", selected_episodes)

        if args.episode:
            for episode_url in args.episode:
                slug = episode_url.split('/')[-1]
                execute_with_params(args, selected_episodes, anime_title, language, anime_slug=slug)
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


def check_other_extractors(episode_urls: list):
    logging.debug("Those are all urls: %s", episode_urls)

    jav_urls = []
    nhentai_urls = []
    streamkiste_urls = []
    hanime_urls = []
    remaining_urls = []

    for episode in episode_urls:
        if episode.startswith("https://jav.guru/"):
            jav_urls.append(episode)
        elif episode.startswith("https://nhentai.net/g/"):
            nhentai_urls.append(episode)
        elif episode.startswith("https://streamkiste.tv/movie/"):
            streamkiste_urls.append(episode)
        elif episode.startswith("https://hanime.tv/videos/hentai/"):
            hanime_urls.append(episode)
        else:
            remaining_urls.append(episode)

    logging.debug("Jav URLs: %s", jav_urls)
    logging.debug("Nhentai URLs: %s", nhentai_urls)
    logging.debug("Hanime URLs: %s", hanime_urls)
    logging.debug("Streamkiste URLs: %s", streamkiste_urls)

    for jav_url in jav_urls:
        logging.info("Processing JAV URL: %s", jav_url)
        jav(jav_url)

    for nhentai_url in nhentai_urls:
        logging.info("Processing Nhentai URL: %s", nhentai_url)
        nhentai(nhentai_url)

    for hanime_url in hanime_urls:
        logging.info("Processing hanime URL: %s", hanime_url)
        hanime(hanime_url)

    for streamkiste_url in streamkiste_urls:
        logging.info("Processing Streamkiste URL: %s", streamkiste_url)
        streamkiste(streamkiste_url)

    return remaining_urls


def execute_with_params(args, selected_episodes, anime_title, language, anime_slug):
    selected_episodes = check_other_extractors(selected_episodes)
    logging.debug("Aniworld episodes: %s", selected_episodes)

    params = {
        'selected_episodes': selected_episodes,
        'provider_selected': args.provider,
        'action_selected': args.action,
        'aniskip_selected': args.aniskip,
        'lang': language,
        'output_directory': args.output,
        'anime_title': anime_title.replace('-', ' ').title(),
        'anime_slug': anime_slug,
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
