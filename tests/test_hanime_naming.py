"""Naming hanime files.

A hanime "franchise" is not always one show. It can group videos that share
nothing but a brand, so naming the file after the franchise made two different
videos want the same path and the second one was skipped as already
downloaded. The file is named after the video's own name now, the folder still
uses the franchise.
"""

import pytest

from aniworld.extractors.provider import hanime_tv as extractor
from aniworld.models.common import common
from aniworld.models.hanime_tv.episode import HanimeTVEpisode
from aniworld.models.hanime_tv.series import HanimeTVSeries

VIDEO = "https://hanime.tv/videos/hentai/{slug}"

# The two slugs from the report. Same franchise, same episode number, but two
# completely different videos.
COLLIDING = {
    "franchise": "Tonari no Kanojo",
    "videos": {
        "tonari-no-kanojo-1": "Tonari no Kanojo 1",
        "yogoreta-kanojo-1": "Yogoreta Kanojo 1",
    },
}

# An ordinary franchise, where every video is a numbered part of one show.
ORDINARY = {
    "franchise": "Ane Yome Quartet",
    "videos": {
        "ane-yome-quartet-1": "Ane Yome Quartet 1",
        "ane-yome-quartet-2": "Ane Yome Quartet 2",
    },
}

# Real shape from hanime, where the video name carries a subtitle the
# franchise does not. Nothing collides here, so nothing may be renamed.
WORDY = {
    "franchise": "Ichigo Aika",
    "videos": {
        "ichigo-aika-1": "Ichigo Aika: Zatsu de Namaiki na Imouto 1",
        "ichigo-aika-2": "Ichigo Aika: Zatsu de Namaiki na Imouto 2",
    },
}

# Casing the site gets right and .capitalize() would not.
SHOUTY = {
    "franchise": "JK to Ero Konbini Tenchou",
    "videos": {
        "jk-to-ero-konbini-tenchou-1": "JK to Ero Konbini Tenchou 1",
        "ova-natsuyasumi-1": "OVA Natsuyasumi 1",
    },
}


def api_data_for(fixture, slug):
    return {
        "hentai_video": {
            "slug": slug,
            "name": fixture["videos"][slug],
            "description": "",
            "released_at_unix": None,
        },
        "hentai_franchise": {
            "slug": "franchise-slug",
            "title": fixture["franchise"],
            "name": fixture["franchise"],
        },
        "hentai_franchise_hentai_videos": [
            {"slug": video_slug, "name": name}
            for video_slug, name in fixture["videos"].items()
        ],
        "brand": {"title": "Some Brand"},
    }


@pytest.fixture
def hanime(monkeypatch, tmp_path):
    """Serve canned api data so nothing here touches the network."""

    def install(fixture):
        def fake_fetch(slug, *args, **kwargs):
            if slug not in fixture["videos"]:
                raise AssertionError(f"unexpected slug fetched: {slug}")
            return api_data_for(fixture, slug)

        for module in ("episode", "series"):
            monkeypatch.setattr(
                f"aniworld.models.hanime_tv.{module}.fetch_hanime_api_data",
                fake_fetch,
            )

        # Each queue item builds its own episode straight from a url, which is
        # how both videos ended up claiming episode 1.
        return [
            HanimeTVEpisode(url=VIDEO.format(slug=slug), selected_path=str(tmp_path))
            for slug in fixture["videos"]
        ]

    return install


def test_two_videos_in_one_franchise_get_their_own_file(hanime):
    first, second = hanime(COLLIDING)

    assert first._file_name == "Tonari no Kanojo S01E001"
    assert second._file_name == "Yogoreta Kanojo S01E001"


def test_the_second_video_is_no_longer_taken_for_the_first(hanime):
    first, second = hanime(COLLIDING)

    # Same folder, same episode number. Only the file name keeps them apart,
    # and it has to, or is_downloaded skips the second one.
    assert first._folder_path == second._folder_path
    assert first.episode_number == second.episode_number == 1
    assert first._episode_path != second._episode_path


def test_the_folder_still_uses_the_franchise(hanime):
    first, second = hanime(COLLIDING)

    for episode in (first, second):
        assert "Tonari no Kanojo" in str(episode._base_folder)


def test_an_ordinary_franchise_keeps_the_names_it_had(hanime):
    """The names only move where they had to, so nobody re-downloads."""

    first, second = hanime(ORDINARY)

    assert first._file_name == "Ane Yome Quartet S01E001"
    assert second._file_name == "Ane Yome Quartet S01E002"


