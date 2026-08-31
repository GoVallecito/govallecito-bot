"""
Assembles the day's data bundle -- the single object the composer reasons over.

DESIGN RULE: the bundle carries provenance for every value, and it is explicit
about what is MISSING. An LLM handed a dict with holes in it will cheerfully
fill them. An LLM handed a dict that says {"snotel": {"ok": false, "error":
"..."}} will not, because the absence is stated rather than implied.
"""

import datetime as _dt
from zoneinfo import ZoneInfo

from . import constants as C
from . import snowline as SL
from .sources import caic, cdot, nws, openmeteo, snotel, water

TZ = ZoneInfo(C.TIMEZONE)


def build(days=5, want_model_spread=True, calibration_offset_ft=0.0,
          fetchers=None):
    """Fetch everything and shape it for composition.

    `fetchers` lets tests inject fakes without touching the network. Production
    passes nothing.
    """
    f = {
        "alerts": nws.fetch_alerts,
        "afd": nws.fetch_afd,
        "bands": openmeteo.fetch_all_bands,
        "spread": openmeteo.fetch_model_spread,
        "snotel": snotel.fetch_stations,
        "flow": water.fetch_streamflow,
        "reservoir": water.fetch_reservoir,
        "caic": caic.resolve_zone,
        "roads": cdot.fetch_conditions,
    }
    if fetchers:
        f.update(fetchers)

    now = _dt.datetime.now(TZ)
    out = {
        "generated_at": now.isoformat(),
        "local_date": now.date().isoformat(),
        "season": _season(now),
        "sources": {},
        "missing": [],
        "bands": {},
    }

    def record(key, result):
        out["sources"][key] = result.to_dict() if hasattr(result, "to_dict") else result
        ok = getattr(result, "ok", bool(result))
        if not ok:
            out["missing"].append(key)
        return result

    alerts = record("alerts", f["alerts"]())
    out["alerts"] = alerts.data if alerts.ok else []
    out["life_safety_alerts"] = [a for a in (out["alerts"] or []) if a.get("life_safety")]

    afd = record("afd", f["afd"]())
    if afd.ok:
        # Trimmed hard. The AFD is long, and the composer needs the forecaster's
        # reasoning, not the boilerplate aviation and marine sections.
        out["afd_excerpt"] = _trim_afd(afd.data.get("text", ""))
        out["afd_issued"] = afd.data.get("issued")

    band_results = f["bands"](days=days)
    for key, res in band_results.items():
        record(f"band:{key}", res)
        band_meta = next(b for b in C.BANDS if b["key"] == key)
        entry = {"label": band_meta["label"], "elevation_ft": band_meta["elevation_ft"],
                 "nws_zone": band_meta["nws_zone"], "ok": res.ok}
        if res.ok:
            entry["summary"] = openmeteo.summarize_hourly(res.data)
            entry["snow_line_series"] = SL.series_from_payload(
                res.data, calibration_offset_ft=calibration_offset_ft)
        out["bands"][key] = entry

    # Snow line is derived from the Vallecito band -- the middle of our spread
    # and the point the product is named for.
    van = out["bands"].get("vallecito", {})
    out["snow_line"] = SL.summarize(van.get("snow_line_series") or [])
    out["precip_type_by_band"] = SL.classify_bands(out["snow_line"], C.BANDS)

    if want_model_spread:
        spread = f["spread"](next(b for b in C.BANDS if b["key"] == "vallecito"), days=days)
        out["model_spread"] = {}
        for model, res in spread.items():
            record(f"model:{model}", res)
            if res.ok:
                s = openmeteo.summarize_hourly(res.data)
                out["model_spread"][openmeteo.MODEL_LABELS.get(model, model)] = {
                    "total_snow_in": s["total_snow_in"] if s else None,
                    "total_precip_in": s["total_precip_in"] if s else None,
                }
        out["model_disagreement"] = _disagreement(out["model_spread"])

    sn = record("snotel", f["snotel"]())
    if sn.ok:
        out["snotel"] = sn.data
        out["basin"] = snotel.basin_percent_of_median(sn.data)
        out["home_snotel"] = sn.data.get(C.HOME_SNOTEL)

    flow = record("streamflow", f["flow"]())
    if flow.ok:
        out["streamflow"] = flow.data

    res = record("reservoir", f["reservoir"]())
    if res.ok:
        out["reservoir"] = res.data

    # Roads are best-effort. The pass card is valuable but it is not
    # load-bearing -- a missing CDOT key must never cost the forecast.
    roads = f["roads"]()
    out["sources"]["roads"] = roads.to_dict()
    if roads.ok:
        out["roads"] = roads.data
        out["pass_card"] = cdot.format_pass_card(roads.data)

    cz = f["caic"](C.VALLECITO["lat"], C.VALLECITO["lon"])
    out["sources"]["caic"] = cz.to_dict()
    out["caic_zone"] = cz.data if cz.ok else None

    return out


def _season(dt):
    """Colorado seasons as this audience experiences them, not astronomical ones.

    Copied from the model persona's own stated convention: Fall Sep-Nov,
    Winter Dec-Feb, Spring Mar-May, Summer Jun-Aug.
    """
    m = dt.month
    if m in (12, 1, 2):
        return "winter"
    if m in (3, 4, 5):
        return "spring"
    if m in (6, 7, 8):
        return "summer"
    return "fall"


AFD_SECTIONS_WANTED = ("SYNOPSIS", "SHORT TERM", "LONG TERM", "DISCUSSION",
                       "FIRE WEATHER", "HYDROLOGY")


def _trim_afd(text, limit=6000):
    """Keep the reasoning sections, drop aviation/marine/boilerplate."""
    if not text:
        return ""
    lines = text.splitlines()
    keep, on = [], False
    for line in lines:
        upper = line.strip().upper()
        if upper.startswith(".") or upper.startswith("&&"):
            on = any(s in upper for s in AFD_SECTIONS_WANTED)
        if on:
            keep.append(line)
    result = "\n".join(keep) if keep else text
    return result[:limit]


def _disagreement(spread):
    """Turn four model totals into the sentence the forecaster actually says.

    Model disagreement IS the uncertainty statement in this voice. A blended
    mean would erase the most characteristic thing the forecaster does.
    """
    vals = {k: v.get("total_snow_in") for k, v in (spread or {}).items()
            if v.get("total_snow_in") is not None}
    if len(vals) < 2:
        return None
    lo_k = min(vals, key=vals.get)
    hi_k = max(vals, key=vals.get)
    lo, hi = vals[lo_k], vals[hi_k]
    span = hi - lo
    if hi <= 0.1:
        level = "none -- all models dry"
    elif span < 0.15 * max(hi, 0.01):
        level = "tight"
    elif span < 0.5 * max(hi, 0.01):
        level = "moderate"
    else:
        level = "wide"
    return {
        "level": level,
        "low_model": lo_k, "low_snow_in": round(lo, 2),
        "high_model": hi_k, "high_snow_in": round(hi, 2),
        "spread_in": round(span, 2),
        "all": {k: round(v, 2) for k, v in vals.items()},
    }
