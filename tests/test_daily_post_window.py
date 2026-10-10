"""
The daily conditions card posts inside a WINDOW, once per slot per day.

Why: GitHub fires only ~5-7 of the 24 hourly runs, at arbitrary minutes, so the old
"only if this run lands in the 7 o'clock or 14 o'clock hour" gate missed most slots
(17 of 64 posted between 2026-08-26 and 2026-09-26). These tests replay the real run
times of the days it failed.

The morning slot was later removed (its window overlapped the weather forecaster's
on the same page), so these replays were RETARGETED to the afternoon, not deleted:
a run that lands in morning hours is now correctly a no-op.
"""
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import main as M  # noqa: E402

DEN = ZoneInfo("America/Denver")


def at(day, hour, minute=0, month=9):
    return datetime(2026, month, day, hour, minute, tzinfo=DEN)


def posted(slot, when, post_type="daily"):
    """A post_history entry the way the Actions runner writes it: UTC."""
    return {"post_id": "x", "slot": slot, "post_type": post_type,
            "posted_at": when.astimezone(timezone.utc).isoformat()}


EMPTY = {"posts": []}


class TestWindows:
    def test_slot_hours(self):
        assert [M.slot_for_hour(h) for h in (6, 7, 10, 11, 13, 14, 17, 18)] == \
            [None, None, None, None, None, "afternoon", "afternoon", None]

    def test_morning_is_no_longer_a_slot(self):
        assert "morning" not in M.SLOT_WINDOWS
        assert "morning" not in M.SLOT_HOURS.values()

    def test_the_nominal_hours_are_inside_the_windows(self):
        for hour, slot in M.SLOT_HOURS.items():
            assert M.slot_for_hour(hour) == slot


class TestReplayOfTheDaysItFailed:
    """Real GitHub run times (Mountain) on days that produced no post at all."""

    def test_sep25_posts_the_afternoon(self):
        # runs landed at 04:48 09:39 13:41 16:57 19:08 -- none in the 14 o'clock hour
        hist = {"posts": []}
        assert M.determine_slot(at(25, 4, 48), hist) is None
        assert M.determine_slot(at(25, 9, 39), hist) is None        # morning hours: no slot any more
        assert M.determine_slot(at(25, 13, 41), hist) is None       # before the window
        assert M.determine_slot(at(25, 16, 57), hist) == "afternoon"
        hist["posts"].append(posted("afternoon", at(25, 16, 57)))
        assert M.determine_slot(at(25, 19, 8), hist) is None

    def test_sep21_has_only_a_late_morning_and_afternoon_run(self):
        # runs at 05:26 11:25 15:23 18:23 23:36: 11:25 is outside every window, the afternoon posts
        assert M.determine_slot(at(21, 11, 25), EMPTY) is None
        assert M.determine_slot(at(21, 15, 23), EMPTY) == "afternoon"

    def test_sep26_afternoon(self):
        # runs at 00:50 05:57 09:39 12:50 15:42 18:02
        assert M.determine_slot(at(26, 9, 39), EMPTY) is None
        assert M.determine_slot(at(26, 15, 42), EMPTY) == "afternoon"
        assert M.determine_slot(at(26, 18, 2), EMPTY) is None


class TestOncePerSlot:
    def test_a_second_run_in_the_same_window_does_not_post_again(self):
        hist = {"posts": [posted("afternoon", at(24, 14, 6))]}
        for hour, minute in ((14, 40), (15, 15), (17, 59)):
            assert M.determine_slot(at(24, hour, minute), hist) is None

    def test_a_stale_morning_entry_does_not_read_as_posted_today(self):
        # post_history.json holds 42 "morning" entries from before the slot was removed
        hist = {"posts": [posted("morning", at(24, 7, 6))]}
        assert M.determine_slot(at(24, 14, 30), hist) == "afternoon"

    def test_yesterdays_post_does_not_block_today(self):
        hist = {"posts": [posted("afternoon", at(23, 14, 6))]}
        assert M.determine_slot(at(24, 15, 0), hist) == "afternoon"

    def test_the_date_is_a_denver_date_not_a_utc_date(self):
        # An entry at 18:30 Denver on the 24th is 00:30 UTC on the 25th: the runner writes UTC, the date must be Denver's.
        late = posted("afternoon", at(24, 18, 30))
        assert late["posted_at"].startswith("2026-09-25T"), "sanity: UTC date has rolled over"
        assert M.slot_already_posted("afternoon", at(24, 17, 59), {"posts": [late]}) is True
        assert M.slot_already_posted("afternoon", at(25, 14, 5), {"posts": [late]}) is False

    def test_an_emergency_alert_never_counts_as_the_daily_post(self):
        hist = {"posts": [posted("afternoon", at(24, 14, 10), post_type="emergency_alert")]}
        assert M.determine_slot(at(24, 14, 30), hist) == "afternoon"

    def test_old_entries_without_post_type_count_as_daily(self):
        entry = posted("afternoon", at(24, 14, 6))
        del entry["post_type"]
        assert M.determine_slot(at(24, 15, 0), {"posts": [entry]}) is None

    def test_a_run_that_posted_nothing_leaves_the_slot_open_for_the_next_run(self):
        # a run that dies before posting records nothing, so the next run in the window retries
        assert M.determine_slot(at(24, 14, 5), EMPTY) == "afternoon"
        assert M.determine_slot(at(24, 16, 5), EMPTY) == "afternoon"

    def test_garbage_entries_are_ignored_not_fatal(self):
        hist = {"posts": [{"slot": "afternoon"}, {"slot": "afternoon", "posted_at": "not a date"}, {}, None]}
        assert M.determine_slot(at(24, 15, 0), hist) == "afternoon"


class TestForcedRuns:
    def test_force_slot_bypasses_the_clock_and_the_ledger(self, monkeypatch):
        monkeypatch.setenv("FORCE_SLOT", "afternoon")
        hist = {"posts": [posted("afternoon", at(24, 14, 6))]}
        assert M.determine_slot(at(24, 3, 0), hist) == "afternoon"

    def test_force_slot_morning_can_no_longer_post(self, monkeypatch):
        # the testing hatch must not put a morning-slot post on the page after the slot is gone
        monkeypatch.setenv("FORCE_SLOT", "morning")
        assert M.determine_slot(at(24, 8, 0), EMPTY) is None
