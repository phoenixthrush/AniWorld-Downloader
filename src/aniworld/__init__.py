#!/usr/bin/env python
# encoding: utf-8

from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup
import npyscreen
import requests

from helpers.voe import voe_get_direct_link
from helpers.doodstream import doodstream_get_direct_link
from helpers.vidoza import vidoza_get_direct_link
from helpers.streamtape import streamtape_get_direct_link

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

def get_season_episodes(season_url: str) -> list:
    season_soup = BeautifulSoup(requests.get(season_url).text, 'html.parser')
    episodes = season_soup.find_all('meta', itemprop='episodeNumber')
    episode_numbers = [int(episode['content']) for episode in episodes]
    highest_episode = max(episode_numbers) if episode_numbers else None

    return [f"{season_url}staffel-{season_url.split('/')[-1]}/episode-{num}" for num in range(1, highest_episode + 1)]

anime = "one-punch-man"
BASE_URL = f"https://aniworld.to/anime/stream/{anime}/"
soup = BeautifulSoup(requests.get(BASE_URL).text, 'html.parser')

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
        episode_list = [f"S{str(season).zfill(2)}-E{str(ep).zfill(2)}" 
                for season, episodes in season_data.items() 
                for ep in range(1, len(episodes) + 1)]
        self.episode_selector = self.add(npyscreen.TitleMultiSelect, name="Select Episodes", values=episode_list, max_height=10)

    def on_ok(self):
        selected_episodes = self.episode_selector.get_selected_objects()
        if selected_episodes:
            selected_str = "\n".join(selected_episodes)
            npyscreen.notify_confirm(f"Selected episodes:\n{selected_str}", title="Selection")
            print("Selected episodes:", selected_episodes)
        else:
            npyscreen.notify_confirm("No episodes selected.", title="Selection")

    def on_cancel(self):
        self.parentApp.setNextForm(None)

class AnimeApp(npyscreen.NPSAppManaged):
    def onStart(self):
        self.addForm("MAIN", EpisodeForm, name="Anime Downloader")

if __name__ == "__main__":
    App = AnimeApp()
    App.run()
