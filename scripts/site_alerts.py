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
  * County: each ORDER posts once (county_events). A map entry's order is
    "<incident>:<status>"; a texted/relayed/emailed copy of it within 3 hours
    does not post again, whichever arrived first. A status change (Set -> Go,
    any -> clear) is a new order. Corrections post as their own updates.
    Ids are still remembered, so no single message ever posts twice.
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

# One post per ORDER, not per message (2026-10-23). During the Oct 22-23 flood the
# county map entry, a texted copy of the same order and a hand relay each posted.
# A map entry's order key is "<incident>:<status>"; a text/relay/email within
# SAME_ORDER_WINDOW of a map entry of the same kind (and, for alerts, the same level
# and category) is the same order. See county_events().
SAME_ORDER_WINDOW_MS = 3 * 60 * 60 * 1000
KEEP_ORDER_KEYS = 50
_MAP_CLEAR_ID = re.compile(r"^zone-(?P<incident>[a-z0-9-]+?)-clear-\d+$")
_MAP_ALERT_ID = re.compile(r"^zone-(?P<incident>[a-z0-9-]+?)-(?P<status>ready|set|go)(?:-|$)")


# chip id -> (gauge key, rank). Higher rank = more severe.
STREAM_RANKS = {
    "stream-creek-rise": ("creek", 1),
    "stream-creek-high": ("creek", 2),
    "stream-creek-flood": ("creek", 3),
    # Creek at the county's evacuation (Go) trigger, when the site publishes one.
    "stream-creek-go": ("creek", 4),
    "stream-pine-rise": ("pine", 1),
    "stream-below-dam-action": ("below", 1),
    "stream-below-dam-minor": ("below", 2),
    "stream-below-dam-moderate": ("below", 3),
    "stream-below-dam-major": ("below", 4),
}

DEFAULT_SITE_STATE = {"county_posted_ids": [], "county_posted_orders": [], "county_bound_ids": [], "stream": {}}


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
           "county_posted_orders": list(s.get("county_posted_orders") or []),
           "county_bound_ids": list(s.get("county_bound_ids") or []),
           "stream": dict(s.get("stream") or {})}
    if "county_posted_orders" not in s:
        # Older state held ids only: rebuild the order keys from them, in posting
        # order, so the first run after this change does not re-post a live order.
        # Texts already posted count as used, so none can stand in for a new map order.
        for pid in out["county_posted_ids"]:
            key = _map_order_key({"id": pid})
            if key:
                _set_order(out, key)
            else:
                _bind(out, pid)
    state["site_alerts"] = out
    return out


def _map_order_key(a, groups=None):
    """'<incident>:<status>' for a county evacuation MAP entry, else None (a text,
    relay, email, or a map id this cannot parse -- those dedupe by id, so an
    unparseable entry posts rather than being silently merged)."""
    aid = str(a.get("id") or "")
    if not aid.startswith("zone-"):
        return None
    m = _MAP_CLEAR_ID.match(aid)
    if m:
        return f"{m.group('incident')}:clear"
    # Prefer the feed's own incident names, longest first, so a slug that happens
    # to contain "-go-" or "-set-" is not cut short by the regex fallback.
    for inc in sorted((groups or {}), key=len, reverse=True):
        prefix = f"zone-{inc}-"
        if aid.startswith(prefix):
            status = aid[len(prefix):].split("-", 1)[0]
            if status in ("ready", "set", "go", "clear"):
                return f"{inc}:{status}"
    m = _MAP_ALERT_ID.match(aid)
    return f"{m.group('incident')}:{m.group('status')}" if m else None


def _set_order(ss, key):
    """Record key as its incident's current posted status (one key per incident)."""
    incident = key.rsplit(":", 1)[0]
    keep = [k for k in ss["county_posted_orders"] if k.rsplit(":", 1)[0] != incident]
    ss["county_posted_orders"] = (keep + [key])[-KEEP_ORDER_KEYS:]


def _bind(ss, aid):
    ss["county_bound_ids"] = ([i for i in ss["county_bound_ids"] if i != aid] + [aid])[-KEEP_COUNTY_IDS:]


def _add_id(ss, aid):
    ids = [i for i in ss["county_posted_ids"] if i != aid] + [aid]
    ss["county_posted_ids"] = ids[-KEEP_COUNTY_IDS:]


def _county_category(text):
    t = text.lower()
    if re.search(r"evacuat|go now|leave now|shelter[- ]in[- ]place", t):
        return "evacuation"
    if re.search(r"flood|high water|dam (failure|breach)", t):
        return "flood"
    if re.search(r"\bfire\b|wildfire|smoke|red flag", t):
        return "fire"
    return "disaster"


def _same_order(a, b):
    """Two county entries announcing the same order: same kind, received within
    SAME_ORDER_WINDOW_MS, and for alerts/corrections the same level and category.
    Missing timestamps mean 'not sure', and not sure means post."""
    if a.get("kind") != b.get("kind"):
        return False
    ra, rb = a.get("receivedMs"), b.get("receivedMs")
    if not isinstance(ra, (int, float)) or not isinstance(rb, (int, float)) or abs(ra - rb) > SAME_ORDER_WINDOW_MS:
        return False
    if a["kind"] == "clear":
        return True
    text = lambda e: f"{e.get('subject') or ''} {e.get('body') or ''}"
    return a.get("level") == b.get("level") and _county_category(text(a)) == _county_category(text(b))


