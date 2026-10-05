"""MegaKino movie and serial pages retain canonical hoster aliases."""

import pytest

from aniworld.config import Audio, Subtitles
from aniworld.extractors import provider_functions
from aniworld.models.megakino import MegaKinoEpisode


@pytest.fixture(params=["movie", "series"])
def megakino_page(request, monkeypatch):
    def build(url):
        if request.param == "movie":
            html = (
                f'<div class="tabs-block__content"><iframe src="{url}"></iframe></div>'
            )
            page_url = "https://megakino.example/films/123-example.html"
        else:
            html = f"""
                <select class="se-select">
                    <option value="ep1">Episode 1</option>
                    <option value="ep2">Episode 2</option>
                </select>
                <select class="mr-select" id="ep1">
                    <option value="https://voe.sx/e/first">VOE</option>
                </select>
                <select class="mr-select" id="ep2">
                    <option value="{url}">Mirror</option>
                </select>
            """
            page_url = "https://megakino.example/serials/123-example.html#mkep=2"

        monkeypatch.setattr(MegaKinoEpisode, "_html", property(lambda self: html))
        return MegaKinoEpisode(page_url, selected_language="German Dub")

    return build


@pytest.mark.parametrize(
    "host, provider",
    [
        ("www.voe.sx", "VOE"),
        ("dood.watch", "Doodstream"),
        ("www.filemoon.sx", "Filemoon"),
        ("gupload.xyz", "Gupload"),
        ("www.gxplayer.xyz", "MegaKino"),
        ("moflix-stream.click", "MoflixClick"),
        ("vidara.so", "Vidara"),
    ],
)
def test_pages_keep_supported_hoster_aliases(megakino_page, host, provider):
    url = f"https://{host}/e/video"
    episode = megakino_page(url)

    assert episode.provider_data.get((Audio.GERMAN, Subtitles.NONE)) == {provider: url}
    assert episode.provider_link("German Dub", provider) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://unsupported.example/e/video",
        "https://unsupported.example/e/video?next=https://voe.sx/e/video",
        "/e/video",
    ],
)
def test_pages_ignore_unknown_hosts(megakino_page, url):
    assert megakino_page(url).provider_data is None


def test_pages_ignore_hosters_without_a_registered_extractor(
    megakino_page, monkeypatch
):
    monkeypatch.delitem(provider_functions, "get_direct_link_from_doodstream")

    assert megakino_page("https://dood.watch/e/video").provider_data is None
