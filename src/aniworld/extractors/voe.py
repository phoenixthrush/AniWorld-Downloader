from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import re

from aniworld import globals


def voe_get_direct_link(soup):
    REDIRECT_PATTERN = re.compile(r"window\.location\.href\s*=\s*'(https://[^/]+/e/\w+)';")
    NODE_DETAILS_PATTERN = re.compile(r'let nodeDetails = prompt\("Node",\s*"(https://[^"]+)"\);')

    redirect_match = REDIRECT_PATTERN.search(str(soup.prettify))
    if redirect_match:
        redirect_url = redirect_match.group(1)

        try:
            redirect_content = urlopen(Request(redirect_url, headers={'User-Agent': globals.DEFAULT_USER_AGENT}), timeout=10).read()
            redirect_content_str = redirect_content.decode('utf-8')
        except (HTTPError, URLError, TimeoutError) as e:
            print(f"Failed to fetch URL {redirect_url}: {e}")
            redirect_content_str = None

        if redirect_content_str:
            node_details_match = NODE_DETAILS_PATTERN.search(redirect_content_str)
            if node_details_match:
                return node_details_match.group(1)

    print("No direct link found.")
    return None
