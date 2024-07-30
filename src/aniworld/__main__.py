#!/usr/bin/env python
# encoding: utf-8

from bs4 import BeautifulSoup
from json import loads, JSONDecodeError
from re import findall, sub
from shutil import which, copy
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen, Request
import configparser
import curses
import glob
import npyscreen
import os
import platform
import sys

from aniworld import doodstream_get_direct_link
from aniworld import streamtape_get_direct_link
from aniworld import vidoza_get_direct_link
from aniworld import voe_get_direct_link

from aniworld import anime_skip

def check_dependencies():
    dependencies = ["yt-dlp", "mpv"]
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

def read_config():
    config = configparser.ConfigParser()
    source_file_dir = os.path.dirname(os.path.abspath(__file__))

    current_working_dir = os.getcwd()
    config_file_name = '.aniworld-downloader.ini'

    source_file_config_path = os.path.join(source_file_dir, config_file_name)
    cwd_config_path = os.path.join(current_working_dir, config_file_name)

    if os.path.exists(source_file_config_path):
        config.read(source_file_config_path)
    elif os.path.exists(cwd_config_path):
        config.read(cwd_config_path)
    else:
        print("Configuration file not found.")
        return None

    for section in config.sections():
        print(f"[{section}]")
        for key, value in config.items(section):
            print(f"{key} = {value}")

    """
    config = read_config()
    if config:
        if 'Provider' in config:
            provider = config['Provider'].get('Provider', 'Vidoza')
    """
    
    return config

def search_anime() -> None:
    clear_screen()
    while True:
        keyword = input("Search for a series: ")
        clear_screen()
        encoded_keyword = quote(keyword)
        url = f"https://aniworld.to/ajax/seriesSearch?keyword={encoded_keyword}"

        json_data = fetch_data(url)

        if not isinstance(json_data, list) or not json_data:
            print("No series found. Try again...")
            continue

        selected_link = curses.wrapper(display_menu, json_data)

        return selected_link

def fetch_data(url: str) -> list:
    try:
        with urlopen(url) as response:
            data = response.read()
    except Exception as e:
        print(f"An error occurred: {e}")
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
    height, width = stdscr.getmaxyx()

    current_row = 0
    num_rows = len(animes)

    while True:
        stdscr.clear()
        for idx, anime in enumerate(animes):
            x = 0
            y = idx
            if idx == current_row:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(y, x, f"{anime.get('name', 'No Name')} ({anime.get('productionYear', 'No Year')})")
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(y, x, f"{anime.get('name', 'No Name')} ({anime.get('productionYear', 'No Year')})")

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


