"""Turning "every monday at 10pm" into the next time Auto-Sync should run.

Nothing here reads the clock: every "now" is handed in, so a run at 23:59 on a
Sunday behaves like every other run.
"""

from datetime import datetime

import pytest

from aniworld.web import schedule
from aniworld.web.schedule import ScheduleError

# A Friday afternoon, the moment every "next run" below is measured from
FRIDAY = datetime(2026, 8, 21, 15, 30)


# ---------------------------------------------------------------------------
# Intervals
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "written,seconds",
    [
        ("24h", 86400),
        ("6h", 21600),
        ("90m", 5400),
        ("1h30m", 5400),
        ("2d", 172800),
        ("1w", 604800),
        ("300s", 300),
        ("  12H  ", 43200),
        (6, 21600),
        ("6", 21600),
        (1.5, 5400),
    ],
)
def test_an_interval_can_be_written_in_several_ways(written, seconds):
    assert schedule.parse_interval(written) == seconds


def test_a_bare_number_means_hours():
    """The unit Auto-Sync was pinned to before the schedule was configurable."""
    assert schedule.parse_interval("24") == 86400


@pytest.mark.parametrize("bad", ["", "   ", "abc", "4h5", "2y", "-3h", True, None])
def test_nonsense_is_not_an_interval(bad):
    with pytest.raises(ScheduleError):
        schedule.parse_interval(bad)


def test_an_interval_has_a_floor():
    """Hammering aniworld.to every ten seconds helps nobody."""
    with pytest.raises(ScheduleError, match="at least"):
        schedule.parse_interval("10s")


def test_an_interval_has_a_ceiling():
    with pytest.raises(ScheduleError, match="longer than a year"):
        schedule.parse_interval("400d")


@pytest.mark.parametrize(
    "seconds,written", [(86400, "24h"), (5400, "90m"), (300, "5m"), (90, "90s")]
)
def test_an_interval_is_written_back_out_shortest_first(seconds, written):
    assert schedule.format_interval(seconds) == written


def test_an_interval_round_trips():
    for written in ("24h", "90m", "6h", "5m"):
        assert schedule.format_interval(schedule.parse_interval(written)) == written


# ---------------------------------------------------------------------------
# Cron expressions
# ---------------------------------------------------------------------------
def test_a_cron_expression_is_kept_as_written():
    assert schedule.parse("0 22 * * 1").expression == "0 22 * * 1"


def test_the_fields_are_read_apart():
    entry = schedule.parse("30 8,20 * * 1,5").entries[0]
    assert entry.minutes == {30}
    assert entry.hours == {8, 20}
    assert entry.weekdays == {1, 5}
    assert entry.dom_any is True


@pytest.mark.parametrize(
    "expression,hours",
    [
        ("0 */6 * * *", {0, 6, 12, 18}),
        ("0 8-11 * * *", {8, 9, 10, 11}),
        ("0 8-16/4 * * *", {8, 12, 16}),
        ("0 22-2 * * *", {22, 23, 0, 1, 2}),
    ],
)
def test_steps_and_ranges(expression, hours):
    assert schedule.parse(expression).entries[0].hours == hours


def test_sunday_is_both_zero_and_seven():
    assert schedule.parse("0 0 * * 7").entries[0].weekdays == {0}
    assert schedule.parse("0 0 * * 0").entries[0].weekdays == {0}


def test_names_work_in_place_of_numbers():
    entry = schedule.parse("0 0 * * mon-fri").entries[0]
    assert entry.weekdays == {1, 2, 3, 4, 5}
    assert schedule.parse("0 0 1 jan *").entries[0].months == {1}


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "22 * * *", "0 99 * * *", "60 0 * * *", "0 0 * * 9", "0 0 * * blah"],
)
def test_a_broken_expression_is_rejected(bad):
    with pytest.raises(ScheduleError):
        schedule.parse(bad)


@pytest.mark.parametrize(
    "quoted",
    ['"0 22 * * 1"', "'0 22 * * 1'", '  "0 22 * * 1" ', '"every monday at 10pm"'],
)
def test_quotes_around_a_schedule_are_taken_off(quoted):
    """A .env quotes values with spaces, and `docker --env-file` keeps them."""
    assert schedule.parse(quoted).expression == "0 22 * * 1"


def test_quotes_around_an_interval_are_taken_off():
    assert schedule.parse_interval('"90m"') == 5400


@pytest.mark.parametrize("bad", ['""', "''", '"   "'])
def test_nothing_but_quotes_is_still_empty(bad):
    with pytest.raises(ScheduleError, match="empty"):
        schedule.parse(bad)


