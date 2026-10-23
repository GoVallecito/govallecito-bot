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
    assert e["rank"] == 3 and e["hook"] == "Very high water on Vallecito Creek."
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


def test_county_go_level_reposts_above_flood():
    run = lambda chips, now, st={}: site_alerts.stream_events(st, {"stream": chips}, now)
    st = {}
    [e] = site_alerts.stream_events(st, {"stream": [chip("stream-creek-flood", "danger")]}, T0)
    site_alerts.mark(st, e, T0)
    [g] = site_alerts.stream_events(st, {"stream": [chip("stream-creek-go", "danger")]}, T0 + timedelta(hours=1))
    assert g["rank"] == 4 and g["gauge"] == "creek"


def test_creek_post_has_no_hardcoded_incident_notice():
    """The Oct 22 notice (COUNTY_INCIDENT_*) was hand-written for one event; it is gone."""
    assert not any(n.startswith("COUNTY_INCIDENT") for n in dir(site_alerts))
    now = datetime(2026, 10, 23, 3, 0, tzinfo=timezone.utc)
    [e] = site_alerts.stream_events({}, {"stream": [chip("stream-creek-flood", "danger")]}, now)
    assert "lpcgov" not in e["full_text"] and "3,200" not in e["full_text"]
    assert e["source_url"] == "https://govallecito.com/streamflow"


def test_county_map_and_relay_entries_are_labelled_by_their_real_source():
    feed = {"active": [
        {"id": "zone-x", "kind": "alert", "source": "readylaplata", "subject": "PRE-EVACUATION, zones VAL-1 to VAL-4", "body": "b", "receivedMs": 2},
        {"id": "lpc-manual-x", "kind": "alert", "manual": True, "subject": "PRE-EVACUATION for North Vallecito", "body": "b", "receivedMs": 1},
        {"id": "lpc-abc", "kind": "alert", "subject": "EVACUATE NOW", "body": "b", "receivedMs": 3},
    ]}
    ev = {e["id"]: e for e in site_alerts.county_events({}, feed)}
    assert ev["zone-x"]["hook"] == "La Plata County evacuation map."
    assert "readylaplata.org" in ev["zone-x"]["source_url"]
    assert "relayed word for word" in ev["lpc-manual-x"]["source_name"]
    assert ev["lpc-abc"]["source_name"] == "La Plata County, LPC Alerts (reposted by GoVallecito)"


# ---- one post per ORDER (2026-10-23) -----------------------------------------
H = 60 * 60 * 1000
INC = "vallecito-creek-flooding"
MAP_SET = {"id": f"zone-{INC}-set-val-1-val-2-val-3-val-4", "kind": "alert", "level": "warn",
           "source": "readylaplata", "receivedMs": 10 * H,
           "subject": "PRE-EVACUATION (SET), zones VAL-1 to VAL-4", "body": "Be ready to leave."}
MAP_SET_5 = {**MAP_SET, "id": f"zone-{INC}-set-val-1-val-2-val-3-val-4-val-5", "receivedMs": 11 * H,
             "subject": "PRE-EVACUATION (SET), zones VAL-1 to VAL-5"}
MAP_GO = {**MAP_SET, "id": f"zone-{INC}-go-val-1-val-2", "level": "danger", "receivedMs": 12 * H,
          "subject": "EVACUATE NOW (GO), zones VAL-1 to VAL-2", "body": "Leave now."}
TEXT_SET = {"id": "relay-d723268d4e40f577", "kind": "alert", "level": "warn", "via": "text", "relayed": True,
            "receivedMs": 10 * H + 20 * 60 * 1000, "subject": "LPC Alert",
            "body": "Pre-evacuation for North Vallecito. Be ready to evacuate."}
MANUAL_SET = {"id": "lpc-manual-2026-10-22-preevac-north-vallecito", "kind": "alert", "level": "warn", "manual": True,
              "receivedMs": 9 * H + 30 * 60 * 1000, "subject": "PRE-EVACUATION for North Vallecito",
              "body": "Pre-evacuation order."}
MAP_CLEAR = {"id": f"zone-{INC}-clear-1792789115739", "kind": "clear", "level": "warn", "source": "readylaplata",
             "receivedMs": 20 * H, "subject": "Evacuation zones cleared", "body": "VAL-1 to VAL-5 cleared."}
TEXT_CLEAR = {"id": "relay-clear01", "kind": "clear", "level": "warn", "via": "text", "relayed": True,
              "receivedMs": 20 * H + 15 * 60 * 1000, "subject": "LPC Alert",
              "body": "All clear. Evacuation orders lifted."}


def _run(state, *entries, zones=None):
    """One emergency run: returns the posted ids, marking each as a successful post."""
    feed = {"active": list(entries)}
    if zones:
        feed["zones"] = {"groups": zones}
    evs = site_alerts.county_events(state, feed)
    for e in evs:
        site_alerts.mark(state, e)
    return [e["id"] for e in evs]


def test_order_key_parsing():
    k = site_alerts._map_order_key
    assert k(MAP_SET) == f"{INC}:set"
    assert k(MAP_GO) == f"{INC}:go"
    assert k(MAP_CLEAR) == f"{INC}:clear"
    assert k(TEXT_SET) is None and k(MANUAL_SET) is None
    # the feed's own incident names beat the regex when a slug contains a status word
    odd = {"id": "zone-durango-go-kart-fire-set-val-9"}
    assert k(odd) == "durango:go"
    assert k(odd, {"durango-go-kart-fire": {}}) == "durango-go-kart-fire:set"
    assert k({"id": "zone-something-unparseable"}) is None


