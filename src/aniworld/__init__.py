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


url = "https://aniworld.to/anime/stream/gods-games-we-play/staffel-1/episode-1"
soup = BeautifulSoup(make_request(url), 'html.parser')
data = providers(soup)


for language in data["VOE"]:
    soup = BeautifulSoup(make_request(data["VOE"][language]), 'html.parser')
    print(f"{str(language).replace("1", "German Dub").replace("2", "English Sub").replace("3", "German Sub")}: {voe_get_direct_link(soup)}")

for language in data["Doodstream"]:
    soup = BeautifulSoup(make_request(data["Doodstream"][language]), 'html.parser')
    print(f"{str(language).replace("1", "German Dub").replace("2", "English Sub").replace("3", "German Sub")}: {doodstream_get_direct_link(soup)}")

for language in data["Vidoza"]:
    soup = BeautifulSoup(make_request(data["Vidoza"][language]), 'html.parser')
    print(f"{str(language).replace("1", "German Dub").replace("2", "English Sub").replace("3", "German Sub")}: {vidoza_get_direct_link(soup)}")

for language in data["Streamtape"]:
    soup = BeautifulSoup(make_request(data["Streamtape"][language]), 'html.parser')
    print(f"{str(language).replace("1", "German Dub").replace("2", "English Sub").replace("3", "German Sub")}: {streamtape_get_direct_link(soup)}")