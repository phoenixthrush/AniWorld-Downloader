#!/usr/bin/env python
# encoding: utf-8

from json import loads, JSONDecodeError
from re import findall
from shutil import which, copy
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request
import argparse
import curses
import getpass
import glob
import os
import platform
import shlex
import subprocess
import sys

from bs4 import BeautifulSoup
import npyscreen

from aniworld import doodstream_get_direct_link
from aniworld import streamtape_get_direct_link
from aniworld import vidoza_get_direct_link
from aniworld import voe_get_direct_link
from aniworld import aniskip
from aniworld import make_request


def check_dependencies(use_yt_dlp=False, use_mpv=False, use_syncplay=False):
    dependencies = []

    if use_yt_dlp:
        dependencies.append("yt-dlp")
    if use_mpv:
        dependencies.append("mpv")
    if use_syncplay:
        if platform.system() == "nt":
            dependencies.append("SyncplayConsole")
        else:
            dependencies.append("syncplay")

    missing = [dep for dep in dependencies if which(dep) is None]
    if missing:
        print(f"Missing dependencies: {', '.join(missing)} in path. Please install and try again.")
        sys.exit(1)


def clear_screen():
    current_os = platform.system()

    if current_os == "Windows":
        os.system("cls")
    else:
        os.system("clear")


def search_anime(slug=None, link=None) -> None:
    """
    This returns the anime slug for example: demon-slayer-kimetsu-no-yaiba
    """
    clear_screen()

    response = None

    if slug:
        response = make_request.get(f"https://aniworld.to/anime/stream/{slug}")
    elif link:
        try:
            response = make_request.get(link)
        except ValueError:
            link = None
            response = None

    if slug or link:
        not_found = "Die gewünschte Serie wurde nicht gefunden oder ist im Moment deaktiviert."
        if response and not_found in response.decode():
            slug = None
            link = None

    if slug:
        return slug
    if link:
        return link.split('/')[-1]

    keyword = input("Search for a series: ")

    while True:
        clear_screen()
        encoded_keyword = quote(keyword)
        url = f"https://aniworld.to/ajax/seriesSearch?keyword={encoded_keyword}"

        json_data = fetch_data(url)

        if not isinstance(json_data, list) or not json_data:
            print("No series found. Try again...")
            keyword = input("Search for a series: ")
            continue

        selected_slug = curses.wrapper(display_menu, json_data)

        return selected_slug


def fetch_data(url: str) -> list:
    try:
        with urlopen(url) as response:
            data = response.read()
    except HTTPError as e:
        print(f"HTTP error occurred: {e.code} {e.reason}")
        return None
    except URLError as e:
        print(f"URL error occurred: {e.reason}")
        return None

    if data is None:
        print("Failed to fetch data.")
        sys.exit(1)

    decoded_data = data.decode()

    if "Deine Anfrage wurde als Spam erkannt." in decoded_data:
        print("Your IP address is blacklisted. Please use a VPN or try again later.")
        sys.exit(1)

    try:
        return loads(decoded_data)
    except JSONDecodeError:
        print("Failed to decode JSON response.")
        return None


def display_menu(stdscr, animes):
    stdscr.clear()

    current_row = 0
    num_rows = len(animes)

    while True:
        stdscr.clear()
        for idx, anime in enumerate(animes):
            x = 0
            y = idx
            if idx == current_row:
                stdscr.attron(curses.A_REVERSE)
                name = anime.get('name', 'No Name')
                year = anime.get('productionYear', 'No Year')
                stdscr.addstr(y, x, f"{name} {year}")
                stdscr.attroff(curses.A_REVERSE)
            else:
                name = anime.get('name', 'No Name')
                year = anime.get('productionYear', 'No Year')
                stdscr.addstr(y, x, f"{name} {year}")

        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_DOWN:
            current_row = (current_row + 1) % num_rows
        elif key == curses.KEY_UP:
            current_row = (current_row - 1 + num_rows) % num_rows
        elif key == ord('\n'):
            selected_anime = animes[current_row]
            return selected_anime.get('link', 'No Link')
        elif key == ord('q'):
            break

    return None


