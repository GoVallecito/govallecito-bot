"""
Storm-mode trigger -- the growth engine.

WHY THIS IS THE HIGHEST-VALUE MISSING PIECE
The engagement data is unambiguous and counterintuitive: a post about a storm
FOUR DAYS OUT scored 333 reactions. A post about a severe-warned storm
happening RIGHT NOW scored 23. Nowcasts earn trust; anticipation earns reach.
Until now nothing but the clock could fire a post, which meant the single
highest-engagement content class could only happen if a human noticed.

WHAT IT DOES NOT DO
It does not put snow numbers on a day-4 storm. The setup post is prose and
pattern -- "models show a cutoff dropping into the Four Corners Thursday" --
because a bare long-range snow map is the cardinal sin of this genre and the
guardrails block it anyway. This trigger decides WHETHER to talk, not what
numbers to give.

DEDUPLICATION
A storm three days out is still a storm two days out. Firing every morning for
the same system would be exactly the hype behaviour this whole product is
positioned against, so a fired storm is fingerprinted by its date window and
not re-fired unless it materially escalates.
"""

import datetime as _dt
import json
import os

from . import constants as C

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(REPO_ROOT, "state", "storm_watch.json")

# Thresholds, in liquid inches over the window, at the Vallecito band. Tuned to
# "worth a post," not "worth a warning" -- and deliberately conservative,
# because crying wolf is the failure mode that costs the most here.
MIN_LIQUID_IN = 0.35
MIN_SNOW_IN = 4.0
# A storm is interesting from day 5 in to day 2. Inside 48h the normal daily
# posts already cover it.
WINDOW_START_H, WINDOW_END_H = 48, 120
# Escalation needed to re-post about a system we already flagged.
ESCALATION_FACTOR = 1.6


def _load():
    if not os.path.exists(STATE):
        return {"fired": {}}
    try:
        with open(STATE) as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {"fired": {}}


def _save(obj):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = f"{STATE}.tmp-{os.getpid()}"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, STATE)


def _window_totals(payload, start_h, end_h):
    """Liquid and snow summed over an hour window, plus when it peaks."""
    h = (payload or {}).get("hourly") or {}
    times = h.get("time") or []
    if not times:
        return None
    lo, hi = min(start_h, len(times)), min(end_h, len(times))
    if hi <= lo:
        return None
    precip = (h.get("precipitation") or [])[lo:hi]
    snow = (h.get("snowfall") or [])[lo:hi]
    liquid = sum(x for x in precip if x is not None)
    snowfall = sum(x for x in snow if x is not None)
    peak_i = max(range(len(precip)), key=lambda i: precip[i] or 0) if precip else 0
    return {
        "liquid_in": round(liquid, 2),
        "snow_in": round(snowfall, 1),
        "window_start": times[lo],
        "window_end": times[hi - 1],
        "peak_hour": times[lo + peak_i] if precip else times[lo],
    }


def evaluate(bundle, raw_band_payloads=None, now=None):
    """Should we fire a storm-setup post?

    Returns {"fire": bool, "reason": str, "storm": {...}|None}.

    `raw_band_payloads` is {band_key: open-meteo payload}; when absent, the
    bundle's summarized blocks are used instead, which is coarser but works.
    """
    now = now or C.local_now()
    payload = (raw_band_payloads or {}).get("vallecito")

    if payload:
        totals = _window_totals(payload, WINDOW_START_H, WINDOW_END_H)
    else:
        totals = _from_blocks(bundle)

    if not totals:
        return {"fire": False, "reason": "no forecast data in the day 2-5 window",
                "storm": None}

    strong = (totals["liquid_in"] >= MIN_LIQUID_IN
              or totals["snow_in"] >= MIN_SNOW_IN)
    if not strong:
        return {"fire": False,
                "reason": (f"below threshold ({totals['liquid_in']}in liquid / "
                           f"{totals['snow_in']}in snow in the window)"),
                "storm": totals}

    # Fingerprint by the day the peak lands on, not by an id -- the same system
    # keeps the same peak day across runs even as amounts wobble.
    fingerprint = str(totals["peak_hour"])[:10]
    state = _load()
    prior = state["fired"].get(fingerprint)

    if prior:
        grew = totals["liquid_in"] >= prior.get("liquid_in", 0) * ESCALATION_FACTOR
        if not grew:
            return {"fire": False,
                    "reason": (f"already posted about the {fingerprint} system "
                               f"and it has not materially escalated"),
                    "storm": totals}
        reason = f"the {fingerprint} system escalated materially since the last post"
    else:
        reason = f"new system peaking {fingerprint} clears the threshold"

    state["fired"][fingerprint] = {
        "liquid_in": totals["liquid_in"], "snow_in": totals["snow_in"],
        "posted_at": now.isoformat(),
    }
    # Keep the file from growing forever.
    if len(state["fired"]) > 60:
        for k in sorted(state["fired"])[:-60]:
            state["fired"].pop(k, None)
    _save(state)

    return {"fire": True, "reason": reason, "storm": totals,
            "fingerprint": fingerprint,
            "disagreement": bundle.get("model_disagreement")}


def _from_blocks(bundle):
    """Fallback using the bundle's 6-hour blocks when raw payloads are absent."""
    b = (bundle.get("bands") or {}).get("vallecito") or {}
    blocks = ((b.get("summary") or {}).get("blocks")) or []
    # Blocks are 6 hours each; day 2-5 is roughly blocks 8..20.
    window = blocks[8:20]
    if not window:
        return None
    liquid = sum(x.get("precip_in") or 0 for x in window)
    snow = sum(x.get("snow_in") or 0 for x in window)
    peak = max(window, key=lambda x: x.get("precip_in") or 0)
    return {"liquid_in": round(liquid, 2), "snow_in": round(snow, 1),
            "window_start": window[0]["from"], "window_end": window[-1]["to"],
            "peak_hour": peak["from"]}
