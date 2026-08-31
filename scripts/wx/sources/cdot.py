"""
CDOT road conditions -- the pass card.

Covers the two routes that matter and the way locals actually talk about them:
US-550 north (Coal Bank / Molas / Red Mountain, which close as a UNIT) and
US-160 east over Wolf Creek. "The pass is closed," unqualified, means Red
Mountain in Durango and Wolf Creek in Bayfield or Pagosa -- so the card always
names which one.

NEEDS A FREE API KEY from data.cotrip.org. Without it this returns a clean
"unavailable" rather than failing the run: the pass card is valuable but it is
not load-bearing, and a missing road line should never cost you the forecast.

*** NOT CONFIRMED LIVE *** -- written from CDOT's documented OpenAPI shape.
Run selftest.py on Actions and read the raw output before trusting the field
names. Same caveat, same reason, as every other adapter here.
"""

import os
import re

from .http import SourceResult, get_json

BASE = "https://data.cotrip.org/api/v1"

ROUTES = {
    "us550_north": {
        "label": "US-550 north",
        "segments": ["Coal Bank Pass", "Molas Pass", "Red Mountain Pass"],
        "note": "these three close as a unit",
    },
    "us160_east": {
        "label": "US-160 east",
        "segments": ["Wolf Creek Pass"],
        "note": "the main way in from the rest of the state",
    },
    "us160_west": {
        "label": "US-160 west",
        "segments": ["Hesperus Hill", "Mancos Hill"],
        "note": "",
    },
}

CLOSED = re.compile(r"\bclosed\b", re.I)
TRACTION = re.compile(r"traction|chain", re.I)
WINTRY = re.compile(r"snow|ice|icy|packed|slush", re.I)


def _key():
    return os.environ.get("CDOT_API_KEY")


def fetch_conditions():
    key = _key()
    if not key:
        return SourceResult(False, source="CDOT",
                            error="CDOT_API_KEY not set -- free at data.cotrip.org")
    url = f"{BASE}/roadConditions?apiKey={key}"
    try:
        data = get_json(url)
    except Exception as exc:  # noqa: BLE001
        return SourceResult(False, source="CDOT", url=BASE, error=str(exc))

    features = data.get("features") or data.get("roadConditions") or []
    rows = []
    for feat in features:
        p = feat.get("properties") or feat
        name = str(p.get("routeName") or p.get("name") or "")
        status = str(p.get("currentConditions") or p.get("status")
                     or p.get("conditionDescription") or "")
        if not name and not status:
            continue
        rows.append({"name": name, "status": status,
                     "updated": p.get("lastUpdated") or p.get("timestamp")})

    if not rows:
        return SourceResult(False, source="CDOT", url=BASE,
                            error="no road-condition features in response")
    return SourceResult(True, _by_route(rows), source="CDOT", url=BASE)


def _by_route(rows):
    out = {}
    for key, meta in ROUTES.items():
        hits = []
        for seg in meta["segments"]:
            for r in rows:
                blob = f"{r['name']} {r['status']}"
                if seg.lower() in blob.lower():
                    hits.append({"segment": seg, "status": r["status"]})
                    break
        worst = "no report"
        if hits:
            joined = " ".join(h["status"] for h in hits)
            if CLOSED.search(joined):
                worst = "closed"
            elif TRACTION.search(joined):
                worst = "traction/chain law"
            elif WINTRY.search(joined):
                worst = "snow or ice"
            else:
                worst = "clear"
        out[key] = {"label": meta["label"], "note": meta["note"],
                    "segments": hits, "summary": worst}
    return out


def format_pass_card(routes):
    """The recurring daily block. Bottom line first, then route by route."""
    if not routes:
        return None
    closed = [r["label"] for r in routes.values() if r["summary"] == "closed"]
    lines = []
    if closed:
        lines.append(f"Short version: {', '.join(closed)} closed.")
    for meta in routes.values():
        seg = "; ".join(f"{h['segment']} {h['status']}" for h in meta["segments"])
        line = f"{meta['label']} — {seg or meta['summary']}"
        if meta["note"] and meta["summary"] in ("closed", "traction/chain law"):
            line += f" ({meta['note']})"
        lines.append(line)
    return "\n".join(lines)
