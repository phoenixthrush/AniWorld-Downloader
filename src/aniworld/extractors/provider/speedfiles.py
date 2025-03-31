import re
import base64
import requests

from aniworld.config import DEFAULT_REQUEST_TIMEOUT, RANDOM_USER_AGENT

SPEEDFILES_PATTERN = re.compile(r'var _0x5opu234 = "(?P<encoded_data>.*?)";')


def get_direct_link_from_speedfiles(embeded_speedfiles_link):
    response = requests.get(
        embeded_speedfiles_link,
        timeout=DEFAULT_REQUEST_TIMEOUT,
        headers={'User-Agent': RANDOM_USER_AGENT}
    )

    if "<span class=\"inline-block\">Web server is down</span>" in response.text:
        raise ValueError(
            "The SpeedFiles server is currently down.\n"
            "Please try again later or choose a different hoster."
        )

    match = SPEEDFILES_PATTERN.search(response.text)

    if not match:
        raise ValueError("Pattern not found in the response.")

    encoded_data = match.group("encoded_data")
    decoded = base64.b64decode(encoded_data).decode()
    decoded = decoded.swapcase()[::-1]
    decoded = base64.b64decode(decoded).decode()[::-1]
    decoded_hex = ''.join(chr(int(decoded[i:i + 2], 16))
                          for i in range(0, len(decoded), 2))
    shifted = ''.join(chr(ord(char) - 3) for char in decoded_hex)
    result = base64.b64decode(shifted.swapcase()[::-1]).decode()

    return result


if __name__ == '__main__':
    speedfiles_link = input("Enter Speedfiles Link: ")
    print(get_direct_link_from_speedfiles(
        embeded_speedfiles_link=speedfiles_link))