def providers(soup):
    hoster_site_video = soup.find(class_='hosterSiteVideo').find('ul', class_='row')
    episode_links = hoster_site_video.find_all('li')

    extracted_data = {}
    for link in episode_links:
        data_lang_key = int(link.get('data-lang-key'))
        redirect_link = link.get('data-link-target')
        h4_text = link.find('h4').text.strip()

        if h4_text not in extracted_data:
            extracted_data[h4_text] = {}

        extracted_data[h4_text][data_lang_key] = f"https://aniworld.to{redirect_link}"

    return extracted_data


# TODO hella goofy needs dictionary as parameter
def execute(
    selected_episodes: list,
    provider_selected,
    action_selected,
    aniskip_selected,
    lang,
    output_directory,
    anime_title,
    only_direct_link=False,
    only_command=False,
    debug=False
):
    for episode_url in selected_episodes:
        episode_html = make_request.get(episode_url)
        if episode_html is None:
            continue
        soup = BeautifulSoup(episode_html, 'html.parser')

        if debug:
            print(f"Episode Soup: {soup.prettify}")

        episodeGermanTitle = soup.find('span', class_='episodeGermanTitle').text
        episodeEnglishTitle = soup.find('small', class_='episodeEnglishTitle').text
        episode_title = f"{episodeGermanTitle} / {episodeEnglishTitle}"

        anime_title = soup.find('div', class_='hostSeriesTitle').text

        if debug:
            print(f"Episode Title: {episode_title}")

        data = providers(soup)

        if debug:
            print(f"Provider Data: {data}")

        provider_mapping = {
            "Vidoza": vidoza_get_direct_link,
            "VOE": voe_get_direct_link,
            "Doodstream": doodstream_get_direct_link,
            "Streamtape": streamtape_get_direct_link
        }

        if provider_selected in data:
            for language in data[provider_selected]:
                if language == int(lang):
                    matches = findall(r'\d+', episode_url)
                    season_number = matches[-2]
                    episode_number = matches[-1]

                    action = action_selected

                    if aniskip_selected:
                        script_directory = os.path.dirname(os.path.abspath(__file__))
                        source_path = os.path.join(script_directory, 'aniskip', 'skip.lua')

                        if os.name == 'nt':
                            destination_path = os.path.join(
                                os.environ['APPDATA'], 'mpv', 'scripts', 'skip.lua'
                            )
                        else:
                            destination_path = os.path.expanduser(
                                '~/.config/mpv/scripts/skip.lua'
                            )

                        if not os.path.exists(destination_path):
                            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                            copy(source_path, destination_path)

                    provider_function = provider_mapping[provider_selected]
                    request_url = data[provider_selected][language]
                    html_content = make_request.get(request_url)
                    soup = BeautifulSoup(html_content, 'html.parser')

                    if debug:
                        print(f"Episode Data: {soup.prettify}")

                    link = provider_function(soup)

                    if only_direct_link:
                        print(link)
                        sys.exit()

                    mpv_title = f"{anime_title} S{season_number}E{episode_number} - {episode_title}"

                    if action == "Watch":
                        check_dependencies(use_mpv=True)
                        if not only_command:
                            print(f"Playing '{mpv_title}")
                        command = [
                            "mpv",
                            link,
                            "--fs",
                            "--quiet",
                            "--really-quiet",
                            f"--force-media-title={mpv_title}"
                        ]
                        if aniskip_selected:
                            if season_number != 1:
                                print("Warning: This is not season 1.\n"
                                      "Aniskip timestamps may be incorrect.\n"
                                      "This will be fixed in future!")
                            skip_options = aniskip(anime_title, episode_number)
                            skip_options_list = skip_options.split(' --')
                            result = [
                                f"--{opt}" if not opt.startswith('--') else opt
                                for opt in skip_options_list
                            ]
                            command.extend(result)

                        if only_command:
                            print(' '.join(shlex.quote(arg) for arg in command))
                        else:
                            subprocess.run(command, check=True)
                    elif action == "Download":
                        check_dependencies(use_yt_dlp=True)
                        file_name = f"{mpv_title}.mp4"
                        file_path = os.path.join(output_directory, file_name)
                        if not only_command:
                            print(f"Downloading to '{file_path}'")

                        output_file = os.path.join(
                            output_directory,
                            f"{mpv_title}.mp4"
                        )

                        command = [
                            "yt-dlp",
                            "--fragment-retries",
                            "infinite",
                            "--concurrent-fragments",
                            "4",
                            "-o", output_file,
                            "--quiet",
                            "--progress",
                            "--no-warnings",
                            link
                        ]
                        if only_command:
                            print(' '.join(shlex.quote(arg) for arg in command))
                        else:
                            subprocess.run(command, check=True)
                    elif action == "Syncplay":
                        check_dependencies(use_syncplay=True)
                        if platform.system() == "Windows":
                            syncplay = "SyncplayConsole"
                        else:
                            syncplay = "syncplay"

                        command = [
                            syncplay,
                            "--no-gui",
                            "--host", "syncplay.pl:8997",
                            "--name", getpass.getuser(),
                            "--room", mpv_title,
                            "--player-path", which("mpv"),
                            link,
                            "--", "--fs",
                            "--", f"--force-media-title={mpv_title}"
                        ]
                        if aniskip_selected:
                            if season_number != 1:
                                print("Warning: This is not season 1.\n"
                                      "Aniskip timestamps may be incorrect.\n"
                                      "This will be fixed in future!")
                            skip_options = aniskip(anime_title, episode_number)
                            skip_options_list = skip_options.split(' --')
                            result = [
                                f"--{opt}" if not opt.startswith('--') else opt
                                for opt in skip_options_list
                            ]
                            command.extend(result)
                        if only_command:
                            print(' '.join(shlex.quote(arg) for arg in command))
                        else:
                            subprocess.run(command, check=True)
                        break


