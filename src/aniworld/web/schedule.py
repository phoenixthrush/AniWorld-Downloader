"""Working out when Auto-Sync should run next.

Two ways to say it, both settable from the settings page:

  * an interval, "every 6 hours", stored as "6h"
  * fixed times, cron style, "0 22 * * 1,2"

The cron form also takes plain English (and German), because "every monday and
friday at 10pm" is what people actually type into a text field. Whatever comes
in is normalised to cron, and that is what gets stored.

One schedule can hold several cron lines, separated by ";". Cron cannot say
"08:00 and 22:30" in a single line, the two would cross-multiply into four
runs, so times that do not share a minute become one line each.

Everything here works on naive datetimes read as local wall-clock time: a cron
line means 22:00 in the timezone the machine is in and stays at 22:00 across a
DST switch. Converting to and from UTC is the caller's job.
"""

import re
from datetime import timedelta


class ScheduleError(ValueError):
    """Raised when a schedule cannot be understood."""


# ---------------------------------------------------------------------------
# Intervals
# ---------------------------------------------------------------------------
MIN_INTERVAL_SECONDS = 5 * 60
MAX_INTERVAL_SECONDS = 365 * 24 * 60 * 60

_UNITS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "week": 604800,
    "weeks": 604800,
}

_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)([a-z]+)")


def _unquoted(text):
    """Values with spaces get quoted in a .env, and not everything strips them.

    python-dotenv does, but `docker run --env-file` hands the quotes straight
    through, and someone typing into the settings field may add their own.
    """
    text = text.strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1].strip()
    return text


def parse_interval(value):
    """Seconds between two runs, from "90m", "6h", "1h30m" or a number of hours."""
    if isinstance(value, bool):
        raise ScheduleError(f"Invalid interval: {value!r}")
    if isinstance(value, (int, float)):
        return _checked_interval(float(value) * 3600, value)

    text = _unquoted(str(value)).lower().replace(" ", "")
    if not text:
        raise ScheduleError("The interval cannot be empty")

    # A bare number is hours, the unit Auto-Sync was pinned to before this
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return _checked_interval(float(text) * 3600, value)

    parts = _AMOUNT_RE.findall(text)
    if not parts or "".join(amount + unit for amount, unit in parts) != text:
        raise ScheduleError(f'Invalid interval: "{value}"')

    seconds = 0.0
    for amount, unit in parts:
        if unit not in _UNITS:
            raise ScheduleError(f'Unknown interval unit "{unit}" in "{value}"')
        seconds += float(amount) * _UNITS[unit]
    return _checked_interval(seconds, value)


def _checked_interval(seconds, original):
    seconds = round(seconds)
    if seconds < MIN_INTERVAL_SECONDS:
        raise ScheduleError(
            f'"{original}" is too short, the interval has to be at least '
            f"{MIN_INTERVAL_SECONDS // 60} minutes"
        )
    if seconds > MAX_INTERVAL_SECONDS:
        raise ScheduleError(f'"{original}" is longer than a year')
    return seconds


def format_interval(seconds):
    """Shortest way to write this many seconds: "24h", "90m"."""
    seconds = int(seconds)
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


# ---------------------------------------------------------------------------
# Cron
# ---------------------------------------------------------------------------
_WEEKDAYS = {
    "sunday": 0,
    "sun": 0,
    "su": 0,
    "sonntag": 0,
    "so": 0,
    "monday": 1,
    "mon": 1,
    "mo": 1,
    "montag": 1,
    "tuesday": 2,
    "tues": 2,
    "tue": 2,
    "tu": 2,
    "dienstag": 2,
    "di": 2,
    "wednesday": 3,
    "wed": 3,
    "we": 3,
    "mittwoch": 3,
    "mi": 3,
    "thursday": 4,
    "thurs": 4,
    "thur": 4,
    "thu": 4,
    "th": 4,
    "donnerstag": 4,
    "do": 4,
    "friday": 5,
    "fri": 5,
    "fr": 5,
    "freitag": 5,
    "saturday": 6,
    "sat": 6,
    "sa": 6,
    "samstag": 6,
    "sonnabend": 6,
}

_MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MONTHS = {name: number for number, name in enumerate(_MONTH_NAMES, start=1)}
_MONTHS.update({name[:3]: number for number, name in enumerate(_MONTH_NAMES, start=1)})

