from ...config import ANIME_ID_HENTAI_EPISODE_PATTERN
from ..hentai_tv.episode import HentaiTVEpisode


class AnimeIDHentaiEpisode(HentaiTVEpisode):
    """AnimeID episode; its nhplayer extractor is shared with hentai.tv."""

    site_name = "animeidhentai.com"
    provider_name = "AnimeIDHentai"
    url_pattern = ANIME_ID_HENTAI_EPISODE_PATTERN
