"""HTTP requests for the sites using nhplayer and HentaiHaven."""

from niquests.exceptions import RequestException

from ...config import GLOBAL_SESSION


def get_response(url, **kwargs):
    kwargs.setdefault("timeout", 20)
    kwargs.setdefault("headers", {"Accept-Encoding": "gzip, deflate"})
    try:
        response = GLOBAL_SESSION.get(url, **kwargs)
    except RequestException:
        response = None
    if response is None or getattr(response, "status_code", 200) == 403:
        # These sites reject plain TLS clients, even for public catalogue pages.
        from curl_cffi import requests

        response = requests.get(url, impersonate="chrome", **kwargs)
    response.raise_for_status()
    return response


def post_response(url, **kwargs):
    kwargs.setdefault("timeout", 20)
    kwargs.setdefault("headers", {"Accept-Encoding": "gzip, deflate"})
    try:
        response = GLOBAL_SESSION.post(url, **kwargs)
    except RequestException:
        response = None
    if response is None or getattr(response, "status_code", 200) == 403:
        from curl_cffi import requests

        response = requests.post(url, impersonate="chrome", **kwargs)
    response.raise_for_status()
    return response
