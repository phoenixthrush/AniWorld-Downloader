import json
import re
import tempfile

import requests

AGENT = "Mozilla/5.0 (Windows NT 6.1; Win64; rv:109.0) Gecko/20100101 Firefox/109.0"
CHAPTER_FORMAT = "\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={}\nEND={}\nTITLE={}\n"
OPTION_FORMAT = "skip-{}_start={},skip-{}_end={}"


def debug_print(message, debug=False):
    if debug:
        print(message)


def die(message):
    raise RuntimeError(message)


def fetch_mal_id(anime_title, debug=False):
    debug_print(f"Fetching MAL ID for: {anime_title}", debug)
    name = re.sub(r' \(\d+ episodes\)', '', anime_title)
    keyword = re.sub(r'\s+', '%20', name)

    response = requests.get(
        f"https://myanimelist.net/search/prefix.json?type=anime&keyword={keyword}",
        headers={"User-Agent": AGENT},
        timeout=10
    )

    if response.status_code != 200:
        die("Failed to fetch MyAnimeList data.")

    mal_metadata = response.json()
    results = [entry['name'] for entry in mal_metadata['categories'][0]['items']]
    relevant_name = results[0] if results else None

    if relevant_name:
        for entry in mal_metadata['categories'][0]['items']:
            if entry['name'] == relevant_name:
                debug_print(f"Found MAL ID: {entry['id']} for {relevant_name}", debug)
                return entry['id']
    return None


def ftoi(value):
    return str(int(float(value) * 1000))


def build_options(metadata, chapters_file):
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


def build_flags(mal_id, episode, chapters_file, debug=False):
    aniskip_api = f"https://api.aniskip.com/v1/skip-times/{mal_id}/{episode}?types=op&types=ed"
    debug_print(f"Fetching skip times from: {aniskip_api}", debug)
    response = requests.get(aniskip_api, headers={"User-Agent": AGENT}, timeout=10)

    if response.status_code != 200:
        die("Failed to fetch AniSkip data.")

    metadata = response.json()
    debug_print(f"AniSkip response: {json.dumps(metadata, indent=2)}", debug)

    if not metadata.get("found"):
        return ""

    with open(chapters_file, 'w', encoding='utf-8') as f:
        f.write(";FFMETADATA1")

    options = build_options(metadata, chapters_file)
    return f"--chapters-file={chapters_file} --script-opts={options}"


def aniskip(anime_title, episode, debug=False):
    mal_id = fetch_mal_id(anime_title, debug) if not anime_title.isdigit() else anime_title
    if not mal_id:
        return ""

    chapters_file = tempfile.mktemp()
    return build_flags(mal_id, episode, chapters_file, debug)


if __name__ == "__main__":
    print(aniskip("Kaguya-sama: Love is War", 1, False))
