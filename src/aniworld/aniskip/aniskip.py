import json
import re
import tempfile
from typing import Dict, Optional
import logging

import requests
from thefuzz import process

from aniworld.common import raise_runtime_error, ftoi
from aniworld import globals

CHAPTER_FORMAT = "\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={}\nEND={}\nTITLE={}\n"
OPTION_FORMAT = "skip-{}_start={},skip-{}_end={}"


def fetch_mal_id(anime_title: str) -> Optional[str]:
    logging.debug(f"Fetching MAL ID for: {anime_title}")
    
    name = re.sub(r' \(\d+ episodes\)', '', anime_title)
    keyword = re.sub(r'\s+', '%20', name)

    response = requests.get(
        f"https://myanimelist.net/search/prefix.json?type=anime&keyword={keyword}",
        headers={"User-Agent": globals.DEFAULT_USER_AGENT},
        timeout=10
    )

    if response.status_code != 200:
        raise_runtime_error("Failed to fetch MyAnimeList data.")

    mal_metadata = response.json()
    results = [entry['name'] for entry in mal_metadata['categories'][0]['items']]

    logging.debug(anime_title)
    logging.debug(results)

    filtered_choices = [choice for choice in results if 'OVA' not in choice]
    best_match = process.extractOne(anime_title, filtered_choices)

    logging.debug(best_match)

    if best_match[0]:
        for entry in mal_metadata['categories'][0]['items']:
            if entry['name'] == best_match[0]:
                logging.debug(f"Found MAL ID: {entry['id']} for {best_match[0]}")
                return entry['id']
    return None

def build_options(metadata: Dict, chapters_file: str) -> str:
    op_end, ed_start = None, None
    options = []

    for skip in metadata["results"]:
        skip_type = skip["skip_type"]
        st_time = skip["interval"]["start_time"]
        ed_time = skip["interval"]["end_time"]

        ch_name = None

        if skip_type == "op":
            op_end = ed_time
            ch_name = "Opening"
        elif skip_type == "ed":
            ed_start = st_time
            ch_name = "Ending"

        with open(chapters_file, 'a', encoding='utf-8') as f:
            f.write(CHAPTER_FORMAT.format(ftoi(st_time), ftoi(ed_time), ch_name))

        options.append(OPTION_FORMAT.format(skip_type, st_time, skip_type, ed_time))

    if op_end:
        ep_ed = ed_start if ed_start else op_end
        with open(chapters_file, 'a', encoding='utf-8') as f:
            f.write(CHAPTER_FORMAT.format(ftoi(op_end), ftoi(ep_ed), "Episode"))

    return ",".join(options)


def build_flags(mal_id: str, episode: int, chapters_file: str) -> str:
    """
    Fetches skip times and builds the flags for a given anime episode.

    Args:
        mal_id (str): The MAL ID of the anime.
        episode (int): The episode number.
        chapters_file (str): The path to the chapters file.

    Returns:
        str: The flags for skip times.
    """
    aniskip_api = f"https://api.aniskip.com/v1/skip-times/{mal_id}/{episode}?types=op&types=ed"
    logging.debug(f"Fetching skip times from: {aniskip_api}")
    response = requests.get(aniskip_api, headers={"User-Agent": globals.DEFAULT_USER_AGENT}, timeout=10)

    if response.status_code != 200:
        raise_runtime_error("Failed to fetch AniSkip data.")

    metadata = response.json()
    logging.debug(f"AniSkip response: {json.dumps(metadata, indent=2)}")

    if not metadata.get("found"):
        return ""

    with open(chapters_file, 'w', encoding='utf-8') as f:
        f.write(";FFMETADATA1")

    options = build_options(metadata, chapters_file)
    return f"--chapters-file={chapters_file} --script-opts={options}"


def aniskip(anime_title: str, episode: int) -> str:
    """
    Retrieves AniSkip data and builds the command options for a given anime episode.

    Args:
        anime_title (str): The title of the anime.
        episode (int): The episode number.

    Returns:
        str: The command options for AniSkip.
    """
    mal_id = fetch_mal_id(anime_title) if not anime_title.isdigit() else anime_title
    if not mal_id:
        return ""

    chapters_file = tempfile.mktemp()
    return build_flags(mal_id, episode, chapters_file)


if __name__ == "__main__":
    print(aniskip("Kaguya-sama: Love is War", 1, False))
