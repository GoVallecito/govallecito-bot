"""
Storm watch runner -- fires the setup post when a system shows up in the
day 2-5 window.

Runs a few times a day rather than hourly. A storm five days out does not
change meaningfully between 9am and 10am, and checking constantly would only
increase the chance of firing on a model wobble.

The setup post is the single highest-engagement class in the research (333
reactions against 23 for a live severe warning), and until this runner existed
it could only happen if a person noticed. Now it happens on its own -- with the
deliberate restraints in storm_watch.evaluate(): nothing inside 48 hours,
nothing twice for the same system unless it materially escalates.
"""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wx import bundle as B          # noqa: E402
from wx import compose as CO        # noqa: E402
from wx import constants as C       # noqa: E402
from wx import guardrails as G      # noqa: E402
from wx import notify as N          # noqa: E402
from wx import publish as P         # noqa: E402
from wx import sanitize as SAN     # noqa: E402
from wx import render_forecast_card as RC   # noqa: E402
from wx import storm_watch as SW    # noqa: E402
from wx import verify as V          # noqa: E402
from wx.sources import openmeteo    # noqa: E402

TZ = ZoneInfo(C.TIMEZONE)


def run(llm=None, bundle_override=None, first_30_days=None):
    now = datetime.now(TZ)
    print(f"=== storm watch @ {now:%Y-%m-%d %H:%M %Z} ===")

    cal_offset, calibrated = V.current_calibration()
    bundle = bundle_override or B.build(days=7, calibration_offset_ft=cal_offset)

    problems = G.require_or_abort(bundle)
    if problems:
        print(f"ABORT -- preconditions not met: {problems}")
        return 0

    # Raw payloads give the trigger real hourly resolution out to day 7,
    # rather than the coarser 6-hour blocks the summary keeps.
    raw = {}
    vall = next(b for b in C.BANDS if b["key"] == "vallecito")
    res = openmeteo.fetch_band(vall, days=7)
    if res.ok:
        raw["vallecito"] = res.data

    decision = SW.evaluate(bundle, raw, now=now)
    print(f"decision: fire={decision['fire']} -- {decision['reason']}")
    if decision.get("storm"):
        s = decision["storm"]
        print(f"  window {s['window_start']} -> {s['window_end']}, "
              f"{s['liquid_in']}in liquid / {s['snow_in']}in snow, peak {s['peak_hour']}")

    if not decision["fire"]:
        return 0
    if llm is None:
        print("No LLM supplied -- would have fired but cannot compose.")
        return 0

    bundle["storm_watch"] = decision
    text = CO.compose(
        bundle, llm, post_type="storm_setup",
        extra_instruction=(
            "This system is still "
            f"{_days_out(decision)} days out. Write about PATTERN and "
            "POSSIBILITY in prose. Do NOT give snowfall amounts for it -- name "
            "the setup, name which models disagree and how, give the timing "
            "window, and say plainly that the details will change. The amounts "
            "come later when they mean something."))

    if first_30_days is None:
        first_30_days = (os.environ.get("WX_FIRST_30_DAYS") or "true").lower() \
            not in ("false", "0", "no")

    text = SAN.clean(text)

    verdict, reasons = G.evaluate(bundle, text, first_30_days=first_30_days,
                                  calibrated=calibrated)
    print(f"guardrails: {verdict.upper()}")
    for r in reasons:
        print(f"  - {r}")

    os.makedirs("output", exist_ok=True)
    with open(os.path.join("output", "storm_draft.txt"), "w") as fh:
        fh.write(text)

    if verdict == G.BLOCK:
        print("BLOCKED -- nothing published.")
        return 0
    if verdict == G.REVIEW:
        N.review_requested(text, verdict, reasons, bundle, slot="storm_setup")
        return 0

    card = None
    try:
        card = RC.render(RC.card_data_from_bundle(bundle),
                         os.path.join("output", "storm_card.png"))
    except Exception as exc:  # noqa: BLE001
        print(f"[card] render failed, posting text only: {exc}")

    site_dir = os.environ.get("WX_SITE_DIR")
    if site_dir:
        print(f"site post -> {P.write_site_post(text, bundle, site_dir, 'storm_setup')}")
    print(f"page: {P.post_photo_to_page(text, card) if card else P.post_to_page(text)}")
    return 0


def _days_out(decision):
    try:
        from datetime import date
        peak = decision["storm"]["peak_hour"][:10]
        return max(1, (date.fromisoformat(peak) - C.local_date()).days)
    except Exception:  # noqa: BLE001
        return 3


if __name__ == "__main__":
    from wx.run_forecast import _llm_from_env
    try:
        _llm = _llm_from_env()
    except RuntimeError as exc:
        print(f"({exc} -- evaluating only)")
        _llm = None
    sys.exit(run(llm=_llm))
