from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup

from aniworld import doodstream_get_direct_link
from aniworld import streamtape_get_direct_link
from aniworld import vidoza_get_direct_link
from aniworld import voe_get_direct_link

from os import name, system


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


def clear_screen():
    if name == 'nt':
        _ = system('cls')
    else:
        _ = system('clear')


def test_provider(data, provider_name, get_direct_link_func):
    print(f"{provider_name} TEST")
    for language in data[provider_name]:
        soup = BeautifulSoup(make_request(data[provider_name][language]), 'html.parser')
        direct_link = get_direct_link_func(soup)
        language_str = str(language).replace("1", "German Dub").replace("2", "English Sub").replace("3", "German Sub")
        #print(f"{language_str}: {direct_link}")
        if 'http' in direct_link:
            print("\033[92mOK\033[0m - Direct link found.")
        else:
            print("\033[91mFAILURE\033[0m - No valid direct link found.")
    print()


url = "https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1"
soup = BeautifulSoup(make_request(url), 'html.parser')
data = providers(soup)

clear_screen()
test_provider(data, "VOE", voe_get_direct_link)
test_provider(data, "Doodstream", doodstream_get_direct_link)
test_provider(data, "Vidoza", vidoza_get_direct_link)
test_provider(data, "Streamtape", streamtape_get_direct_link)