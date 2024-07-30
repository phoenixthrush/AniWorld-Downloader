from random import choices
from re import search
from time import time
from urllib.parse import urlparse

# use urllib in future
from requests import Session


def random_str(length: int = 10) -> str:
    return ''.join(choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=length))


def doodstream_get_direct_link(url: str) -> str:
    with Session() as session:
        response = session.head(url)
        if response.is_redirect:
            redirect_url = response.headers.get("Location")
            u2 = urlparse(redirect_url)._replace(netloc="d000d.com").geturl()
            response = session.get(u2)

        pass_md5 = r"/pass_md5/[\w-]+/[\w-]+"
        pass_md5_match = search(pass_md5, response.text)
        response = session.get(f"https://d0000d.com{pass_md5_match.group()}", headers={'Referer': 'https://d0000d.com/'})
        return f"{response.text}{random_str()}?token={pass_md5_match.group().split('/')[-1]}&expiry={int(time() * 1000)}"
