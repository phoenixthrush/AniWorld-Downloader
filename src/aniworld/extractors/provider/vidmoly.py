import re

import requests
from bs4 import BeautifulSoup

from aniworld.config import DEFAULT_REQUEST_TIMEOUT, RANDOM_USER_AGENT


def get_direct_link_from_vidmoly(embeded_vidmoly_link: str):
    response = requests.get(
        embeded_vidmoly_link,
        headers={'User-Agent': RANDOM_USER_AGENT},
        timeout=DEFAULT_REQUEST_TIMEOUT
    )
    html_content = response.text
    soup = BeautifulSoup(html_content, 'html.parser')
    scripts = soup.find_all('script')

    file_link_pattern = r'file:\s*"(https?://.*?)"'

    for script in scripts:
        if script.string:
            match = re.search(file_link_pattern, script.string)
            if match:
                file_link = match.group(1)
                return file_link
    return None


if __name__ == '__main__':
    link = input("Enter Vidmoly Link: ")
    print('Note: --referer "https://vidmoly.to"')
    print(get_direct_link_from_vidmoly(embeded_vidmoly_link=link))
