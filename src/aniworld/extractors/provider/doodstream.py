import re
import random
import time

import requests

from aniworld.config import RANDOM_USER_AGENT, DEFAULT_REQUEST_TIMEOUT


def get_direct_link_from_doodstream(embeded_doodstream_link):
    headers = {
        'User-Agent': RANDOM_USER_AGENT,
        'Referer': 'https://dood.li/'
    }

    def extract_data(pattern, content):
        match = re.search(pattern, content)
        return match.group(1) if match else None

    def generate_random_string(length=10):
        characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        return ''.join(random.choice(characters) for _ in range(length))

    response = requests.get(
        embeded_doodstream_link,
        headers=headers,
        timeout=DEFAULT_REQUEST_TIMEOUT,
        verify=False
    )
    response.raise_for_status()

    pass_md5_pattern = r"\$\.get\('([^']*\/pass_md5\/[^']*)'"
    pass_md5_url = extract_data(pass_md5_pattern, response.text)
    if not pass_md5_url:
        raise ValueError(
            f'pass_md5 URL not found using {embeded_doodstream_link}.')

    full_md5_url = f"https://dood.li{pass_md5_url}"

    token_pattern = r"token=([a-zA-Z0-9]+)"
    token = extract_data(token_pattern, response.text)
    if not token:
        raise ValueError(f'Token not found using {embeded_doodstream_link}.')

    md5_response = requests.get(
        full_md5_url, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT, verify=False)
    md5_response.raise_for_status()
    video_base_url = md5_response.text.strip()

    random_string = generate_random_string(10)
    expiry = int(time.time())

    direct_link = f"{video_base_url}{random_string}?token={token}&expiry={expiry}"
    # print(direct_link)

    return direct_link


if __name__ == '__main__':
    link = input("Enter Doodstream Link: ")
    print(get_direct_link_from_doodstream(embeded_doodstream_link=link))
