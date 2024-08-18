#!/usr/bin/env python
# encoding: utf-8

import argparse
import os
import sys
import time
import re

from bs4 import BeautifulSoup
import npyscreen

from aniworld import clear_screen, search, execute
from aniworld.common import fetch_url_content, clean_up_leftovers, get_season_data


class AnimeDownloader:
    BASE_URL_TEMPLATE = "https://aniworld.to/anime/stream/{anime}/"

    def __init__(self, anime_slug):
        self.anime_slug = anime_slug
        self.anime_title = self.format_anime_title(anime_slug)
        self.base_url = self.BASE_URL_TEMPLATE.format(anime=anime_slug)
        self.season_data = self.get_season_data()

    @staticmethod
    def format_anime_title(anime_slug):
        try:
            return anime_slug.replace("-", " ").title()
        except AttributeError:
            sys.exit()

    def get_season_episodes(self, season_url):
        season_url_old = season_url
        season_url = season_url[:-2]
        season_html = fetch_url_content(season_url)
        if season_html is None:
            return []
        season_soup = BeautifulSoup(season_html, 'html.parser')
        episodes = season_soup.find_all('meta', itemprop='episodeNumber')
        episode_numbers = [int(episode['content']) for episode in episodes]
        highest_episode = max(episode_numbers, default=None)

        season_suffix = f"/staffel-{season_url_old.split('/')[-1]}"
        episode_urls = [
            f"{season_url}{season_suffix}/episode-{num}"
            for num in range(1, highest_episode + 1)
        ]

        return episode_urls

    def get_season_data(self):
        main_html = fetch_url_content(self.base_url)
        if main_html is None:
            sys.exit("Failed to retrieve main page.")

        soup = BeautifulSoup(main_html, 'html.parser')
        if 'Deine Anfrage wurde als Spam erkannt.' in soup.text:
            sys.exit("Your IP-Address is blacklisted, please use a VPN or try later.")

        season_meta = soup.find('meta', itemprop='numberOfSeasons')
        number_of_seasons = int(season_meta['content']) if season_meta else 0
        if soup.find('a', title='Alle Filme'):
            number_of_seasons -= 1

        season_data = {}
        for i in range(1, number_of_seasons + 1):
            season_url = f"{self.base_url}{i}"
            season_data[i] = self.get_season_episodes(season_url)

        return season_data


class EpisodeForm(npyscreen.ActionForm):
    def create(self):
        episode_list = [
            url
            for season, episodes in self.parentApp.anime_downloader.season_data.items()
            for url in episodes
        ]

        self.action_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Watch, Download or Syncplay",
            values=["Watch", "Download", "Syncplay"],
            max_height=4,
            value=[1],
            scroll_exit=True
        )

        self.aniskip_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Use Aniskip (Skip Intro & Outro)",
            values=["Yes", "No"],
            max_height=3,
            value=[1],
            scroll_exit=True
        )

        self.directory_field = self.add(
            npyscreen.TitleFilenameCombo,
            name="Directory:",
            value=os.path.join(os.path.expanduser('~'), 'Downloads')
        )

        self.language_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Language Options",
            values=["German Dub", "English Sub", "German Sub"],
            max_height=4,
            value=[2],
            scroll_exit=True
        )

        self.provider_selector = self.add(
            npyscreen.TitleSelectOne,
            name="Provider Options (VOE recommended for Downloading)",
            values=["Vidoza", "Streamtape", "VOE", "Doodstream"],
            max_height=4,
            value=[0],
            scroll_exit=True
        )

        self.episode_selector = self.add(
            npyscreen.TitleMultiSelect,
            name="Select Episodes",
            values=episode_list,
            max_height=7
        )

        self.action_selector.when_value_edited = self.update_directory_visibility

    def update_directory_visibility(self):
        selected_action = self.action_selector.get_selected_objects()
        if selected_action and selected_action[0] == "Watch" or selected_action[0] == "Syncplay":
            self.directory_field.hidden = True
            self.aniskip_selector.hidden = False
        else:
            self.directory_field.hidden = False
            self.aniskip_selector.hidden = True
        self.display()

    def on_ok(self):  # TODO - refactor the code to reduce complexity
        npyscreen.blank_terminal()
        output_directory = self.directory_field.value if not self.directory_field.hidden else None
        if not output_directory and not self.directory_field.hidden:
            npyscreen.notify_confirm("Please provide a directory.", title="Error")
            return

        selected_episodes = self.episode_selector.get_selected_objects()
        action_selected = self.action_selector.get_selected_objects()
        language_selected = self.language_selector.get_selected_objects()
        provider_selected = self.provider_selector.get_selected_objects()
        aniskip_selected = self.aniskip_selector.get_selected_objects()

        lang = language_selected[0]

        lang = lang.replace('German Dub', "1")
        lang = lang.replace('English Sub', "2")
        lang = lang.replace('German Sub', "3")

        # doodstream currently broken
        valid_providers = ["Vidoza", "Streamtape", "VOE"]

        while provider_selected[0] not in valid_providers:
            message = (
                "Doodstream is currently broken.\n"
                "Falling back to Vidoza."
            )
            title = "Provider Error"

            npyscreen.notify_confirm(message, title=title)
            self.provider_selector.value = 0

            provider_selected = ["Vidoza"]

        if selected_episodes and action_selected and language_selected:
            selected_str = "\n".join(selected_episodes)
            npyscreen.notify_confirm(f"Selected episodes:\n{selected_str}", title="Selection")

            if not self.directory_field.hidden:
                anime_title = self.parentApp.anime_downloader.anime_title
                output_directory = os.path.join(output_directory, anime_title)
                os.makedirs(output_directory, exist_ok=True)

            params = {
                'selected_episodes': selected_episodes,
                'provider_selected': provider_selected[0],
                'action_selected': action_selected[0],
                'aniskip_selected': aniskip_selected[0],
                'lang': lang,
                'output_directory': output_directory,
                'anime_title': self.parentApp.anime_downloader.anime_title
            }

            execute(params)

            if not self.directory_field.hidden:
                clean_up_leftovers(output_directory)

            self.parentApp.setNextForm(None)
            self.parentApp.switchFormNow()
        else:
            npyscreen.notify_confirm("No episodes selected.", title="Selection")

    def on_cancel(self):
        self.parentApp.setNextForm(None)


