"""Auto-Sync scheduling, run against a clock we control.

    python tests/autosync_simulation.py

Not a test file and not named like one, so pytest never collects it: it walks
months of simulated time, which the suite has no business doing on every run.
What it is for is the questions a unit test answers badly, because they are
about a loop over time rather than a single call:

  * does a fixed time stay on the wall clock across both DST switches
  * does the night with no 02:30, and the one with two, run exactly once
  * does turning Auto-Sync on queue a pile of downloads on the spot
  * does a schedule changed in the settings take effect without a restart
  * does the thread ever spin, or nap past the tick

The real _due(), next_run_at() and _nap_seconds() are used throughout. Only
the clock and the two bits of state the loop touches are stand-ins, and the
body of run() is the body of autosync._loop() minus the downloading.
"""

import itertools
import os
import sys
import tempfile
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ["ANIWORLD_INSTALL_FOLDER"] = tempfile.mkdtemp()

from aniworld.web import autosync


class Sim:
    """A fake clock plus the two bits of state the loop touches."""

    def __init__(self, start_local, tz="Europe/Berlin"):
        os.environ["TZ"] = tz
        _time.tzset()
        self.now = datetime.fromisoformat(start_local).astimezone(timezone.utc)
        self.state = {}
        self.runs = []
        self.naps = []

        autosync._now = lambda: self.now
        autosync.db.get_autosync_state = lambda: dict(self.state)
        autosync.db.set_autosync_state = lambda **kw: self.state.update(
            {k: (str(v) if v is not None else None) for k, v in kw.items()}
        )
        autosync._anchored_at = None

    def local(self, moment=None):
        return (moment or self.now).astimezone().replace(tzinfo=None)

    def run(self, days, on_tick=None):
        """The body of autosync._loop(), minus the actual downloading."""
        end = self.now + timedelta(days=days)
        steps = 0
        while self.now < end:
            steps += 1
            if steps > 2_000_000:
                raise AssertionError("the loop is spinning")
            if on_tick:
                on_tick(self)
            from aniworld.web.settings_store import autosync_enabled

            if autosync_enabled():
                if autosync._due():
                    self.state["last_run"] = self.now.isoformat()
                    self.runs.append(self.now)
            else:
                autosync._reset_anchor()
            nap = autosync._nap_seconds()
            self.naps.append(nap)
            assert nap > 0, f"a nap of {nap}s would spin the CPU"
            self.now += timedelta(seconds=nap)
        return self.runs


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  <- {detail}" if detail else ""))
    return ok


failures = []


def case(label, ok, detail=""):
    if not check(label, ok, detail):
        failures.append(label)


def fresh(**env):
    for key in list(os.environ):
        if key.startswith("ANIWORLD_AUTOSYNC") or key == "ANIWORLD_ENABLE_AUTOSYNC":
            del os.environ[key]
    os.environ["ANIWORLD_ENABLE_AUTOSYNC"] = "1"
    os.environ.update(env)


# ---------------------------------------------------------------------------
print("\n=== fixed time, one month ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 22 * * *")
sim = Sim("2026-06-01 09:00")
runs = sim.run(days=30)
stamps = {sim.local(r).strftime("%H:%M") for r in runs}
case("one run a day", len(runs) == 30, f"{len(runs)} runs")
case("always at 22:00 local", stamps == {"22:00"}, stamps)

print("\n=== fixed time across the spring DST switch (Berlin, 29 Mar 02:00->03:00) ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 22 * * *")
sim = Sim("2026-03-26 09:00")
runs = sim.run(days=7)
stamps = sorted({sim.local(r).strftime("%H:%M") for r in runs})
case("still one run a day", len(runs) == 7, f"{len(runs)} runs")
case("still 22:00 on the wall", stamps == ["22:00"], stamps)

