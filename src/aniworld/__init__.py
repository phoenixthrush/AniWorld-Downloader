#!/usr/bin/env python
# encoding: utf-8

from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup

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


def watch(url):
    """
    for language in data["VOE"]:
        soup = BeautifulSoup(make_request(data["VOE"][language]), 'html.parser')
        print(f"{str(language).replace("1", "German Dub").replace("2", "English Sub").replace("3", "German Sub")}: {voe_get_direct_link(soup)}")

    for language in data["Doodstream"]:
        print(f"{str(language).replace("1", "German Dub").replace("2", "English Sub").replace("3", "German Sub")}: {doodstream_get_direct_link(data["Doodstream"][language])}")

    for language in data["Vidoza"]:
        soup = BeautifulSoup(make_request(data["Vidoza"][language]), 'html.parser')
        print(f"{str(language).replace("1", "German Dub").replace("2", "English Sub").replace("3", "German Sub")}: {vidoza_get_direct_link(soup)}")

    for language in data["Streamtape"]:
        soup = BeautifulSoup(make_request(data["Streamtape"][language]), 'html.parser')
        print(f"{str(language).replace("1", "German Dub").replace("2", "English Sub").replace("3", "German Sub")}: {streamtape_get_direct_link(soup)}")
    """

import npyscreen
import requests
from bs4 import BeautifulSoup

anime = "one-punch-man"
BASE_URL = f"https://aniworld.to/anime/stream/{anime}/"
soup = BeautifulSoup(requests.get(BASE_URL).text, 'html.parser')

season_meta = soup.find('meta', itemprop='numberOfSeasons')
number_of_seasons = int(season_meta['content'] if season_meta else 0)

filme_link = soup.find('a', title='Alle Filme')

if filme_link:
    number_of_seasons -= 1

def get_season_episodes(season_url: str) -> int: 
    season_soup = BeautifulSoup(requests.get(season_url).text, 'html.parser')
    episodes = season_soup.find_all('meta', itemprop='episodeNumber')
    episode_numbers = [int(episode['content']) for episode in episodes]
    highest_episode = max(episode_numbers) if episode_numbers else None

    return highest_episode

season_data = {}

for i in range(1, number_of_seasons + 1):
    season_url = f"{BASE_URL}{i}"
    highest_episode = get_season_episodes(season_url)
    season_data[i] = []
    for k in range(1, highest_episode + 1):
        episode_url = f"{BASE_URL}staffel-{i}/episode-{k}"
        season_data[i].append(episode_url)

# Define global variables to store the selected options and directory
selected_options = []
directory = ""

class TestApp(npyscreen.NPSApp):
    def main(self):
        global selected_options, directory  # Use global variables
        
        season_options = [f"Season {season}" for season in season_data.keys()]
        
        F = npyscreen.Form(name="Welcome to Aniworld-Downloader")
        
        fn2 = F.add(npyscreen.TitleFilenameCombo, name="Directory:")
        
        ms2 = F.add(npyscreen.TitleMultiSelect, max_height=-2, name="Pick Season(s)",
                    values=season_options, scroll_exit=True)

        F.edit()

        selected_options = ms2.get_selected_objects()
        directory = fn2.value

        selected_options_str = "\n".join(selected_options)
        npyscreen.notify_confirm("Selected Options:\n" + selected_options_str, title="Selection")

        print("Selected options:", selected_options)
        print("Directory:", directory)

if __name__ == "__main__":
    App = TestApp()
    App.run()

    print("Directory:", directory)
    print("Selected Season(s):", selected_options)
    
    for episode in selected_options:
        print(episode)
        continue
        for language in data["Doodstream"]:
            print(f"{str(language).replace("1", "German Dub").replace("2", "English Sub").replace("3", "German Sub")}: {doodstream_get_direct_link(data["Doodstream"][language])}")