class AnimeApp(npyscreen.NPSAppManaged):
    def __init__(self, anime_slug):
        super().__init__()
        self.anime_downloader = AnimeDownloader(anime_slug)

    def onStart(self):
        self.addForm("MAIN", EpisodeForm, name="Anime Downloader")


def main():
    try:
        parser = argparse.ArgumentParser(description="Parse optional command line arguments.")
        parser.add_argument(
            '--slug',
            type=str,
            help='Search query - E.g. demon-slayer-kimetsu-no-yaiba'
        )
        parser.add_argument(
            '--link',
            type=str,
            help=(
                'Search query - E.g. '
                'https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba'
            )
        )
        parser.add_argument(
            '--query',
            type=str,
            help=(
                'Search query input - E.g. '
                'demon'
            )
        )
        parser.add_argument(
            '--episode',
            type=str,
            nargs='+',
            help=(
                'List of episode URLs - E.g. '
                'https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/ '
                'staffel-1/episode-1, '
                'https://aniworld.to/anime/stream/demon-slayer-kimetsu-no-yaiba/ '
                'staffel-1/episode-2'
            )
        )
        parser.add_argument(
            '--action',
            type=str,
            choices=['Watch', 'Download', 'Syncplay'],
            default='Watch',
            help=(
                'Action to perform - E.g. '
                'Watch, Download, Syncplay'
            )
        )
        parser.add_argument(
            '--output',
            type=str,
            default=os.path.join(os.path.expanduser('~'), 'Downloads'),
            help='Download directory (default: ~/Downloads)'
        )
        parser.add_argument(
            '--language',
            type=str,
            choices=['German Dub', 'English Sub', 'German Sub'],
            default='German Sub',
            help='Language choice - E.g. German Dub, English Sub, German Sub'
        )
        parser.add_argument(
            '--provider',
            type=str,
            choices=['Vidoza', 'Streamtape', 'VOE', 'Doodstream'],
            default='Vidoza',
            help='Provider choice - E.g. Vidoza, Streamtape, VOE, Doodstream'
        )
        parser.add_argument('--aniskip', action='store_true', help='Skip anime opening and ending')
        parser.add_argument('--keep-watching', action='store_true', help='Continue watching')
        parser.add_argument('--only-direct-link', action='store_true', help='Output direct link')
        parser.add_argument('--only-command', action='store_true', help='Output command')
        parser.add_argument('--proxy', type=str, help='Set HTTP Proxy (not working yet)')  # TODO
        parser.add_argument('--debug', action='store_true', help='Enable debug mode')

        args = parser.parse_args()

        if args.query and not args.episode:
            slug = search.search_anime(query=args.query)
            season_data = get_season_data(anime_slug=slug)
            episode_list = [
                url
                for season, episodes in season_data.items()
                for url in episodes
            ]

            user_input = input("Please enter the episode (e.g., S1E2): ")
            match = re.match(r"S(\d+)E(\d+)", user_input)
            if match:
                s = int(match.group(1))
                e = int(match.group(2))

            args.episode = [f"https://aniworld.to/anime/stream/{slug}/staffel-{s}/episode-{e}"]

        language = None
        anime_title = None
        if args.link:
            anime_title = args.link.split('/')[-1]
        elif args.slug:
            anime_title = args.slug
        elif args.episode:
            anime_title = args.episode[0].split('/')[5]

        if args.language:
            language = {
                "German Dub": "1",
                "English Sub": "2",
                "German Sub": "3"
            }.get(args.language, "")

        updated_list = None
        if args.keep_watching:
            if args.episode:
                season_data = get_season_data(anime_slug=anime_title)
                episode_list = [
                    url
                    for season, episodes in season_data.items()
                    for url in episodes
                ]

                if args.debug:
                    print(f"Episode List: {episode_list}\n")
                    print(args.episode[0])

                # remove all episodes before user selection
                index = episode_list.index(args.episode[0])
                updated_list = episode_list[index:]

                if args.debug:
                    print(f"Updated List: {updated_list}\n")

        if updated_list:
            selected_episodes = updated_list
        else:
            selected_episodes = args.episode

        if args.episode:
            params = {
                'selected_episodes': selected_episodes,
                'provider_selected': args.provider,
                'action_selected': args.action,
                'aniskip_selected': args.aniskip,
                'lang': language,
                'output_directory': args.output,
                'anime_title': anime_title.replace('-', ' ').title(),
                'only_direct_link': args.only_direct_link,
                'only_command': args.only_command,
                'debug': args.debug
            }
            execute(params=params)
            sys.exit()
    except KeyboardInterrupt:
        sys.exit()

    def run_app(query):
        app = AnimeApp(query)
        app.run()

    try:
        query = search.search_anime(slug=args.slug, link=args.link)
        keep_running = True

        while keep_running:
            try:
                run_app(query)
                keep_running = False
            except npyscreen.wgwidget.NotEnoughSpaceForWidget:
                clear_screen()
                print("Please increase your current terminal size.")
                time.sleep(1)
        sys.exit()
    except KeyboardInterrupt:
        sys.exit()


if __name__ == "__main__":
    main()
