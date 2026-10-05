import os
import re
from functools import cached_property
from urllib.parse import urljoin, urlparse

import ffmpeg

from ...config import HENTAI_HAVEN_EPISODE_PATTERN, logger
from ...extractors.common import extract_video_metadata
from ..common.common import _run_ffmpeg_with_progress
from ..common.common import download as episode_download
from ..common.hls import _parse_attributes
from ..hentai_tv.episode import HentaiTVEpisode
from ..hentai_tv.http import get_response, post_response
from ..hentai_tv.page import page_objects

# Where the site's own player asks for a source when the page carries none
STREAM_API = "https://hentaihaven.xxx/api/stream/"

# Subtitle codecs each container can hold; a WebVTT file converts to either.
_SUBTITLE_CODECS = {".mkv": "srt", ".mp4": "mov_text"}


class HentaiHavenEpisode(HentaiTVEpisode):
    """A HentaiHaven episode with a direct HLS player source."""

    site_name = "hentaihaven.xxx"
    provider_name = "HentaiHaven"
    url_pattern = HENTAI_HAVEN_EPISODE_PATTERN
    # Newer streams are fMP4 with the audio as its own rendition, which only
    # the shared parallel HLS downloader puts back together correctly.
    _separate_audio_rendition = True

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
        return re.sub(r" — (?:Episode|Season) \d+$", "", self.title)

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
            source = self._requested_source()
        if urlparse(source).scheme not in ("http", "https"):
            raise RuntimeError("The HentaiHaven player returned an invalid media URL")
        return source

    def _requested_source(self):
        """Ask the site for a source, as its player does for older titles."""
        player = self._player
        if not player.get("slug"):
            return ""
        payload = post_response(
            STREAM_API,
            json={
                "slug": player["slug"],
                "permalink": player.get("permalink", ""),
                "poster": player.get("poster", ""),
            },
        ).json()
        data = payload.get("data") or {}
        for source in (data.get("sources") or []) + (data.get("fallbackSources") or []):
            if isinstance(source, dict) and isinstance(source.get("src"), str):
                return source["src"]
        return ""

    def refresh_stream_url(self):
        self.__dict__.pop("_player", None)
        self._clear_page_cache()
        return self.stream_url

    @property
    def subtitle_url(self):
        """The English WebVTT track the master playlist lists, if it has one.

        Newer streams carry no burned-in subtitles, the player overlays these.
        """
        master = get_response(self.stream_url).text
        for line in master.splitlines():
            if not line.startswith("#EXT-X-MEDIA:"):
                continue
            attrs = _parse_attributes(line)
            if (
                attrs.get("TYPE") == "SUBTITLES"
                and attrs.get("LANGUAGE", "").lower().startswith("en")
                and attrs.get("URI", "").split("?", 1)[0].lower().endswith(".vtt")
            ):
                return urljoin(self.stream_url, attrs["URI"])
        return None

    def _add_subtitles(self):
        path = self._episode_path
        codec = _SUBTITLE_CODECS.get(path.suffix.lower())
        if codec is None:
            logger.warning(f"[SUBTITLES] {path.suffix} cannot hold subtitles")
            return

        subtitles = [
            stream
            for stream in ffmpeg.probe(str(path)).get("streams", [])
            if stream.get("codec_type") == "subtitle"
        ]
        if any(
            stream.get("tags", {}).get("language", "").lower() in {"en", "eng"}
            for stream in subtitles
        ):
            return

        url = self.subtitle_url
        if not url:
            return

        subtitle_index = len(subtitles)
        vtt = path.with_suffix(".en.vtt")
        muxed = path.with_suffix(f".subs{path.suffix}")
        try:
            vtt.write_bytes(get_response(url).content)
            _run_ffmpeg_with_progress(
                ffmpeg.output(
                    ffmpeg.input(str(path)),
                    ffmpeg.input(str(vtt)),
                    str(muxed),
                    c="copy",
                    **{
                        f"c:s:{subtitle_index}": codec,
                        f"metadata:s:s:{subtitle_index}": "language=eng",
                        f"disposition:s:{subtitle_index}": "default",
                    },
                ),
                label=self._file_name,
            )
            os.replace(muxed, path)
        finally:
            vtt.unlink(missing_ok=True)
            muxed.unlink(missing_ok=True)

    def download(self):
        episode_download(self)
        if not self._episode_path.exists():
            return
        try:
            self._add_subtitles()
        except Exception as exc:
            # The video itself is fine, keep it rather than throw it away
            logger.warning(f"[SUBTITLES] Could not add English subtitles: {exc}")