def test_bare_numbers_are_read_as_hours():
    """A number on its own is a time here, the same way "at 8" is."""
    assert schedule.parse("8, 20").expression == "0 8,20 * * *"


def test_the_error_says_which_field_broke():
    with pytest.raises(ScheduleError, match="hour"):
        schedule.parse("0 99 * * *")


# ---------------------------------------------------------------------------
# Plain language
#
# What the settings page sends, and what anyone typing into the field expects
# to work.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "phrase,expression",
    [
        ("every day at 10:00pm", "0 22 * * *"),
        ("every day at 10pm", "0 22 * * *"),
        ("every monday at 10pm", "0 22 * * 1"),
        ("every monday, tuesday", "0 0 * * 1,2"),
        ("every monday and friday at 8am", "0 8 * * 1,5"),
        ("weekdays at 07:30", "30 7 * * 1,2,3,4,5"),
        ("weekends at noon", "0 12 * * 0,6"),
        ("mon-fri at 6", "0 6 * * 1,2,3,4,5"),
        ("every 6 hours", "0 */6 * * *"),
        ("every 30 minutes", "*/30 * * * *"),
        ("22:00", "0 22 * * *"),
        ("monday 22:00", "0 22 * * 1"),
        ("sat,sun at midnight", "0 0 * * 0,6"),
        ("jeden montag um 22 uhr", "0 22 * * 1"),
        ("täglich um 20:00", "0 20 * * *"),
    ],
)
def test_a_phrase_becomes_cron(phrase, expression):
    assert schedule.parse(phrase).expression == expression


def test_am_and_pm_are_read_the_way_a_clock_face_is():
    assert schedule.parse("at 12am").expression == "0 0 * * *"
    assert schedule.parse("at 12pm").expression == "0 12 * * *"
    assert schedule.parse("at 1am").expression == "0 1 * * *"


def test_times_that_share_a_minute_stay_on_one_line():
    assert schedule.parse("every day at 08:00, 20:00").expression == "0 8,20 * * *"


def test_times_that_do_not_share_a_minute_get_a_line_each():
    """Cron would cross-multiply them into four runs on a single line."""
    parsed = schedule.parse("every day at 08:00, 22:30")
    assert parsed.expression == "0 8 * * *; 30 22 * * *"
    assert len(parsed.entries) == 2


def test_the_days_carry_over_to_every_line():
    parsed = schedule.parse("monday at 08:00, 22:30")
    assert parsed.expression == "0 8 * * 1; 30 22 * * 1"


# ---------------------------------------------------------------------------
# Several lines at once
# ---------------------------------------------------------------------------
def test_phrases_can_be_separated_by_semicolons_too():
    """Not just cron: the hint under the field promises this for both forms."""
    parsed = schedule.parse("every tue,thu,fri at 03:40; every tue at 03:40")
    assert parsed.expression == "40 3 * * 2,4,5; 40 3 * * 2"


def test_cron_and_plain_language_can_be_mixed():
    parsed = schedule.parse("0 8 * * 1; every friday at 10pm")
    assert parsed.expression == "0 8 * * 1; 0 22 * * 5"


def test_a_newline_separates_lines_as_well():
    parsed = schedule.parse("every day at 08:00\nevery monday at 22:30")
    assert parsed.expression == "0 8 * * *; 30 22 * * 1"


def test_one_broken_line_rejects_the_whole_schedule():
    with pytest.raises(ScheduleError, match="nope"):
        schedule.parse("every tue at 03:40; nope")


def test_a_broken_cron_line_still_reports_the_cron_problem():
    with pytest.raises(ScheduleError, match="hour"):
        schedule.parse("0 8 * * 1; 0 99 * * *")


def test_a_day_on_its_own_runs_at_midnight():
    assert schedule.parse("every sunday").expression == "0 0 * * 0"


@pytest.mark.parametrize(
    "bad",
    [
        "every blursday",
        "at 25:00",
        "monday at 10:75",
        "nonsense at 10pm",
        "at 13pm",
    ],
)
def test_a_phrase_that_makes_no_sense_is_rejected(bad):
    with pytest.raises(ScheduleError):
        schedule.parse(bad)


def test_a_repeat_in_days_points_at_the_interval_instead():
    with pytest.raises(ScheduleError, match="interval"):
        schedule.parse("every 2 days")


def test_a_broken_cron_expression_reports_the_cron_problem():
    """Five fields starting with a number is a cron attempt, not a sentence."""
    with pytest.raises(ScheduleError, match="minute"):
        schedule.parse("99 0 * * *")


# ---------------------------------------------------------------------------
# When it fires next
# ---------------------------------------------------------------------------
def test_the_next_run_is_the_next_matching_minute():
    assert schedule.parse("0 22 * * *").next_run(FRIDAY) == datetime(2026, 8, 21, 22, 0)


