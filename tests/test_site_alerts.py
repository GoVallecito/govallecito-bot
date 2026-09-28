"""Source (5): govallecito.com alert feed (LPC Alerts + stream gauges). Offline."""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import site_alerts  # noqa: E402
import generate_post_text  # noqa: E402

T0 = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)

EVAC = {"id": "lpc-aaa", "kind": "alert", "level": "danger", "receivedMs": 2,
        "subject": "GO NOW. EVACUATE NOW.",
        "body": "Residents along County Road 501 north of the dam must leave immediately.\nEvacuation center: Bayfield High School."}
CORR = {"id": "lpc-bbb", "kind": "correction", "level": "danger", "receivedMs": 3,
        "subject": "CORRECTED EMERGENCY ALERT", "body": "Disregard the previous alert. Evacuation applies to CR 501 only."}
CLEAR = {"id": "lpc-ccc", "kind": "clear", "level": "warn", "receivedMs": 4,
         "subject": "All clear", "body": "Evacuation orders have been lifted."}
ROAD = {"id": "lpc-ddd", "kind": "alert", "level": "warn", "receivedMs": 1,
        "subject": "Road closure", "body": "CR 240 closed at mile 12."}


def chip(cid, level="warn", text="x"):
    return {"id": cid, "level": level, "text": text, "href": "streamflow"}


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("SITE_ALERTS", raising=False)
    assert site_alerts.enabled() is False
    monkeypatch.setenv("SITE_ALERTS", "on")
    assert site_alerts.enabled() is True


def test_county_events_oldest_first_categories_and_wording():
    state = {}
    ev = site_alerts.county_events(state, {"active": [CLEAR, EVAC, ROAD, CORR]})
    assert [e["id"] for e in ev] == ["lpc-ddd", "lpc-aaa", "lpc-bbb", "lpc-ccc"]
    by = {e["id"]: e for e in ev}
    assert by["lpc-aaa"]["category"] == "evacuation"
    assert by["lpc-ddd"]["category"] == "disaster"
    assert by["lpc-aaa"]["hook"] == "La Plata County alert."     # never "... — Vallecito."
    assert by["lpc-bbb"]["row_label"] == "COUNTY CORRECTION"
    assert by["lpc-ccc"]["calm"] is True and by["lpc-aaa"]["calm"] is False
    assert "Bayfield High School" in by["lpc-aaa"]["full_text"]


def test_county_message_posts_once():
    state = {}
    feed = {"active": [EVAC]}
    [e] = site_alerts.county_events(state, feed)
    site_alerts.mark(state, e)
    assert site_alerts.county_events(state, feed) == []
    assert json.loads(json.dumps(state))["site_alerts"]["county_posted_ids"] == ["lpc-aaa"]


def test_admin_and_unknown_kinds_ignored():
    feed = {"active": [{"id": "x", "kind": "admin", "subject": "Registration"}, {"id": "y", "kind": "test"}, {"kind": "alert"}]}
    assert site_alerts.county_events({}, feed) == []


def test_stream_posts_only_on_escalation_and_resets_after_6h():
    state = {}
    run = lambda chips, t: site_alerts.stream_events(state, {"stream": chips}, now=t)

    [e] = run([chip("stream-creek-rise", text="Vallecito Creek rising fast: +415 cfs in 3 hrs")], T0)
    assert e["rank"] == 1 and e["hook"] == "Rising water at Vallecito."
    site_alerts.mark(state, e, now=T0)
    assert run([chip("stream-creek-rise")], T0 + timedelta(minutes=10)) == []          # same level: silent

    [e] = run([chip("stream-creek-flood", "danger", "Vallecito Creek at flood level: 3,050 cfs")], T0 + timedelta(hours=20))
    assert e["rank"] == 3 and e["hook"] == "Flood-level water at Vallecito."
    site_alerts.mark(state, e, now=T0 + timedelta(hours=20))
    assert run([chip("stream-creek-high")], T0 + timedelta(hours=30)) == []             # drop: silent
    assert run([chip("stream-creek-flood", "danger")], T0 + timedelta(hours=31)) == []  # back up: already posted

    # clears: the clock starts, and 6 quiet hours reset the level
    assert run([], T0 + timedelta(hours=40)) == []
    assert "cleared_at" in state["site_alerts"]["stream"]["creek"]
    assert run([], T0 + timedelta(hours=45)) == []
    assert "creek" in state["site_alerts"]["stream"]
    assert run([], T0 + timedelta(hours=46, minutes=1)) == []
    assert "creek" not in state["site_alerts"]["stream"]
    [e] = run([chip("stream-creek-rise")], T0 + timedelta(hours=50))                   # a NEW event posts again
    assert e["rank"] == 1


def test_stream_one_event_per_gauge_most_severe_wins():
    ev = site_alerts.stream_events({}, {"stream": [chip("stream-creek-high"), chip("stream-creek-flood", "danger"),
                                                   chip("stream-below-dam-minor", "danger"), chip("unknown-id")]}, now=T0)
    assert sorted((e["gauge"], e["rank"]) for e in ev) == [("below", 2), ("creek", 3)]


def test_fetch_failure_fails_closed():
    def boom(url):
        raise RuntimeError("down")
    assert site_alerts.fetch_feed(boom) is None
    assert site_alerts.fetch_feed(lambda url: ["not", "a", "dict"]) is None


def test_alert_post_uses_hook_full_text_and_calm_badge():
    [ev, clear] = site_alerts.county_events({}, {"active": [EVAC, CLEAR]})
    post = generate_post_text.build_alert_post({}, ev, dt=datetime(2026, 10, 11))
    cap = post["caption"]
    assert "La Plata County alert." in cap and "— Vallecito." not in cap
    assert "County Road 501 north of the dam" in cap and "Bayfield High School" in cap
    assert "Full details: https://govallecito.com/county-alert" in cap
    assert post["card_data"]["rows"][0]["label"] == "COUNTY ALERT"
    assert post["card_data"]["rows"][0]["badge"] == generate_post_text.DANGER
    calm = generate_post_text.build_alert_post({}, clear, dt=datetime(2026, 10, 11))
    assert calm["card_data"]["rows"][0]["badge"] == generate_post_text.INFO
    assert calm["card_data"]["rows"][0]["label"] == "COUNTY UPDATE"


def test_existing_nws_alert_post_unchanged():
    nws = {"id": "urn:x", "category": "flood", "headline": "Flash Flood Warning", "description": "Heavy rain", "source_name": "NWS"}
    post = generate_post_text.build_alert_post({}, nws, dt=datetime(2026, 10, 11))
    assert "Flood alert — Vallecito." in post["caption"]
    assert "Full details:" not in post["caption"]
    assert post["card_data"]["rows"][0]["label"] == "FLOOD ALERT"
    assert post["card_data"]["rows"][0]["badge"] == generate_post_text.DANGER
