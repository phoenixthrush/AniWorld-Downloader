"""Mediathek (public broadcasters via MediathekView), with the API stubbed."""

from pathlib import Path

import pytest

from aniworld.models.mediathek import MediathekEpisode, api
from aniworld.providers import resolve_provider

ARD_PAGE = "https://www.ardmediathek.de/video/Y3JpZDovL3dkci5kZS9CZWl0cmFn"


def _entry(**overrides):
    entry = {
        "channel": "WDR",
        "topic": "Tatort",
        "title": "Tatort: Narrentanz",
        "description": "Ein Fall in Köln.",
        "timestamp": 1794780000,  # 2026-11-15
        "duration": 5340,
        "url_website": ARD_PAGE,
        "url_subtitle": "https://example.invalid/sub.xml",
        "url_video": "https://cdn.example.invalid/sd.mp4",
        "url_video_low": "https://cdn.example.invalid/low.mp4",
        "url_video_hd": "https://cdn.example.invalid/hd.mp4",
        "id": "abc+/=",
    }
    entry.update(overrides)
    return entry


REGULAR = _entry()
SIGNED = _entry(title="Tatort: Narrentanz (Gebärdensprache)", id="sign")
DESCRIBED = _entry(title="Tatort: Narrentanz (Audiodeskription)", id="ad")


class Results(list):
    calls = None


@pytest.fixture
def stub(monkeypatch):
    results = Results()
    results.calls = []

    def fake_post(body, timeout=20):
        results.calls.append(body)
        return list(results)

    api.clear_cache()
    monkeypatch.setattr(api, "_post", fake_post)
    monkeypatch.setattr(api, "_fetch_cover", lambda page: "")
    monkeypatch.setattr(api, "_fetch_show_poster", lambda topic: "")
    yield results
    api.clear_cache()


@pytest.mark.parametrize(
    "url",
    [
        ARD_PAGE,
        "https://www.zdf.de/video/serien/soko-koeln-104/durch-die-blumen-100",
        "https://www.arte.tv/de/videos/136382-000-A/titel/",
        "https://www.3sat.de/film/klassixs/die-nase-102.html",
        "https://on.orf.at/video/14347691/alles-finster-6-6",
        "https://www.srf.ch/play/tv/sendung/video/titel?urn=urn:srf:video:1",
        f"{ARD_PAGE}#mvid=abc",
    ],
)
def test_broadcaster_pages_resolve_to_the_mediathek(url):
    provider = resolve_provider(url)
    assert provider.name == "Mediathek"
    assert provider.episode_cls is MediathekEpisode


def test_other_hosts_are_rejected():
    with pytest.raises(ValueError):
        MediathekEpisode("https://example.com/video/1")


def test_entry_url_round_trips_the_id():
    url = api.entry_url(REGULAR)
    assert url.startswith(ARD_PAGE + "#mvid=")
    assert api.split_url(url) == (ARD_PAGE, "abc+/=")
    assert api.split_url(ARD_PAGE) == (ARD_PAGE, None)


def test_page_url_prefers_the_regular_version():
    assert api.pick_entry([DESCRIBED, SIGNED, REGULAR]) is REGULAR


def test_pinned_id_wins_over_the_regular_version():
    assert api.pick_entry([REGULAR, DESCRIBED], "ad") is DESCRIBED


def test_variants_alone_still_resolve():
    assert api.pick_entry([DESCRIBED]) is DESCRIBED
    assert api.pick_entry([]) is None


def test_quality_falls_back_to_the_next_lower_one():
    no_hd = _entry(url_video_hd="")
    assert api.best_video_url(REGULAR, "hd").endswith("hd.mp4")
    assert api.best_video_url(REGULAR, "low").endswith("low.mp4")
    assert api.best_video_url(no_hd, "hd").endswith("sd.mp4")
    assert api.best_video_url(_entry(url_video_hd="", url_video=""), "hd").endswith(
        "low.mp4"
    )
    assert api.best_video_url(REGULAR, "bogus").endswith("hd.mp4")


def test_search_keeps_only_the_listed_channels_exactly(stub):
    stub.extend(
        [
            REGULAR,
            _entry(channel="ARD-alpha", id="alpha"),
            _entry(channel="SRF", id="srf"),
            # Channels MediathekView may add later are left out until listed.
            _entry(channel="SRF.Podcast", id="podcast"),
            _entry(channel="ard", id="lowercase"),
        ]
    )
    assert [e["id"] for e in api.search("tatort")] == ["abc+/=", "alpha", "srf"]
    query = stub.calls[0]
    assert query["queries"] == [{"fields": ["title", "topic"], "query": "tatort"}]
    assert query["future"] is False


