"""
The morning-after job: score yesterday, calibrate, and draft the totals post.

This is the half of the loop most amateur weather pages skip, and skipping it is
why they stay amateur. Three outputs from one run:

  * a totals post, with the honest scoring of what was called
  * one more calibration point for the snow-line heuristic
  * a cumulative, public track record

Runs after the school call so the overnight CoCoRaHS reports are in.
"""

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
from wx import notify as N          # noqa: E402
from wx import observations as OB   # noqa: E402
from wx import publish as P         # noqa: E402
from wx import verify as V          # noqa: E402
from wx.sources import cocorahs     # noqa: E402

TZ = ZoneInfo(C.TIMEZONE)


def run(llm=None, obs=None, bundle_override=None, first_30_days=None):
    now = datetime.now(TZ)
    print(f"=== verify run @ {now:%Y-%m-%d %H:%M %Z} ===")

    observations = obs if obs is not None else OB.collect()
    print(f"observations: {observations.get('_meta')}")

    scored = V.verify_pending(observations)
    if not scored:
        print("Nothing to verify -- no unverified forecast in window. Exiting.")
        return 0

    for fc in scored:
        print(f"  {fc['id']}: hit_rate={fc['score']['hit_rate']} "
              f"line_error={fc['score'].get('snow_line_error_ft')}ft")

    cal = V.update_calibration()
    print(f"calibration: active={cal['active']} offset={cal['offset_ft']}ft "
          f"({cal['events']}/{cal['min_events_required']} events)")
    print(f"track record: {V.track_record()}")

    if llm is None:
        print("No LLM supplied -- scoring only, no totals post drafted.")
        return 0

    bundle = bundle_override or B.build(
        calibration_offset_ft=V.current_calibration()[0])

    reports = observations.get("_cocorahs_reports") or []
    bundle["observed"] = {
        "scored": [{"id": f["id"], "score": f["score"]} for f in scored],
        "cocorahs_block": cocorahs.format_for_post(reports, field="new_snow_in")
                          or cocorahs.format_for_post(reports, field="precip_in"),
        "station_count": len(reports),
        "track_record": V.track_record(),
    }

    text = CO.compose(
        bundle, llm, post_type="totals",
        yesterday_forecast=bundle["observed"],
        extra_instruction=(
            "Print the station reports verbatim as ranked name/amount pairs, in "
            "the order given. Then score yourself out loud: say the range you "
            "called, say what actually fell, and if you missed give the physical "
            "mechanism -- a band that set up somewhere else, a snow line that "
            "hung higher than you had it, a downslope hole. No apology."))

    if first_30_days is None:
        first_30_days = (os.environ.get("WX_FIRST_30_DAYS") or "true").lower() \
            not in ("false", "0", "no")

    verdict, reasons = G.evaluate(bundle, text, first_30_days=first_30_days,
                                  calibrated=cal["active"])
    print(f"guardrails: {verdict.upper()}")

    os.makedirs("output", exist_ok=True)
    with open(os.path.join("output", "totals_draft.txt"), "w") as fh:
        fh.write(text)
    with open(os.path.join("output", "observations.json"), "w") as fh:
        json.dump(observations, fh, indent=2, default=str)

    if verdict == G.BLOCK:
        print("BLOCKED -- nothing published.")
        return 0
    if verdict == G.REVIEW:
        N.review_requested(text, verdict, reasons, bundle, slot="totals")
        return 0

    site_dir = os.environ.get("WX_SITE_DIR")
    if site_dir:
        print(f"site post -> {P.write_site_post(text, bundle, site_dir, 'totals')}")
    print(f"page: {P.post_to_page(text)}")
    return 0


if __name__ == "__main__":
    from wx.run_forecast import _llm_from_env
    try:
        _llm = _llm_from_env()
    except RuntimeError as exc:
        print(f"({exc} -- scoring only)")
        _llm = None
    sys.exit(run(llm=_llm))