class AnimeDownloader:
    BASE_URL_TEMPLATE = "https://aniworld.to/anime/stream/{anime}/"

    def __init__(self, anime_slug):
        self.anime_slug = anime_slug
        self.anime_title = self.format_anime_title(anime_slug)
        self.base_url = self.BASE_URL_TEMPLATE.format(anime=anime_slug)
        self.season_data = self.get_season_data()

    @staticmethod
    def format_anime_title(anime_slug):
        try:
            return anime_slug.replace("-", " ").title()
        except AttributeError:
            sys.exit()

    def make_request(self, url):
        headers = {
            'User-Agent': (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/58.0.3029.110 Safari/537.3"
            )
        }
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=10) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as error:
            print(f"Request failed: {error}")
            return None

    def clean_up_leftovers(self, directory):
        patterns = ['*.part', '*.ytdl', '*.part-Frag*']

        leftover_files = []
        for pattern in patterns:
            leftover_files.extend(glob.glob(os.path.join(directory, pattern)))

        for file_path in leftover_files:
            try:
                os.remove(file_path)
                print(f"Removed leftover file: {file_path}")
            except FileNotFoundError:
                print(f"File not found: {file_path}")
            except PermissionError:
                print(f"Permission denied when trying to remove file: {file_path}")
            except OSError as e:
                print(f"OS error occurred while removing file {file_path}: {e}")

        if not os.listdir(directory):
            try:
                os.rmdir(directory)
                print(f"Removed empty directory: {directory}")
            except FileNotFoundError:
                print(f"Directory not found: {directory}")
            except PermissionError:
                print(f"Permission denied when trying to remove directory: {directory}")
            except OSError as e:
                print(f"OS error occurred while removing directory {directory}: {e}")

    def get_season_episodes(self, season_url):
        season_url_old = season_url
        season_url = season_url[:-2]
        season_html = self.make_request(season_url)
        if season_html is None:
            return []
        season_soup = BeautifulSoup(season_html, 'html.parser')
        episodes = season_soup.find_all('meta', itemprop='episodeNumber')
        episode_numbers = [int(episode['content']) for episode in episodes]
        highest_episode = max(episode_numbers, default=None)

        season_suffix = f"/staffel-{season_url_old.split('/')[-1]}"
        episode_urls = [
            f"{season_url}{season_suffix}/episode-{num}"
            for num in range(1, highest_episode + 1)
        ]

        return episode_urls

    def get_season_data(self):
        main_html = self.make_request(self.base_url)
        if main_html is None:
            sys.exit("Failed to retrieve main page.")

        soup = BeautifulSoup(main_html, 'html.parser')
        if 'Deine Anfrage wurde als Spam erkannt.' in soup.text:
            sys.exit("Your IP-Address is blacklisted, please use a VPN or try later.")

        season_meta = soup.find('meta', itemprop='numberOfSeasons')
        number_of_seasons = int(season_meta['content']) if season_meta else 0
        if soup.find('a', title='Alle Filme'):
            number_of_seasons -= 1

        season_data = {}
        for i in range(1, number_of_seasons + 1):
            season_url = f"{self.base_url}{i}"
            season_data[i] = self.get_season_episodes(season_url)

        return season_data


