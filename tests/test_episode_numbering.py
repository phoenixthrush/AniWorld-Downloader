"""Title numbering stays consistent across naming, browsing and AutoSync."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aniworld import aniskip
from aniworld.models import (
    AniworldEpisode,
    AniworldSeason,
    AniworldSeries,
    SerienstreamEpisode,
    SerienstreamSeason,
    SerienstreamSeries,
)
from aniworld.models.common import common
from aniworld.models.common.batch import run_each
from aniworld.models.common.numbering import (
    EPISODE_URL_PREFIX,
    downloaded_episode_owners,
    episode_is_downloaded,
    episode_number_from_title,
    episode_url_from_file,
)
from aniworld.web import autosync, db, library, media
from aniworld.web.views import api_media


@pytest.fixture(params=["aniworld", "sto"])
def model(request):
    if request.param == "aniworld":
        return AniworldEpisode, "https://aniworld.to/anime/stream/example"
    return SerienstreamEpisode, "https://serienstream.to/serie/example"


@pytest.fixture(params=["Linux", "Windows"])
def download_platform(request, monkeypatch):
    """Exercise both download preflights without installing media binaries."""
    monkeypatch.setattr(
        common, "platform", SimpleNamespace(system=lambda: request.param)
    )
    monkeypatch.setattr(
        common.DependencyManager, "fetch_binary", lambda self, name: name
    )


def make_episode(
    model, tmp_path, *, number=1, title="Title [Episode 062]", season=None
):
    cls, base = model
    return cls(
        f"{base}/staffel-2/episode-{number}",
        series=SimpleNamespace(
            title_cleaned="Example", release_year="2024", imdb="tt123"
        ),
        season=season or SimpleNamespace(season_number=2),
        episode_number=number,
        title_de="Deutscher Titel [Episode 999]",
        title_en=title,
        selected_path=tmp_path,
        selected_language="German Dub",
    )


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Title [Episode 062]", 62),
        ("A Paw-sitively Wonderful Investigation [JP Episode 1218]", 1218),
        ("Title [ jp Episode 0007 ]", 7),
        ("JP Episode 1218", 1218),
        ("JP Episode 2 of my life", None),
        ("[JP Episode 0]", None),
        ("[JP Episode 62] [Episode 63]", None),
        ("[JP Episode 62] [Episode 62]", 62),
        ("Episode 062", 62),
        (" episode 1100 ", 1100),
        ("[episode 1100] Another title 2", 1100),
        ("Title [ Episode  007 ]", 7),
        ("Title &#91;Episode 062&#93;", None),
        ("Part 2: 100 Days", None),
        ("Episode 2 of my life", None),
        ("[Episode 0]", None),
        ("[Episode -1]", None),
        ("[Episode 12.5]", None),
        ("[Episode 62-63]", None),
        ("[Episode 62a]", None),
        ("[Episode 62] [Episode 63]", None),
        ("[Episode 62] [Episode 62]", 62),
        ("", None),
        (None, None),
    ],
)
def test_explicit_english_markers_only(title, expected):
    assert episode_number_from_title(title) == expected


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Title [Episode 062]", 62),
        ("Title [JP Episode 1218]", 1218),
        ("Episode 062", 62),
        ("Part 2", 1),
        ("", 1),
    ],
)
def test_title_overrides_supplied_season_index(model, tmp_path, title, expected):
    episode = make_episode(model, tmp_path, title=title)
    assert episode.episode_number == expected
    assert episode.season_episode_number == 1
    assert episode.season.season_number == 2
    assert episode.url.endswith("/staffel-2/episode-1")


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Title [Episode 1100]", 1100),
        ("Title [JP Episode 1218]", 1218),
        ("Episode 1100", 1100),
        ("Part 2", 1),
        ("", 1),
    ],
)
def test_direct_episode_pages(model, title, expected):
    cls, base = model
    episode = cls(f"{base}/staffel-2/episode-1")
    if cls is AniworldEpisode:
        html = f'<small class="episodeEnglishTitle">{title}</small>'
    else:
        html = f'<h2 class="h4 mb-1">\n S02E01:\n Deutscher Titel ({title}) \n</h2>'
    setattr(episode, f"_{cls.__name__}__html", html)
    assert episode.episode_number == expected
    assert episode.season_episode_number == 1


def test_movies_keep_their_film_index():
    episode = AniworldEpisode(
        "https://aniworld.to/anime/stream/example/filme/film-2",
        title_en="Movie [Episode 999]",
    )
    assert episode.episode_number == 2


@pytest.mark.parametrize("site", ["aniworld", "sto"])
def test_season_metadata_supplies_numbers_without_episode_fetches(site):
    if site == "aniworld":
        series = AniworldSeries("https://aniworld.to/anime/stream/example")
        season = AniworldSeason(f"{series.url}/staffel-2", series=series)
        season._AniworldSeason__html = """
            <tr itemtype="http://schema.org/Episode">
              <td><meta itemprop="episodeNumber" content="1">
                <a itemprop="url" href="/anime/stream/example/staffel-2/episode-1">1</a></td>
              <td><strong>Deutsch</strong><span>Title &#91;Episode 062&#93;</span></td>
            </tr>"""
    else:
        series = SerienstreamSeries("https://serienstream.to/serie/example")
        season = SerienstreamSeason(f"{series.url}/staffel-2", series=series)
        season._SerienstreamSeason__html = """
            <tr class="episode-row" onclick="window.location='/serie/example/staffel-2/episode-1'">
              <td><strong class="episode-title-ger">Deutsch</strong>
                <span class="episode-title-eng">Title &#91;Episode 062&#93;</span></td>
            </tr>"""
    assert season.episode_count == 1
    assert len(season.episodes) == 1
    episode = season.episodes[0]
    assert episode.episode_number == 62
    assert episode.season_episode_number == 1


def test_new_paths_keep_the_season(model, tmp_path, monkeypatch):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE",
        "{title}/Season {season}/{title} S{season}E{episode}.mp4",
    )
    episode = make_episode(model, tmp_path, title="Title [Episode 1100]")
    expected = tmp_path / "Example" / "Season 02" / "Example S02E1100.mp4"
    assert episode._episode_path == expected
    assert episode._folder_path == expected.parent
    assert episode._file_name == expected.stem
    assert episode._file_extension == "mp4"


@pytest.mark.parametrize(
    "template,legacy",
    [
        (
            "{title}/Season {season}/{title} S{season}E{episode}.mkv",
            "Example/Season 02/Example S02E001.mkv",
        ),
        (
            "{episode}/Season {season}/{title} E{episode}.mp4",
            "001/Season 02/Example E001.mp4",
        ),
        ("%title%.S%season%E%episode%.mkv", "Example.S02E001.mkv"),
    ],
)
def test_existing_seasonal_path_is_reused(
    model, tmp_path, monkeypatch, template, legacy
):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", template)
    old = tmp_path / legacy
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"existing")
    episode = make_episode(model, tmp_path)
    assert episode._episode_path == old
    assert episode._folder_path == old.parent
    assert episode._file_name == old.stem
    assert episode.episode_number == 62
    assert episode._episode_path.read_bytes() == b"existing"
    episode.selected_path = tmp_path / "other"
    assert episode._episode_path != old
    assert "062" in episode._episode_path.name


def test_current_path_wins_if_both_names_exist(model, tmp_path, monkeypatch):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    old = tmp_path / "Example S02E001.mkv"
    new = tmp_path / "Example S02E062.mkv"
    old.touch()
    new.touch()
    assert make_episode(model, tmp_path)._episode_path == new


def test_resolution_naming_finds_a_seasonal_file(model, tmp_path, monkeypatch):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.{resolution}.mkv"
    )
    old = tmp_path / "Example S02E001.720p.mkv"
    old.touch()
    monkeypatch.setattr(common, "_read_container_resolution", lambda path: "720p")
    episode = make_episode(model, tmp_path)
    common._prepare_resolution_naming(episode)
    assert episode._episode_path == old


def test_downloading_complete_legacy_file_skips_stream_extraction(
    model, tmp_path, monkeypatch, download_platform
):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    old = tmp_path / "Example S02E001.mkv"
    old.touch()
    episode = make_episode(model, tmp_path)
    monkeypatch.setattr(type(episode), "provider_attempt_order", lambda self: ("VOE",))
    stream = Mock(side_effect=AssertionError("complete file needs no hoster"))
    monkeypatch.setattr(type(episode), "stream_url", property(stream))
    check = Mock(
        return_value={"exists": True, "audio_langs": {"deu"}, "video_langs": {None}}
    )
    monkeypatch.setattr(common, "check_downloaded", check)
    episode.download()
    check.assert_called_once_with(old)
    stream.assert_not_called()


@pytest.mark.parametrize("have", [{(2, 1)}, {(2, 62)}, {(2, 1), (2, 63)}])
def test_autosync_recognises_seasonal_absolute_and_mixed_files(model, tmp_path, have):
    season = SimpleNamespace(season_number=2)
    season.episodes = [
        make_episode(model, tmp_path, season=season),
        make_episode(
            model, tmp_path, number=2, title="Title [Episode 063]", season=season
        ),
    ]
    missing = autosync._missing_episodes(SimpleNamespace(seasons=[season]), have)
    assert missing == ([] if (2, 63) in have else [season.episodes[1].url])


@pytest.mark.parametrize("number", [1, 62])
def test_new_only_autosync_resolves_english_number(
    model, tmp_path, monkeypatch, number
):
    episode = make_episode(model, tmp_path)
    provider = SimpleNamespace(
        episode_cls=lambda **kwargs: episode,
        season_cls=lambda **kwargs: SimpleNamespace(episodes=[episode]),
    )
    monkeypatch.setattr(autosync, "resolve_provider", lambda url: provider)
    assert autosync._announced_episodes([episode.url], {(2, number)}) == []
    assert autosync._announced_episodes([episode.url], set()) == [episode.url]


def test_overlapping_ranges_do_not_count_one_file_as_two_episodes(model, tmp_path):
    season = SimpleNamespace(season_number=2)
    episodes = [
        make_episode(
            model, tmp_path, number=1, title="Title [Episode 002]", season=season
        ),
        make_episode(
            model, tmp_path, number=2, title="Title [Episode 003]", season=season
        ),
    ]
    season.episodes = episodes
    assert downloaded_episode_owners(episodes, {(2, 1), (2, 3)}) == {
        (2, 1): episodes[0].url,
        (2, 3): episodes[1].url,
    }
    # Other files do not prove which episode a shared number identifies.
    for have in ({(2, 2)}, {(2, 1), (2, 2)}, {(2, 2), (2, 3)}):
        with pytest.raises(ValueError, match="Ambiguous episode numbering"):
            downloaded_episode_owners(episodes, have)


def test_a_conflicting_old_filename_is_not_overwritten(model, tmp_path, monkeypatch):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    season = SimpleNamespace(season_number=2)
    episodes = [
        make_episode(
            model, tmp_path, number=n, title=f"Title [Episode {n + 2}]", season=season
        )
        for n in range(1, 4)
    ]
    season.episodes = episodes
    for n in (2, 3):
        (tmp_path / f"Example S02E{n:03d}.mkv").write_bytes(b"old episode")
    with pytest.raises(ValueError, match="Ambiguous episode numbering"):
        _ = episodes[0]._episode_path
    assert (tmp_path / "Example S02E002.mkv").read_bytes() == b"old episode"


@pytest.mark.parametrize("number", [1, 62])
def test_api_sends_new_number_and_preserves_seasonal_language_lookup(
    model, tmp_path, monkeypatch, episode_file, number
):
    episode = make_episode(model, tmp_path)
    season = SimpleNamespace(episodes=[episode], episode_languages={1: ("German Dub",)})
    provider = SimpleNamespace(name="SerienStream", season_cls=lambda **kwargs: season)
    monkeypatch.setattr(api_media, "_resolve_series", lambda *args: episode.series)
    episode_file("Example", 2, number)
    rows = api_media._season_episodes(provider, "season-url", None)
    assert rows[0]["episode_number"] == 62
    assert rows[0]["downloaded"] is True
    assert rows[0]["available_languages"] == ["German Dub"]
    assert rows[0]["url"].endswith("/episode-1")


def test_aniskip_still_uses_the_season_specific_number(tmp_path, monkeypatch):
    episode = make_episode(
        (AniworldEpisode, "https://aniworld.to/anime/stream/example"), tmp_path
    )
    episode.series.mal_id = [123, 456]
    fetch = Mock(return_value={"found": True})
    monkeypatch.setattr(aniskip, "get_skip_times", fetch)
    assert episode.skip_times == {"found": True}
    fetch.assert_called_once_with(456, 1)


def test_four_digit_numbers_work_through_detection_library_and_deletion(episode_file):
    kept = episode_file("Example", 2, 110)
    removed = episode_file("Example", 2, 1100)
    assert media.downloaded_episodes(SimpleNamespace(title_cleaned="Example")) == {
        (2, 110),
        (2, 1100),
    }
    assert autosync.episodes_in_folder(removed.parent.parent) == {(2, 110), (2, 1100)}
    assert [
        row["episode"] for row in library.read_title("Example")["seasons"]["2"]
    ] == [110, 1100]
    assert library.delete("Example", season=2, episode=1100) == 1
    assert kept.is_file()
    assert not removed.exists()


def test_language_and_library_copies_resolve_their_numbering_independently(
    model, tmp_path, monkeypatch, episode_file
):
    monkeypatch.setenv("ANIWORLD_LANG_SEPARATION", "1")
    other = tmp_path / "other"
    other.mkdir()
    db.add_custom_path("Other", str(other))
    season = SimpleNamespace(season_number=2)
    episodes = [
        make_episode(
            model, tmp_path, number=n, title=f"Title [Episode {n + 1}]", season=season
        )
        for n in (1, 2)
    ]
    season.episodes = episodes
    sources = {}
    for n in (1, 2):
        file = episode_file("Example", 2, n, base=other / "german-dub")
        sources[file] = episodes[n - 1].url
    for n in (2, 3):
        file = episode_file("Example", 2, n, base=other / "english-dub")
        sources[file] = episodes[n - 2].url
    monkeypatch.setattr(
        "aniworld.models.common.numbering.episode_url_from_file",
        lambda path: sources[path],
    )
    assert media.downloaded_episode_urls(episodes[0].series, episodes) == {
        entry.url for entry in episodes
    }


def test_incomplete_downloads_and_subtitles_are_not_counted_as_video(episode_file):
    partial = episode_file("Example", 2, 1100, suffix=".temp_full.mkv")
    episode_file("Example", 2, 1101, suffix=".srt")
    assert media.downloaded_episodes(SimpleNamespace(title_cleaned="Example")) == set()
    assert autosync.episodes_in_folder(partial.parent.parent) == set()


def test_new_only_checks_only_the_announced_season_once(model, tmp_path, monkeypatch):
    season = SimpleNamespace(season_number=2)
    season.episodes = [
        make_episode(
            model, tmp_path, number=n, title=f"Title [Episode {n + 61}]", season=season
        )
        for n in (1, 2)
    ]
    fetch = Mock(return_value=season)
    provider = SimpleNamespace(season_cls=fetch)
    monkeypatch.setattr(autosync, "resolve_provider", lambda url: provider)
    urls = [episode.url for episode in season.episodes]
    assert autosync._announced_episodes(urls, {(2, 62)}) == [urls[1]]
    fetch.assert_called_once_with(url=urls[0].rsplit("/episode-", 1)[0])


def test_two_digit_legacy_names_can_still_be_deleted(episode_file):
    old = episode_file("Example", 2, 1)
    old = old.rename(old.with_name("Example S02E01.mkv"))
    assert library.delete("Example", season=2, episode=1) == 1
    assert not old.exists()


@pytest.mark.parametrize("number", [1, 62])
def test_two_digit_existing_paths_are_reused(model, tmp_path, monkeypatch, number):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    old = tmp_path / f"Example S02E{number:02d}.mkv"
    old.touch()
    assert make_episode(model, tmp_path)._episode_path == old


def test_episode_detection_probes_the_existing_seasonal_path(
    model, tmp_path, monkeypatch
):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    old = tmp_path / "Example S02E001.mkv"
    old.touch()
    episode = make_episode(model, tmp_path)
    check = Mock(
        return_value={"exists": True, "video_langs": {None}, "audio_langs": {"deu"}}
    )
    monkeypatch.setattr(f"{type(episode).__module__}.check_downloaded", check)
    assert episode.is_downloaded["exists"] is True
    check.assert_called_once_with(old)


def test_failed_title_lookup_does_not_abort_a_batch(model, tmp_path, monkeypatch):
    episode = make_episode(model, tmp_path)
    error = RuntimeError("episode metadata unavailable")
    title = Mock(side_effect=error)
    monkeypatch.setattr(type(episode), "title_en", property(title))
    episode.download = Mock(side_effect=error)
    next_episode = make_episode(model, tmp_path, number=2)
    next_episode.download = Mock()
    assert run_each([episode, next_episode], "download") == [("S02E01", error)]
    next_episode.download.assert_called_once_with()


@pytest.mark.parametrize("key", ["comment", "COMMENT"])
def test_source_episode_url_is_read_from_container_metadata(tmp_path, monkeypatch, key):
    url = "https://aniworld.to/anime/stream/example/staffel-2/episode-1"
    monkeypatch.setattr(
        "aniworld.models.common.numbering.ffmpeg.probe",
        lambda path: {"format": {"tags": {key: f"{EPISODE_URL_PREFIX}{url}"}}},
    )
    path = tmp_path / "Example.mkv"
    path.touch()
    assert episode_url_from_file(path) == url


def test_source_metadata_disambiguates_overlapping_names(model, tmp_path, monkeypatch):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    season = SimpleNamespace(season_number=2)
    first = make_episode(model, tmp_path, title="Title [Episode 002]", season=season)
    second = make_episode(
        model, tmp_path, number=2, title="Title [Episode 003]", season=season
    )
    season.episodes = [first, second]
    file = tmp_path / "Example S02E002.mkv"
    file.touch()
    source = first.url.replace("serienstream.to", "s.to")
    monkeypatch.setattr(
        "aniworld.models.common.numbering.episode_url_from_file", lambda path: source
    )
    have = media.episode_files_in_folder(tmp_path)
    assert autosync._missing_episodes(SimpleNamespace(seasons=[season]), have) == [
        second.url
    ]
    assert first._episode_path == file
    assert second._episode_path == tmp_path / "Example S02E003.mkv"


def test_an_unchanged_number_cannot_reuse_another_episodes_file(
    model, tmp_path, monkeypatch
):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    season = SimpleNamespace(season_number=2)
    first = make_episode(model, tmp_path, title="Title [Episode 002]", season=season)
    second = make_episode(model, tmp_path, number=2, title="No marker", season=season)
    season.episodes = [first, second]
    file = tmp_path / "Example S02E002.mkv"
    file.write_bytes(b"first episode")
    monkeypatch.setattr(
        "aniworld.models.common.numbering.episode_url_from_file", lambda path: first.url
    )
    with pytest.raises(ValueError, match="belongs to a different episode"):
        _ = second._episode_path
    assert file.read_bytes() == b"first episode"


def test_full_download_records_its_source_episode(
    model, tmp_path, monkeypatch, download_platform
):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    episode = make_episode(model, tmp_path)
    monkeypatch.setattr(type(episode), "provider_attempt_order", lambda self: ("VOE",))
    monkeypatch.setattr(type(episode), "stream_url", "https://example.test/video.m3u8")
    metadata = []

    def download(stream_url, temp_full, input_kwargs, headers, stream_metadata, *args):
        metadata.append(stream_metadata)
        temp_full.write_bytes(b"downloaded video")

    monkeypatch.setattr(common, "_download_full_stream", download)
    episode.download()
    assert metadata[0]["metadata"] == f"comment={EPISODE_URL_PREFIX}{episode.url}"
    assert metadata[0]["metadata:s:a:0"] == "language=deu"
    assert episode._episode_path.read_bytes() == b"downloaded video"


def test_adding_audio_to_a_legacy_file_keeps_its_path_and_records_source(
    model, tmp_path, monkeypatch, download_platform
):
    from pathlib import Path

    import ffmpeg

    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    old = tmp_path / "Example S02E001.mkv"
    old.write_bytes(b"English copy")
    episode = make_episode(model, tmp_path)
    monkeypatch.setattr(type(episode), "provider_attempt_order", lambda self: ("VOE",))
    monkeypatch.setattr(type(episode), "stream_url", "https://example.test/video.m3u8")
    monkeypatch.setattr(
        common,
        "check_downloaded",
        lambda path: {"exists": True, "video_langs": {"und"}, "audio_langs": {"eng"}},
    )
    commands = []

    def run(node, **kwargs):
        args = ffmpeg.compile(node)
        commands.append(args)
        Path(args[-1]).write_bytes(b"merged copy")

    monkeypatch.setattr(common, "_run_ffmpeg_with_progress", run)
    episode.download()
    assert old.read_bytes() == b"merged copy"
    assert not (tmp_path / "Example S02E062.mkv").exists()
    assert f"comment={EPISODE_URL_PREFIX}{episode.url}" in commands[-1]


@pytest.mark.parametrize("padding", [2, 3])
def test_resolution_finalization_keeps_existing_seasonal_number(
    model, tmp_path, monkeypatch, padding
):
    monkeypatch.setenv(
        "ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.{resolution}.mkv"
    )
    old = tmp_path / f"Example S02E{1:0{padding}d}.unknown.mkv"
    old.write_bytes(b"video")
    episode = make_episode(model, tmp_path)
    monkeypatch.setattr(common, "_read_container_resolution", lambda path: "720p")
    common._finalize_resolution_naming(episode)
    expected = old.with_name(old.name.replace("unknown", "720p"))
    assert episode._episode_path == expected
    assert expected.read_bytes() == b"video"
    assert not old.exists()


def test_serienstream_ignores_other_series_episode_links():
    season = SerienstreamSeason("https://serienstream.to/serie/example/staffel-2")
    season._SerienstreamSeason__html = (
        '<a href="/serie/another/staffel-2/episode-1">Related episode</a>'
    )
    assert season.episodes == []
    assert season.episode_count == 0


def test_serienstream_counts_relative_and_absolute_links_once():
    season = SerienstreamSeason("https://serienstream.to/serie/example/staffel-2")
    season._SerienstreamSeason__html = """
        <a href="/serie/example/staffel-2/episode-1">Episode</a>
        <tr onclick="window.location='https://serienstream.to/serie/example/staffel-2/episode-1'"></tr>
    """
    assert season.episode_count == len(season.episodes) == 1


def test_changing_destination_invalidates_download_detection(
    model, tmp_path, monkeypatch
):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    (tmp_path / "Example S02E001.mkv").touch()
    episode = make_episode(model, tmp_path)
    check = Mock(side_effect=lambda path: {"exists": path.is_file()})
    monkeypatch.setattr(f"{type(episode).__module__}.check_downloaded", check)
    assert episode.is_downloaded["exists"] is True
    episode.selected_path = tmp_path / "other"
    assert episode.is_downloaded["exists"] is False
    assert check.call_count == 2


@pytest.mark.parametrize("offset", range(5))
@pytest.mark.parametrize(
    "layout", ["current", "seasonal", "mixed", "duplicate", "untagged"]
)
def test_numbering_layouts_match_the_actual_source_episodes(
    model, tmp_path, monkeypatch, offset, layout
):
    season = SimpleNamespace(season_number=2)
    season.episodes = [
        make_episode(
            model,
            tmp_path,
            number=n,
            title=f"Title [Episode {n + offset}]",
            season=season,
        )
        for n in (1, 2, 3)
    ]
    files = {}
    sources = {}
    for index, episode in enumerate(season.episodes):
        if layout == "duplicate" and index:
            continue
        numbers = {
            "current": [episode.episode_number],
            "seasonal": [episode.season_episode_number],
            "mixed": [
                episode.episode_number if index % 2 else episode.season_episode_number
            ],
            "duplicate": [episode.episode_number, episode.season_episode_number],
            "untagged": [episode.episode_number],
        }[layout]
        for number in numbers:
            path = tmp_path / str(index) / f"Example S02E{number:03d}.mkv"
            files.setdefault((2, number), []).append(path)
            sources[path] = episode.url
    monkeypatch.setattr(
        "aniworld.models.common.numbering.episode_url_from_file",
        lambda path: None if layout == "untagged" else sources[path],
    )
    if layout == "untagged" and offset in (1, 2):
        with pytest.raises(ValueError, match="Ambiguous episode numbering"):
            downloaded_episode_owners(season.episodes, files)
    else:
        assert downloaded_episode_owners(season.episodes, files) == sources


@pytest.mark.parametrize("reencode", [False, True])
def test_mp4_finalization_keeps_all_streams(tmp_path, monkeypatch, reencode):
    from pathlib import Path

    import ffmpeg

    source = tmp_path / "episode.temp_full.mkv"
    target = tmp_path / "episode.mp4"
    source.write_bytes(b"video and multiple audio tracks")
    commands = []

    def run(node, **kwargs):
        args = ffmpeg.compile(node)
        commands.append(args)
        if reencode and len(commands) == 1:
            raise RuntimeError("unsupported MP4 codec")
        Path(args[-1]).write_bytes(b"finished video")

    monkeypatch.setattr(common, "_run_ffmpeg_with_progress", run)
    common._finalize_episode(source, target)
    for args in commands:
        assert args[args.index("-map") + 1] == "0"
    assert len(commands) == (2 if reencode else 1)
    assert target.read_bytes() == b"finished video"
    assert not source.exists()


def test_completed_download_invalidates_the_cached_probe(model, tmp_path, monkeypatch):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    episode = make_episode(model, tmp_path)
    monkeypatch.setattr(
        f"{type(episode).__module__}.check_downloaded",
        lambda path: {"exists": path.is_file()},
    )
    assert episode.is_downloaded["exists"] is False
    temp = tmp_path / "episode.temp_full.mkv"
    temp.write_bytes(b"completed video")
    common._finalize_episode(temp, episode._episode_path, owner=episode)
    assert episode.is_downloaded["exists"] is True


def test_recorded_source_takes_precedence_over_a_different_filename_number(
    model, tmp_path, monkeypatch
):
    season = SimpleNamespace(season_number=2)
    first = make_episode(model, tmp_path, title="Title [Episode 062]", season=season)
    second = make_episode(
        model, tmp_path, number=2, title="Title [Episode 063]", season=season
    )
    season.episodes = [first, second]
    file = tmp_path / "Example S02E063.mkv"
    monkeypatch.setattr(
        "aniworld.models.common.numbering.episode_url_from_file", lambda path: first.url
    )
    have = {(2, 63): [file]}
    assert downloaded_episode_owners([first, second], have) == {file: first.url}
    assert episode_is_downloaded(first, have)
    assert not episode_is_downloaded(second, have)
    assert autosync._missing_episodes(SimpleNamespace(seasons=[season]), have) == [
        second.url
    ]
    monkeypatch.setattr(
        autosync,
        "resolve_provider",
        lambda url: SimpleNamespace(season_cls=lambda **kwargs: season),
    )
    assert autosync._announced_episodes([first.url, second.url], have) == [second.url]


def test_another_backend_cannot_claim_a_tagged_bleach_file(tmp_path, monkeypatch):
    model = SerienstreamEpisode, "https://serienstream.to/serie/bleach"
    season = SimpleNamespace(season_number=2)
    episodes = [
        make_episode(model, tmp_path, number=n, title="No marker", season=season)
        for n in (1, 21)
    ]
    file = tmp_path / "Bleach S02E021.mkv"
    monkeypatch.setattr(
        "aniworld.models.common.numbering.episode_url_from_file",
        lambda path: "https://aniworld.to/anime/stream/bleach/staffel-2/episode-1",
    )
    assert downloaded_episode_owners(episodes, {(2, 21): [file]}) == {}


def test_source_metadata_cache_follows_file_changes(tmp_path, monkeypatch):
    file = tmp_path / "episode.mkv"
    file.write_bytes(b"first")
    probe = Mock(
        side_effect=[
            {
                "format": {
                    "tags": {
                        "comment": EPISODE_URL_PREFIX
                        + "https://aniworld.to/anime/stream/example/staffel-1/episode-1"
                    }
                }
            },
            {
                "format": {
                    "tags": {
                        "comment": EPISODE_URL_PREFIX
                        + "https://aniworld.to/anime/stream/example/staffel-1/episode-2"
                    }
                }
            },
        ]
    )
    monkeypatch.setattr("aniworld.models.common.numbering.ffmpeg.probe", probe)
    first = episode_url_from_file(file)
    assert episode_url_from_file(file) == first
    assert probe.call_count == 1
    file.write_bytes(b"updated video")
    assert episode_url_from_file(file).endswith("episode-2")
    assert probe.call_count == 2


@pytest.mark.parametrize(
    "german,english",
    [
        ("Das Wiedersehen (Teil 2)", "Episode 062"),
        ("Das Wiedersehen (Teil 2)", "Reunion (Part 2) [Episode 062]"),
        ("", "Episode 062"),
    ],
)
def test_serienstream_parentheses_in_titles_keep_the_english_number(german, english):
    episode = SerienstreamEpisode(
        "https://serienstream.to/serie/example/staffel-2/episode-1"
    )
    episode._SerienstreamEpisode__html = (
        f'<h2 class="h4 mb-1">\nS02E01: {german} ({english})\n</h2>'
    )
    assert episode.title_de == german
    assert episode.title_en == english
    assert episode.episode_number == 62


@pytest.mark.parametrize("password", [None, "room-key"])
def test_syncplay_room_stays_the_same_with_old_and_new_numbering(
    model, tmp_path, monkeypatch, password
):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title} S{season}E{episode}.mkv")
    if password:
        monkeypatch.setenv("ANIWORLD_SYNCPLAY_PASSWORD", password)
    monkeypatch.setattr(
        common,
        "_resolve_stream_url_with_fallback",
        lambda *args: ("https://example.test/video", "VOE"),
    )
    monkeypatch.setattr(common, "get_syncplay_path", lambda: "syncplay")
    monkeypatch.setattr(common, "get_player_path", lambda **kwargs: "mpv")
    commands = []
    monkeypatch.setattr(
        common.subprocess, "run", lambda command, **kwargs: commands.append(command)
    )
    episode = make_episode(model, tmp_path)
    episode.syncplay()
    (tmp_path / "Example S02E001.mkv").touch()
    episode.selected_path = tmp_path
    episode.syncplay()
    rooms = [command[command.index("--room") + 1] for command in commands]
    assert rooms[0] == rooms[1]
    if password:
        assert password not in rooms[0]
    else:
        assert rooms[0] == "AniWorld-Example_S02E001"