def test_empty_search_skips_the_api(stub):
    assert api.search("  ") == []
    assert stub.calls == []


def test_lookup_ignores_similar_pages(stub):
    stub.extend([REGULAR, _entry(url_website=ARD_PAGE + "X", id="other")])
    entries, entry_id = api.lookup(api.entry_url(REGULAR))
    assert entries == [REGULAR]
    assert entry_id == "abc+/="
    assert stub.calls[0]["queries"][0] == {
        "fields": ["url_website"],
        "query": ARD_PAGE,
    }


def test_episode_exposes_the_channel_as_its_provider(stub, monkeypatch):
    monkeypatch.delenv("ANIWORLD_MEDIATHEK_QUALITY", raising=False)
    stub.extend([DESCRIBED, REGULAR])
    episode = MediathekEpisode(ARD_PAGE)

    assert episode.title == "Tatort: Narrentanz"
    assert episode.channel == "WDR"
    assert episode.selected_provider == "WDR"
    assert episode.available_providers() == ("WDR",)
    assert episode.provider_attempt_order() == ("WDR",)
    assert episode.stream_url.endswith("hd.mp4")
    assert episode.release_year == 2026
    assert episode.duration_min == 89

    # Fallback handling sets the provider; the channel stays what it is.
    episode.selected_provider = "VOE"
    assert episode.selected_provider == "WDR"


def test_quality_setting_picks_the_stream(stub, monkeypatch):
    monkeypatch.setenv("ANIWORLD_MEDIATHEK_QUALITY", "sd")
    stub.append(REGULAR)
    assert MediathekEpisode(ARD_PAGE).stream_url.endswith("sd.mp4")


def test_channel_labels_follow_the_broadcasters(stub):
    stub.append(_entry(channel="ARTE.DE"))
    assert MediathekEpisode(ARD_PAGE).channel == "Arte"


def test_missing_programme_is_reported(stub):
    with pytest.raises(ValueError, match="lists no programme"):
        _ = MediathekEpisode(ARD_PAGE).stream_url


def test_files_land_under_the_topic_with_the_date(stub, monkeypatch, tmp_path):
    monkeypatch.setenv("ANIWORLD_NAMING_TEMPLATE", "{title}/{title}.mkv")
    stub.append(_entry(title="Alles finster (6/6)", topic="Alles finster"))
    episode = MediathekEpisode(ARD_PAGE, selected_path=str(tmp_path))
    assert episode._episode_path == Path(
        tmp_path, "Alles finster", "Alles finster (6-6) (2026-11-15).mkv"
    )


def test_web_provider_map_lists_the_channel(stub):
    from aniworld.web import media

    stub.append(REGULAR)
    data = MediathekEpisode(ARD_PAGE).provider_data
    assert media.provider_map(data) == {"German Dub": ["WDR"]}


def test_site_search_returns_labelled_results(stub):
    from aniworld.web import sitesearch

    stub.extend([REGULAR, _entry(id="older", timestamp=1794000000)])
    [hit] = sitesearch.search("mediathek", "tatort")
    assert hit["url"] == api.show_url("WDR", "Tatort")
    assert hit["title"] == "Tatort"
    assert hit["genre"] == "WDR · 15.11.2026"
    assert hit["channel"] == "WDR"


def test_channels_send_a_browser_user_agent():
    from aniworld.config import PROVIDER_HEADERS_D, PROVIDER_HEADERS_W
    from aniworld.models.mediathek import MEDIATHEK_CHANNELS

    for channel in MEDIATHEK_CHANNELS:
        assert "User-Agent" in PROVIDER_HEADERS_D[channel]
        assert "User-Agent" in PROVIDER_HEADERS_W[channel]


def test_short_clips_round_up_to_a_minute():
    assert api.result_details(_entry(duration=45)).endswith("· 1 min")


# -----------------------------
# Shows, seasons and numbering
# -----------------------------

SHOW_URL = api.show_url("MDR", "In aller Freundschaft")


def _show_entry(title, timestamp, page, **overrides):
    return _entry(
        channel="MDR",
        topic="In aller Freundschaft",
        title=title,
        timestamp=timestamp,
        url_website=f"{ARD_PAGE}{page}",
        id=f"id-{page}",
        **overrides,
    )


