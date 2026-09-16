"""Resolve Vidara's player API to its HLS stream."""

from urllib.parse import urlparse

from curl_cffi import requests


def get_direct_link_from_vidara(embed_url):
    parsed = urlparse(embed_url or "")
    if parsed.scheme != "https" or parsed.hostname not in {"vidara.to", "vidara.so"}:
        raise ValueError("Invalid Vidara embed URL")
    filecode = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    if not filecode or not filecode.isalnum():
        raise ValueError("Invalid Vidara file code")

    session = requests.Session(impersonate="chrome124")
    page = session.get(embed_url, timeout=20)
    page.raise_for_status()
    origin = f"{parsed.scheme}://{parsed.netloc}"
    response = session.post(
        f"{origin}/api/stream",
        json={"filecode": filecode, "device": "web"},
        headers={"Origin": origin, "Referer": embed_url},
        timeout=20,
    )
    response.raise_for_status()
    stream_url = response.json().get("streaming_url")
    if not isinstance(stream_url, str) or urlparse(stream_url).scheme != "https":
        raise ValueError("Vidara did not return a usable stream URL")
    return stream_url