_FIELD_NAMES = ("minute", "hour", "day of the month", "month", "day of the week")
_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_FIELD_ALIASES = ({}, {}, {}, _MONTHS, _WEEKDAYS)

# A cron line can be sparse (29 February on a Sunday), so give up only after
# enough years that nothing sane is left.
_SEARCH_DAYS = 4 * 366


def _field_value(token, index):
    lo, hi = _BOUNDS[index]
    value = _FIELD_ALIASES[index].get(token)
    if value is None:
        if not token.isdigit():
            raise ScheduleError(f'"{token}" is not a valid {_FIELD_NAMES[index]}')
        value = int(token)
    if not lo <= value <= hi:
        raise ScheduleError(
            f'"{token}" is out of range for the {_FIELD_NAMES[index]} ({lo}-{hi})'
        )
    # Cron knows Sunday as both 0 and 7
    return value % 7 if index == 4 else value


def _parse_field(text, index):
    """(values, restricted) for one cron field. Restricted is False for "*"."""
    lo, hi = _BOUNDS[index]
    if index == 4:
        hi = 6  # 7 is Sunday again, so the real range stops at Saturday
    text = text.strip()
    if not text:
        raise ScheduleError(f"Empty {_FIELD_NAMES[index]} in the schedule")

    values = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise ScheduleError(f"Empty {_FIELD_NAMES[index]} in the schedule")

        step = 1
        if "/" in part:
            part, _, raw_step = part.partition("/")
            if not raw_step.isdigit() or int(raw_step) == 0:
                raise ScheduleError(f'"{raw_step}" is not a valid step')
            step = int(raw_step)

        if part in ("*", ""):
            start, end = lo, hi
        elif "-" in part:
            first, _, last = part.partition("-")
            start = _field_value(first, index)
            end = _field_value(last, index)
        else:
            start = _field_value(part, index)
            # "5/15" is cron for "from 5 onwards, every 15"
            end = hi if step > 1 else start

        if start <= end:
            values.update(range(start, end + 1, step))
        else:
            # "fri-mon" and "22-2" wrap around the end of the week or the day
            wrapped = list(range(start, hi + 1)) + list(range(lo, end + 1))
            values.update(wrapped[::step])

    return values, text != "*"


