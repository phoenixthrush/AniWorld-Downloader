"""FFmpeg input options for HLS and progressive streams."""

from types import SimpleNamespace

import pytest

from aniworld.models import AniworldEpisode
from aniworld.models.common import common


@pytest.mark.parametrize(
    "stream_url,streamed",
    [
        ("https://cdn.example/hls/master.m3u8?t=1", False),
        ("https://cdn.example/video.mp4", True),
    ],
)
def test_hls_inputs_do_not_reconnect_as_a_stream(
    tmp_path, monkeypatch, stream_url, streamed
):
    monkeypatch.setattr(common, "platform", SimpleNamespace(system=lambda: "Linux"))
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    episode = AniworldEpisode(
        "https://aniworld.to/anime/stream/example/staffel-1/episode-1",
        series=SimpleNamespace(
            title_cleaned="Example", release_year="2024", imdb="tt1"
        ),
        season=SimpleNamespace(season_number=1),
        episode_number=1,
        title_en="Title",
        selected_path=tmp_path,
        selected_language="German Sub",
    )
    monkeypatch.setattr(type(episode), "provider_attempt_order", lambda self: ("VOE",))
    monkeypatch.setattr(type(episode), "stream_url", stream_url)
    options = []

    def download(url, temp_full, input_kwargs, *args):
        options.append(dict(input_kwargs))
        temp_full.write_bytes(b"video")

    monkeypatch.setattr(common, "_download_full_stream", download)
    episode.download()
    assert options[0]["reconnect"] == 1
    assert ("reconnect_streamed" in options[0]) is streamed
