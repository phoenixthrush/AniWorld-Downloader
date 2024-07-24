#!/usr/bin/env python
# encoding: utf-8

import os
import sys
import glob
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup
import npyscreen
from re import findall

from helpers.vidoza import vidoza_get_direct_link
# from helpers.doodstream import doodstream_get_direct_link
# from helpers.voe import voe_get_direct_link
# from helpers.streamtape import streamtape_get_direct_link

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
        season_html = self.make_request(season_url)
        if season_html is None:
            return []
        season_soup = BeautifulSoup(season_html, 'html.parser')
        episodes = season_soup.find_all('meta', itemprop='episodeNumber')
        episode_numbers = [int(episode['content']) for episode in episodes]
        highest_episode = max(episode_numbers, default=None)
        return [f"{season_url}/staffel-{season_url.split('/')[-1]}/episode-{num}" for num in range(1, highest_episode + 1)]

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
        self.directory_field = self.add(npyscreen.TitleFilenameCombo, name="Directory:", value=os.path.join(os.path.expanduser('~'), 'Downloads'))
        self.language_selector = self.add(npyscreen.TitleSelectOne, name="Language Options", values=["German Dub", "English Sub", "German Sub"], max_height=4, value=[2], scroll_exit=True)
        self.episode_selector = self.add(npyscreen.TitleMultiSelect, name="Select Episodes", values=episode_list, max_height=10)

        self.action_selector.when_value_edited = self.update_directory_visibility

    def update_directory_visibility(self):
        selected_action = self.action_selector.get_selected_objects()
        if selected_action and selected_action[0] == "Watch":
            self.directory_field.hidden = True
        else:
            self.directory_field.hidden = False
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

        lang = language_selected[0].replace('German Dub', "1").replace('English Sub', "2").replace('German Sub', "3")

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
                
                if "Vidoza" in data:
                    for language in data["Vidoza"]:
                        if language == int(lang):
                            #print(f"DEBUG: {str(language).replace('1', 'German Dub').replace('2', 'English Sub').replace('3', 'German Sub')}: {vidoza_get_direct_link(BeautifulSoup(self.parentApp.anime_downloader.make_request(data['Vidoza'][language]), 'html.parser'))}")

                            matches = findall(r'\d+', episode_url)
                            season_number = matches[-2]
                            episode_number = matches[-1]
                            
                            anime_title = self.parentApp.anime_downloader.anime_title
                            action = action_selected[0]

                            if action == "Watch":
                                command = (
                                    f"mpv "
                                    f"'{vidoza_get_direct_link(BeautifulSoup(self.parentApp.anime_downloader.make_request(data['Vidoza'][language]), 'html.parser'))}' "
                                    f"--quiet --really-quiet --title='{anime_title} - S{season_number}E{episode_number}'"
                                )
                            else:
                                command = (
                                    f"yt-dlp "
                                    f"-o '{output_directory}/{anime_title} - S{season_number}E{episode_number}.mp4' "
                                    f"--quiet --progress \"{vidoza_get_direct_link(BeautifulSoup(self.parentApp.anime_downloader.make_request(data['Vidoza'][language]), 'html.parser'))}\""
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

if __name__ == "__main__":
    try:
        anime_slug = "kaguya-sama-love-is-war"  # hardcoded testing
        app = AnimeApp(anime_slug)
        app.run()
    except KeyboardInterrupt:
        sys.exit()
