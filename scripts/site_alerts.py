"""
Source (5) for check_emergency.py: govallecito.com's own alert feed.

WHAT IT READS: https://govallecito.com/data/lpc-alerts.json, served by the
govallecito-lpcalerts Worker in the SITE repo (worker-lpcalerts/). Two things
live there that no other source this bot reads can see:

  1. `active` -- La Plata County LPC Alerts messages. The county's system has
     no public API (the gap the rest of this file's family documents), so the
     Worker receives them by EMAIL at alerts@govallecito.com, verifies each is
     really from Regroup (DMARC/DKIM pass), and publishes them here. Admin and
     test messages never appear in `active`.
  2. `stream` -- gauge chips: Vallecito Creek high / flood level / rising fast,
     Pine River above the lake rising fast, and the NWS flood category below
     the dam. Thresholds and the October 2025 replay are documented in the
     site repo's worker-lpcalerts/stream-logic.js.

OFF BY DEFAULT. Nothing here runs unless the repo variable SITE_ALERTS is
"on" (the workflow passes it through as env SITE_ALERTS). With it unset this
module is inert and check_emergency.py behaves exactly as before.

POSTING RULES (all state in state/emergency_alert_state.json -> "site_alerts"):
  * County: each message id posts ONCE. Corrections and all-clears are their
    own messages and post as their own (calmer-worded) updates.
  * Stream: a gauge posts only when its level RISES above the highest level
    already posted for it (rising -> high -> flood). A drop never posts. The
    level resets only after the gauge has shown NO chip for 6 hours, so a
    reading wobbling around a threshold cannot post every 10 minutes.
  * State changes only at those transitions, so a quiet run commits nothing.
  * Fetch failure = no events this run (fail closed, same contract as every
    other fetch in this bot).
Pure functions below take `now` and the parsed feed, so tests need no network.
"""

import os
import re
from datetime import datetime, timezone, timedelta

SITE_ALERTS_URL = os.environ.get("SITE_ALERTS_URL", "https://govallecito.com/data/lpc-alerts.json")
STREAM_RESET_AFTER = timedelta(hours=6)
KEEP_COUNTY_IDS = 50

# chip id -> (gauge key, rank). Higher rank = more severe.
STREAM_RANKS = {
    "stream-creek-rise": ("creek", 1),
    "stream-creek-high": ("creek", 2),
    "stream-creek-flood": ("creek", 3),
    "stream-pine-rise": ("pine", 1),
    "stream-below-dam-action": ("below", 1),
    "stream-below-dam-minor": ("below", 2),
    "stream-below-dam-moderate": ("below", 3),
    "stream-below-dam-major": ("below", 4),
}

DEFAULT_SITE_STATE = {"county_posted_ids": [], "stream": {}}


def enabled():
    return os.environ.get("SITE_ALERTS", "").strip().lower() in ("on", "true", "1", "live")


def fetch_feed(get_json):
    """get_json: fetch_conditions._get_json-compatible callable. Returns the
    parsed feed or None on any failure (fail closed)."""
    try:
        feed = get_json(SITE_ALERTS_URL)
        return feed if isinstance(feed, dict) else None
    except Exception as exc:  # noqa: BLE001 -- never crash the emergency run
        print(f"[site_alerts] could not fetch {SITE_ALERTS_URL} ({exc}); no site alerts this run.")
        return None


def site_state(state):
    s = state.get("site_alerts")
    if not isinstance(s, dict):
        s = {}
    out = {"county_posted_ids": list(s.get("county_posted_ids") or []),
           "stream": dict(s.get("stream") or {})}
    state["site_alerts"] = out
    return out


def _county_category(text):
    t = text.lower()
    if re.search(r"evacuat|go now|leave now|shelter[- ]in[- ]place", t):
        return "evacuation"
    if re.search(r"flood|high water|dam (failure|breach)", t):
        return "flood"
    if re.search(r"\bfire\b|wildfire|smoke|red flag", t):
        return "fire"
    return "disaster"


