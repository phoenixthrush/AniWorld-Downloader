from base64 import b64decode
from re import search


def voe_get_direct_link(soup):
    for tag in soup.find_all('script'):
        if 'var sources =' in tag.text:
            match = search(r"'hls': '(.*?)'", tag.text)
            if match:
                return b64decode(match.group(1)).decode()
    return None