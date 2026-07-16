import unittest
from unittest.mock import patch

from aniworld.models import AniworldEpisode


class _SeriesWithoutMalId:
    mal_id = []


class _FirstSeason:
    season_number = 1


class _SeriesWithMalId:
    mal_id = [5114]


class AniSkipFallbackTests(unittest.TestCase):
    def test_missing_mal_id_skips_optional_aniskip_lookup(self):
        episode = AniworldEpisode(
            "https://aniworld.to/anime/stream/example/staffel-1/episode-1",
            series=_SeriesWithoutMalId(),
            season=_FirstSeason(),
            episode_number=1,
        )

        with patch("aniworld.aniskip.get_skip_times") as get_skip_times:
            self.assertIsNone(episode.skip_times)
            get_skip_times.assert_not_called()

    def test_aniskip_request_error_does_not_escape(self):
        episode = AniworldEpisode(
            "https://aniworld.to/anime/stream/example/staffel-1/episode-1",
            series=_SeriesWithMalId(),
            season=_FirstSeason(),
            episode_number=1,
        )

        with patch(
            "aniworld.aniskip.get_skip_times", side_effect=RuntimeError("offline")
        ) as get_skip_times:
            self.assertIsNone(episode.skip_times)
            get_skip_times.assert_called_once_with(5114, 1)


if __name__ == "__main__":
    unittest.main()