class EpisodeForm(npyscreen.ActionForm):
    def create(self):
        episode_list = [
            url
            for season, episodes in self.parentApp.anime_downloader.season_data.items()
            for url in episodes
        ]

        self.action_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Watch, Download or Syncplay",
            values=["Watch", "Download", "Syncplay"],
            max_height=4,
            value=[1],
            scroll_exit=True
        )

        self.aniskip_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Use Aniskip (Skip Intro & Outro)",
            values=["Yes", "No"],
            max_height=3,
            value=[1],
            scroll_exit=True
        )

        self.directory_field = self.add(
            npyscreen.TitleFilenameCombo,
            name="Directory:",
            value=os.path.join(os.path.expanduser('~'), 'Downloads')
        )

        self.language_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Language Options",
            values=["German Dub", "English Sub", "German Sub"],
            max_height=4,
            value=[2],
            scroll_exit=True
        )

        self.provider_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Provider Options (VOE recommended for Downloading)",
            values=["Vidoza", "Streamtape", "VOE", "Doodstream"],
            max_height=4,
            value=[0],
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
        selected_action = self.action_selector.get_selected_objects()
        if selected_action and selected_action[0] == "Watch" or selected_action[0] == "Syncplay":
            self.directory_field.hidden = True
            self.aniskip_selector.hidden = False
        else:
            self.directory_field.hidden = False
            self.aniskip_selector.hidden = True
        self.display()

    def on_ok(self):  # TODO - refactor the code to reduce complexity
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

        lang = language_selected[0]

        lang = lang.replace('German Dub', "1")
        lang = lang.replace('English Sub', "2")
        lang = lang.replace('German Sub', "3")

        # doodstream currently broken
        valid_providers = ["Vidoza", "Streamtape", "VOE"]

        while provider_selected[0] not in valid_providers:
            message = (
                "Doodstream is currently broken.\n"
                "Falling back to Vidoza."
            )
            title = "Provider Error"

            npyscreen.notify_confirm(message, title=title)
            self.provider_selector.value = 0

            provider_selected = ["Vidoza"]

        if selected_episodes and action_selected and language_selected:
            selected_str = "\n".join(selected_episodes)
            npyscreen.notify_confirm(f"Selected episodes:\n{selected_str}", title="Selection")

            if not self.directory_field.hidden:
                anime_title = self.parentApp.anime_downloader.anime_title
                output_directory = os.path.join(output_directory, anime_title)
                os.makedirs(output_directory, exist_ok=True)

            execute(
                selected_episodes=selected_episodes,
                provider_selected=provider_selected[0],
                action_selected=action_selected[0],
                aniskip_selected=aniskip_selected[0],
                lang=lang,
                output_directory=output_directory,
                anime_title=self.parentApp.anime_downloader.anime_title
            )

            if not self.directory_field.hidden:
                self.parentApp.anime_downloader.clean_up_leftovers(output_directory)

            self.parentApp.setNextForm(None)
            self.parentApp.switchFormNow()
        else:
            npyscreen.notify_confirm("No episodes selected.", title="Selection")

    def on_cancel(self):
        self.parentApp.setNextForm(None)


