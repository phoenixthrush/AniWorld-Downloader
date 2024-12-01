import os
import platform
import logging
import requests

from bs4 import BeautifulSoup
from aniworld.config import DEFAULT_REQUEST_TIMEOUT, RANDOM_USER_AGENT


def get_embeded_link(redirect_link: str):
    response = requests.head(
        redirect_link,
        allow_redirects=True,
        headers={'User-Agent': RANDOM_USER_AGENT},
        timeout=DEFAULT_REQUEST_TIMEOUT
    )

    if response.status_code == 200:
        logging.debug("Embeded Link: %s", response.url)
        return response.url

    logging.debug("Error Statuscode: %s", response.status_code)
    return None


def clear_screen() -> None:
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")


if __name__ == '__main__':
    pass
