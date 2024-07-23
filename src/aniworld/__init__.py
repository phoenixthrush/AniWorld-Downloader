#!/usr/bin/env python
# encoding: utf-8

from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup
import npyscreen
from os import system
import requests
from re import findall

from helpers.doodstream import doodstream_get_direct_link
#from helpers.voe import voe_get_direct_link
#from helpers.vidoza import vidoza_get_direct_link
#from helpers.streamtape import streamtape_get_direct_link

def make_request(url):
    try:
        headers = {'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"}
        req = Request(url, headers=headers)
        with urlopen(req, timeout=10) as response:
            return response.read()
    except HTTPError as error:
        print(error.status, error.reason)
    except URLError as error:
        print(error.reason)
    except TimeoutError:
        print("Request timed out")

def providers(soup) -> dict:
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

def get_season_episodes(season_url: str) -> list:
    season_soup = BeautifulSoup(requests.get(season_url).text, 'html.parser')
    episodes = season_soup.find_all('meta', itemprop='episodeNumber')
    episode_numbers = [int(episode['content']) for episode in episodes]
    highest_episode = max(episode_numbers) if episode_numbers else None

    return [f"{season_url}/staffel-{season_url.split('/')[-1]}/episode-{num}" for num in range(1, highest_episode + 1)]

anime = "one-punch-man"
BASE_URL = f"https://aniworld.to/anime/stream/{anime}/"
soup = BeautifulSoup(requests.get(BASE_URL).text, 'html.parser')

if 'Deine Anfrage wurde als Spam erkannt.' in soup:
        print("Your IP-Address is blacklisted, please use a VPN or try later.")
        exit()

season_meta = soup.find('meta', itemprop='numberOfSeasons')
number_of_seasons = int(season_meta['content'] if season_meta else 0)

filme_link = soup.find('a', title='Alle Filme')
if filme_link:
    number_of_seasons -= 1

season_data = {}
for i in range(1, number_of_seasons + 1):
    season_url = f"{BASE_URL}{i}"
    season_data[i] = get_season_episodes(season_url)

class EpisodeForm(npyscreen.ActionForm):
    def create(self):
        episode_list = [url for season, episodes in season_data.items() for url in episodes]
        self.fn2 = self.add(npyscreen.TitleFilenameCombo, name="Directory:")
        self.episode_selector = self.add(npyscreen.TitleMultiSelect, name="Select Episodes", values=episode_list, max_height=10)

    def on_ok(self):
        npyscreen.blank_terminal()
        output_directory = self.fn2.value
        if not output_directory:
            npyscreen.notify_confirm("Please provide a directory.", title="Error")
            return

        selected_episodes = self.episode_selector.get_selected_objects()
        if selected_episodes:
            selected_str = "\n".join(selected_episodes)
            npyscreen.notify_confirm(f"Selected episodes:\n{selected_str}", title="Selection")

            for episode_url in selected_episodes:
                response = requests.get(episode_url)
                soup = BeautifulSoup(response.text, 'html.parser')

                data = providers(soup)

                for language in data["Doodstream"]:
                    if language == 2:
                        print(f"Downloading {episode_url} to {output_directory}.")
                        
                        matches = findall(r'\d+', episode_url)
                        season_number = matches[-2]
                        episode_number = matches[-1]
                        
                        system(f"yt-dlp --add-header 'Referer: https://d0000d.com/' -o '{output_directory}/{anime.replace("-", " ").title()} - S{season_number}E{episode_number}.mp4' --quiet --progress \"{doodstream_get_direct_link(data['Doodstream'][language])}\"")
                        break
            self.parentApp.setNextForm(None)
            self.parentApp.switchFormNow()
        else:
            npyscreen.notify_confirm("No episodes selected.", title="Selection")

    def on_cancel(self):
        self.parentApp.setNextForm(None)

class AnimeApp(npyscreen.NPSAppManaged):
    def onStart(self):
        self.addForm("MAIN", EpisodeForm, name="Anime Downloader")

if __name__ == "__main__":
    try:
        App = AnimeApp()
        App.run()
    except KeyboardInterrupt:
        exit()