def test_a_wordier_video_name_does_not_rename_anything(hanime):
    """Most videos are named differently to their franchise without colliding.

    Renaming those was measured at about a third of hanime, all of it pointless
    re-downloads, so a difference on its own must not be enough.
    """

    first, second = hanime(WORDY)

    assert first._file_name == "Ichigo Aika S01E001"
    assert second._file_name == "Ichigo Aika S01E002"


def test_casing_from_the_site_is_left_alone(hanime):
    first, second = hanime(SHOUTY)

    assert first._file_name.startswith("JK to Ero Konbini Tenchou")
    assert second._file_name.startswith("OVA Natsuyasumi")


def test_naming_costs_no_extra_request(monkeypatch, tmp_path):
    """The franchise list rides along with the api data we already have."""

    calls = []

    def counting_fetch(slug, *args, **kwargs):
        calls.append(slug)
        return api_data_for(COLLIDING, slug)

    for module in ("episode", "series"):
        monkeypatch.setattr(
            f"aniworld.models.hanime_tv.{module}.fetch_hanime_api_data",
            counting_fetch,
        )

    episode = HanimeTVEpisode(
        url=VIDEO.format(slug="yogoreta-kanojo-1"), selected_path=str(tmp_path)
    )
    assert episode._file_name == "Yogoreta Kanojo S01E001"
    assert calls == ["yogoreta-kanojo-1"]


def test_a_video_missing_from_the_franchise_list_falls_back_to_its_own_name(
    monkeypatch, tmp_path
):
    def partial_fetch(slug, *args, **kwargs):
        data = api_data_for(COLLIDING, slug)
        # Still two videos, so the collision is seen, but this one has no name
        # in the list and has to be fetched on its own.
        data["hentai_franchise_hentai_videos"] = [
            {"slug": "tonari-no-kanojo-1", "name": "Tonari no Kanojo 1"},
            {"slug": "yogoreta-kanojo-1"},
        ]
        return data

    for module in ("episode", "series"):
        monkeypatch.setattr(
            f"aniworld.models.hanime_tv.{module}.fetch_hanime_api_data",
            partial_fetch,
        )

    episode = HanimeTVEpisode(
        url=VIDEO.format(slug="yogoreta-kanojo-1"), selected_path=str(tmp_path)
    )
    assert episode._file_name == "Yogoreta Kanojo S01E001"


def test_a_nameless_video_falls_back_to_the_franchise(monkeypatch, tmp_path):
    def nameless_fetch(slug, *args, **kwargs):
        data = api_data_for(COLLIDING, slug)
        data["hentai_video"]["name"] = ""
        data["hentai_franchise_hentai_videos"] = [
            {"slug": "tonari-no-kanojo-1"},
            {"slug": "yogoreta-kanojo-1"},
        ]
        return data

    for module in ("episode", "series"):
        monkeypatch.setattr(
            f"aniworld.models.hanime_tv.{module}.fetch_hanime_api_data",
            nameless_fetch,
        )

    episode = HanimeTVEpisode(
        url=VIDEO.format(slug="yogoreta-kanojo-1"), selected_path=str(tmp_path)
    )
    assert episode._file_name == "Tonari no Kanojo S01E001"


def test_strip_episode_number_keeps_a_title_that_is_only_a_number():
    assert HanimeTVSeries.strip_episode_number("Tonari no Kanojo 1") == (
        "Tonari no Kanojo"
    )
    assert HanimeTVSeries.strip_episode_number("2") == "2"
    assert HanimeTVSeries.strip_episode_number("") == ""


def test_a_failed_handshake_only_opens_one_browser(monkeypatch, tmp_path):
    calls = []

    def fail(_url, timeout):
        calls.append(timeout)
        raise TimeoutError("handshake timed out")

    monkeypatch.setattr(extractor, "playwright_get_hanime_manifest_token", fail)
    monkeypatch.setattr(common, "_prepare_resolution_naming", lambda _episode: None)
    monkeypatch.setattr(common.platform, "system", lambda: "Linux")

    class Episode:
        _episode_path = tmp_path / "episode.mkv"
        _folder_path = tmp_path
        _file_name = "episode"

        @property
        def stream_url(self):
            return extractor.fetch_hanime_manifest("episode")

    with pytest.raises(RuntimeError, match="Hanime download failed"):
        common.download_hanime(Episode())

    assert calls == [15]
