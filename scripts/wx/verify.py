"""
The forecast -> verify loop. This is the trust engine, and it is the thing
most amateur weather pages skip entirely.

Every forecast is written to state/forecast_log.json when it publishes. The
next morning, the observed totals come back from SNOTEL and the gauge, and the
prediction is scored against them. Three things fall out of that:

  1. THE VERIFY POST. "I called 3-7 for the Valley and it came in 2-4." Posting
     your own miss, with the physical mechanism, is what makes the hit
     believable. It also measurably does not hurt engagement -- a post
     admitting low skill scored 115 reactions against a 14-30 baseline for
     routine nowcasts.

  2. SNOW LINE CALIBRATION. The heuristic in snowline.py ships uncalibrated.
     Every verified event is one observation of "predicted line vs what
     actually happened at a known elevation," and after a season those fit an
     offset that is genuinely local. This is the loop that makes a hyperlocal
     forecaster better than a national model rather than merely closer to one.

  3. AN HONEST TRACK RECORD. Public, cumulative, and checkable.
"""

import datetime as _dt
import json
import os
import statistics

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_DIR = os.path.join(REPO_ROOT, "state")
FORECAST_LOG = os.path.join(STATE_DIR, "forecast_log.json")
CALIBRATION = os.path.join(STATE_DIR, "snowline_calibration.json")

# Below this many verified events the calibration stays off. Fitting an offset
# to four observations would be worse than not fitting one -- it would look
# principled while being noise.
MIN_EVENTS_TO_CALIBRATE = 20
# Never let the learned correction exceed this. A runaway offset from a bad
# season of observations should degrade the forecast a little, not invert it.
MAX_CALIBRATION_FT = 800.0


def _load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        backup = path + ".corrupt-backup"
        try:
            os.replace(path, backup)
            print(f"[verify] {path} unparseable ({exc}); backed up to {backup}")
        except OSError:
            print(f"[verify] {path} unparseable ({exc}) and backup failed")
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def record_forecast(bundle, predicted_by_band, post_id=None, note=None):
    """Log what we said, so tomorrow can score it.

    `predicted_by_band` is {band_key: {"snow_low_in": x, "snow_high_in": y}} --
    the ranges that actually appeared in the post, not the raw model numbers.
    We score what we published.
    """
    log = _load(FORECAST_LOG, {"forecasts": []})
    log["forecasts"].append({
        "id": f"{bundle['local_date']}-{len(log['forecasts'])}",
        "issued_at": bundle["generated_at"],
        "valid_date": bundle["local_date"],
        "post_id": post_id,
        "predicted": predicted_by_band,
        "snow_line_predicted_ft": (bundle.get("snow_line") or {}).get("representative_ft"),
        "model_disagreement": (bundle.get("model_disagreement") or {}).get("level"),
        "note": note,
        "verified": False,
        "observed": None,
        "score": None,
    })
    _save(FORECAST_LOG, log)
    return log["forecasts"][-1]["id"]


