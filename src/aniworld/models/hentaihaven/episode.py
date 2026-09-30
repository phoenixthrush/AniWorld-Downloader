from functools import cached_property
from urllib.parse import urlparse

from ...config import HENTAI_HAVEN_EPISODE_PATTERN
from ...extractors.common import extract_video_metadata
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
        return extract_video_metadata(self._html).get("uploadDate", "")

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
