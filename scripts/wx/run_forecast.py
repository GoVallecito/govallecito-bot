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
from wx import sanitize as SAN     # noqa: E402
from wx import render_forecast_card as RC  # noqa: E402
from wx import email_digest as ED   # noqa: E402
from wx import verify as V          # noqa: E402

TZ = ZoneInfo(C.TIMEZONE)
SLOT_HOURS = {C.SCHOOL_CALL_HOUR: "school_call", C.EVENING_HOUR: "evening"}


def _enabled_slots():
    """Which slots actually post. Defaults to the school call alone.

    The research is blunt that cadence beats brilliance: one post a day that
    never misses beats three that are erratic. The evening slot gets switched
    on by setting WX_SLOTS once the morning one has gone a month without
    failing.
    """
    raw = (os.environ.get("WX_SLOTS") or "school_call").strip()
    return {s.strip() for s in raw.split(",") if s.strip()}


def determine_slot(now=None, forced=None):
    forced = forced or os.environ.get("FORCE_SLOT")
    if forced in ("school_call", "evening", "storm_setup", "totals", "life_safety"):
        print(f"FORCE_SLOT={forced} -- skipping the clock check.")
        return forced
    now = now or datetime.now(TZ)
    slot = SLOT_HOURS.get(now.hour)
    if slot is not None and slot not in _enabled_slots():
        print(f"{slot} is not in WX_SLOTS ({sorted(_enabled_slots())}); skipping.")
        return None
    if slot is None:
        print(f"{now:%Y-%m-%d %H:%M %Z} is not a posting hour "
              f"({sorted(SLOT_HOURS)} local). Exiting.")
    return slot


class LLMError(RuntimeError):
    """A model-call failure, translated into something actionable."""

    HINTS = {
        401: ("The API rejected the key. Nothing on your side was changed by "
              "storing it here - a secret is a read-only copy and cannot revoke "
              "the original. Almost always this is the pasted VALUE: a trailing "
              "newline, a leading space, a partial copy, or a key from a "
              "different account. Re-paste it (select the whole value, no "
              "surrounding whitespace). Do NOT regenerate a key other systems "
              "share - that would break them; create an additional key instead."),
        403: ("Authenticated but not permitted. The key is probably scoped to a "
              "workspace without access to this model."),
        404: ("Model not found. Check the WX_MODEL variable - the default is "
              "claude-sonnet-4-5."),
        429: ("Rate limited or out of credit. The key is VALID; this is a "
              "quota or spend-limit issue, not an auth issue."),
        400: ("The request was rejected as malformed. Usually the model name."),
    }

    def __init__(self, status, body, model):
        self.status, self.body, self.model = status, body, model
        hint = self.HINTS.get(status, "Unexpected response from the API.")
        super().__init__(f"HTTP {status} calling model {model}. {hint}\n"
                         f"API said: {body}")


def _llm_from_env():
    """Anthropic by default. Returns a callable(messages) -> str.

    Kept tiny and swappable on purpose -- everything upstream of this is
    provider-agnostic and offline-testable.
    """
    import urllib.request

    # .strip() is not cosmetic. Secrets are stored byte-for-byte, and a
    # trailing newline or leading space from a paste is the single most common
    # cause of a 401 that looks like a bad key but is not.
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    model = (os.environ.get("WX_MODEL") or "claude-sonnet-4-5").strip()

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
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            # Surface WHICH failure this is. A traceback ending in "401" tells
            # you almost nothing; the API's own message distinguishes a bad key
            # from a wrong model name from a spend limit. The response body
            # never contains the key itself.
            try:
                body = exc.read().decode("utf-8", "replace")[:600]
            except Exception:  # noqa: BLE001
                body = ""
            raise LLMError(exc.code, body, model) from None
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
        # The dead-man switch firing is the case that most needs an explanation:
        # a silent 5:45am with no post and no reason is indistinguishable from
        # the agent being broken.
        write_status("aborted — data unavailable", "\n".join(problems), bundle, slot,
                     hint="No post went out, deliberately. A forecast built on "
                          "half its inputs is worse than silence at 5:45am. If "
                          "this repeats, check state/selftest-latest.md for which "
                          "source is down.")
        return 0

    if bundle.get("life_safety_alerts") and slot in ("school_call", "evening"):
        events = sorted({a["event"] for a in bundle["life_safety_alerts"]})
        print(f"life-safety alert(s) active {events} -- composing as life_safety")
        slot = "life_safety"

    if llm is None:
        try:
            llm = _llm_from_env()
        except RuntimeError as exc:
            # A missing key is a configuration state, not a bug. Crashing here
            # produced a red X whose only explanation lived in a log that is
            # genuinely hard to read after the fact.
            write_status("not configured", str(exc), bundle, slot,
                         hint="Add ANTHROPIC_API_KEY under Settings > Secrets and "
                              "variables > Actions > Secrets. Nothing else is missing.")
            print(f"ABORT -- {exc}")
            return 0
    try:
        text = CO.compose(bundle, llm, post_type=slot)
    except LLMError as exc:
        write_status(f"model call failed (HTTP {exc.status})", str(exc), bundle, slot,
                     hint=LLMError.HINTS.get(exc.status, ""))
        print(f"ABORT -- {exc}")
        return 0

    # Strip the machine tells before the gate sees it, so the guardrail's
    # dash check only fires if the sanitizer somehow missed something.
    text = SAN.clean(text)

    verdict, reasons = G.evaluate(bundle, text, first_30_days=first_30_days,
                                  calibrated=calibrated)
    print(f"guardrails: {verdict.upper()}")
    for r in reasons:
        print(f"  - {r}")

    os.makedirs("output", exist_ok=True)
    with open(os.path.join("output", "draft.txt"), "w") as fh:
        fh.write(text)
    _archive_draft(text, bundle, slot, verdict)
    with open(os.path.join("output", "bundle.json"), "w") as fh:
        json.dump(bundle, fh, indent=2, default=str)

    if verdict == G.BLOCK:
        print("BLOCKED -- nothing published. Draft saved to output/draft.txt")
        write_status("blocked", "\n".join(reasons), bundle, slot, draft=text)
        return 0
    if verdict == G.REVIEW:
        print("HELD FOR REVIEW -- draft saved to output/draft.txt")
        # A review gate nobody sees is not a safety mechanism. Open an issue so
        # the held draft actually reaches a human.
        write_status("held for review", "\n".join(reasons), bundle, slot, draft=text)
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