def verify_pending(observations, max_age_days=4):
    """Score every unverified forecast we now have observations for.

    `observations` is {band_key: {"snow_in": x, "snow_line_observed_ft": y|None}}
    assembled by the caller from SNOTEL, CoCoRaHS and the home gauge.
    """
    log = _load(FORECAST_LOG, {"forecasts": []})
    today = _dt.date.today()
    scored = []

    for fc in log["forecasts"]:
        if fc.get("verified"):
            continue
        try:
            valid = _dt.date.fromisoformat(fc["valid_date"])
        except Exception:  # noqa: BLE001
            continue
        age = (today - valid).days
        if age < 1 or age > max_age_days:
            continue

        per_band, hits = {}, []
        for band, pred in (fc.get("predicted") or {}).items():
            obs = (observations or {}).get(band, {})
            actual = obs.get("snow_in")
            lo, hi = pred.get("snow_low_in"), pred.get("snow_high_in")
            if actual is None or lo is None or hi is None:
                continue
            in_range = lo <= actual <= hi
            if actual < lo:
                miss, direction = lo - actual, "over-forecast"
            elif actual > hi:
                miss, direction = actual - hi, "under-forecast"
            else:
                miss, direction = 0.0, "in range"
            per_band[band] = {
                "predicted_range_in": [lo, hi],
                "observed_in": actual,
                "in_range": in_range,
                "miss_in": round(miss, 2),
                "direction": direction,
            }
            hits.append(in_range)

        if not per_band:
            continue

        fc["verified"] = True
        fc["observed"] = observations
        fc["score"] = {
            "bands_scored": len(per_band),
            "bands_in_range": sum(1 for h in hits if h),
            "hit_rate": round(sum(1 for h in hits if h) / len(hits), 2),
            "per_band": per_band,
            "snow_line_observed_ft": (observations or {}).get("snow_line_observed_ft"),
            "snow_line_error_ft": _line_error(fc, observations),
        }
        scored.append(fc)

    if scored:
        _save(FORECAST_LOG, log)
    return scored


def _line_error(fc, observations):
    pred = fc.get("snow_line_predicted_ft")
    obs = (observations or {}).get("snow_line_observed_ft")
    if pred is None or obs is None:
        return None
    return int(round(obs - pred))


def update_calibration():
    """Fit the snow-line offset from verified events. Conservative on purpose.

    A positive learned offset means the real line has been sitting HIGHER than
    predicted, so the heuristic is dropping it too far. The median of errors is
    used rather than the mean because a single blown event -- and there will be
    blown events -- should not move the constant much.
    """
    log = _load(FORECAST_LOG, {"forecasts": []})
    errors = [f["score"]["snow_line_error_ft"] for f in log["forecasts"]
              if f.get("verified") and (f.get("score") or {}).get("snow_line_error_ft") is not None]

    cal = {
        "events": len(errors),
        "min_events_required": MIN_EVENTS_TO_CALIBRATE,
        "active": False,
        "offset_ft": 0.0,
        "updated_at": _dt.datetime.now().isoformat(),
    }
    if len(errors) >= MIN_EVENTS_TO_CALIBRATE:
        med = statistics.median(errors)
        cal["active"] = True
        cal["offset_ft"] = round(max(-MAX_CALIBRATION_FT, min(MAX_CALIBRATION_FT, -med)), 1)
        cal["median_error_ft"] = round(med, 1)
        cal["mean_abs_error_ft"] = round(statistics.mean(abs(e) for e in errors), 1)
    _save(CALIBRATION, cal)
    return cal


def current_calibration():
    """The offset to hand snowline.py, and whether it is trustworthy yet."""
    cal = _load(CALIBRATION, {"active": False, "offset_ft": 0.0, "events": 0})
    return (cal.get("offset_ft", 0.0) if cal.get("active") else 0.0,
            bool(cal.get("active")))


def track_record(limit=None):
    """Public, cumulative honesty. Suitable for a pinned post or a site page."""
    log = _load(FORECAST_LOG, {"forecasts": []})
    verified = [f for f in log["forecasts"] if f.get("verified")]
    if limit:
        verified = verified[-limit:]
    if not verified:
        return {"verified_events": 0}
    rates = [f["score"]["hit_rate"] for f in verified]
    line_errs = [abs(f["score"]["snow_line_error_ft"]) for f in verified
                 if f["score"].get("snow_line_error_ft") is not None]
    return {
        "verified_events": len(verified),
        "mean_hit_rate": round(statistics.mean(rates), 2),
        "snow_line_mean_abs_error_ft": round(statistics.mean(line_errs)) if line_errs else None,
        "worst_miss": max(
            ((b, d["miss_in"]) for f in verified for b, d in f["score"]["per_band"].items()),
            key=lambda t: t[1], default=None),
    }
