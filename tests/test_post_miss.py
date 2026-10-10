"""
The missed-post alarm: a slot that closes with no daily post opens ONE issue.

Background: 47 of 64 slots vanished between 2026-08-26 and 2026-09-26 with every workflow green.
"""
import json
import os
import sys
import urllib.error
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import main as M  # noqa: E402
import post_miss as PM  # noqa: E402
import generate_post_text as G  # noqa: E402

DEN = ZoneInfo("America/Denver")


def at(day, hour, minute=0):
    return datetime(2026, 9, day, hour, minute, tzinfo=DEN)


def posted(slot, when):
    return {"post_id": "x", "slot": slot, "post_type": "daily", "posted_at": when.astimezone(timezone.utc).isoformat()}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "DAILY_POST_STATE_PATH", str(tmp_path / "daily_post_state.json"))
    monkeypatch.delenv("DRY_RUN", raising=False)
    filed = []
    monkeypatch.setattr(PM, "_open_issue", lambda title, body: (filed.append((title, body)), {"notified": True})[1])
    return filed


def titles(filed):
    return [t for t, _ in filed]


def test_a_run_before_the_window_closes_reports_only_yesterday(env):
    PM.report_if_needed(at(25, 9, 39), M, {"posts": []})
    assert titles(env) == ["[miss] no afternoon conditions post for 2026-09-24"]


def test_a_run_after_the_afternoon_window_reports_the_afternoon(env):
    hist = {"posts": [posted("afternoon", at(24, 15))]}
    PM.report_if_needed(at(25, 19, 8), M, hist)
    assert titles(env) == ["[miss] no afternoon conditions post for 2026-09-25"]


def test_nothing_is_reported_when_the_slot_posted(env):
    hist = {"posts": [posted("afternoon", at(24, 15)), posted("afternoon", at(25, 15))]}
    PM.report_if_needed(at(25, 19), M, hist)
    assert env == []


def test_a_retired_morning_slot_is_never_reported(env):
    PM.report_if_needed(at(25, 19), M, {"posts": []})
    assert all("morning" not in t for t in titles(env))


def test_the_same_miss_is_never_filed_twice(env):
    hist = {"posts": []}
    PM.report_if_needed(at(25, 19, 8), M, hist)
    first = len(env)
    assert first == 2      # yesterday and today
    PM.report_if_needed(at(25, 22, 30), M, hist)
    PM.report_if_needed(at(26, 4, 0), M, hist)     # next day: yesterday is 25 now, 24 is no longer looked at
    assert titles(env)[first:] == []


def test_a_day_with_no_run_after_the_window_is_still_reported_by_the_next_day(env):
    # Sep 21: runs at 05:26 11:25 15:23 18:23 23:36 -- if the afternoon never posted, the 23:36 run reports it
    hist = {"posts": [posted("afternoon", at(20, 15))]}
    PM.report_if_needed(at(21, 23, 36), M, hist)
    assert titles(env) == ["[miss] no afternoon conditions post for 2026-09-21"]


def test_a_dry_run_is_silent(env, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    PM.report_if_needed(at(25, 19), M, {"posts": []})
    assert env == []


def test_an_emergency_alert_does_not_hide_a_missed_daily_post(env):
    alert = posted("afternoon", at(25, 15))
    alert["post_type"] = "emergency_alert"
    PM.report_if_needed(at(25, 19), M, {"posts": [alert, posted("afternoon", at(24, 15))]})
    assert titles(env) == ["[miss] no afternoon conditions post for 2026-09-25"]


def test_a_failed_notification_is_retried_by_the_next_run(env, monkeypatch):
    calls = []
    monkeypatch.setattr(PM, "_open_issue", lambda t, b: (calls.append(t), {"notified": False, "reason": "boom"})[1])
    PM.report_if_needed(at(25, 13), M, {"posts": []})
    n = len(calls)
    assert n > 0
    PM.report_if_needed(at(25, 14, 5), M, {"posts": []})
    assert len(calls) == 2 * n, "an issue that could not be filed must be tried again, not remembered as reported"


def test_the_alarm_never_raises_into_the_post_path(env, monkeypatch):
    monkeypatch.setattr(PM, "missed_slots", lambda *a, **k: 1 / 0)
    assert PM.report_if_needed(at(25, 13), M, {"posts": []}) == []


def test_the_body_says_where_to_look_and_lists_the_week(env):
    PM.report_if_needed(at(25, 19), M, {"posts": []})
    body = env[-1][1]
    assert "Actions tab" in body and "DRY_RUN" in body and "FB_PAGE_ACCESS_TOKEN" in body
    assert "missed slots in the last 7 days" in body


def test_open_issue_falls_back_to_unlabelled_on_422(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(PM.notify, "_open_issue_titled", lambda *a: None)
    sent = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"number": 7}'

    def fake_urlopen(req, timeout=0):
        body = json.loads(req.data.decode())
        sent.append(body)
        if "labels" in body:
            raise urllib.error.HTTPError(req.full_url, 422, "no label", {}, None)
        return Resp()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert PM._open_issue("t", "b") == {"notified": True, "issue": 7}
    assert "labels" in sent[0] and "labels" not in sent[1]


def test_an_open_issue_with_the_same_title_is_not_duplicated(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(PM.notify, "_open_issue_titled", lambda *a: {"number": 3})
    assert PM._open_issue("t", "b") == {"notified": True, "duplicate": True}
