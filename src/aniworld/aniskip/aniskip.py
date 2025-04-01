import re
import logging
import tempfile
from typing import Dict
import os
import shutil

import requests
from bs4 import BeautifulSoup

from aniworld.config import DEFAULT_REQUEST_TIMEOUT, MPV_SCRIPTS_DIRECTORY

CHAPTER_FORMAT = "\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={}\nEND={}\nTITLE={}\n"
OPTION_FORMAT = "skip-{}_start={},skip-{}_end={}"
MAL_ANIME_URL = "https://myanimelist.net/anime/{}"
MAL_SEARCH_URL = "https://myanimelist.net/search/prefix.json?type=anime&keyword={}"
ANISKIP_API_URL = "https://api.aniskip.com/v1/skip-times/{}/{}?types=op&types=ed"


def ftoi(value: float) -> str:
    return str(int(value * 1000))


def check_episodes(anime_id):
    response = requests.get(
        MAL_ANIME_URL.format(anime_id),
        timeout=DEFAULT_REQUEST_TIMEOUT
    )
    soup = BeautifulSoup(response.content, 'html.parser')
    episodes_span = soup.find('span', class_='dark_text', string='Episodes:')

    if episodes_span and episodes_span.parent:
        episodes = episodes_span.parent.text.replace("Episodes:", "").strip()
        logging.debug("Count of the episodes %s", episodes)
        return int(episodes)

    logging.warning("The Number can not be found!")
    return None


def get_mal_id_from_title(title: str, season: int) -> int:
    logging.debug("Fetching MAL ID for: %s", title)

    name = re.sub(r' \(\d+ episodes\)', '', title)
    keyword = re.sub(r'\s+', '%20', name)

    response = requests.get(
        MAL_SEARCH_URL.format(keyword),
        timeout=DEFAULT_REQUEST_TIMEOUT
    )
    logging.debug("Response status code: %d", response.status_code)

    if response.status_code != 200:
        logging.error(
            "Failed to fetch MyAnimeList data. HTTP Status: %d", response.status_code)
        return 0

    mal_metadata = response.json()
    results = [
        entry for entry in mal_metadata['categories'][0]['items']
        if 'OVA' not in entry['name']
    ]

    if not results:
        logging.error("No match found!")
        raise ValueError("No match found!")

    best_match = results[0]
    anime_id = best_match['id']
    logging.debug("Found MAL ID: %s for %s", anime_id, best_match)

    while season > 1:
        anime_id = get_sequel_anime_id(anime_id)
        season -= 1

    return anime_id


