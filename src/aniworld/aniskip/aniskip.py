import re
import logging
import json
import tempfile
from typing import Dict

import requests
from bs4 import BeautifulSoup

from aniworld.config import DEFAULT_REQUEST_TIMEOUT

CHAPTER_FORMAT = "\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={}\nEND={}\nTITLE={}\n"
OPTION_FORMAT = "skip-{}_start={},skip-{}_end={}"


def ftoi(value: float) -> str:
    return str(int(value * 1000))


def check_episodes(anime_id):
    response = requests.get(
        f"https://myanimelist.net/anime/{anime_id}",
        timeout=DEFAULT_REQUEST_TIMEOUT
    )
    soup = BeautifulSoup(response.content, 'html.parser')
    episodes_span = soup.find('span', class_='dark_text', string='Episodes:')

    if episodes_span and episodes_span.parent:
        episodes = episodes_span.parent.text.replace("Episodes:", "").strip()
        logging.debug("Count of the episodes %s", episodes)
        return int(episodes)

    logging.debug("The Number can not be found!")
    return None


def get_mal_id_from_title(title: str, season: int) -> int:
    logging.debug("Fetching MAL ID for: %s", title)

    name = re.sub(r' \(\d+ episodes\)', '', title)
    logging.debug("Processed name: %s", name)

    keyword = re.sub(r'\s+', '%20', name)
    logging.debug("Keyword for search: %s", keyword)

    response = requests.get(
        f"https://myanimelist.net/search/prefix.json?type=anime&keyword={keyword}",
        timeout=DEFAULT_REQUEST_TIMEOUT
    )
    logging.debug("Response status code: %d", response.status_code)

    if response.status_code != 200:
        logging.error("Failed to fetch MyAnimeList data. HTTP Status: %d", response.status_code)
        # raise ValueError("Error fetching data from MyAnimeList.")
        return 0

    mal_metadata = response.json()
    results = [
        entry for entry in mal_metadata['categories'][0]['items']
        if 'OVA' not in entry['name']
    ]
    logging.debug("Search results: %s", results)

    if not results:
        logging.error("No match found!")
        raise ValueError("No match found!")

    best_match = results[0]
    logging.debug("Best match: %s", best_match)

    for entry in mal_metadata['categories'][0]['items']:
        if entry['name'] == best_match['name']:
            anime_id = entry['id']
            logging.debug("Found MAL ID: %s for %s", anime_id, best_match)

            while season > 1:
                url = f"https://myanimelist.net/anime/{anime_id}"
                logging.debug("Fetching URL: %s", url)

                response = requests.get(url, timeout=DEFAULT_REQUEST_TIMEOUT)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')
                sequel_div = soup.find(
                    "div",
                    string=lambda text: text and "Sequel" in text and "(TV)" in text
                )

                if not sequel_div:
                    error_msg = "Sequel (TV) not found"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                title_div = sequel_div.find_next("div", class_="title")
                if not title_div:
                    error_msg = "No 'title'-Div found"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                link_element = title_div.find("a")
                if not link_element:
                    error_msg = "No Link found in 'title'-Div"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                link_url = link_element.get("href")
                logging.debug("Found Link: %s", link_url)
                match = re.search(r'/anime/(\d+)', link_url)

                if not match:
                    error_msg = "No Anime-ID found in the link URL"
                    logging.error(error_msg)
                    raise ValueError(error_msg)

                anime_id = match.group(1)
                logging.debug("Anime ID: %s", anime_id)
                season -= 1

            return anime_id

    error_msg = "No match found!"
    logging.error(error_msg)
    raise ValueError(error_msg)


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
        timeout=DEFAULT_REQUEST_TIMEOUT
    )
    logging.debug("Response status code: %d", response.status_code)

    if response.status_code == 500:
        logging.info("Aniskip API is currently not working!")
        return ""
    if response.status_code != 200:
        logging.info("Failed to fetch AniSkip data.")
        return ""

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


def aniskip(title: str, episode: int, season: int) -> str:
    logging.debug("Running aniskip for anime_title: %s, episode: %d", title, episode)
    anime_id = get_mal_id_from_title(title, season) if not title.isdigit() else title
    logging.debug("Fetched MAL ID: %s", anime_id)
    if not anime_id:
        logging.debug("No MAL ID found.")
        return ""

    if check_episodes(anime_id):  # == episode_count: # TODO Add episode count of season
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as chapters_file:
            logging.debug("Created temporary chapters file: %s", chapters_file.name)
            return build_flags(anime_id, episode, chapters_file.name)
    else:
        logging.debug("Check_Episode: %s", check_episodes(anime_id))
        logging.debug("Check get_season_episode_count: %s", 123)
        logging.debug("Mal ID isn't matching episode counter!")
        return ""


if __name__ == '__main__':
    print(get_mal_id_from_title("Kaguya-sama: Love is War", season=1))
