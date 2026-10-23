"""Incident mode: the upbeat conditions card pauses during a county emergency. Offline."""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import incident_mode as IM  # noqa: E402
import main as M  # noqa: E402
import post_miss as PM  # noqa: E402
import generate_post_text as G  # noqa: E402

DEN = ZoneInfo("America/Denver")
H = 3600 * 1000
NOW = 100 * H


def entry(kind="alert", level="danger", received=NOW - H, expires=None, **kw):
    return {"id": "x", "kind": kind, "level": level, "receivedMs": received, "expiresMs": expires,
            "subject": "Subject", **kw}


@pytest.mark.parametrize("feed, paused", [
    ({"active": [entry()]}, True),                                        # county danger alert
    ({"active": [entry(level="warn")]}, False),                           # warn alert alone: post
    ({"active": [entry(kind="correction")]}, False),
    ({"active": [entry(kind="clear", level="warn", received=NOW - H)]}, True),       # all-clear cooldown
    ({"active": [entry(kind="clear", level="warn", received=NOW - 2 * H - 1)]}, False),
    ({"active": [entry(expires=NOW - 1)]}, False),                        # expired danger alert
    ({"active": [], "stream": [{"id": "stream-creek-flood", "level": "danger", "text": "flood"}]}, True),
    ({"active": [], "stream": [{"id": "stream-creek-high", "level": "warn"}]}, False),
    ({"active": ["junk", None], "stream": [None]}, False),
    ({}, False),
    (None, False),
    (["not", "a", "dict"], False),
])
def test_incident_reason(feed, paused):
    assert bool(IM.incident_reason(feed, now_ms=NOW)) is paused


def test_fetch_failure_fails_open():
    def boom(url):
        raise RuntimeError("site down")
    assert IM.check(boom, now_ms=NOW) is None


def test_check_reads_the_site_alerts_feed():
    seen = []
    reason = IM.check(lambda url: (seen.append(url), {"active": [entry()]})[1], now_ms=NOW)
    assert reason and "danger" in reason
    assert seen == ["https://govallecito.com/data/lpc-alerts.json"]


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "DAILY_POST_STATE_PATH", str(tmp_path / "daily_post_state.json"))
    return tmp_path


def test_main_skips_the_card_during_an_incident_and_records_the_pause(state_file, monkeypatch):
    monkeypatch.delenv("CONDITIONS_BOT_ENABLED", raising=False)
    monkeypatch.setattr(M, "determine_slot", lambda now: "afternoon")
    monkeypatch.setattr(M.incident_mode, "check", lambda get_json: "active county danger alert: GO")
    monkeypatch.setattr(M.fetch_conditions, "fetch_all", lambda: pytest.fail("must not fetch or post"))
    assert M.main() == 0
    paused = G._load_daily_post_state()[M.PAUSE_STATE_KEY]
    assert list(paused.values()) == [["afternoon"]]


def test_main_posts_normally_when_quiet(state_file, monkeypatch):
    monkeypatch.delenv("CONDITIONS_BOT_ENABLED", raising=False)
    monkeypatch.setattr(M, "determine_slot", lambda now: "afternoon")
    monkeypatch.setattr(M.incident_mode, "check", lambda get_json: None)

    class Reached(Exception):
        pass

    def fetch_all():
        raise Reached
    monkeypatch.setattr(M.fetch_conditions, "fetch_all", fetch_all)
    with pytest.raises(Reached):
        M.main()


def test_conditions_bot_enabled_false_still_wins(monkeypatch):
    monkeypatch.setenv("CONDITIONS_BOT_ENABLED", "false")
    monkeypatch.setattr(M.incident_mode, "check", lambda get_json: pytest.fail("not consulted when off"))
    assert M.main() == 0


def test_a_paused_slot_is_not_reported_as_missed(state_file, monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    filed = []
    monkeypatch.setattr(PM, "_open_issue", lambda t, b: (filed.append(t), {"notified": True})[1])
    now = datetime(2026, 10, 22, 19, 0, tzinfo=DEN)        # afternoon window closed
    monkeypatch.setattr(M.incident_mode, "check", lambda get_json: "danger")
    assert M.incident_pause("afternoon", datetime(2026, 10, 22, 15, 0, tzinfo=DEN))
    PM.report_if_needed(now, M, history={"posts": []})
    assert "[miss] no afternoon conditions post for 2026-10-22" not in filed
    assert "[miss] no afternoon conditions post for 2026-10-21" in filed   # an unpaused day still reports
