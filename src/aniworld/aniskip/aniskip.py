import json
import logging
import tempfile
from typing import Dict

import requests
from bs4 import BeautifulSoup

from aniworld.common import (
    fetch_anime_id,
    fetch_url_content,
    ftoi,
    get_season_episode_count,
    raise_runtime_error
)

from aniworld import globals as aniworld_globals


CHAPTER_FORMAT = "\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={}\nEND={}\nTITLE={}\n"
OPTION_FORMAT = "skip-{}_start={},skip-{}_end={}"


def check_episodes(anime_id):
    url = f"https://myanimelist.net/anime/{anime_id}"

    page_content = fetch_url_content(url)

    soup = BeautifulSoup(page_content, 'html.parser')

    episodes_span = soup.find('span', class_='dark_text', string='Episodes:')

    if episodes_span and episodes_span.parent:
        episodes = episodes_span.parent.text.replace("Episodes:", "").strip()
        logging.debug("Count of the episodes %s", episodes)
        return int(episodes)

    logging.debug("The Number can not be found!")
    return None


def build_options(metadata: Dict, chapters_file: str) -> str:
    logging.debug("Building options with metadata: %s and chapters_file: %s",
                  json.dumps(metadata, indent=2), chapters_file)
    op_end, ed_start = None, None
    options = []

    for skip in metadata["results"]:
        logging.debug("Processing skip: %s", skip)
        skip_type = skip["skip_type"]
        st_time = skip["interval"]["start_time"]
        ed_time = skip["interval"]["end_time"]
        logging.debug("Skip type: %s, start time: %s, end time: %s", skip_type, st_time, ed_time)

        ch_name = None

        if skip_type == "op":
            op_end = ed_time
            ch_name = "Opening"
        elif skip_type == "ed":
            ed_start = st_time
            ch_name = "Ending"
        logging.debug("Chapter name: %s", ch_name)

        with open(chapters_file, 'a', encoding='utf-8') as f:
            f.write(CHAPTER_FORMAT.format(ftoi(st_time), ftoi(ed_time), ch_name))
            logging.debug("Wrote chapter to file: %s", chapters_file)

        options.append(OPTION_FORMAT.format(skip_type, st_time, skip_type, ed_time))
        logging.debug("Options so far: %s", options)

    if op_end:
        ep_ed = ed_start if ed_start else op_end
        with open(chapters_file, 'a', encoding='utf-8') as f:
            f.write(CHAPTER_FORMAT.format(ftoi(op_end), ftoi(ep_ed), "Episode"))
            logging.debug("Wrote episode chapter to file: %s", chapters_file)

    return ",".join(options)


def build_flags(anime_id: str, episode: int, chapters_file: str) -> str:
    logging.debug(
        "Building flags for MAL ID: %s, episode: %d, chapters_file: %s",
        anime_id, episode, chapters_file
    )
    aniskip_api = f"https://api.aniskip.com/v1/skip-times/{anime_id}/{episode}?types=op&types=ed"
    logging.debug("Fetching skip times from: %s", aniskip_api)
    response = requests.get(
        aniskip_api,
        headers={"User-Agent": aniworld_globals.DEFAULT_USER_AGENT},
        timeout=15
    )
    logging.debug("Response status code: %d", response.status_code)

    if response.status_code == 500:
        logging.info("Aniskip API is currently not working!")
        return ""
    if response.status_code != 200:
        raise_runtime_error("Failed to fetch AniSkip data.")

    metadata = response.json()
    logging.debug("AniSkip response: %s", json.dumps(metadata, indent=2))

    if not metadata.get("found"):
        logging.debug("No skip times found.")
        return ""

    with open(chapters_file, 'w', encoding='utf-8') as f:
        f.write(";FFMETADATA1")
        logging.debug("Initialized chapters file: %s", chapters_file)

    options = build_options(metadata, chapters_file)
    logging.debug("Built options: %s", options)
    return f"--chapters-file={chapters_file} --script-opts={options}"


def aniskip(anime_title: str, anime_slug: str, episode: int, season: int) -> str:
    logging.debug("Running aniskip for anime_title: %s, episode: %d", anime_title, episode)
    anime_id = fetch_anime_id(anime_title, season) if not anime_title.isdigit() else anime_title
    logging.debug("Fetched MAL ID: %s", anime_id)
    if not anime_id:
        logging.debug("No MAL ID found.")
        return ""

    logging.debug("Anime_Slug: %s", anime_slug)
    if check_episodes(anime_id) == get_season_episode_count(anime_slug, str(season)):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as chapters_file:
            logging.debug("Created temporary chapters file: %s", chapters_file.name)
            return build_flags(anime_id, episode, chapters_file.name)
    else:
        logging.debug("Check_Episode: %s", check_episodes(anime_id))
        logging.debug("Check get_season_episode_count: %s",
                      get_season_episode_count(anime_slug, str(season)))
        logging.debug("Mal ID isn't matching episode counter!")
        return ""


if __name__ == "__main__":
    # print(fetch_anime_id("Kaguya-sama: Love is War", 2))
    # print(aniskip("Kaguya-sama: Love is War", "kaguya-sama-love-is-war", 1, 2))
    pass
