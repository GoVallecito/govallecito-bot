"""
Orchestrator. The entry point GitHub Actions calls.

FLOW
  slot check -> build bundle -> hard precondition gate -> compose -> guardrails
  -> publish or hold -> log the forecast for tomorrow's verification

Like the existing bot's main.py, this runs hourly and checks the clock itself
in America/Denver rather than trusting a fixed UTC cron, so the 5:45am promise
survives both DST transitions without anyone editing YAML twice a year.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wx import bundle as B          # noqa: E402
from wx import compose as CO        # noqa: E402
from wx import constants as C       # noqa: E402
from wx import guardrails as G      # noqa: E402
from wx import notify as N         # noqa: E402
from wx import publish as P         # noqa: E402
from wx import render_forecast_card as RC  # noqa: E402
from wx import email_digest as ED   # noqa: E402
from wx import verify as V          # noqa: E402

TZ = ZoneInfo(C.TIMEZONE)
SLOT_HOURS = {C.SCHOOL_CALL_HOUR: "school_call", C.EVENING_HOUR: "evening"}


def determine_slot(now=None, forced=None):
    forced = forced or os.environ.get("FORCE_SLOT")
    if forced in ("school_call", "evening", "storm_setup", "totals", "life_safety"):
        print(f"FORCE_SLOT={forced} -- skipping the clock check.")
        return forced
    now = now or datetime.now(TZ)
    slot = SLOT_HOURS.get(now.hour)
    if slot is None:
        print(f"{now:%Y-%m-%d %H:%M %Z} is not a posting hour "
              f"({sorted(SLOT_HOURS)} local). Exiting.")
    return slot


def _llm_from_env():
    """Anthropic by default. Returns a callable(messages) -> str.

    Kept tiny and swappable on purpose -- everything upstream of this is
    provider-agnostic and offline-testable.
    """
    import urllib.request

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    model = os.environ.get("WX_MODEL", "claude-sonnet-4-5")

    def call(messages):
        system = next(m["content"] for m in messages if m["role"] == "system")
        user = [m for m in messages if m["role"] != "system"]
        body = json.dumps({
            "model": model, "max_tokens": 2000, "system": system,
            "messages": user, "temperature": 0.7,
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"content-type": "application/json", "x-api-key": key,
                     "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode())
        return "".join(b.get("text", "") for b in payload.get("content", []))

    return call


def run(slot=None, llm=None, first_30_days=None, site_dir=None, dry_bundle=None):
    now = datetime.now(TZ)
    slot = slot or determine_slot(now)
    if slot is None:
        return 0

    if first_30_days is None:
        first_30_days = (os.environ.get("WX_FIRST_30_DAYS") or "true").lower() \
            not in ("false", "0", "no")

    print(f"=== Vallecito forecast: {slot} @ {now:%Y-%m-%d %H:%M %Z} ===")

    cal_offset, calibrated = V.current_calibration()
    print(f"snow-line calibration: offset={cal_offset}ft active={calibrated}")

    bundle = dry_bundle or B.build(calibration_offset_ft=cal_offset)

    problems = G.require_or_abort(bundle)
    if problems:
        # The dead-man switch. Silence is recoverable; a 5:45am forecast built
        # on half its inputs is not.
        print("ABORT -- preconditions not met, posting nothing:")
        for p in problems:
            print(f"  - {p}")
        return 0

    if bundle.get("life_safety_alerts") and slot in ("school_call", "evening"):
        events = sorted({a["event"] for a in bundle["life_safety_alerts"]})
        print(f"life-safety alert(s) active {events} -- composing as life_safety")
        slot = "life_safety"

    llm = llm or _llm_from_env()
    text = CO.compose(bundle, llm, post_type=slot)

    verdict, reasons = G.evaluate(bundle, text, first_30_days=first_30_days,
                                  calibrated=calibrated)
    print(f"guardrails: {verdict.upper()}")
    for r in reasons:
        print(f"  - {r}")

    os.makedirs("output", exist_ok=True)
    with open(os.path.join("output", "draft.txt"), "w") as fh:
        fh.write(text)
    with open(os.path.join("output", "bundle.json"), "w") as fh:
        json.dump(bundle, fh, indent=2, default=str)

    if verdict == G.BLOCK:
        print("BLOCKED -- nothing published. Draft saved to output/draft.txt")
        return 0
    if verdict == G.REVIEW:
        print("HELD FOR REVIEW -- draft saved to output/draft.txt")
        # A review gate nobody sees is not a safety mechanism. Open an issue so
        # the held draft actually reaches a human.
        N.review_requested(text, verdict, reasons, bundle, slot=slot)
        return 0

    site_dir = site_dir or os.environ.get("WX_SITE_DIR")
    if site_dir:
        print(f"site post -> {P.write_site_post(text, bundle, site_dir, slot)}")

    # The card is best-effort: a rendering failure must not cost the forecast.
    card = None
    try:
        card = RC.render(RC.card_data_from_bundle(bundle),
                         os.path.join("output", "card.png"))
        print(f"card -> {card}")
    except Exception as exc:  # noqa: BLE001
        print(f"[card] render failed, posting text only: {exc}")

    result = (P.post_photo_to_page(text, card) if card else P.post_to_page(text))
    print(f"page: {result}")

    recipients = ED.load_recipients()
    if recipients:
        subject, plain, html = ED.render(text, bundle, card)
        print(f"email: {ED.send(subject, plain, html, recipients, card)}")
    if os.environ.get("FB_GROUP_ID"):
        print(f"group: {P.post_to_group(_group_caption(slot))}")

    fid = V.record_forecast(bundle, _predicted_ranges(bundle),
                            post_id=result.get("id"))
    print(f"logged forecast {fid} for tomorrow's verification")
    return 0


def _group_caption(slot):
    return {"school_call": "Latest on the snow line and the roads this morning.",
            "evening": "A look at the next few days.",
            "totals": "What actually fell overnight.",
            "life_safety": "Heads up -- details in the post."}.get(slot, "Latest forecast.")


def _predicted_ranges(bundle):
    """What we will score ourselves against tomorrow.

    Derived from the band totals actually shown, widened into the kind of range
    a post states. Scoring against a range we published is the honest version;
    scoring against a raw model number we never said would be flattering and
    meaningless.
    """
    out = {}
    for key in C.BAND_ORDER:
        b = (bundle.get("bands") or {}).get(key) or {}
        s = b.get("summary") or {}
        total = s.get("total_snow_in")
        if total is None:
            continue
        lo = max(0.0, round(total * 0.6, 1))
        hi = round(total * 1.5, 1) if total > 0 else 0.5
        out[key] = {"snow_low_in": lo, "snow_high_in": hi, "model_total_in": total}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slot", nargs="?", default=None)
    ap.add_argument("--site-dir", default=None)
    args = ap.parse_args()
    return run(slot=determine_slot(forced=args.slot), site_dir=args.site_dir)


if __name__ == "__main__":
    sys.exit(main())
