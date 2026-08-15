"""A failed episode must not abandon the rest of the batch (issue #274).

Before this, the CLI looped episodes with no guard, so the first exception
escaped to the catch-all, printed "An unexpected error occurred" and quit. The
Web UI worker already survived a bad episode; the CLI did not, and the two
disagreed about what one failure meant.
"""

import pytest

from aniworld.models.common.batch import _label, run_each


class FakeEpisode:
    """Stands in for a real episode without any network behind it."""

    def __init__(self, number, season=1, fail=None):
        self.episode_number = number
        self.season = type("S", (), {"season_number": season})()
        self.url = f"https://example.test/episode-{number}"
        self._fail = fail
        self.ran = False

    def download(self):
        self.ran = True
        if self._fail:
            raise self._fail


# ---------------------------------------------------------------------------
# Carrying on past a failure
# ---------------------------------------------------------------------------
def test_a_clean_run_reports_nothing():
    episodes = [FakeEpisode(n) for n in (1, 2, 3)]
    assert run_each(episodes, "download") == []
    assert all(e.ran for e in episodes)


def test_one_failure_does_not_stop_the_rest():
    """The whole point of the issue: episode 2 dying must not cost 3 and 4."""
    episodes = [
        FakeEpisode(1),
        FakeEpisode(2, fail=ValueError("no stream found")),
        FakeEpisode(3),
        FakeEpisode(4),
    ]
    failures = run_each(episodes, "download")

    assert [e.episode_number for e in episodes if e.ran] == [1, 2, 3, 4]
    assert len(failures) == 1


def test_every_failure_is_collected():
    episodes = [
        FakeEpisode(1, fail=ValueError("a")),
        FakeEpisode(2),
        FakeEpisode(3, fail=RuntimeError("b")),
    ]
    failures = run_each(episodes, "download")
    assert [str(exc) for _, exc in failures] == ["a", "b"]


def test_a_failure_carries_a_readable_label():
    episodes = [FakeEpisode(4, season=2, fail=ValueError("boom"))]
    ((label, _),) = run_each(episodes, "download")
    assert label == "S02E04"


def test_an_all_failing_batch_still_attempts_every_episode():
    episodes = [FakeEpisode(n, fail=ValueError("x")) for n in (1, 2, 3)]
    assert len(run_each(episodes, "download")) == 3
    assert all(e.ran for e in episodes)


def test_an_empty_batch_is_fine():
    assert run_each([], "download") == []


# ---------------------------------------------------------------------------
# Ctrl+C must still interrupt everything
#
# KeyboardInterrupt inherits from BaseException, not Exception, so the guard
# does not catch it. If someone ever widens that except clause, these fail.
# ---------------------------------------------------------------------------
def test_ctrl_c_is_not_swallowed():
    episodes = [
        FakeEpisode(1),
        FakeEpisode(2, fail=KeyboardInterrupt()),
        FakeEpisode(3),
    ]
    with pytest.raises(KeyboardInterrupt):
        run_each(episodes, "download")


def test_ctrl_c_stops_the_remaining_episodes():
    """Not just re-raised at the end: nothing after it may run."""
    episodes = [
        FakeEpisode(1),
        FakeEpisode(2, fail=KeyboardInterrupt()),
        FakeEpisode(3),
    ]
    with pytest.raises(KeyboardInterrupt):
        run_each(episodes, "download")
    assert episodes[0].ran
    assert not episodes[2].ran


def test_a_hard_exit_is_not_swallowed_either():
    """SystemExit is also a BaseException, and also has to get out."""
    episodes = [FakeEpisode(1, fail=SystemExit(2)), FakeEpisode(2)]
    with pytest.raises(SystemExit):
        run_each(episodes, "download")
    assert not episodes[1].ran


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------
def test_label_falls_back_when_there_is_no_season():
    episode = FakeEpisode(7)
    episode.season = None
    assert _label(episode) == "Episode 7"


def test_label_falls_back_to_the_url_when_nothing_else_is_known():
    episode = FakeEpisode(1)
    episode.season = None
    episode.episode_number = None
    assert episode.url in _label(episode)


# ---------------------------------------------------------------------------
# Every batch path goes through the guard
# ---------------------------------------------------------------------------
def test_no_season_still_loops_episodes_unguarded():
    """A provider added later must not reintroduce the bug."""
    from pathlib import Path

    models = Path(__file__).resolve().parent.parent / "src" / "aniworld" / "models"
    offenders = []
    for path in models.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "for episode in self.episodes:" in text:
            offenders.append(str(path.relative_to(models)))
    assert not offenders, f"unguarded batch loops: {offenders}"


# ---------------------------------------------------------------------------
# Series must delegate to Season, not loop episodes itself (issue #274,
# follow-up: s_to, hanime_tv and aniworld_to still reimplemented the loop
# at the Series level, bypassing the run_each() guard entirely)
# ---------------------------------------------------------------------------
class FakeSeason:
    """A season exactly as batch-safe as the real ones: delegates to run_each."""

    def __init__(self, episodes):
        self.episodes = episodes

    def download(self):
        return run_each(self.episodes, "download")

    def watch(self):
        return run_each(self.episodes, "watch")

    def syncplay(self):
        return run_each(self.episodes, "syncplay")


_SERIES_PROVIDERS = [
    (
        "aniworld.models.aniworld_to.series",
        "AniworldSeries",
        "https://aniworld.to/anime/stream/example-series",
    ),
    (
        "aniworld.models.s_to.series",
        "SerienstreamSeries",
        "https://serienstream.to/serie/example-series",
    ),
    (
        "aniworld.models.hanime_tv.series",
        "HanimeTVSeries",
        "https://hanime.tv/videos/hentai/example-video-1",
    ),
]


@pytest.mark.parametrize("module_path, class_name, url", _SERIES_PROVIDERS)
def test_series_delegates_to_season_so_one_failure_does_not_abort_the_batch(
    monkeypatch, module_path, class_name, url
):
    """A single failed episode must not kill Series.download() either -
    Series has to go through Season (which already guards with run_each()),
    not loop season.episodes directly."""
    import importlib

    module = importlib.import_module(module_path)
    series_cls = getattr(module, class_name)

    episodes = [
        FakeEpisode(1),
        FakeEpisode(2, fail=ValueError("no stream found")),
        FakeEpisode(3),
    ]
    fake_season = FakeSeason(episodes)
    monkeypatch.setattr(series_cls, "seasons", property(lambda self: [fake_season]))

    series = series_cls(url)
    series.download()  # must not raise

    assert all(e.ran for e in episodes), "every episode must still be attempted"


def test_no_series_still_loops_season_episodes_unguarded():
    """A provider added later must not reintroduce the Series-level version
    of #274: looping season.episodes directly instead of delegating to
    season.download()/.watch()/.syncplay()."""
    from pathlib import Path

    models = Path(__file__).resolve().parent.parent / "src" / "aniworld" / "models"
    offenders = []
    for path in models.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "for episode in season.episodes:" in text:
            offenders.append(str(path.relative_to(models)))
    assert not offenders, f"unguarded Series-level batch loops: {offenders}"
