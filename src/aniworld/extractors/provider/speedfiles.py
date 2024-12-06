import re
import base64
import requests

from aniworld.config import DEFAULT_REQUEST_TIMEOUT, RANDOM_USER_AGENT

SPEEDFILES_PATTERN = re.compile(r'var _0x5opu234 = "(?P<encoded_data>.*?)";')


def get_direct_link_from_speedfiles(url):
    response = requests.get(
        url,
        verify=False,
        timeout=DEFAULT_REQUEST_TIMEOUT,
        headers={'User-Agent': RANDOM_USER_AGENT}
    )

    match = SPEEDFILES_PATTERN.search(response.text)

    if not match:
        raise ValueError("Pattern not found in the response.")

    encoded_data = match.group("encoded_data")
    decoded_data = base64.b64decode(encoded_data).decode()[::-1].swapcase()[::-1]
    second_decode = base64.b64decode(decoded_data).decode()[::-1]
    hex_decoded = ''.join(chr(int(second_decode[i:i + 2], 16)) for i in range(0, len(second_decode), 2))
    shifted_chars = ''.join(chr(ord(char) - 3) for char in hex_decoded)[::-1].swapcase()
    final_decoded = base64.b64decode(shifted_chars).decode()

    return final_decoded


if __name__ == '__main__':
    url = input("Enter Speedfiles Link: ")
    print(get_direct_link_from_speedfiles(url))