def get_sequel_anime_id(anime_id: int) -> int:
    url = MAL_ANIME_URL.format(anime_id)
    response = requests.get(url, timeout=DEFAULT_REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    sequel_div = soup.find(
        "div", string=lambda text: text and "Sequel" in text and "(TV)" in text)

    if not sequel_div:
        raise ValueError("Sequel (TV) not found")

    title_div = sequel_div.find_next("div", class_="title")
    if not title_div:
        raise ValueError("No 'title'-Div found")

    link_element = title_div.find("a")
    if not link_element:
        raise ValueError("No Link found in 'title'-Div")

    link_url = link_element.get("href")
    match = re.search(r'/anime/(\d+)', link_url)

    if not match:
        raise ValueError("No Anime-ID found in the link URL")

    return match.group(1)


def build_options(metadata: Dict, chapters_file: str) -> str:
    op_end, ed_start = None, None
    options = []

    for skip in metadata["results"]:
        skip_type = skip["skip_type"]
        st_time = skip["interval"]["start_time"]
        ed_time = skip["interval"]["end_time"]

        ch_name = "Opening" if skip_type == "op" else "Ending" if skip_type == "ed" else None
        if skip_type == "op":
            op_end = ed_time
        elif skip_type == "ed":
            ed_start = st_time

        with open(chapters_file, 'a', encoding='utf-8') as f:
            f.write(CHAPTER_FORMAT.format(
                ftoi(st_time), ftoi(ed_time), ch_name))

        options.append(OPTION_FORMAT.format(
            skip_type, st_time, skip_type, ed_time))

    if op_end:
        ep_ed = ed_start if ed_start else op_end
        with open(chapters_file, 'a', encoding='utf-8') as f:
            f.write(CHAPTER_FORMAT.format(
                ftoi(op_end), ftoi(ep_ed), "Episode"))

    return ",".join(options)


def build_flags(anime_id: str, episode: int, chapters_file: str) -> str:
    aniskip_api = ANISKIP_API_URL.format(anime_id, episode)
    response = requests.get(aniskip_api, timeout=DEFAULT_REQUEST_TIMEOUT)

    if response.status_code == 500:
        logging.info("Aniskip API is currently not working!")
        return ""
    if response.status_code != 200:
        logging.info("Failed to fetch AniSkip data.")
        return ""

    metadata = response.json()

    if not metadata.get("found"):
        logging.warning("No skip times found.")
        return ""

    with open(chapters_file, 'w', encoding='utf-8') as f:
        f.write(";FFMETADATA1")

    options = build_options(metadata, chapters_file)
    return f"--chapters-file={chapters_file} --script-opts={options}"


def aniskip(title: str, episode: int, season: int) -> str:
    setup_autostart()
    setup_autoexit()
    setup_aniskip()

    anime_id = get_mal_id_from_title(
        title, season) if not title.isdigit() else title
    if not anime_id:
        logging.warning("No MAL ID found.")
        return ""

    if check_episodes(anime_id):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as chapters_file:
            return build_flags(anime_id, episode, chapters_file.name)
    else:
        logging.warning("Mal ID isn't matching episode counter!")
        return ""


def copy_file_if_different(source_path, destination_path):
    if os.path.exists(destination_path):
        with open(source_path, 'r', encoding="utf-8") as source_file:
            source_content = source_file.read()

        with open(destination_path, 'r', encoding="utf-8") as destination_file:
            destination_content = destination_file.read()

        if source_content != destination_content:
            logging.debug(
                "Content differs, overwriting %s", os.path.basename(
                    destination_path)
            )
            shutil.copy(source_path, destination_path)
        else:
            logging.debug(
                "%s already exists and is identical, no overwrite needed",
                os.path.basename(destination_path)
            )
    else:
        logging.debug(
            "Copying %s to %s",
            os.path.basename(source_path),
            os.path.dirname(destination_path)
        )
        shutil.copy(source_path, destination_path)


def setup_aniskip():
    script_directory = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    mpv_scripts_directory = MPV_SCRIPTS_DIRECTORY

    if not os.path.exists(mpv_scripts_directory):
        os.makedirs(mpv_scripts_directory)

    skip_source_path = os.path.join(
        script_directory, 'aniskip', 'scripts', 'aniskip.lua')
    skip_destination_path = os.path.join(mpv_scripts_directory, 'aniskip.lua')

    copy_file_if_different(skip_source_path, skip_destination_path)


def setup_autostart():
    logging.debug("Copying autostart.lua to mpv script directory")
    script_directory = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    mpv_scripts_directory = MPV_SCRIPTS_DIRECTORY

    if not os.path.exists(mpv_scripts_directory):
        os.makedirs(mpv_scripts_directory)

    autostart_source_path = os.path.join(
        script_directory, 'aniskip', 'scripts', 'autostart.lua')
    autostart_destination_path = os.path.join(
        mpv_scripts_directory, 'autostart.lua')

    copy_file_if_different(autostart_source_path, autostart_destination_path)


def setup_autoexit():
    logging.debug("Copying autoexit.lua to mpv script directory")
    script_directory = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    mpv_scripts_directory = MPV_SCRIPTS_DIRECTORY

    if not os.path.exists(mpv_scripts_directory):
        os.makedirs(mpv_scripts_directory)

    autoexit_source_path = os.path.join(
        script_directory, 'aniskip', 'scripts', 'autoexit.lua')
    autoexit_destination_path = os.path.join(
        mpv_scripts_directory, 'autoexit.lua')

    copy_file_if_different(autoexit_source_path, autoexit_destination_path)


if __name__ == '__main__':
    # setup_aniskip()
    # setup_autoexit()
    # setup_autostart()

    print(get_mal_id_from_title("Kaguya-sama: Love is War", season=1))