print("\n=== a 02:30 run on the night that has no 02:30 ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="30 2 * * *")
sim = Sim("2026-03-27 09:00")
runs = sim.run(days=5)
case("no day lost, none doubled", len(runs) == 5, [str(sim.local(r)) for r in runs])

print("\n=== the autumn switch, when 02:30 happens twice ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="30 2 * * *")
sim = Sim("2026-10-23 09:00")
runs = sim.run(days=5)
case(
    "not run twice in the repeated hour",
    len(runs) == 5,
    [str(sim.local(r)) for r in runs],
)

print("\n=== weekdays only ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 7 * * 1,2,3,4,5")
sim = Sim("2026-06-01 00:30")
runs = sim.run(days=28)
weekdays = {sim.local(r).weekday() for r in runs}
case("20 runs in four weeks", len(runs) == 20, f"{len(runs)} runs")
case("never at the weekend", weekdays <= {0, 1, 2, 3, 4}, weekdays)

print("\n=== two times a day that cron needs two lines for ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 8 * * *; 30 22 * * *")
sim = Sim("2026-06-01 00:05")
runs = sim.run(days=10)
stamps = sorted({sim.local(r).strftime("%H:%M") for r in runs})
case("20 runs", len(runs) == 20, f"{len(runs)} runs")
case("08:00 and 22:30", stamps == ["08:00", "22:30"], stamps)

print("\n=== interval mode ===")
fresh(ANIWORLD_AUTOSYNC_INTERVAL="6h")
sim = Sim("2026-06-01 00:00")
runs = sim.run(days=7)
gaps = {round((b - a).total_seconds()) for a, b in itertools.pairwise(runs)}
case("first run is immediate", runs and runs[0] == sim.runs[0], "")
case("every six hours", gaps == {6 * 3600}, gaps)
case("one at once plus one every six hours", len(runs) == 28, f"{len(runs)} runs")

print("\n=== a 90 minute interval ===")
fresh(ANIWORLD_AUTOSYNC_INTERVAL="90m")
sim = Sim("2026-06-01 00:00")
runs = sim.run(days=2)
gaps = {round((b - a).total_seconds()) for a, b in itertools.pairwise(runs)}
case("every 90 minutes", gaps == {5400}, gaps)

print("\n=== every 30 minutes, as cron ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="*/30 * * * *")
sim = Sim("2026-06-01 00:01")
runs = sim.run(days=2)
case("48 a day", len(runs) == 96, f"{len(runs)} runs")

print("\n=== turned on at 23:00 with a 22:00 schedule ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 22 * * *")
sim = Sim("2026-06-01 23:00")
runs = sim.run(days=1)
case(
    "waits for tomorrow, does not fire at once",
    len(runs) == 1,
    [str(sim.local(r)) for r in runs],
)
case(
    "and fires at 22:00",
    sim.local(runs[0]).strftime("%H:%M") == "22:00" if runs else False,
    "",
)

print("\n=== the machine was off for a week ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 22 * * *")
sim = Sim("2026-06-08 10:00")
sim.state["last_run"] = (sim.now - timedelta(days=7)).isoformat()
runs = sim.run(days=1)
case(
    "catches up once, not seven times",
    len(runs) == 2,
    [str(sim.local(r)) for r in runs],
)

print("\n=== the schedule is changed while it runs ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 22 * * *")
sim = Sim("2026-06-01 09:00")


def switch(s):
    if s.local().day == 3 and s.local().hour == 10:
        os.environ["ANIWORLD_AUTOSYNC_CRON"] = "0 6 * * *"


runs = sim.run(days=6, on_tick=switch)
stamps = [sim.local(r).strftime("%d %H:%M") for r in runs]
case(
    "picks the new time up without a restart",
    any(s.endswith("06:00") for s in stamps),
    stamps,
)

print("\n=== switched off halfway ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 22 * * *")
sim = Sim("2026-06-01 09:00")


def disable(s):
    if s.local().day == 3:
        os.environ["ANIWORLD_ENABLE_AUTOSYNC"] = "0"


runs = sim.run(days=6, on_tick=disable)
case("stops when it is turned off", len(runs) == 2, [str(sim.local(r)) for r in runs])

print("\n=== enabled long after the process started ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 3 * * *")
os.environ["ANIWORLD_ENABLE_AUTOSYNC"] = "0"
sim = Sim("2026-06-01 09:00")


def enable_later(s):
    if s.local().day == 5 and s.local().hour == 14:
        os.environ["ANIWORLD_ENABLE_AUTOSYNC"] = "1"


runs = sim.run(days=7, on_tick=enable_later)
first = sim.local(runs[0]) if runs else None
case(
    "does not fire the moment it is switched on",
    bool(runs) and first.strftime("%H:%M") == "03:00" and first.day == 6,
    str(first),
)

print("\n=== enabled late, with the thread started at boot ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 3 * * *")
os.environ["ANIWORLD_ENABLE_AUTOSYNC"] = "0"
sim = Sim("2026-06-01 09:00")
autosync._anchor()  # what ensure_started() does at boot, while it is still off


def enable_on_the_fifth(s):
    if s.local().day == 5 and s.local().hour == 14:
        os.environ["ANIWORLD_ENABLE_AUTOSYNC"] = "1"


runs = sim.run(days=7, on_tick=enable_on_the_fifth)
first = sim.local(runs[0]) if runs else None
case(
    "a boot-time anchor does not make it fire on switch-on",
    bool(runs) and first.day == 6 and first.strftime("%H:%M") == "03:00",
    str(first),
)
case(
    "and then keeps to the schedule", len(runs) == 3, [str(sim.local(r)) for r in runs]
)

print("\n=== a schedule that never comes round ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 0 30 2 *")
sim = Sim("2026-06-01 09:00")
runs = sim.run(days=3)
case(
    "never runs, never spins",
    len(runs) == 0 and autosync.next_run_at() is None,
    len(runs),
)

print("\n=== how often the thread wakes ===")
fresh(ANIWORLD_AUTOSYNC_MODE="cron", ANIWORLD_AUTOSYNC_CRON="0 22 * * *")
sim = Sim("2026-06-01 09:00")
sim.run(days=2)
case("naps stay within the tick", max(sim.naps) <= autosync.TICK_SECONDS, max(sim.naps))
case("a day is under 300 wakeups", len(sim.naps) / 2 < 300, len(sim.naps) / 2)

print("\n=== a last run written without a timezone ===")
fresh(ANIWORLD_AUTOSYNC_INTERVAL="6h")
sim = Sim("2026-06-01 09:00")
sim.state["last_run"] = "2026-06-01T00:00:00"
try:
    runs = sim.run(days=1)
    case("a naive timestamp does not stall the worker", len(runs) >= 3, len(runs))
except Exception as exc:
    case(
        "a naive timestamp does not stall the worker",
        False,
        f"{type(exc).__name__}: {exc}",
    )

print()
print("FAILURES:", failures or "none")
sys.exit(1 if failures else 0)
