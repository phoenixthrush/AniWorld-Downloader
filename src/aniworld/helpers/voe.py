from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import re

def voe_get_direct_link(soup):
    REDIRECT_PATTERN = re.compile(r"window\.location\.href\s*=\s*'(https://[^/]+/e/\w+)';")
    NODE_DETAILS_PATTERN = re.compile(r'let nodeDetails = prompt\("Node",\s*"(https://[^"]+)"\);')

    redirect_match = REDIRECT_PATTERN.search(str(soup.prettify))
    if redirect_match:
        redirect_url = redirect_match.group(1)

        try:
            redirect_content = urlopen(Request(redirect_url, headers={'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"}), timeout=10).read()
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