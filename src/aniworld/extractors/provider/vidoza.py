import re

import requests
from bs4 import BeautifulSoup

from aniworld.config import DEFAULT_REQUEST_TIMEOUT, RANDOM_USER_AGENT


def get_direct_link_from_vidoza(embeded_vidoza_link: str) -> str:
    response = requests.get(
        embeded_vidoza_link,
        headers={'User-Agent': RANDOM_USER_AGENT},
        timeout=DEFAULT_REQUEST_TIMEOUT
    )

    soup = BeautifulSoup(response.content, "html.parser")

    for tag in soup.find_all('script'):
        if 'sourcesCode:' in tag.text:
            match = re.search(r'src: "(.*?)"', tag.text)
            if match:
                return match.group(1)

    raise ValueError("No direct link found.")


if __name__ == '__main__':
    link = input("Enter Vidoza Link: ")
    print(get_direct_link_from_vidoza(embeded_vidoza_link=link))
