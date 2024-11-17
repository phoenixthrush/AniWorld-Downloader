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

import argparse
import shutil
import subprocess
import sys
import platform
import os
from pathlib import Path


def clear_screen() -> None:
    os.system("cls" if platform.system() == "Windows" else "clear")


def check_for_ytdl():
    if shutil.which("yt-dlp") is None:
        print("yt-dlp not found. Please install it.")
        sys.exit(1)


def check_for_mpv():
    if shutil.which("mpv") is None:
        print("mpv not found. Please install it.")
        sys.exit(1)


def capture_request(route, referrer_data):
    request = route.request
    referrer = request.headers.get("referer")
    if referrer and not referrer_data["referrer"]:
        referrer_data["referrer"] = referrer
    route.continue_()


def capture_response(response, m3u8_counts):
    if response.url.endswith(".m3u8"):
        m3u8_counts[response.url] = m3u8_counts.get(response.url, 0) + 1


def fetch_m3u8_urls(url, browser_type):
    from playwright.sync_api import sync_playwright, Error  # pylint: disable=import-outside-toplevel, import-error
    m3u8_counts = {}
    referrer_data = {"referrer": None}

    with sync_playwright() as p:
        browser = p[browser_type].launch(headless=False)
        page = browser.new_page()

        # Handle popups: Close any popups that open during navigation
        page.on("popup", lambda popup: popup.close())  # Automatically close popups

        page.on("route", lambda route: capture_request(route, referrer_data))
        page.on("response", lambda response: capture_response(response, m3u8_counts))

        page.goto(url)
        page.wait_for_selector("#section-li", timeout=5000)
        page.wait_for_timeout(1000)

        # Click the second li item
        try:
            page.locator('ul#section-li > li').nth(1).locator('a.wp-btn-iframe__shortcode').click()
        except Error as e:
            print(f"Error clicking on the element: {e}")

        page.wait_for_timeout(3000)
        page.wait_for_selector("div.large-screenshot", timeout=3000)
        try:
            for _ in range(3):
                if page.locator("div.large-screenshot").first:
                    page.click("div.large-screenshot")
                    page.wait_for_timeout(2000)
        except Error as e:
            print(f"Error clicking on large-screenshot: {e}")

        page.wait_for_timeout(5000)

        unique_m3u8_urls = [url for url, count in m3u8_counts.items() if count == 1]
        browser.close()
        return unique_m3u8_urls, referrer_data["referrer"]


def process_urls(unique_m3u8_urls, use_mpv, referrer=None):
    print("\nAvailable M3U8 URLs:")
    for idx, url in enumerate(unique_m3u8_urls, start=1):
        print(f"{idx}. {url}")

    choice = int(input("Select the M3U8 URL to download/play (by number): ")) - 1
    selected_url = unique_m3u8_urls[choice]

    referrer_args = ["--referrer", referrer] if referrer else []

    if use_mpv:
        subprocess.run(["mpv", selected_url, *referrer_args], check=False)
    else:
        output_path = os.path.join(os.path.expanduser("~/Downloads"), "%(title)s.%(ext)s")
        subprocess.run(
            ["yt-dlp", selected_url, "-o", output_path, "--no-warnings", *referrer_args],
            check=False
        )


def jav(link: str = None):
    mpv = False
    if not link:
        parser = argparse.ArgumentParser(description="Fetch and download/play video from a URL.")
        parser.add_argument("url", nargs="?", help="URL of the page to fetch.")
        parser.add_argument("--mpv", action="store_true", help="Use mpv instead of yt-dlp.")
        args = parser.parse_args()

        clear_screen()
        input_url = args.url or input("Enter the URL: ")

        if args.mpv:
            check_for_mpv()
            mpv = True
    else:
        input_url = link

    check_for_ytdl()

    try:
        unique_m3u8_urls, referrer = fetch_m3u8_urls(input_url, "webkit")
        if unique_m3u8_urls:
            process_urls(unique_m3u8_urls, mpv, referrer)
        else:
            print("No unique M3U8 URLs found with WebKit. Trying Firefox as a fallback...")

        unique_m3u8_urls, referrer = fetch_m3u8_urls(input_url, "firefox")
        if unique_m3u8_urls:
            process_urls(unique_m3u8_urls, mpv, referrer)
        else:
            print("No unique M3U8 URLs found with Firefox either.")

    except KeyboardInterrupt:
        if not args.mpv:
            for file_extension in [".part", ".ytdl"]:
                for file in Path(".").glob(f"*{file_extension}"):
                    file.unlink()


if __name__ == "__main__":
    jav()