class CronEntry:
    """One cron line."""

    __slots__ = (
        "days",
        "dom_any",
        "dow_any",
        "expression",
        "hours",
        "minutes",
        "months",
        "weekdays",
    )

    def __init__(self, expression, minute, hour, day, month, weekday):
        self.expression = expression
        self.minutes = minute[0]
        self.hours = hour[0]
        self.days, dom_restricted = day
        self.months = month[0]
        self.weekdays, dow_restricted = weekday
        self.dom_any = not dom_restricted
        self.dow_any = not dow_restricted

    def __repr__(self):
        return f"CronEntry({self.expression!r})"

    def matches(self, moment):
        """Does this wall-clock minute fire?"""
        return (
            moment.minute in self.minutes
            and moment.hour in self.hours
            and moment.month in self.months
            and self._day_matches(moment)
        )

    def _day_matches(self, moment):
        # cron counts Sunday as 0, python counts Monday as 0
        weekday = (moment.weekday() + 1) % 7
        by_month_day = moment.day in self.days
        by_weekday = weekday in self.weekdays
        if not self.dom_any and not self.dow_any:
            # Cron's one oddity: with both fields set it fires on either
            return by_month_day or by_weekday
        return by_month_day and by_weekday

    def next_run(self, after):
        """First matching wall-clock minute strictly after `after`."""
        moment = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = moment + timedelta(days=_SEARCH_DAYS)
        while moment <= limit:
            if moment.month not in self.months:
                moment = _first_of_next_month(moment)
                continue
            if not self._day_matches(moment):
                moment = (moment + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if moment.hour not in self.hours:
                moment = (moment + timedelta(hours=1)).replace(minute=0)
                continue
            if moment.minute not in self.minutes:
                moment += timedelta(minutes=1)
                continue
            return moment
        return None

    @property
    def every_day(self):
        return self.dom_any and self.dow_any and len(self.months) == 12

    @property
    def is_plain(self):
        """Days and times only, the shape that reads back as a sentence."""
        return (
            self.dom_any
            and len(self.months) == 12
            and len(self.hours) * len(self.minutes) <= 8
        )


def _first_of_next_month(moment):
    start = moment.replace(day=1, hour=0, minute=0)
    return (start + timedelta(days=32)).replace(day=1)


def parse_entry(text):
    """One cron line into a CronEntry."""
    fields = text.split()
    if len(fields) != 5:
        raise ScheduleError(
            f'"{text}" is not a cron expression, expected 5 fields '
            "(minute hour day month weekday)"
        )
    parsed = [_parse_field(field, index) for index, field in enumerate(fields)]
    return CronEntry(" ".join(fields), *parsed)


class Schedule:
    """One or more cron lines. The next run is the first one any of them hits."""

    __slots__ = ("entries",)

    def __init__(self, entries):
        entries = tuple(entries)
        if not entries:
            raise ScheduleError("The schedule is empty")
        self.entries = entries

    def __repr__(self):
        return f"Schedule({self.expression!r})"

    @property
    def expression(self):
        return "; ".join(entry.expression for entry in self.entries)

    def matches(self, moment):
        return any(entry.matches(moment) for entry in self.entries)

    def next_run(self, after):
        upcoming = [entry.next_run(after) for entry in self.entries]
        upcoming = [moment for moment in upcoming if moment is not None]
        return min(upcoming) if upcoming else None

    def describe(self, language="en"):
        """One readable line for the UI, or the raw expression when it is exotic."""
        words = _WORDS.get(language) or _WORDS["en"]

        if len(self.entries) == 1 and self.entries[0].every_day:
            repeat = _repeat_phrase(self.entries[0], words)
            if repeat:
                return _capitalise(repeat)

        if not all(entry.is_plain for entry in self.entries):
            return self.expression

        # Lines that share their days are one clause, "at 08:00 and 22:30",
        # lines that do not get a clause each
        grouped = {}
        for entry in self.entries:
            days = None if entry.dow_any else frozenset(entry.weekdays)
            grouped.setdefault(days, set()).update(
                (hour, minute) for hour in entry.hours for minute in entry.minutes
            )

        clauses = []
        for days, times in grouped.items():
            if len(times) > 8:
                return self.expression
            listed = _join(
                [f"{hour:02d}:{minute:02d}" for hour, minute in sorted(times)], words
            )
            clauses.append(f"{_days_phrase(days, words)} {words['at']} {listed}")
        return _capitalise(_join(clauses, words))


# ---------------------------------------------------------------------------
# Plain language
# ---------------------------------------------------------------------------
_FILLER = {
    "every",
    "each",
    "on",
    "the",
    "run",
    "runs",
    "sync",
    "jeden",
    "jede",
    "jedes",
    "alle",
    "uhr",
    "o'clock",
}
_EVERY_DAY = {"day", "days", "daily", "everyday", "tag", "tage", "täglich", "taeglich"}
_DAY_GROUPS = {
    "weekday": {1, 2, 3, 4, 5},
    "weekdays": {1, 2, 3, 4, 5},
    "wochentag": {1, 2, 3, 4, 5},
    "wochentags": {1, 2, 3, 4, 5},
    "werktags": {1, 2, 3, 4, 5},
    "weekend": {0, 6},
    "weekends": {0, 6},
    "wochenende": {0, 6},
}
_NOON = {"noon", "midday", "mittag"}
_MIDNIGHT = {"midnight", "mitternacht"}

_SPLIT_AT = re.compile(r"\s*(?:\bat\b|\bum\b|@)\s*")
_TIME_RE = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?(am|pm|uhr)?")
_STEP_RE = re.compile(r"(\d+)(minutes?|mins?|m|hours?|hrs?|h|days?|d)")


def parse(text):
    """A Schedule from cron lines, from plain language, or from a mix of both.

    Lines are separated by ";" and each one is read on its own, so
    "0 8 * * 1; every friday at 10pm" is as good as either form alone.
    """
    if not isinstance(text, str):
        raise ScheduleError(f"Invalid schedule: {text!r}")
    cleaned = _unquoted(text)
    if not cleaned:
        raise ScheduleError("The schedule cannot be empty")

    entries = []
    for line in re.split(r"[;\n]+", cleaned):
        line = line.strip()
        if line:
            entries.extend(_parse_line(line).entries)
    if not entries:
        raise ScheduleError("The schedule cannot be empty")
    return Schedule(entries)


def _parse_line(line):
    """One line, cron first because it is the stricter of the two readings."""
    try:
        return Schedule([parse_entry(line)])
    except ScheduleError as cron_error:
        try:
            return _parse_phrase(line)
        except ScheduleError as phrase_error:
            # Five fields starting with a digit was meant as cron, so say what
            # was wrong with it rather than complaining about weekday names
            meant_as_cron = len(line.split()) == 5 and line[:1] in ("*", *"0123456789")
            raise (cron_error if meant_as_cron else phrase_error) from None


def _parse_phrase(text):
    cleaned = text.lower().strip().rstrip(".")
    cleaned = cleaned.replace("&", ",")
    cleaned = re.sub(r"\b(?:and|und)\b", ",", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    parts = _SPLIT_AT.split(cleaned, maxsplit=1)
    day_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else ""

    tokens = [
        token
        for token in re.split(r"[,\s]+", day_part)
        if token and token not in _FILLER
    ]

    step = _STEP_RE.fullmatch("".join(tokens)) if tokens else None
    if step:
        return _step_schedule(int(step.group(1)), step.group(2), time_part)

    # "at" is optional: "monday 22:00" and a bare "22:00" have to work too
    times = [token for token in tokens if _looks_like_time(token)]
    if time_part:
        times.append(time_part)

    weekdays = _parse_days([t for t in tokens if not _looks_like_time(t)])
    return _build(weekdays, _parse_times(",".join(times)))


def _looks_like_time(token):
    token = token.strip(",.")
    return token in _NOON or token in _MIDNIGHT or bool(_TIME_RE.fullmatch(token))


def _step_schedule(amount, unit, time_part):
    """The one repeating phrase cron can express: "every 6 hours" and friends."""
    if time_part:
        raise ScheduleError(f'"every {amount} {unit}" cannot be combined with a time')
    if unit.startswith("d"):
        raise ScheduleError(
            f'Use the interval instead of "every {amount} days" for fixed times'
        )
    if amount < 1:
        raise ScheduleError("A repeat has to be at least 1")
    if unit.startswith("m"):
        if amount > 59:
            raise ScheduleError("Minutes only repeat up to 59")
        return Schedule([parse_entry(f"*/{amount} * * * *")])
    if amount > 23:
        raise ScheduleError("Hours only repeat up to 23")
    return Schedule([parse_entry(f"0 */{amount} * * *")])


def _parse_days(tokens):
    """The weekday numbers a phrase names, or None for every day."""
    days = set()
    for token in tokens:
        token = token.strip(",.")
        if not token or token in _EVERY_DAY:
            continue
        group = _DAY_GROUPS.get(token)
        if group:
            days |= group
            continue
        if "-" in token:
            first, _, last = token.partition("-")
            days |= _weekday_range(first, last)
            continue
        day = _WEEKDAYS.get(token)
        if day is None:
            raise ScheduleError(f'"{token}" is not a day of the week')
        days.add(day)
    return days or None


def _weekday_range(first, last):
    start = _WEEKDAYS.get(first)
    end = _WEEKDAYS.get(last)
    if start is None or end is None:
        raise ScheduleError(f'"{first}-{last}" is not a range of weekdays')
    if start <= end:
        return set(range(start, end + 1))
    return set(range(start, 7)) | set(range(end + 1))


def _parse_times(text):
    """[(hour, minute)] from "10pm", "08:00, 20:00" or "" (which means midnight)."""
    text = text.strip()
    if not text:
        return [(0, 0)]

    times = []
    for chunk in re.split(r"[,;]+", text):
        chunk = chunk.strip().replace(" ", "")
        if not chunk:
            continue
        if chunk in _MIDNIGHT:
            times.append((0, 0))
            continue
        if chunk in _NOON:
            times.append((12, 0))
            continue

        match = _TIME_RE.fullmatch(chunk)
        if not match:
            raise ScheduleError(f'"{chunk}" is not a time')
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        suffix = match.group(3)

        if suffix in ("am", "pm"):
            if not 1 <= hour <= 12:
                raise ScheduleError(
                    f'"{chunk}" is not a time, {suffix} runs from 1 to 12'
                )
            if suffix == "am" and hour == 12:
                hour = 0
            elif suffix == "pm" and hour != 12:
                hour += 12
        if hour > 23 or minute > 59:
            raise ScheduleError(f'"{chunk}" is not a time')
        times.append((hour, minute))

    if not times:
        raise ScheduleError("No time given")
    return times


def _build(weekdays, times):
    """Days plus times into cron lines, one line per distinct minute."""
    day_field = "*" if weekdays is None else ",".join(str(d) for d in sorted(weekdays))

    by_minute = {}
    for hour, minute in sorted(set(times)):
        by_minute.setdefault(minute, []).append(hour)

    return Schedule(
        parse_entry(f"{minute} {','.join(str(hour) for hour in hours)} * * {day_field}")
        for minute, hours in sorted(by_minute.items())
    )


# ---------------------------------------------------------------------------
# Describing a schedule
# ---------------------------------------------------------------------------
_WORDS = {
    "en": {
        "at": "at",
        "and": "and",
        "every_day": "every day",
        "weekdays": "on weekdays",
        "weekends": "at the weekend",
        "days_prefix": "on ",
        "every_hour": "every hour",
        "every_hours": "every {count} hours",
        "every_minutes": "every {count} minutes",
        "every_days": "every {count} days",
        "past": "{minute} past every hour",
        "names": (
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
        ),
    },
    "de": {
        "at": "um",
        "and": "und",
        "every_day": "jeden Tag",
        "weekdays": "wochentags",
        "weekends": "am Wochenende",
        "days_prefix": "jeden ",
        "every_hour": "jede Stunde",
        "every_hours": "alle {count} Stunden",
        "every_minutes": "alle {count} Minuten",
        "every_days": "alle {count} Tage",
        "past": "{minute} nach jeder vollen Stunde",
        "names": (
            "Sonntag",
            "Montag",
            "Dienstag",
            "Mittwoch",
            "Donnerstag",
            "Freitag",
            "Samstag",
        ),
    },
}


def describe_interval(seconds, language="en"):
    """Interval mode in words, e.g. "Every 6 hours"."""
    words = _WORDS.get(language) or _WORDS["en"]
    seconds = int(seconds)
    if seconds % 86400 == 0:
        days = seconds // 86400
        phrase = (
            words["every_day"] if days == 1 else words["every_days"].format(count=days)
        )
    elif seconds % 3600 == 0:
        hours = seconds // 3600
        phrase = (
            words["every_hour"]
            if hours == 1
            else words["every_hours"].format(count=hours)
        )
    else:
        phrase = words["every_minutes"].format(count=max(1, seconds // 60))
    return _capitalise(phrase)


def _repeat_phrase(entry, words):
    """ "every 6 hours" style, when the cron line is really a repeat."""
    hourly = len(entry.hours) == 24
    if hourly and len(entry.minutes) == 1:
        minute = next(iter(entry.minutes))
        if minute == 0:
            return words["every_hour"]
        return words["past"].format(minute=f":{minute:02d}")
    if hourly:
        step = _even_step(entry.minutes, 60)
        return words["every_minutes"].format(count=step) if step else None
    if entry.minutes == {0}:
        step = _even_step(entry.hours, 24)
        return words["every_hours"].format(count=step) if step else None
    return None


def _even_step(values, span):
    """The step of an evenly spaced field starting at 0, or None."""
    ordered = sorted(values)
    if len(ordered) < 2 or ordered[0] != 0:
        return None
    step = ordered[1]
    if span % step or list(range(0, span, step)) != ordered:
        return None
    return step


def _days_phrase(days, words):
    if days is None:
        return words["every_day"]
    if days == {1, 2, 3, 4, 5}:
        return words["weekdays"]
    if days == {0, 6}:
        return words["weekends"]
    # Monday first, the way a week is read
    names = [words["names"][day] for day in sorted(days, key=lambda day: (day + 6) % 7)]
    return words["days_prefix"] + _join(names, words)


def _join(items, words):
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} {words['and']} {items[-1]}"


def _capitalise(text):
    return text[:1].upper() + text[1:]