def write_status(state, detail, bundle=None, slot=None, hint=None, draft=None):
    """Leave a readable record of what this run did, committed to the repo.

    The self-test learned this the hard way: GitHub's raw logs sit behind
    short-lived signed URLs and the API log endpoint needs a token, so a failure
    is oddly hard to read after the fact. This runs twice a day, so it needs the
    same treatment even more.
    """
    import os as _os
    path = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
        "state", "forecast-status.md")
    L = [f"# Forecast run — {state}", ""]
    L.append(f"When: {C.local_now().isoformat(timespec='seconds')} (Mountain)")
    if slot:
        L.append(f"Slot: `{slot}`")
    L.append("")
    if detail:
        L.append("## Detail")
        L.append("")
        L.append("```")
        L.append(str(detail).strip()[:3000])
        L.append("```")
        L.append("")
    if hint:
        L.append(f"**What to do:** {hint}")
        L.append("")
    if bundle:
        sl = (bundle.get("snow_line") or {}).get("representative_ft")
        L.append("## What the data looked like")
        L.append("")
        L.append(f"- Snow line: {sl if sl else 'no precipitation forecast'}")
        L.append(f"- Alerts: {[a['event'] for a in (bundle.get('alerts') or [])] or 'none'}")
        L.append(f"- Missing sources: {bundle.get('missing') or 'none'}")
        if bundle.get("pass_card"):
            L.append("- Pass forecast: built")
        L.append("")
    if draft:
        L.append("## Draft")
        L.append("")
        L.append("```")
        L.append(draft.strip()[:6000])
        L.append("```")
    try:
        _os.makedirs(_os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("\n".join(L) + "\n")
        print(f"Wrote {path}")
    except Exception as exc:  # noqa: BLE001
        print(f"could not write status file: {exc}")


def _archive_draft(text, bundle, slot, verdict):
    """Keep every draft in state/drafts/ so a week of them reads in one place.

    The review issues are the notification; this is the archive. Reading seven
    drafts side by side is how the voice actually gets tuned, and scrolling
    seven separate issues is a worse way to do it.
    """
    import os as _os
    root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    d = _os.path.join(root, "state", "drafts")
    name = f"{bundle.get('post_for_date', bundle.get('local_date'))}-{slot}.md"
    try:
        _os.makedirs(d, exist_ok=True)
        with open(_os.path.join(d, name), "w") as fh:
            fh.write(f"# {bundle.get('post_for_weekday')}, "
                     f"{bundle.get('post_for_date')}, {slot}\n\n")
            fh.write(f"Verdict: `{verdict}` | Snow line: "
                     f"{(bundle.get('snow_line') or {}).get('representative_ft', 'n/a')} | "
                     f"Alerts: {[a['event'] for a in (bundle.get('alerts') or [])] or 'none'}\n\n")
            fh.write("---\n\n")
            fh.write(text.strip() + "\n")
        print(f"Archived draft -> state/drafts/{name}")
    except Exception as exc:  # noqa: BLE001
        print(f"could not archive draft: {exc}")


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
    try:
        _code = main()
    except Exception:
        import traceback
        _tb = traceback.format_exc()
        print(_tb)
        write_status("crashed", _tb)
        _code = 1
    sys.exit(_code)
