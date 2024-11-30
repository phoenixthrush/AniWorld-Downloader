import re
import requests

from aniworld.config import DEFAULT_REQUEST_TIMEOUT, RANDOM_USER_AGENT

REDIRECT_PATTERN = re.compile(r"window\.location\.href\s*=\s*'(https://[^/]+/e/\w+)';")
NODE_DETAILS_PATTERN = re.compile(r'let nodeDetails = prompt\("Node",\s*"(https://[^"]+)"\);')


def get_direct_link_from_voe(embeded_voe_link: str) -> str:  # TODO - fix voe direct link
    response = requests.get(
        embeded_voe_link,
        headers={'User-Agent': RANDOM_USER_AGENT},
        timeout=DEFAULT_REQUEST_TIMEOUT
    )

    redirect_match = REDIRECT_PATTERN.search(response.text)
    if redirect_match:
        redirect_url = redirect_match.group(1)
        try:
            response = requests.get(
                redirect_url,
                headers={'User-Agent': RANDOM_USER_AGENT},
                timeout=DEFAULT_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            redirect_content_str = response.text
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
            print(f"Failed to fetch URL {redirect_url}: {e}")

        if redirect_content_str:
            node_details_match = NODE_DETAILS_PATTERN.search(redirect_content_str)
            if node_details_match:
                return node_details_match.group(1)

    raise ValueError("No direct link found.")


if __name__ == '__main__':
    print(get_direct_link_from_voe(embeded_voe_link=""))
