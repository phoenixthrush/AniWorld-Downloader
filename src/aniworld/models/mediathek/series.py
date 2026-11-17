"""A show in the Mediathek: one topic on one channel, split into seasons."""

try:
    from ..common import run_each
    from . import api
    from . import versions as language_versions
    from .episode import MediathekEpisode, channel_label, clean_name
except ImportError:
    from aniworld.models.common import run_each
    from aniworld.models.mediathek import api
    from aniworld.models.mediathek import versions as language_versions
    from aniworld.models.mediathek.episode import (
        MediathekEpisode,
        channel_label,
        clean_name,
    )

# Programmes without a season marker are listed together under this number.
# AniWorld keeps season 0 for movies the same way.
UNNUMBERED_SEASON = 0


class MediathekSeries:
    """
    Every programme MediathekView lists for one show, e.g. "In aller
    Freundschaft" on MDR.

    Parameters:
        url:    A show link as built by ``api.show_url()``:
                https://mediathekviewweb.de/#query=...&channel=MDR&topic=In%20aller%20Freundschaft

    Seasons come from the "(S26/E04)" / "(Staffel 1, Folge 12)" markers the
    broadcasters put into titles. Programmes without one are grouped into
    season 0, newest last, and keep their dated file names.

    Each episode carries all its versions (English, sign language, Arte's
    other language channels ...), see versions.py.

    Only what the broadcaster currently offers is listed: media libraries take
    programmes offline after a while.
    """

    def __init__(self, url, selected_path=None, selected_language=None, **_):
        self.channel_id, self.topic, _season = api.parse_show_url(url)
        # An Arte series: a family id and name inside a category topic.
        self.family, self.name = api.show_series(url)
        self.url = api.show_url(
            self.channel_id, self.topic, family=self.family, name=self.name
        )
        self.selected_path = selected_path
        self.selected_language = selected_language
        self.__entries = None
        self.__groups = None
        self.__seasons = None

    @property
    def entries(self):
        """Every entry of the show on its channel, all versions included."""
        if self.__entries is None:
            self.__entries = api.show_entries(
                self.channel_id,
                self.topic,
                family=self.family,
                series=None if self.family else self.name,
                include_variants=True,
            )
        return self.__entries

    @property
    def groups(self):
        """[(primary entry, {label: entry})], one per episode."""
        if self.__groups is None:
            entries = list(self.entries)
            if self.channel_id.startswith("ARTE."):
                # Arte's other languages are other channels.
                entries += language_versions.arte_translations(entries)
            self.__groups = language_versions.group(
                entries, preferred_channel=self.channel_id
            )
        return self.__groups

    @property
    def title(self):
        return self.name or self.topic

    @property
    def title_cleaned(self):
        return clean_name(self.title)

    @property
    def channel(self):
        return channel_label(self.channel_id)

    @property
    def _newest(self):
        return self.entries[0] if self.entries else {}

    @property
    def description(self):
        return (self._newest.get("description") or "").strip()

    @property
    def release_year(self):
        date = api.broadcast_date(self._newest) if self._newest else None
        return date.year if date else ""

    @property
    def genres(self):
        return [self.channel]

    @property
    def poster_url(self):
        # The show's own poster where TVmaze knows the show (series mostly).
        poster = api.show_poster(self.title)
        if poster:
            return poster
        # Otherwise the newest programme's preview image stands in for it.
        for entry in self.entries[:3]:
            cover = api.cover_url(entry.get("url_website"))
            if cover:
                return cover
        return ""

    @property
    def seasons(self):
        if self.__seasons is None:
            numbers = {api.episode_marker(primary)[0] for primary, _ in self.groups}
            numbered = sorted(n for n in numbers if n is not None)
            seasons = [
                MediathekSeason(self._season_url(n), series=self) for n in numbered
            ]
            if None in numbers:
                seasons.append(
                    MediathekSeason(self._season_url(UNNUMBERED_SEASON), series=self)
                )
            self.__seasons = seasons
        return self.__seasons

    def _season_url(self, number):
        return api.show_url(
            self.channel_id,
            self.topic,
            season=number,
            family=self.family,
            name=self.name,
        )

    @property
    def episodes(self):
        return [episode for season in self.seasons for episode in season.episodes]

    def _run(self, action):
        failures = run_each(self.episodes, action)
        if failures:
            raise RuntimeError(f"{len(failures)} episode(s) failed")

    def download(self):
        self._run("download")

    def watch(self):
        self._run("watch")

    def syncplay(self):
        self._run("syncplay")


class MediathekSeason:
    """One season of a show, or (season 0) its unnumbered programmes."""

    def __init__(
        self, url, series=None, selected_path=None, selected_language=None, **_
    ):
        channel, topic, season = api.parse_show_url(url)
        if season is None:
            raise ValueError(f"Not a Mediathek season URL: {url}")
        self.url = url
        self.season_number = season
        family, name = api.show_series(url)
        self.series = series or MediathekSeries(
            api.show_url(channel, topic, family=family, name=name)
        )
        self.selected_path = selected_path
        self.selected_language = selected_language
        self.__episodes = None

    @property
    def is_unnumbered(self):
        return self.season_number == UNNUMBERED_SEASON

    @property
    def are_movies(self):
        return False

    @property
    def label(self):
        """Heading for season 0; numbered seasons use the usual "Season N"."""
        return "Episodes" if self.is_unnumbered else ""

    @property
    def episodes(self):
        if self.__episodes is None:
            self.__episodes = self._build_episodes()
        return self.__episodes

    @property
    def episode_count(self):
        return len(self.episodes)

    def _build_episodes(self):
        if self.is_unnumbered:
            groups = [
                group
                for group in self.series.groups
                if api.episode_marker(group[0])[0] is None
            ]
            # Oldest first, so the listing reads like a season.
            groups.sort(key=lambda group: group[0].get("timestamp") or 0)
            numbered = [(index, group) for index, group in enumerate(groups, 1)]
        else:
            groups = [
                group
                for group in self.series.groups
                if api.episode_marker(group[0])[0] == self.season_number
            ]
            groups.sort(key=lambda group: api.episode_marker(group[0])[1])
            numbered = [(None, group) for group in groups]

        return [
            MediathekEpisode(
                url=api.entry_url(primary),
                selected_path=self.selected_path or self.series.selected_path,
                selected_language=self.selected_language,
                entry=primary,
                versions=versions,
                season=self,
                series=self.series,
                episode_number=index,
            )
            for index, (primary, versions) in numbered
        ]

    def _run(self, action):
        failures = run_each(self.episodes, action)
        if failures:
            raise RuntimeError(f"{len(failures)} episode(s) failed")

    def download(self):
        self._run("download")

    def watch(self):
        self._run("watch")

    def syncplay(self):
        self._run("syncplay")