SHOW = [
    _show_entry("Folge 1009: Mein freier Wille (S26/E04)", 1794900000, "a"),
    _show_entry(
        "Folge 1009: Mein freier Wille (S26/E04) (Audiodeskription)", 1794900000, "b"
    ),
    _show_entry("Folge 1008: Schutzlos (S26/E03)", 1794800000, "c"),
    _show_entry("Folge 1: In Leipzig (S01/E01)", 1794700000, "d"),
    _show_entry("Trailer zur Folge 1010", 1794950000, "e"),
    _show_entry("Hinter den Kulissen", 1794600000, "f"),
    _show_entry("Interview mit dem Cast", 1794500000, "g"),
    _entry(channel="MDR", topic="In aller Freundschaft - Die jungen Ärzte", id="x"),
    _entry(channel="ARD", topic="In aller Freundschaft", id="y"),
]


@pytest.mark.parametrize(
    ("title", "marker", "clean"),
    [
        (
            "Folge 1009: Mein freier Wille (S26/E04)",
            (26, 4),
            "Folge 1009: Mein freier Wille",
        ),
        (
            "Durch die Blumen gesagt (S23/E05) (Audiodeskription)",
            (23, 5),
            "Durch die Blumen gesagt (Audiodeskription)",
        ),
        (
            "Nussbaumbandi – Fescht – (Staffel 1, Folge 12)",
            (1, 12),
            "Nussbaumbandi – Fescht",
        ),
        (
            "Soko Donau (12/15): Scheinheilig",
            (None, None),
            "Soko Donau (12/15): Scheinheilig",
        ),
        ("Folge 4675", (None, None), "Folge 4675"),
    ],
)
def test_episode_markers(title, marker, clean):
    entry = _entry(title=title, topic="Other")
    assert api.episode_marker(entry) == marker
    assert api.episode_title(entry) == clean


def test_episode_title_drops_the_show_name():
    entry = _entry(title="Tatort: Narrentanz", topic="Tatort")
    assert api.episode_title(entry) == "Narrentanz"


def test_show_urls_round_trip_and_resolve():
    from aniworld.entry import model_for_url
    from aniworld.models.mediathek import MediathekSeason, MediathekSeries

    assert api.parse_show_url(SHOW_URL) == ("MDR", "In aller Freundschaft", None)
    season_url = api.show_url("MDR", "In aller Freundschaft", season=26)
    assert api.parse_show_url(season_url) == ("MDR", "In aller Freundschaft", 26)

    assert resolve_provider(SHOW_URL).name == "Mediathek"
    assert isinstance(model_for_url(SHOW_URL), MediathekSeries)
    assert isinstance(model_for_url(season_url), MediathekSeason)


def test_show_url_opens_the_same_search_on_the_site():
    assert SHOW_URL.startswith(
        "https://mediathekviewweb.de/#query=%21mdr%20%23in%2Caller%2Cfreundschaft&"
    )


def test_search_groups_programmes_into_shows(stub):
    stub.extend(SHOW)
    shows = api.search_shows("freundschaft")
    assert [(s["channel"], s["topic"]) for s in shows] == [
        ("MDR", "In aller Freundschaft"),
        ("MDR", "In aller Freundschaft - Die jungen Ärzte"),
        ("ARD", "In aller Freundschaft"),
    ]
    # The first programme the API returns (the newest) stands for the show.
    assert shows[0]["newest"]["id"] == "id-a"


def test_show_lists_its_seasons_and_episodes(stub):
    from aniworld.models.mediathek import MediathekSeries

    stub.extend(SHOW)
    show = MediathekSeries(SHOW_URL)
    assert show.title == "In aller Freundschaft"
    assert show.channel == "MDR"

    seasons = {season.season_number: season for season in show.seasons}
    assert list(seasons) == [1, 26, 0]
    assert seasons[0].label == "Episodes"
    assert seasons[26].label == ""

    s26 = seasons[26].episodes
    # One version per episode, the regular one, in episode order.
    assert [(e.episode_number, e.url) for e in s26] == [
        (3, api.entry_url(SHOW[2])),
        (4, api.entry_url(SHOW[0])),
    ]
    assert s26[1].title_de == "Folge 1009: Mein freier Wille"

    # Trailers are left out; the rest count up by broadcast date.
    extras = seasons[0].episodes
    assert [(e.episode_number, e.title) for e in extras] == [
        (1, "Interview mit dem Cast"),
        (2, "Hinter den Kulissen"),
    ]

    # The listing already holds every entry, so no lookup per episode.
    calls = len(stub.calls)
    assert s26[0].stream_url.endswith("hd.mp4")
    assert len(stub.calls) == calls


