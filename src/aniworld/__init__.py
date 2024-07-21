from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from os import system
import urllib.request

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
    #url = "https://aniworld.to/anime/stream/gods-games-we-play/staffel-1/episode-1"
    soup = BeautifulSoup(make_request(url), 'html.parser')

    if 'Browser Check (Anti Bot/Spam)' in soup.text:
        print("Your IP-Address is blacklisted, please use a VPN or try later.")
        exit()

    data = providers(soup)

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

    mpv_title = "Debug TODO"
    for language in data["Doodstream"]:
        if language == 2:
            system(
                    f"mpv \"--http-header-fields=Referer: https://d0000d.com/\" \"{doodstream_get_direct_link(data["Doodstream"][language])}\" --quiet --really-quiet --title=\"{mpv_title}\""
            )
            break

anime = "one-punch-man" # debug for testing
BASE_URL = f"https://aniworld.to/anime/stream/{anime}/"

def fetch_page(url):
    with urllib.request.urlopen(url) as response:
        return response.read()

# Get the page and parse it
soup = BeautifulSoup(fetch_page(BASE_URL), 'html.parser')

season_meta = soup.find('meta', itemprop='numberOfSeasons')
number_of_seasons = int(season_meta['content'] if season_meta else 0)

filme_link = soup.find('a', title='Alle Filme')

if filme_link:
    number_of_seasons -= 1

def get_season_episodes(season_url: str) -> int:
    season_soup = BeautifulSoup(fetch_page(season_url), 'html.parser')
    episodes = season_soup.find_all('meta', itemprop='episodeNumber')
    episode_numbers = [int(episode['content']) for episode in episodes]
    highest_episode = max(episode_numbers) if episode_numbers else None

    return highest_episode

highest_episodes_per_season = []

for i in range(1, number_of_seasons + 1):
    season_url = f"{BASE_URL}{i}"
    highest_episode = get_season_episodes(season_url)
    highest_episodes_per_season.append(highest_episode)
    # print(season_url, highest_episode)

# print(highest_episodes_per_season)

anime_links = []

for i in range(0, len(highest_episodes_per_season)):
    for k in range(0, highest_episodes_per_season[i]):
        # print(f"{base_url}staffel-{i + 1}/episode-{k + 1}")
        anime_links.append(f"{BASE_URL}staffel-{i + 1}/episode-{k + 1}")

for link in anime_links:
    watch(link)
