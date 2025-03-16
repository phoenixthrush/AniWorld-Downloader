import re

import requests
import jsbeautifier

from aniworld.config import DEFAULT_REQUEST_TIMEOUT, RANDOM_USER_AGENT


def get_direct_link_from_luluvdo(embeded_luluvdo_link):
    id = embeded_luluvdo_link.split('/')[-1]
    filelink = f"https://luluvdo.com/dl?op=embed&file_code={id}&auto=1&referer=https://aniworld.to"
    headers = {
        "User-Agent": RANDOM_USER_AGENT
    }

    response = requests.get(filelink, headers=headers,
                            timeout=DEFAULT_REQUEST_TIMEOUT)

    if response.status_code == 200:
        beautified_js = jsbeautifier.beautify(response.text)
        pattern = r'file:\s*"([^"]+)"'
        matches = re.findall(pattern, str(beautified_js))

        if matches:
            return matches[0]

    raise ValueError("No match found")


if __name__ == '__main__':
    url = input("Enter Luluvdo Link: ")
    print(get_direct_link_from_luluvdo(url))