class AnimeDownloader:
    BASE_URL_TEMPLATE = "https://aniworld.to/anime/stream/{anime}/"

    def __init__(self, anime_slug):
        self.anime_slug = anime_slug
        self.anime_title = self.format_anime_title(anime_slug)
        self.base_url = self.BASE_URL_TEMPLATE.format(anime=anime_slug)
        self.season_data = self.get_season_data()

    @staticmethod
    def format_anime_title(anime_slug):
        return anime_slug.replace("-", " ").title()

    def make_request(self, url):
        headers = {'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"}
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=10) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as error:
            print(f"Request failed: {error}")
            return None

    def providers(self, soup):
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

    def clean_up_leftovers(self, directory):
        leftover_files = glob.glob(os.path.join(directory, '*.part'))
        for file_path in leftover_files:
            try:
                os.remove(file_path)
                print(f"Removed leftover file: {file_path}")
            except Exception as e:
                print(f"Error removing file {file_path}: {e}")

        if not os.listdir(directory):
            try:
                os.rmdir(directory)
                print(f"Removed empty directory: {directory}")
            except Exception as e:
                print(f"Error removing directory {directory}: {e}")

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
        return [f"{season_url}/staffel-{season_url_old.split('/')[-1]}/episode-{num}" for num in range(1, highest_episode + 1)]

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
        episode_list = [url for season, episodes in self.parentApp.anime_downloader.season_data.items() for url in episodes]
        self.action_selector = self.add(npyscreen.TitleSelectOne, name="Watch or Download", values=["Watch", "Download"], max_height=4, value=[1], scroll_exit=True)
        self.aniskip_selector = self.add(npyscreen.TitleSelectOne, name="Use Aniskip", values=["Yes", "No"], max_height=2, value=[0], scroll_exit=True)
        self.directory_field = self.add(npyscreen.TitleFilenameCombo, name="Directory:", value=os.path.join(os.path.expanduser('~'), 'Downloads'))
        self.language_selector = self.add(npyscreen.TitleSelectOne, name="Language Options", values=["German Dub", "English Sub", "German Sub"], max_height=4, value=[2], scroll_exit=True)
        self.provider_selector = self.add(npyscreen.TitleSelectOne, name="Provider Options", values=["Vidoza", "Streamtape", "Doodstream", "VOE"], max_height=4, value=[0], scroll_exit=True)
        self.episode_selector = self.add(npyscreen.TitleMultiSelect, name="Select Episodes", values=episode_list, max_height=7)

        self.action_selector.when_value_edited = self.update_directory_visibility

    def update_directory_visibility(self):
        selected_action = self.action_selector.get_selected_objects()
        if selected_action and selected_action[0] == "Watch":
            self.directory_field.hidden = True
            self.aniskip_selector.hidden = False
        else:
            self.directory_field.hidden = False
            self.aniskip_selector.hidden = True
        self.display()

    def on_ok(self):
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

        lang = language_selected[0].replace('German Dub', "1").replace('English Sub', "2").replace('German Sub', "3")

        # doodstream currently broken
        valid_providers = ["Vidoza", "Streamtape", "VOE"]

        while provider_selected[0] not in valid_providers:
            npyscreen.notify_confirm("Doodstream and VOE are currently broken.\nFalling back to Vidoza.", title="Provider Error")
            self.provider_selector.value = 0

            provider_selected = ["Vidoza"]

        if selected_episodes and action_selected and language_selected:
            selected_str = "\n".join(selected_episodes)
            npyscreen.notify_confirm(f"Selected episodes:\n{selected_str}", title="Selection")

            if not self.directory_field.hidden:
                output_directory = os.path.join(output_directory, self.parentApp.anime_downloader.anime_title)
                os.makedirs(output_directory, exist_ok=True)

            for episode_url in selected_episodes:
                episode_html = self.parentApp.anime_downloader.make_request(episode_url)
                if episode_html is None:
                    continue
                soup = BeautifulSoup(episode_html, 'html.parser')
                data = self.parentApp.anime_downloader.providers(soup)
                
                provider_mapping = {
                    "Vidoza": vidoza_get_direct_link,
                    "VOE": voe_get_direct_link,
                    "Doodstream": doodstream_get_direct_link,
                    "Streamtape": streamtape_get_direct_link
                }

                if provider_selected[0] in data:
                    for language in data[provider_selected[0]]:
                        if language == int(lang):
                            #print(f"DEBUG: {str(language).replace('1', 'German Dub').replace('2', 'English Sub').replace('3', 'German Sub')}: {vidoza_get_direct_link(BeautifulSoup(self.parentApp.anime_downloader.make_request(data['Vidoza'][language]), 'html.parser'))}")

                            matches = findall(r'\d+', episode_url)
                            season_number = matches[-2]
                            episode_number = matches[-1]
                            
                            anime_title = self.parentApp.anime_downloader.anime_title
                            action = action_selected[0]
                            use_aniskip = aniskip_selected[0] == "Yes"

                            if use_aniskip:
                                script_directory = os.path.dirname(os.path.abspath(__file__))
                                source_path = os.path.join(script_directory, 'skip.lua')
                                destination_path = os.path.expanduser('~/.config/mpv/scripts/skip.lua')

                                if not os.path.exists(destination_path):
                                    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
                                    copy(source_path, destination_path)

                            link = provider_mapping[provider_selected[0]](
                                BeautifulSoup(self.parentApp.anime_downloader.make_request(data[provider_selected[0]][language]), 'html.parser')
                            )

                            if action == "Watch":
                                print(f"Playing '{output_directory}/{anime_title} - S{season_number}E{episode_number}'")
                                command = (
                                    f"mpv "
                                    f"'{link}' "
                                    f"{anime_skip(anime_title, episode_number) if use_aniskip else ''} "
                                    f"--quiet --really-quiet --title='{anime_title} - S{season_number}E{episode_number}'"
                                )
                            else:
                                print(f"Downloading '{output_directory}/{anime_title} - S{season_number}E{episode_number}'")
                                command = (
                                    f"yt-dlp "
                                    f"-o '{output_directory}/{anime_title} - S{season_number}E{episode_number}.mp4' "
                                    f"--quiet --progress \"{link}\""
                                )

                            os.system(command)
                            break

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
        check_dependencies()
        app = AnimeApp(search_anime())
        app.run()
    except KeyboardInterrupt:
        sys.exit()
    except npyscreen.wgwidget.NotEnoughSpaceForWidget as e:
        print(f"Please increase your current terminal size.\nException: {e}")

if __name__ == "__main__":
    main()