"""The conditions bot's coexistence boundaries with the weather forecaster.

WHY THIS EXISTS. Both bots post to the same Facebook page. On 2026-10-10 the
conditions card said "63°F now, headed to a high of 59°": a current temperature
above the day's high, while the forecaster that morning had Durango into the
mid-60s. One page, two stories. The rule that came out of it:

  * this bot is OBSERVATION ONLY, it states what is true right now and no
    forward-looking number (highs, tomorrow, anything predictive belong to the
    forecaster); short_forecast stays because it describes the sky;
  * it posts in the afternoon only, so its window never overlaps the
    forecaster's 04:00-09:00 window;
  * it has its own on/off switch, CONDITIONS_BOT_ENABLED, where ABSENT MEANS
    ENABLED, and a disabled run must not file missed-slot reports;
  * the caption it published is persisted, because nothing in the repo held the
    words it published and so nothing could review them.

These tests cover what is new. The morning-slot tests were retargeted, not
deleted, in test_daily_post_window.py and test_post_miss.py.
"""
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import generate_post_text as G  # noqa: E402
import main as M  # noqa: E402
import post_history as PH  # noqa: E402

# The 2026-10-10 conditions, verbatim from the incident.
INCIDENT = {"weather": {"current_f": 63, "high_f": 59, "short_forecast": "Mostly cloudy"},
            "streamflow": None, "lake_level": None, "fire": None}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "DAILY_POST_STATE_PATH", str(tmp_path / "daily_post_state.json"))
    monkeypatch.setattr(PH, "HISTORY_PATH", str(tmp_path / "post_history.json"))
    return tmp_path


def _weather_row(post):
    return next(r for r in post["card_data"]["rows"] if r["label"] == "WEATHER")


def test_caption_and_card_state_no_forecast_high(isolated):
    post = G.build_post(INCIDENT, "afternoon", dt=datetime(2026, 10, 10, 14, 30),
                        image_dest_path=str(isolated / "i.jpg"))
    row = _weather_row(post)
    assert "63°F now. Mostly cloudy." in post["caption"]
    assert row["value"] == "63°F now, mostly cloudy"
    for text in (post["caption"], row["value"]):
        assert "59" not in text
        assert "headed to" not in text
        assert "high" not in text.lower()


def test_alert_post_states_no_forecast_high():
    alert = {"id": "urn:x", "category": "flood", "headline": "Flash Flood Warning",
             "description": "Heavy rain", "source_name": "NWS"}
    post = G.build_alert_post(INCIDENT, alert, dt=datetime(2026, 10, 10, 14, 30))
    row = _weather_row(post)
    assert row["value"] == "63°F now"
    assert "59" not in post["caption"] and "high" not in post["caption"].lower()


def test_enabled_when_the_variable_is_absent(monkeypatch):
    monkeypatch.delenv("CONDITIONS_BOT_ENABLED", raising=False)
    assert M.enabled() is True


@pytest.mark.parametrize("raw", ["false", "FALSE", "False", "  false  ", "\tfAlSe\n"])
def test_only_the_literal_false_switches_it_off(monkeypatch, raw):
    monkeypatch.setenv("CONDITIONS_BOT_ENABLED", raw)
    assert M.enabled() is False


@pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "", "   ", "no", "0", "off", "falsey"])
def test_anything_else_leaves_it_on(monkeypatch, raw):
    monkeypatch.setenv("CONDITIONS_BOT_ENABLED", raw)
    assert M.enabled() is True


def test_a_disabled_run_files_no_missed_slot(monkeypatch):
    monkeypatch.setenv("CONDITIONS_BOT_ENABLED", "false")
    calls = []
    monkeypatch.setattr(M.post_miss, "report_if_needed", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(M, "determine_slot", lambda *a, **k: calls.append("slot"))
    assert M.main() == 0
    assert calls == []


def test_record_post_writes_the_caption(isolated):
    PH.record_post("123_456", datetime(2026, 10, 10, 14, 30, tzinfo=ZoneInfo("America/Denver")).isoformat(),
                   "afternoon", {"hook_line": "h"}, caption="63°F now. Mostly cloudy.")
    entry = json.load(open(PH.HISTORY_PATH))["posts"][-1]
    assert entry["caption"] == "63°F now. Mostly cloudy."


def test_record_post_writes_an_explicit_none_without_a_caption(isolated):
    PH.record_post("123_457", "2026-10-10T14:30:00-06:00", "afternoon", {"hook_line": "h"})
    entry = json.load(open(PH.HISTORY_PATH))["posts"][-1]
    assert "caption" in entry and entry["caption"] is None
