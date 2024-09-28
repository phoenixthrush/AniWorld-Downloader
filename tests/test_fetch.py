import time
import requests
from aniworld.common import fetch_url_content

url = "https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/staffel-1/episode-1"


def measure_fetch_time(fetch_function, url):
    start_time = time.time()
    try:
        content = fetch_function(url)
    except Exception as e:
        return None, str(e)
    duration = time.time() - start_time
    return content, duration


content_fetch, fetch_duration = measure_fetch_time(fetch_url_content, url)
content_requests, requests_duration = measure_fetch_time(lambda u: requests.get(u).text, url)

print(f"Time taken using fetch_url_content: {fetch_duration:.4f} seconds")
print(f"Time taken using requests.get:      {requests_duration:.4f} seconds")
