from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request, ProxyHandler, build_opener, install_opener
from sys import exit


def get(url, proxy=None):
    headers = {
        'User-Agent': (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/58.0.3029.110 Safari/537.3"
        )
    }
    req = Request(url, headers=headers)

    if proxy:
        proxy_handler = ProxyHandler({'http': proxy, 'https': proxy})
        opener = build_opener(proxy_handler)
        install_opener(opener)

    try:
        with urlopen(req, timeout=10) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        print(f"Request to {url} failed: {error}")
        exit()
