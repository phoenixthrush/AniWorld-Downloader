import re
from functools import cached_property
from html import unescape
from urllib.parse import urljoin

from ...config import HENTAI_HAVEN_SERIES_PATTERN
from ..common import run_each
from ..hentai_tv.http import get_response
from .episode import HentaiHavenEpisode


class HentaiHavenSeries:
    """A HentaiHaven title and its episodes, in release order."""

    def __init__(
        self, url, selected_path=None, selected_language=None, selected_provider=None
    ):
        if not isinstance(url, str) or not HENTAI_HAVEN_SERIES_PATTERN.fullmatch(url):
            raise ValueError(f"Invalid hentaihaven.xxx series URL: {url}")
        self.url = url
        self.selected_path = selected_path
        self.selected_language = selected_language
        self.selected_provider = selected_provider

    @cached_property
    def episodes(self):
        html = get_response(self.url).text
        urls = set()
        for href in re.findall(r'href=["\']([^"\']+)', html):
            url = urljoin(self.url, unescape(href))
            if url.startswith(
                self.url.rstrip("/") + "/"
            ) and HentaiHavenEpisode._is_valid_url(url):
                urls.add(url)
        if not urls:
            raise RuntimeError("Could not find any HentaiHaven episodes")
        episodes = [
            HentaiHavenEpisode(
                url,
                selected_path=self.selected_path,
                selected_language=self.selected_language,
                selected_provider=self.selected_provider,
            )
            for url in urls
        ]
        return sorted(episodes, key=lambda episode: episode.episode_number)

    def _run(self, action):
        failures = run_each(self.episodes, action)
        if failures:
            raise RuntimeError(
                f"Could not {action} {len(failures)} HentaiHaven episode(s)"
            )

    def download(self):
        self._run("download")

    def watch(self):
        self._run("watch")

    def syncplay(self):
        self._run("syncplay")