def test_zones_groups_in_the_feed_are_used_for_the_key():
    st = {}
    odd = {**MAP_SET, "id": "zone-durango-go-kart-fire-set-val-9"}
    assert _run(st, odd, zones={"durango-go-kart-fire": {"status": "set"}}) == [odd["id"]]
    assert st["site_alerts"]["county_posted_orders"] == ["durango-go-kart-fire:set"]


def test_map_then_text_then_manual_is_one_post():
    st = {}
    assert _run(st, MAP_SET) == [MAP_SET["id"]]
    assert _run(st, MAP_SET, TEXT_SET) == []
    assert TEXT_SET["id"] in st["site_alerts"]["county_posted_ids"]
    assert st["site_alerts"]["county_posted_orders"] == [f"{INC}:set"]


def test_text_first_then_map_is_one_post():
    st = {}
    assert _run(st, MANUAL_SET) == [MANUAL_SET["id"]]
    assert _run(st, MANUAL_SET, MAP_SET) == []
    assert st["site_alerts"]["county_posted_orders"] == [f"{INC}:set"]
    assert _run(st, MANUAL_SET, MAP_SET, TEXT_SET) == []   # a second copy of the same order


def test_all_three_in_one_run_is_one_post():
    st = {}
    assert _run(st, MAP_SET, TEXT_SET, MANUAL_SET) == [MANUAL_SET["id"]]   # oldest posts, the rest ride along
    ss = st["site_alerts"]
    assert {MAP_SET["id"], TEXT_SET["id"]} <= set(ss["county_posted_ids"])
    assert ss["county_posted_orders"] == [f"{INC}:set"]
    assert _run(st, MAP_SET, TEXT_SET, MANUAL_SET, MAP_SET_5) == []


def test_zone_list_change_is_an_update_not_a_post():
    st = {}
    _run(st, MAP_SET)
    assert _run(st, MAP_SET_5) == []
    assert _run({}, MAP_SET, MAP_SET_5) == [MAP_SET["id"]]     # both new in one run: still one


def test_set_to_go_posts():
    st = {}
    _run(st, MAP_SET)
    assert _run(st, MAP_SET, MAP_GO) == [MAP_GO["id"]]
    assert st["site_alerts"]["county_posted_orders"] == [f"{INC}:go"]


def test_a_set_text_never_stands_in_for_a_later_go():
    st = {}
    _run(st, MANUAL_SET)
    _run(st, MANUAL_SET, MAP_SET)          # the text is now bound to the Set order
    go_same_level = {**MAP_GO, "level": "warn", "body": "Pre-evacuation zones now evacuate."}
    assert _run(st, MANUAL_SET, MAP_SET, go_same_level) == [go_same_level["id"]]


def test_map_clear_and_texted_clear_post_once_either_order():
    st = {}
    _run(st, MAP_SET)
    assert _run(st, MAP_CLEAR) == [MAP_CLEAR["id"]]
    assert _run(st, MAP_CLEAR, TEXT_CLEAR) == []
    st2 = {}
    _run(st2, MAP_SET)
    assert _run(st2, TEXT_CLEAR) == [TEXT_CLEAR["id"]]
    assert _run(st2, TEXT_CLEAR, MAP_CLEAR) == []
    assert st2["site_alerts"]["county_posted_orders"] == [f"{INC}:clear"]


def test_a_new_order_after_a_clear_posts_again():
    st = {}
    _run(st, MAP_SET)
    _run(st, MAP_CLEAR)
    later = {**MAP_SET, "id": MAP_SET["id"] + "-val-6", "receivedMs": 60 * H}
    assert _run(st, later) == [later["id"]]


def test_unsure_means_post():
    """Outside 3 h, a different level, a different category, or no timestamp: all post."""
    st = {}
    _run(st, MAP_SET)
    late = {**TEXT_SET, "id": "relay-late", "receivedMs": MAP_SET["receivedMs"] + 4 * H}
    other_level = {**TEXT_SET, "id": "relay-danger", "level": "danger"}
    road = {**TEXT_SET, "id": "relay-road", "subject": "Road closure", "body": "CR 501 closed at mile 3."}
    no_time = {**TEXT_SET, "id": "relay-notime", "receivedMs": None}
    assert _run(st, MAP_SET, late, other_level, road, no_time) == \
        ["relay-notime", "relay-danger", "relay-road", "relay-late"]


def test_corrections_still_post():
    st = {}
    _run(st, MAP_SET)
    corr = {"id": "relay-corr", "kind": "correction", "level": "warn", "receivedMs": MAP_SET["receivedMs"] + H,
            "subject": "Correction", "body": "Pre-evacuation applies to VAL-1 to VAL-3 only."}
    assert _run(st, MAP_SET, corr) == ["relay-corr"]


def test_old_state_with_ids_only_is_migrated_without_reposting():
    """The real state file left by the Oct 22-23 flood: ids only, no order keys."""
    st = {"site_alerts": {"county_posted_ids": [MANUAL_SET["id"], MAP_SET["id"], MAP_CLEAR["id"], TEXT_SET["id"]],
                          "stream": {}}}
    assert site_alerts.site_state(st)["county_posted_orders"] == [f"{INC}:clear"]
    assert _run(st, MAP_CLEAR, TEXT_CLEAR) == []
    # texts posted before the change are spent: they cannot stand in for a new map order
    new_set = {**MAP_SET_5, "receivedMs": TEXT_SET["receivedMs"] + 60 * 1000}
    assert _run(st, TEXT_SET, new_set) == [new_set["id"]]


def test_a_failed_post_leaves_the_order_open():
    st = {}
    feed = {"active": [MAP_SET, TEXT_SET]}
    assert [e["id"] for e in site_alerts.county_events(st, feed)] == [MAP_SET["id"]]
    # no mark() (the post failed): the next run offers the same order again, still once
    assert [e["id"] for e in site_alerts.county_events(st, feed)] == [MAP_SET["id"]]
