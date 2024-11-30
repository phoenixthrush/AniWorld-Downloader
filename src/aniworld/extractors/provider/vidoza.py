import re
import requests

from bs4 import BeautifulSoup

from aniworld.common import get_embeded_link, get_redirect_link_from_provider
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
    EPISODE_LINK = "https://aniworld.to/anime/stream/solo-leveling/staffel-1/episode-9"
    LANG = 1
    redirect_link = get_redirect_link_from_provider(EPISODE_LINK, "VOE", LANG)
    embeded_link = get_embeded_link(redirect_link)
    direct_link = get_direct_link_from_vidoza(embeded_link)
    print(
        redirect_link,"\n",
        embeded_link,"\n",
        direct_link,"\n"
)
