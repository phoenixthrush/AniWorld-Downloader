from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request


def get(url):
    headers = {
        'User-Agent': (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/58.0.3029.110 Safari/537.3"
        )
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=10) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        print(f"Request failed: {error}")
        return None
