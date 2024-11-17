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
import re

from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

COLORS = {
    'pink': '\033[38;5;219m',
    'cyan': '\033[38;5;51m',
    'green': '\033[38;5;156m',
    'red': '\033[38;5;196m',
    'reset': '\033[0m',
    'clear': '\033[H\033[2J'
}


def get_input(prompt):
    return input(f"{prompt}{COLORS['cyan']}> {COLORS['reset']}")


def create_output_folder(folder_name):
    output_path = os.path.join(os.path.expanduser("~/Downloads"), folder_name)
    os.makedirs(output_path, exist_ok=True)
    return output_path


def download_image(image_url, output_path, i):
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200 and response.content.startswith(b'\xff\xd8'):
            image_path = os.path.join(output_path, f'{i}.jpg')
            with open(image_path, 'wb') as image_file:
                image_file.write(response.content)
            return f"Image {i} downloaded."
    except requests.RequestException as e:
        return f"Error downloading image {i}: {e}"
    return None


def download_images_concurrently(base_url, output_path):
    with ThreadPoolExecutor(os.cpu_count() * 2) as executor:
        futures = {
            executor.submit(download_image, f"{base_url}/{i}.jpg", output_path, i): i
            for i in range(1, 1000)
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                print(f"{COLORS['green']}{result}{COLORS['reset']}", end='\r')
            else:
                break


def fetch_image_base_url(gallery_id):
    page_url = f"https://nhentai.net/g/{gallery_id}/1"
    try:
        response = requests.get(page_url, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            img_tag = soup.select_one('#image-container a img')
            if img_tag:
                img_url = img_tag['src']
                match = re.match(r'https://(\w+)\.nhentai\.net/galleries/(\d+)/\d+\.jpg', img_url)
                if match:
                    subdomain, gallery_id = match.groups()
                    return f"https://{subdomain}.nhentai.net/galleries/{gallery_id}"
    except requests.RequestException:
        pass
    return None


def nhentai(link: str = None):
    try:
        if not link:
            print(COLORS['clear'], end='')
            source = get_input(
                f"{COLORS['pink']}Please provide the image id for any doujin image (E.g. 234781)."
            )
            folder = get_input(
                f"{COLORS['pink']}What should the output folder be called?"
            )
        else:
            nhentai_id = re.search(r'\d+', link).group()

            source = nhentai_id
            folder = nhentai_id

        output_path = create_output_folder(folder)
        base_url = fetch_image_base_url(source)

        if base_url:
            download_images_concurrently(base_url, output_path)
        else:
            print(f"{COLORS['red']}"
                  f"Error: Unable to fetch the base URL for images.{COLORS['reset']}")
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    nhentai()
