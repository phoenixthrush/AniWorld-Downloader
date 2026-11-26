"""HTTP requests for the sites using nhplayer and HentaiHaven."""

from niquests.exceptions import RequestException

from ...config import GLOBAL_SESSION


def _request(method, url, **kwargs):
    kwargs.setdefault("timeout", 20)
    kwargs.setdefault("headers", {"Accept-Encoding": "gzip, deflate"})
    try:
        response = getattr(GLOBAL_SESSION, method)(url, **kwargs)
    except RequestException:
        response = None
    if response is None or getattr(response, "status_code", 200) == 403:
        # These sites reject plain TLS clients, even for public catalogue pages.
        from curl_cffi import requests

        response = getattr(requests, method)(url, impersonate="chrome", **kwargs)
    response.raise_for_status()
    return response


def get_response(url, **kwargs):
    return _request("get", url, **kwargs)


def post_response(url, **kwargs):
    return _request("post", url, **kwargs)
