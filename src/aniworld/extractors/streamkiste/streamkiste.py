"""
MIT License

Copyright (c) 2024 Phoenixthrush UwU

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import os
import subprocess
import re
import platform
import requests

from bs4 import BeautifulSoup
from aniworld.extractors import voe_get_direct_link
from aniworld import globals as aniworld_globals
from aniworld.common import install_and_import


def clear_screen() -> None:
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")


def fetch_direct_link(link):
    filtered_urls = []

    install_and_import("playwright")
    from playwright.sync_api import sync_playwright  # pylint: disable=import-error, import-outside-toplevel

    with sync_playwright() as p:
        # TODO - add firefox or chromium fallback
        browser = p.webkit.launch(headless=False)
        page = browser.new_page()

        page.on("request", lambda request: filtered_urls.append(request.url)
                if re.match(r"https://voe\.sx/e/.*", request.url) else None)

        page.goto(link)

        # TODO - check for google captcha

        page.wait_for_selector("div.info-right")
        title_element = page.query_selector("div.info-right .title h1")
        title_text = title_element.inner_text().strip() if title_element else "StreamKisteTV"

        page.wait_for_selector("div#single-stream div#stream li.stream div#stream-links a")
        first_stream_link = page.query_selector("div#single-stream div#"
                                                "stream li.stream div#""stream-links a")

        if first_stream_link:
            first_stream_link.click()

        page.wait_for_timeout(5000)
        browser.close()

    try:
        response = requests.get(
            filtered_urls[0],
            timeout=30,
            headers={'User-Agent': aniworld_globals.DEFAULT_USER_AGENT}
        )
    except IndexError:
        # TODO
        # add fallback using another provider or
        # doing the request again with higher timeout and headless=False

        print("No VOE redirect link found.")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')

    # TODO - add other provider options -> Streamtape
    direct_link = voe_get_direct_link(soup)

    return direct_link, title_text


def download_video(link, title):
    filename = os.path.join(os.path.expanduser('~'), 'Downloads', f"{title}.mp4")
    subprocess.run(['yt-dlp', '--quiet', '--no-warnings',
                    '--progress', '-o', filename, link], check=False)


def watch_video(link, title):
    mpv_title = title.replace(" ", "_")
    subprocess.run(['mpv', f'--force-media-title={mpv_title}',
                    '--fs', '--quiet', '--really-quiet', link], check=False)


def streamkiste_get_direct_link(link: str):
    return fetch_direct_link(link)


def streamkiste(episode_link: str = None):
    try:
        if not episode_link:
            clear_screen()
            link = input("Enter the StreamKisteTV link: ")
            action = input("(D)ownload or (W)atch?: ").strip().lower()
        else:
            link = episode_link
            action = "d"

        try:
            link, title = streamkiste_get_direct_link(link)
        except TypeError:
            return

        if action == 'd':
            download_video(link, title)
        elif action == 'w':
            watch_video(link, title)
        else:
            print("Invalid option. Please choose 'D' for download or 'W' for watch.")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    streamkiste()
