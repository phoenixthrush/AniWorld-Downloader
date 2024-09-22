from bs4 import BeautifulSoup

from aniworld.extractors import (
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


def test_provider(data, provider_name, get_direct_link_func) -> dict:
    if provider_name != "VOE":
        print()
    direct_links = {}
    print(f"Testing {provider_name}...")
    for language in data[provider_name]:
        request_url = data[provider_name][language]
        try:
            direct_link = fetch_direct_link(get_direct_link_func, request_url)
            direct_links[language] = direct_link
        except (ConnectionError, TimeoutError, ValueError) as e:
            direct_links[language] = f"Error: {e}"
            print(f"Error fetching direct link for {language}: {e}")

    for link in direct_links.values():
        if 'http' in link:
            print("\033[92mOK\033[0m - Direct link found.", end='')
        else:
            print("\033[91mFAILURE\033[0m - No valid direct link found.", end='')
        print()

    return direct_links


def main():
    clear_screen()
    url = "https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1"
    try:
        html_content = fetch_url_content(url)
    except (ConnectionError, TimeoutError, ValueError) as e:
        print(f"Error fetching URL content: {e}")
        return

    soup = BeautifulSoup(html_content, 'html.parser')
    data = providers(soup)

    test_provider(data, "VOE", voe_get_direct_link)
    test_provider(data, "Vidoza", vidoza_get_direct_link)
    test_provider(data, "Streamtape", streamtape_get_direct_link)

    # doodstream is currently not working
    # test_provider(data, "Doodstream", doodstream_get_direct_link)


if __name__ == "__main__":
    main()