def test_numbered_episodes_follow_the_naming_template(stub, monkeypatch, tmp_path):
    monkeypatch.delenv("ANIWORLD_NAMING_TEMPLATE", raising=False)
    stub.extend(SHOW)
    episode = MediathekEpisode(api.entry_url(SHOW[0]), selected_path=str(tmp_path))
    assert episode.season_number == 26
    assert episode.episode_number == 4
    assert episode._episode_path == Path(
        tmp_path,
        "In aller Freundschaft",
        "Season 26",
        "In aller Freundschaft S26E004.mkv",
    )


def test_unnumbered_episodes_keep_a_dated_name(stub, tmp_path):
    stub.extend(SHOW)
    episode = MediathekEpisode(api.entry_url(SHOW[5]), selected_path=str(tmp_path))
    assert episode.season_number is None
    assert episode._episode_path.parent == Path(tmp_path, "In aller Freundschaft")
    assert episode._episode_path.name.startswith("Hinter den Kulissen (2026-")
    assert episode.title_de.startswith("Hinter den Kulissen · ")


def test_show_cover_is_the_newest_preview_image(stub, monkeypatch):
    from aniworld.models.mediathek import MediathekSeries

    stub.extend(SHOW)
    pages = []

    def fake_cover(page):
        pages.append(page)
        return "https://img.example.invalid/cover.jpg"

    monkeypatch.setattr(api, "_fetch_cover", fake_cover)
    assert MediathekSeries(SHOW_URL).poster_url.endswith("cover.jpg")
    assert pages == [SHOW[0]["url_website"]]


