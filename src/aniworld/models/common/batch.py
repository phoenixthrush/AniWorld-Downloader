"""Running an action over many episodes without one failure ending the run.

A season is a batch. One dead hoster link, one 403, one captcha in the middle of
it should cost you that episode, not the eleven after it. Before this, the first
exception escaped all the way to the CLI's catch-all, which printed "An
unexpected error occurred" and quit, leaving the rest of the season undownloaded
and no way to resume short of invoking each episode by hand.

Ctrl+C is deliberately still fatal. `except Exception` does not catch
KeyboardInterrupt, since that inherits from BaseException, so pressing Ctrl+C
stops everything immediately instead of being logged as a failed episode and
having the loop grind on through the rest of the season.
"""

from ...config import logger


def _label(episode):
    """Something short and recognisable to print when an episode fails."""
    season = getattr(episode, "season", None)
    number = getattr(episode, "episode_number", None)
    season_number = getattr(season, "season_number", None)
    if season_number is not None and number is not None:
        return f"S{season_number:02d}E{number:02d}"
    if number is not None:
        return f"Episode {number}"
    return getattr(episode, "url", "") or "unknown episode"


def run_each(episodes, action):
    """Run `action` on every episode, carrying on past the ones that fail.

    Returns the list of (label, error) that failed, so the caller can decide
    what to do with an incomplete run.
    """
    episodes = list(episodes)
    failures = []

    for episode in episodes:
        try:
            getattr(episode, action)()
        except Exception as exc:
            # KeyboardInterrupt is not an Exception, so Ctrl+C still gets out
            # of here untouched and stops the whole run.
            label = _label(episode)
            # Logged as it happens, then listed again in the summary. The
            # traceback is debug only, or a season with three dead links buries
            # the summary under three of them.
            logger.error("%s failed: %s", label, exc)
            logger.debug("%s traceback", label, exc_info=True)
            failures.append((label, exc))

    report(len(episodes), failures, action)
    return failures


def report(total, failures, action="download"):
    """Print what happened, but only when there is something worth saying."""
    if not failures:
        return
    done = total - len(failures)
    print(f"\n{action.capitalize()}ed {done} of {total}. {len(failures)} failed:")
    for label, exc in failures:
        print(f"  {label}: {exc}")