def county_events(state, feed):
    """New county ORDERS, oldest first. One post per order (see SAME_ORDER_WINDOW_MS):
      * a map entry posts when its incident's status changes (Set -> Go, any -> clear);
        a zone-list change alone (VAL-1..4 -> VAL-1..5) is the same order;
      * a text/relay/email that matches a map entry already posted (or posting this
        run) is the same order and does not post, and vice versa when the text came first.
    Posting marks happen in mark(). The only mutation here is recording an entry as
    covered when the order it repeats has ALREADY posted (so it is never posted later)."""
    ss = site_state(state)
    seen = set(ss["county_posted_ids"])
    groups = ((feed.get("zones") or {}).get("groups") or {}) if isinstance(feed.get("zones"), dict) else {}
    items = [a for a in (feed.get("active") or []) if isinstance(a, dict) and a.get("id")
             and a.get("kind") in ("alert", "correction", "clear")]
    items.sort(key=lambda a: a.get("receivedMs") or 0)
    keys = {a["id"]: _map_order_key(a, groups) for a in items}
    planned = {}   # entry id -> the event that will post it this run
    events = []
    for a in items:
        if a["id"] in seen:
            continue
        key = keys[a["id"]]
        if key and key in ss["county_posted_orders"]:
            _add_id(ss, a["id"])          # same order, e.g. zones VAL-1..4 -> VAL-1..5
            seen.add(a["id"])
            continue
        same_key = next((ev for ev in planned.values() if key and ev["order_key"] == key), None)
        if same_key is not None:
            same_key["also_ids"].append(a["id"])
            planned[a["id"]] = same_key
            continue
        # The partner is on the other side (map vs not-map) and already posted or posting.
        # A map order may adopt a text only once (bound), so a text that announced Set can
        # never stand in for a later Go.
        def usable(b):
            if b is a or bool(keys[b["id"]]) == bool(key) or not _same_order(a, b):
                return False
            if not key:
                return b["id"] in seen or b["id"] in planned
            if b["id"] in planned:
                return planned[b["id"]]["order_key"] is None
            return b["id"] in seen and b["id"] not in ss["county_bound_ids"]
        partner = next((b for b in items if usable(b)), None)
        if partner is not None:
            if partner["id"] in planned:
                ev = planned[partner["id"]]
                ev["also_ids"].append(a["id"])
                planned[a["id"]] = ev
                if key:
                    ev["order_key"] = key
                    ev["bound_ids"].append(partner["id"])
            else:
                _add_id(ss, a["id"])
                seen.add(a["id"])
                if key:
                    _set_order(ss, key)
                    _bind(ss, partner["id"])
            print(f"[site_alerts] {a['id']} repeats the order already in {partner['id']}; not posting it again.")
            continue
        kind = a["kind"]
        subject = (a.get("subject") or "La Plata County alert").strip()
        body = (a.get("body") or "").strip()
        hook, row = {
            "alert": ("La Plata County alert.", "COUNTY ALERT"),
            "correction": ("La Plata County correction.", "COUNTY CORRECTION"),
            "clear": ("La Plata County update.", "COUNTY UPDATE"),
        }[kind]
        # Say where it really came from (2026-10-22): the county's evacuation MAP (polled by the
        # site), a county TEXT relayed by GoVallecito, or an LPC Alerts EMAIL.
        src = a.get("source")
        if src == "readylaplata":
            hook = {"clear": "La Plata County evacuation map update."}.get(kind, "La Plata County evacuation map.")
            row = "COUNTY EVAC MAP"
            source_name = "La Plata County evacuation map (readylaplata.org), shown by GoVallecito"
            source_url = "https://readylaplata.org"
        elif a.get("manual") or a.get("relayed"):
            source_name = "La Plata County LPC Alerts text, relayed word for word by GoVallecito"
            source_url = "https://govallecito.com/county-alert"
        else:
            source_name = "La Plata County, LPC Alerts (reposted by GoVallecito)"
            source_url = "https://govallecito.com/county-alert"
        event = {
            "id": a["id"],
            "kind": "site_county",
            "order_key": key,
            "also_ids": [],
            "bound_ids": [],
            "event": "LPC Alerts message",
            "category": _county_category(subject + " " + body),
            "headline": subject,
            "description": "",
            "full_text": body,
            "hook": hook,
            "row_label": row,
            "calm": kind == "clear",
            "source_name": source_name,
            "source_url": source_url,
        }
        planned[a["id"]] = event
        events.append(event)
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
            "hook": "Very high water on Vallecito Creek." if danger else "Rising water at Vallecito.",
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
        for aid in [event["id"]] + list(event.get("also_ids") or []):
            _add_id(ss, aid)
        if event.get("order_key"):
            _set_order(ss, event["order_key"])
        for aid in event.get("bound_ids") or []:
            _bind(ss, aid)
    elif event["kind"] == "site_stream":
        ss["stream"][event["gauge"]] = {"rank": event["rank"], "posted_at": now.isoformat()}
