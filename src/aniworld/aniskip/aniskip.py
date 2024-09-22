import json
import re
import tempfile
from typing import Dict, Optional
import logging

import requests
from thefuzz import process

import aniworld.globals as aniworld_globals
from aniworld.common import raise_runtime_error, ftoi

CHAPTER_FORMAT = "\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={}\nEND={}\nTITLE={}\n"
OPTION_FORMAT = "skip-{}_start={},skip-{}_end={}"


def fetch_mal_id(anime_title: str) -> Optional[str]:
    logging.debug("Fetching MAL ID for: %s", anime_title)

    name = re.sub(r' \(\d+ episodes\)', '', anime_title)
    logging.debug("Processed name: %s", name)
    keyword = re.sub(r'\s+', '%20', name)
    logging.debug("Keyword for search: %s", keyword)

    response = requests.get(
        f"https://myanimelist.net/search/prefix.json?type=anime&keyword={keyword}",
        headers={"User-Agent": aniworld_globals.DEFAULT_USER_AGENT},
        timeout=10
    )
    logging.debug("Response status code: %d", response.status_code)

    if response.status_code != 200:
        raise_runtime_error("Failed to fetch MyAnimeList data.")

    mal_metadata = response.json()
    logging.debug("MAL metadata: %s", json.dumps(mal_metadata, indent=2))
    results = [entry['name'] for entry in mal_metadata['categories'][0]['items']]
    logging.debug("Results: %s", results)

    filtered_choices = [choice for choice in results if 'OVA' not in choice]
    logging.debug("Filtered choices: %s", filtered_choices)
    best_match = process.extractOne(anime_title, filtered_choices)
    logging.debug("Best match: %s", best_match)

    if best_match[0]:
        for entry in mal_metadata['categories'][0]['items']:
            if entry['name'] == best_match[0]:
                logging.debug("Found MAL ID: %s for %s", entry['id'], best_match[0])
                return entry['id']
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


def build_flags(mal_id: str, episode: int, chapters_file: str) -> str:
    logging.debug(
        "Building flags for MAL ID: %s, episode: %d, chapters_file: %s",
        mal_id, episode, chapters_file
    )
    aniskip_api = f"https://api.aniskip.com/v1/skip-times/{mal_id}/{episode}?types=op&types=ed"
    logging.debug("Fetching skip times from: %s", aniskip_api)
    response = requests.get(
        aniskip_api,
        headers={"User-Agent": aniworld_globals.DEFAULT_USER_AGENT},
        timeout=10
    )
    logging.debug("Response status code: %d", response.status_code)

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


def aniskip(anime_title: str, episode: int) -> str:
    logging.debug("Running aniskip for anime_title: %s, episode: %d", anime_title, episode)
    mal_id = fetch_mal_id(anime_title) if not anime_title.isdigit() else anime_title
    logging.debug("Fetched MAL ID: %s", mal_id)
    if not mal_id:
        logging.debug("No MAL ID found.")
        return ""

    chapters_file = tempfile.mktemp()
    logging.debug("Created temporary chapters file: %s", chapters_file)
    return build_flags(mal_id, episode, chapters_file)


if __name__ == "__main__":
    logging.debug("Starting main execution")
    print(aniskip("Kaguya-sama: Love is War", 1))
    logging.debug("Finished main execution")