class AnimeApp(npyscreen.NPSAppManaged):
    def __init__(self, anime_slug):
        super().__init__()
        self.anime_downloader = AnimeDownloader(anime_slug)

    def onStart(self):
        self.addForm("MAIN", EpisodeForm, name="Anime Downloader")


def main():
    try:
        parser = argparse.ArgumentParser(description="Parse optional command line arguments.")
        parser.add_argument(
            '--slug',
            type=str,
            help='Search query - E.g. demon-slayer-kimetsu-no-yaiba'
        )
        parser.add_argument(
            '--link',
            type=str,
            help=(
                'Search query - E.g. '
                'https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba'
            )
        )
        parser.add_argument(
            '--episode',
            type=str,
            nargs='+',
            help=(
                'List of episode URLs - E.g. '
                'https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/ '
                'staffel-1/episode-1, '
                'https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/ '
                'staffel-1/episode-2'
            )
        )
        parser.add_argument(
            '--action',
            type=str,
            choices=['Watch', 'Download', 'Syncplay'],
            default='Watch',
            help=(
                'Action to perform - E.g. '
                'Watch, Download, Syncplay'
            )
        )
        parser.add_argument(
            '--output',
            type=str,
            default=os.path.join(os.path.expanduser('~'), 'Downloads'),
            help='Download directory (default: ~/Downloads)'
        )
        parser.add_argument(
            '--language',
            type=str,
            choices=['German Dub', 'English Sub', 'German Sub'],
            default='German Sub',
            help='Language choice - E.g. German Dub, English Sub, German Sub'
        )
        parser.add_argument(
            '--provider',
            type=str,
            choices=['Vidoza', 'Streamtape', 'VOE', 'Doodstream'],
            default='Vidoza',
            help='Provider choice - E.g. Vidoza, Streamtape, VOE, Doodstream'
        )
        parser.add_argument('--aniskip', action='store_true', help='Skip anime opening and ending')
        parser.add_argument('--only-direct-link', action='store_true', help='Output direct link')
        parser.add_argument('--only-command', action='store_true', help='Output command')
        parser.add_argument('--proxy', type=str, help='Set HTTP Proxy (not working yet)')  # TODO
        parser.add_argument('--debug', action='store_true', help='Enable debug mode')

        args = parser.parse_args()

        language = None
        anime_title = None
        if args.link:
            anime_title = args.link.split('/')[-1].replace('-', ' ').title()
        elif args.slug:
            anime_title = args.slug.replace('-', ' ').title()
        elif args.episode:
            anime_title = args.episode[0].split('/')[5].replace('-', ' ').title()

        if args.language:
            language = {
                "German Dub": "1",
                "English Sub": "2",
                "German Sub": "3"
            }.get(args.language, "")

        if args.episode:
            execute(
                selected_episodes=args.episode,
                provider_selected=args.provider,
                action_selected=args.action,
                aniskip_selected=args.aniskip,
                lang=language,
                output_directory=args.output,
                anime_title=anime_title,
                only_direct_link=args.only_direct_link,
                only_command=args.only_command,
                debug=args.debug
            )
            sys.exit()
    except KeyboardInterrupt:
        sys.exit()

    def run_app(query):
        app = AnimeApp(query)
        app.run()

    try:
        query = search_anime(slug=args.slug, link=args.link)
        keep_running = True

        while keep_running:
            try:
                run_app(query)
                keep_running = False
            except npyscreen.wgwidget.NotEnoughSpaceForWidget:
                clear_screen()
                print("Please increase your current terminal size.")
                sleep(1)
        sys.exit()
    except KeyboardInterrupt:
        sys.exit()


if __name__ == "__main__":
    main()
