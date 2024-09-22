from os import environ
from aniworld.common import fetch_url_content


def fetch_ip(url):
    response = fetch_url_content(url)
    return response.decode()


def main():
    url = "http://icanhazip.com"

    print("Without proxy:")
    print(fetch_ip(url))

    proxy = "http://0.0.0.0:8080"

    environ['HTTP_PROXY'] = proxy
    environ['HTTPS_PROXY'] = proxy

    print("With proxy:")
    print(fetch_ip(url), end="")


if __name__ == "__main__":
    main()
