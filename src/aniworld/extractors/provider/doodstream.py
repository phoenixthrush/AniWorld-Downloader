import re
import random
import time

import requests

from aniworld.globals import DEFAULT_USER_AGENT


def doodstream_get_direct_link(soup):
    headers = {
        'User-Agent': DEFAULT_USER_AGENT,
        'Referer': 'https://dood.li/'
    }

    def extract_data(pattern, content):
        match = re.search(pattern, content)
        return match.group(1) if match else None

    def generate_random_string(length=10):
        characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        return ''.join(random.choice(characters) for _ in range(length))

    # response = requests.get(embeded_doodstream_link, headers=headers)
    # response.raise_for_status()
    content = str(soup)

    pass_md5_pattern = r"\$\.get\('([^']*\/pass_md5\/[^']*)'"
    pass_md5_url = extract_data(pass_md5_pattern, content)
    if not pass_md5_url:
        raise ValueError('pass_md5 URL not found.')

    full_md5_url = f"https://dood.li{pass_md5_url}"

    token_pattern = r"token=([a-zA-Z0-9]+)"
    token = extract_data(token_pattern, content)
    if not token:
        raise ValueError('Token not found.')

    md5_response = requests.get(full_md5_url, headers=headers, timeout=30)
    md5_response.raise_for_status()
    video_base_url = md5_response.text.strip()

    random_string = generate_random_string(10)
    expiry = int(time.time())

    direct_link = f"{video_base_url}{random_string}?token={token}&expiry={expiry}"
    # print(direct_link)

    return direct_link