def test_a_time_that_passed_today_lands_tomorrow():
    assert schedule.parse("0 8 * * *").next_run(FRIDAY) == datetime(2026, 8, 22, 8, 0)


def test_a_weekday_schedule_waits_for_that_day():
    assert schedule.parse("0 22 * * 1").next_run(FRIDAY) == datetime(2026, 8, 24, 22, 0)


def test_the_current_minute_does_not_count_again():
    """Otherwise a run would fire in a loop for the whole minute it started in."""
    at_ten = datetime(2026, 8, 21, 22, 0)
    assert schedule.parse("0 22 * * *").next_run(at_ten) == datetime(2026, 8, 22, 22, 0)


def test_the_earliest_of_several_lines_wins():
    parsed = schedule.parse("every day at 08:00, 22:30")
    assert parsed.next_run(FRIDAY) == datetime(2026, 8, 21, 22, 30)
    assert parsed.next_run(datetime(2026, 8, 21, 23, 0)) == datetime(2026, 8, 22, 8, 0)


def test_a_sparse_schedule_is_still_found():
    """29 February is four years out and must not fall off the search."""
    assert schedule.parse("0 0 29 2 *").next_run(datetime(2026, 3, 1)) == datetime(
        2028, 2, 29, 0, 0
    )


def test_a_day_of_the_month_and_a_weekday_both_fire():
    """Cron's one oddity: with both set it is an or, not an and."""
    parsed = schedule.parse("0 0 13 * 5")
    assert parsed.next_run(datetime(2026, 8, 21, 0, 1)) == datetime(2026, 8, 28, 0, 0)
    assert parsed.matches(datetime(2026, 9, 13, 0, 0)), "the 13th, a Sunday"


def test_matches_only_says_yes_on_the_minute():
    parsed = schedule.parse("30 22 * * *")
    assert parsed.matches(datetime(2026, 8, 21, 22, 30))
    assert not parsed.matches(datetime(2026, 8, 21, 22, 31))


# ---------------------------------------------------------------------------
# Saying it back to the user
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "expression,described",
    [
        ("0 22 * * *", "Every day at 22:00"),
        ("0 22 * * 1", "On Monday at 22:00"),
        ("0 22 * * 1,2", "On Monday and Tuesday at 22:00"),
        ("0 8 * * 1,2,3,4,5", "On weekdays at 08:00"),
        ("0 12 * * 0,6", "At the weekend at 12:00"),
        ("0 8,20 * * *", "Every day at 08:00 and 20:00"),
        ("0 8 * * *; 30 22 * * *", "Every day at 08:00 and 22:30"),
        ("0 */6 * * *", "Every 6 hours"),
        ("*/30 * * * *", "Every 30 minutes"),
        ("0 * * * *", "Every hour"),
    ],
)
def test_a_schedule_reads_as_a_sentence(expression, described):
    assert schedule.parse(expression).describe() == described


def test_a_schedule_can_be_read_in_german():
    assert schedule.parse("0 22 * * 1").describe("de") == "Jeden Montag um 22:00"
    assert schedule.parse("0 */6 * * *").describe("de") == "Alle 6 Stunden"


def test_an_unknown_language_falls_back_to_english():
    assert schedule.parse("0 22 * * *").describe("klingon") == "Every day at 22:00"


def test_lines_with_different_days_each_get_their_own_clause():
    """They used to fall back to the raw expression, which reads as noise."""
    assert schedule.parse("0 3 * * 3;0 4 * * 2").describe() == (
        "On Wednesday at 03:00 and on Tuesday at 04:00"
    )


def test_three_clauses_read_as_a_list():
    assert schedule.parse("0 8 * * 1; 0 22 * * 5; 0 12 * * 0").describe() == (
        "On Monday at 08:00, on Friday at 22:00 and on Sunday at 12:00"
    )


def test_clauses_are_read_in_german_too():
    assert schedule.parse("0 3 * * 3; 0 4 * * 2").describe("de") == (
        "Jeden Mittwoch um 03:00 und jeden Dienstag um 04:00"
    )


def test_an_expression_too_exotic_to_read_is_shown_as_it_is():
    assert schedule.parse("15 14 1 * *").describe() == "15 14 1 * *"


@pytest.mark.parametrize(
    "seconds,described",
    [
        (86400, "Every day"),
        (21600, "Every 6 hours"),
        (3600, "Every hour"),
        (5400, "Every 90 minutes"),
        (172800, "Every 2 days"),
    ],
)
def test_an_interval_reads_as_a_sentence(seconds, described):
    assert schedule.describe_interval(seconds) == described
