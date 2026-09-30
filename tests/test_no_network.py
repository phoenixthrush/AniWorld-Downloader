"""Accidental real fetches must fail before opening a connection."""

import socket
from urllib.request import urlopen

import niquests
import pytest
from curl_cffi import AsyncCurl, requests
from patchright.async_api import BrowserType as AsyncBrowserType
from patchright.sync_api import BrowserType

URL = "https://example.invalid/"


@pytest.mark.parametrize(
    "fetch",
    [
        lambda: socket.create_connection(("example.invalid", 443)),
        lambda: socket.getaddrinfo("example.invalid", 443),
        lambda: socket.gethostbyname("example.invalid"),
        lambda: urlopen(URL),
        lambda: niquests.get(URL),
        lambda: requests.get(URL, impersonate="chrome"),
        lambda: AsyncCurl.add_handle(None, None),
    ],
    ids=["socket", "dns", "dns-ipv4", "urllib", "niquests", "curl", "async-curl"],
)
def test_real_network_calls_are_blocked(fetch):
    with pytest.raises(RuntimeError, match="stub the fetch instead"):
        fetch()


@pytest.mark.parametrize("browser_type", [BrowserType, AsyncBrowserType])
@pytest.mark.parametrize(
    "method", ["launch", "launch_persistent_context", "connect", "connect_over_cdp"]
)
def test_real_browser_connections_are_blocked(browser_type, method):
    with pytest.raises(RuntimeError, match="stub the fetch instead"):
        getattr(browser_type, method)(None)
