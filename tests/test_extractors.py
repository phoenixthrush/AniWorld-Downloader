from aniworld.extractors import (
    doodstream_get_direct_link,
    streamtape_get_direct_link,
    vidoza_get_direct_link,
    voe_get_direct_link
)

from aniworld.common import (
    clear_screen,
    fetch_url_content
)

from aniworld.execute import (
    providers,
    fetch_direct_link
)

from aniworld.globals import IS_DEBUG_MODE
from bs4 import BeautifulSoup

def test_provider(data, provider_name, get_direct_link_func) -> dict:
    if IS_DEBUG_MODE:
        print(f"{provider_name} TEST")

    direct_links = {}
    for language in data[provider_name]:
        request_url = data[provider_name][language]
        direct_link = fetch_direct_link(get_direct_link_func, request_url)
        direct_links[language] = direct_link

    if IS_DEBUG_MODE:
        for link in direct_links.values():
            if 'http' in link:
                print("\033[92mOK\033[0m - Direct link found.")
            else:
                print("\033[91mFAILURE\033[0m - No valid direct link found.")
        print()

    return direct_links


def main():
    url = "https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1"
    html_content = fetch_url_content(url)
    soup = BeautifulSoup(html_content, 'html.parser')
    data = providers(soup)

    clear_screen()
    test_provider(data, "VOE", voe_get_direct_link)
    test_provider(data, "Doodstream", doodstream_get_direct_link)
    test_provider(data, "Vidoza", vidoza_get_direct_link)
    test_provider(data, "Streamtape", streamtape_get_direct_link)


if __name__ == "__main__":
    main()