def county_events(state, feed):
    """New county messages, oldest first. Read-only (marking happens in mark())."""
    ss = site_state(state)
    seen = set(ss["county_posted_ids"])
    items = [a for a in (feed.get("active") or []) if isinstance(a, dict) and a.get("id")]
    items.sort(key=lambda a: a.get("receivedMs") or 0)
    events = []
    for a in items:
        if a["id"] in seen or a.get("kind") not in ("alert", "correction", "clear"):
            continue
        kind = a["kind"]
        subject = (a.get("subject") or "La Plata County alert").strip()
        body = (a.get("body") or "").strip()
        hook, row = {
            "alert": ("La Plata County alert.", "COUNTY ALERT"),
            "correction": ("La Plata County correction.", "COUNTY CORRECTION"),
            "clear": ("La Plata County update.", "COUNTY UPDATE"),
        }[kind]
        events.append({
            "id": a["id"],
            "kind": "site_county",
            "event": "LPC Alerts message",
            "category": _county_category(subject + " " + body),
            "headline": subject,
            "description": "",
            "full_text": body,
            "hook": hook,
            "row_label": row,
            "calm": kind == "clear",
            "source_name": "La Plata County, LPC Alerts (reposted by GoVallecito)",
            "source_url": "https://govallecito.com/county-alert",
        })
    return events


def stream_events(state, feed, now=None):
    """Gauge escalations. Also resets levels that have been clear for 6 h.
    Mutates only the reset bookkeeping; posting marks happen in mark()."""
    now = now or datetime.now(timezone.utc)
    ss = site_state(state)
    present = {}
    for chip in feed.get("stream") or []:
        key_rank = STREAM_RANKS.get((chip or {}).get("id"))
        if not key_rank:
            continue
        key, rank = key_rank
        if rank > present.get(key, (0, None))[0]:
            present[key] = (rank, chip)

    # Bookkeeping for gauges that went quiet: start the clock, reset after 6 h.
    for key, rec in list(ss["stream"].items()):
        if key in present:
            if rec.get("cleared_at"):
                rec.pop("cleared_at", None)
            continue
        if not rec.get("cleared_at"):
            rec["cleared_at"] = now.isoformat()
        else:
            try:
                since = datetime.fromisoformat(rec["cleared_at"])
            except ValueError:
                since = now
            if now - since >= STREAM_RESET_AFTER:
                del ss["stream"][key]

    events = []
    for key, (rank, chip) in present.items():
        if rank <= (ss["stream"].get(key) or {}).get("rank", 0):
            continue
        danger = chip.get("level") == "danger"
        text = chip.get("text") or "Stream gauge alert"
        events.append({
            "id": f"site-stream-{key}-{rank}",
            "kind": "site_stream",
            "gauge": key,
            "rank": rank,
            "event": "Stream gauge alert",
            "category": "flood",
            "headline": text,
            "description": "",
            "full_text": ("Measured by the stream gauge, refreshed about every 15 minutes. "
                          "This is a gauge reading, not an official warning: follow the National "
                          "Weather Service and La Plata County for instructions, and stay off creek "
                          "banks and low crossings."),
            "hook": "Flood-level water at Vallecito." if danger else "Rising water at Vallecito.",
            "row_label": "STREAM GAUGE",
            "calm": False,
            "source_name": "USGS and NWS stream gauges (via GoVallecito)",
            "source_url": "https://govallecito.com/streamflow",
        })
    return events


def mark(state, event, now=None):
    """Call only after a successful post attempt."""
    now = now or datetime.now(timezone.utc)
    ss = site_state(state)
    if event["kind"] == "site_county":
        ids = [i for i in ss["county_posted_ids"] if i != event["id"]] + [event["id"]]
        ss["county_posted_ids"] = ids[-KEEP_COUNTY_IDS:]
    elif event["kind"] == "site_stream":
        ss["stream"][event["gauge"]] = {"rank": event["rank"], "posted_at": now.isoformat()}
