import os
import re
import shutil
import sys
import subprocess
import shlex
import getpass
import platform

from bs4 import BeautifulSoup

from aniworld import (
    doodstream_get_direct_link,
    streamtape_get_direct_link,
    vidoza_get_direct_link,
    voe_get_direct_link,
    fetch_url_content,
    check_dependencies,
    aniskip,
    setup_aniskip
)

"""
TODO:
    - Split into multiple functions
    - Add type and function description
"""

def providers(soup):
    hoster_site_video = soup.find(class_='hosterSiteVideo').find('ul', class_='row')
    episode_links = hoster_site_video.find_all('li')

    extracted_data = {}
    for link in episode_links:
        data_lang_key = int(link.get('data-lang-key'))
        redirect_link = link.get('data-link-target')
        h4_text = link.find('h4').text.strip()

        if h4_text not in extracted_data:
            extracted_data[h4_text] = {}

        extracted_data[h4_text][data_lang_key] = f"https://aniworld.to{redirect_link}"

    return extracted_data

def execute(
    selected_episodes: list,
    provider_selected,
    action_selected,
    aniskip_selected,
    lang,
    output_directory,
    anime_title,
    only_direct_link=False,
    only_command=False,
    debug=False
):
    for episode_url in selected_episodes:
        episode_html = fetch_url_content(episode_url)
        if episode_html is None:
            continue
        soup = BeautifulSoup(episode_html, 'html.parser')

        if debug:
            print(f"Episode Soup: {soup.prettify}")

        episodeGermanTitle = soup.find('span', class_='episodeGermanTitle').text
        episodeEnglishTitle = soup.find('small', class_='episodeEnglishTitle').text
        episode_title = f"{episodeGermanTitle} / {episodeEnglishTitle}"

        anime_title = soup.find('div', class_='hostSeriesTitle').text

        if debug:
            print(f"Episode Title: {episode_title}")

        data = providers(soup)

        if debug:
            print(f"Provider Data: {data}")

        provider_mapping = {
            "Vidoza": vidoza_get_direct_link,
            "VOE": voe_get_direct_link,
            "Doodstream": doodstream_get_direct_link,
            "Streamtape": streamtape_get_direct_link
        }

        if provider_selected in data:
            for language in data[provider_selected]:
                if language == int(lang):
                    matches = re.findall(r'\d+', episode_url)
                    season_number = matches[-2]
                    episode_number = matches[-1]

                    action = action_selected

                    if aniskip_selected:
                        setup_aniskip()

                    provider_function = provider_mapping[provider_selected]
                    request_url = data[provider_selected][language]
                    html_content = fetch_url_content(request_url)
                    soup = BeautifulSoup(html_content, 'html.parser')

                    if debug:
                        print(f"Episode Data: {soup.prettify}")

                    link = provider_function(soup)

                    if only_direct_link:
                        print(link)
                        sys.exit()

                    mpv_title = f"{anime_title} S{season_number}E{episode_number} - {episode_title}"

                    if action == "Watch":
                        check_dependencies(["mpv"])
                        if not only_command:
                            print(f"Playing '{mpv_title}")
                        command = [
                            "mpv",
                            link,
                            "--fs",
                            "--quiet",
                            "--really-quiet",
                            f"--force-media-title={mpv_title}"
                        ]
                        if aniskip_selected:
                            if season_number != 1:
                                print("Warning: This is not season 1.\n"
                                      "Aniskip timestamps may be incorrect.\n"
                                      "This will be fixed in future!")
                            skip_options = aniskip(anime_title, episode_number)
                            skip_options_list = skip_options.split(' --')
                            result = [
                                f"--{opt}" if not opt.startswith('--') else opt
                                for opt in skip_options_list
                            ]
                            command.extend(result)

                        if only_command:
                            print(' '.join(shlex.quote(arg) for arg in command))
                        else:
                            subprocess.run(command, check=True)
                    elif action == "Download":
                        check_dependencies(["yt-dlp"])
                        file_name = f"{mpv_title}.mp4"
                        file_path = os.path.join(output_directory, file_name)
                        if not only_command:
                            print(f"Downloading to '{file_path}'")

                        output_file = os.path.join(
                            output_directory,
                            f"{mpv_title}.mp4"
                        )

                        command = [
                            "yt-dlp",
                            "--fragment-retries",
                            "infinite",
                            "--concurrent-fragments",
                            "4",
                            "-o", output_file,
                            "--quiet",
                            "--progress",
                            "--no-warnings",
                            link
                        ]
                        if only_command:
                            print(' '.join(shlex.quote(arg) for arg in command))
                        else:
                            subprocess.run(command, check=True)
                    elif action == "Syncplay":
                        check_dependencies(["syncplay"])
                        if platform.system() == "Windows":
                            syncplay = "SyncplayConsole"
                        else:
                            syncplay = "syncplay"

                        command = [
                            syncplay,
                            "--no-gui",
                            "--host", "syncplay.pl:8997",
                            "--name", getpass.getuser(),
                            "--room", mpv_title,
                            "--player-path", shutil.which("mpv"),
                            link,
                            "--", "--fs",
                            "--", f"--force-media-title={mpv_title}"
                        ]
                        if aniskip_selected:
                            if season_number != 1:
                                print("Warning: This is not season 1.\n"
                                      "Aniskip timestamps may be incorrect.\n"
                                      "This will be fixed in future!")
                            skip_options = aniskip(anime_title, episode_number)
                            skip_options_list = skip_options.split(' --')
                            result = [
                                f"--{opt}" if not opt.startswith('--') else opt
                                for opt in skip_options_list
                            ]
                            command.extend(result)
                        if only_command:
                            print(' '.join(shlex.quote(arg) for arg in command))
                        else:
                            subprocess.run(command, check=True)
                        break