def test_og_image_is_read_from_the_page_head(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield (
                b'<html><head><meta property="og:image" '
                b'content="https://i.example.invalid/x.jpg?a=1&amp;b=2">'
            )
            yield b"</head><body>" + b"x" * 1000

        def close(self):
            pass

    api.clear_cache()
    monkeypatch.setattr(api.GLOBAL_SESSION, "get", lambda *a, **k: FakeResponse())
    try:
        assert (
            api.cover_url("https://www.zdf.de/x")
            == "https://i.example.invalid/x.jpg?a=1&b=2"
        )
    finally:
        api.clear_cache()


# -----------------------------
# Show posters (TVmaze)
# -----------------------------


def _tvmaze(name, country="DE", image="https://static.tvmaze.invalid/p.jpg"):
    return {
        "show": {
            "name": name,
            "network": {"country": {"code": country}},
            "image": {"original": image, "medium": image + "?m"},
        }
    }


def test_poster_needs_the_exact_show_name(monkeypatch):
    _fake_tvmaze(
        monkeypatch,
        [
            _tvmaze(
                "In aller Freundschaft – Die Krankenschwestern", image="https://x/k.jpg"
            ),
            _tvmaze(
                "In aller Freundschaft – Die jungen Ärzte", image="https://x/j.jpg"
            ),
        ],
    )
    assert (
        api.show_poster("In aller Freundschaft - Die jungen Ärzte") == "https://x/j.jpg"
    )
    assert api.show_poster("In aller Freundschaft") == ""
    api.clear_cache()


def _fake_tvmaze(monkeypatch, hits):
    queries = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return hits

    def fake_get(url, params=None, **kwargs):
        queries.append(params["q"])
        return FakeResponse()

    api.clear_cache()
    monkeypatch.setattr(api, "_TVMAZE_INTERVAL", 0)
    monkeypatch.setattr(api.GLOBAL_SESSION, "get", fake_get)
    return queries


def test_poster_skips_foreign_shows_of_the_same_name(monkeypatch):
    _fake_tvmaze(monkeypatch, [_tvmaze("Tatort", country="US")])
    assert api.show_poster("Tatort") == ""
    api.clear_cache()


def test_poster_ignores_umlauts_and_orf_season_suffixes(monkeypatch):
    queries = _fake_tvmaze(monkeypatch, [_tvmaze("SOKO Kitzbuhel", country="AT")])
    assert api.show_poster("Soko Kitzbühel Staffel 2").endswith("p.jpg")
    assert queries == ["Soko Kitzbühel"]
    api.clear_cache()


def test_poster_lookups_are_cached(monkeypatch):
    queries = _fake_tvmaze(monkeypatch, [_tvmaze("Tatort")])
    api.show_poster("Tatort")
    api.show_poster("Tatort")
    assert queries == ["Tatort"]
    api.clear_cache()


def test_failed_poster_lookups_are_not_cached(monkeypatch):
    api.clear_cache()
    monkeypatch.setattr(api, "_TVMAZE_INTERVAL", 0)
    calls = []

    def broken(*args, **kwargs):
        calls.append(1)
        raise ConnectionError("offline")

    monkeypatch.setattr(api.GLOBAL_SESSION, "get", broken)
    assert api.show_poster("Tatort") == ""
    assert api.show_poster("Tatort") == ""
    assert len(calls) == 2
    api.clear_cache()


def test_show_prefers_its_poster_over_a_preview_image(stub, monkeypatch):
    from aniworld.models.mediathek import MediathekSeries

    stub.extend(SHOW)
    monkeypatch.setattr(api, "_fetch_show_poster", lambda topic: "https://x/p.jpg")
    monkeypatch.setattr(api, "_fetch_cover", lambda page: "https://x/still.jpg")
    assert MediathekSeries(SHOW_URL).poster_url == "https://x/p.jpg"


# -----------------------------
# ORF season topics
# -----------------------------


def _orf(title, topic, page, timestamp=1794700000):
    return _entry(
        channel="ORF",
        topic=topic,
        title=title,
        timestamp=timestamp,
        url_website=f"https://on.orf.at/video/{page}",
        id=f"orf-{page}",
    )


ORF_SHOW = [
    _orf("Soko Kitzbühel (7/12): Farben des Todes", "Soko Kitzbühel Staffel 2", 1),
    _orf("Soko Kitzbühel (6/12): Abfahrt in den Tod", "Soko Kitzbühel Staffel 2", 2),
    _orf("Soko Kitzbühel (5/6): Die letzte Seilbahn", "Soko Kitzbühel Staffel 1", 3),
    _orf("Soko Kitzbühel: Hinter den Kulissen", "Soko Kitzbühel", 4),
]


@pytest.mark.parametrize(
    ("topic", "show", "season"),
    [
        ("Soko Donau Staffel 11", "Soko Donau", 11),
        ("Die Superklasse - Staffel 2", "Die Superklasse", 2),
        ("Soko Donau", "Soko Donau", None),
        ("Staffel 3", "Staffel 3", None),
    ],
)
def test_season_topics(topic, show, season):
    assert api.show_name(topic) == show
    assert api.topic_season(topic) == season


def test_season_topic_numbers_its_episodes():
    assert api.episode_marker(ORF_SHOW[0]) == (2, 7)
    assert api.episode_title(ORF_SHOW[0]) == "Farben des Todes"
    assert api.episode_marker(ORF_SHOW[3]) == (None, None)


def test_part_numbers_elsewhere_stay_unnumbered():
    # A mini-series part, not an episode of a season.
    entry = _entry(title="Ein Engel verschwindet (3/3) - Requiem", topic="Krimi")
    assert api.episode_marker(entry) == (None, None)


def test_season_topics_join_one_show(stub):
    from aniworld.models.mediathek import MediathekSeries

    stub.extend(ORF_SHOW)
    [show] = api.search_shows("kitzbühel")
    assert (show["channel"], show["topic"]) == ("ORF", "Soko Kitzbühel")

    series = MediathekSeries(api.show_url("ORF", "Soko Kitzbühel"))
    seasons = {season.season_number: season for season in series.seasons}
    assert list(seasons) == [1, 2, 0]
    assert [e.episode_number for e in seasons[2].episodes] == [6, 7]


def test_season_topic_episodes_share_the_show_folder(stub, monkeypatch, tmp_path):
    monkeypatch.delenv("ANIWORLD_NAMING_TEMPLATE", raising=False)
    stub.extend(ORF_SHOW)
    episode = MediathekEpisode(api.entry_url(ORF_SHOW[0]), selected_path=str(tmp_path))
    assert episode._episode_path == Path(
        tmp_path, "Soko Kitzbühel", "Season 02", "Soko Kitzbühel S02E007.mkv"
    )
