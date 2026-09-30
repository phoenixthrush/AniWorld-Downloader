from functools import cached_property
from urllib.parse import urlparse

from ...config import HENTAI_HAVEN_EPISODE_PATTERN
from ..common.common import download as episode_download
from ..hentai_tv.episode import HentaiTVEpisode
from ..hentai_tv.page import page_objects


class HentaiHavenEpisode(HentaiTVEpisode):
    """A HentaiHaven episode with a direct HLS player source."""

    site_name = "hentaihaven.xxx"
    provider_name = "HentaiHaven"
    url_pattern = HENTAI_HAVEN_EPISODE_PATTERN

    @cached_property
    def _player(self):
        for item in page_objects(self._html):
            if "videoId" in item and "indexableSource" in item:
                return item
        raise RuntimeError("Could not find the HentaiHaven episode player")

    @property
    def _metadata(self):
        player = self._player
        return {
            "name": player.get("title", ""),
            "thumbnailUrl": player.get("poster", ""),
            "embedUrl": player.get("indexableSource", ""),
        }

    @property
    def episode_number(self):
        return int(self._slug_from_url(self.url).split("-")[-1])

    @property
    def series_title(self):
        return self.title.rsplit(" — Episode", 1)[0]

    @property
    def release_date(self):
        # The JSON-LD VideoObject carries the episode's publication date.
        import json
        import re
        from html import unescape

        from ..hentai_tv.page import walk_objects

        for script in re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            self._html,
            re.DOTALL,
        ):
            try:
                objects = walk_objects(json.loads(unescape(script)))
                for item in objects:
                    if item.get("@type") == "VideoObject":
                        return item.get("uploadDate", "")
            except ValueError:
                continue
        return ""

    @property
    def provider_url(self):
        return self.url

    @property
    def stream_url(self):
        source = self._player.get("indexableSource", "")
        if urlparse(source).scheme not in ("http", "https"):
            raise RuntimeError("The HentaiHaven player returned an invalid media URL")
        return source

    def refresh_stream_url(self):
        self.__dict__.pop("_player", None)
        self._clear_page_cache()
        return self.stream_url

    download = episode_download
