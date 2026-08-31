"""
The composer: data bundle + persona prompt -> post text.

Two design decisions worth stating.

FIRST, the bundle is rendered to compact, labelled text rather than dumped as
raw JSON. A model handed 500 hourly rows will find patterns in them that are
not there. A model handed "Vallecito, 7,650 ft: 0.42in snow 6pm-midnight, snow
line about 7,200 falling" reasons about the actual forecast. The rendering is
where a lot of the quality lives.

SECOND, the composer is told what it does NOT have. Every missing source is
listed explicitly in the prompt, because an absence that is stated does not get
filled in, and an absence that is merely implied does.

The LLM call is injected rather than hardcoded so the whole pipeline is
testable offline and so swapping providers later touches one function.
"""

import json
import os

from . import constants as C

PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


def load_system_prompt():
    with open(os.path.join(PROMPT_DIR, "system.md")) as fh:
        return fh.read()


def render_bundle(bundle, post_type="school_call"):
    """Turn the bundle into the compact brief the model actually reads."""
    L = []
    A = L.append

    A(f"POST TYPE: {post_type}")
    A(f"LOCAL DATE/TIME: {bundle.get('generated_at')}  (season: {bundle.get('season')})")
    A("")

    # --- alerts first: they change what kind of post this is ---
    alerts = bundle.get("alerts") or []
    if alerts:
        A("ACTIVE NWS ALERTS (from the Grand Junction office):")
        for a in alerts:
            zones = ", ".join(a.get("zones", []))
            zone_note = ""
            if zones == C.ZONE_VALLECITO:
                zone_note = "  [COZ019 ONLY -- Vallecito and up, NOT Durango/Bayfield]"
            elif zones == C.ZONE_ANIMAS:
                zone_note = "  [COZ022 ONLY -- Durango/Bayfield, NOT Vallecito]"
            A(f"  - {a['event']} ({zones}){zone_note}")
            A(f"    {a.get('headline','')}")
            A(f"    onset {a.get('onset')}  expires {a.get('expires')}")
        A("")
    else:
        A("ACTIVE NWS ALERTS: none for COZ019 or COZ022.")
        A("")

    # --- the snow line: the signature number ---
    sl = bundle.get("snow_line")
    if sl:
        A("SNOW LINE (derived, UNCALIBRATED HEURISTIC -- hedge it):")
        A(f"  representative {sl['representative_ft']} ft, {sl['trend']} "
          f"({sl['start_ft']} -> {sl['end_ft']} ft)")
        A(f"  precipitating hours: {sl['hours_with_precip']}, "
          f"{sl['first_precip_hour']} to {sl['last_precip_hour']}")
        A("")
        types = bundle.get("precip_type_by_band") or {}
        A("PRECIP TYPE BY BAND:")
        for key in C.BAND_ORDER:
            t = types.get(key)
            if t:
                A(f"  {t['label']} ({t['elevation_ft']} ft): {t['precip_type']} "
                  f"[{t['feet_above_snow_line']:+d} ft vs line]")
        A("")
    else:
        A("SNOW LINE: no precipitation forecast, so no snow line. Do not state one.")
        A("")

    # --- per-band forecast ---
    A("FORECAST BY ELEVATION BAND (Open-Meteo, elevation-corrected):")
    for key in C.BAND_ORDER:
        b = bundle.get("bands", {}).get(key) or {}
        if not b.get("ok"):
            A(f"  {key}: UNAVAILABLE -- do not forecast for this band")
            continue
        s = b.get("summary") or {}
        A(f"  {b['label']} ({b['elevation_ft']} ft, zone {b['nws_zone']}):")
        A(f"    next 48h totals: {s.get('total_snow_in', 0)}in snow, "
          f"{s.get('total_precip_in', 0)}in liquid")
        for blk in (s.get("blocks") or [])[:8]:
            A(f"    {blk['from']} -> {blk['to']}: "
              f"{blk['temp_f_min']}-{blk['temp_f_max']}F, "
              f"snow {blk['snow_in']}in, liquid {blk['precip_in']}in, "
              f"gust {blk['gust_mph_max']}mph, pop {blk['pop_max']}%")
    A("")

    # --- model disagreement: this IS the uncertainty statement ---
    dis = bundle.get("model_disagreement")
    if dis:
        A(f"MODEL DISAGREEMENT at Vallecito: {dis['level']}")
        A(f"  {dis['low_model']} {dis['low_snow_in']}in ... "
          f"{dis['high_model']} {dis['high_snow_in']}in "
          f"(spread {dis['spread_in']}in)")
        A(f"  all models: {dis['all']}")
        A("  -> Name the models and their disagreement. Do not average them.")
        A("")

    # --- ground truth ---
    home = bundle.get("home_snotel")
    if home:
        A(f"HOME SNOTEL ({home['name']}, {home['elev_ft']} ft):")
        A(f"  SWE {home['swe_in']}in, {home['pct_of_median']}% of median, "
          f"depth {home['snow_depth_in']}in, temp {home['temp_f']}F "
          f"(as of {home['as_of']})")
    basin = bundle.get("basin")
    if basin:
        A(f"BASIN ({basin['basin']}): {basin['pct_of_median']}% of median "
          f"across {basin['station_count']} stations, range {basin['range']}")
    if bundle.get("snotel"):
        A("OTHER SNOTEL:")
        for k, s in bundle["snotel"].items():
            if k == C.HOME_SNOTEL or s.get("swe_in") is None:
                continue
            A(f"  {s['name']} ({s['elev_ft']}ft): {s['swe_in']}in SWE, "
              f"{s['pct_of_median']}% of median")
    A("")

    flow = bundle.get("streamflow") or {}
    live_flow = {k: v for k, v in flow.items() if v.get("cfs") is not None}
    if live_flow:
        A("STREAMFLOW:")
        for k, v in live_flow.items():
            A(f"  {v['name']}: {v['cfs']} cfs")
    res = bundle.get("reservoir")
    if res:
        A(f"VALLECITO RESERVOIR: {res['storage_af']} AF, {res['pct_full']}% of full pool"
          + (f", elev {res['elevation_ft']} ft" if res.get("elevation_ft") else ""))
    A("")

    if bundle.get("pass_card"):
        A("PASSES AND ROADS (CDOT). 'The pass is closed' unqualified means Red")
        A("Mountain in Durango and Wolf Creek in Bayfield -- always name which:")
        A(bundle["pass_card"])
        A("")

    obs = bundle.get("observed")
    if obs:
        A("WHAT ACTUALLY FELL (for the totals post):")
        if obs.get("cocorahs_block"):
            A("  Station reports, already ranked -- print these VERBATIM, in this order:")
            for line in obs["cocorahs_block"].splitlines():
                A(f"    {line}")
        for item in obs.get("scored", []):
            for band, d in (item.get("score", {}).get("per_band") or {}).items():
                A(f"  {band}: you called {d['predicted_range_in']}\", it came in "
                  f"{d['observed_in']}\" -- {d['direction']}")
        tr = obs.get("track_record") or {}
        if tr.get("verified_events"):
            A(f"  Track record so far: {tr['verified_events']} events, "
              f"mean hit rate {tr.get('mean_hit_rate')}")
        A("")

    if bundle.get("afd_excerpt"):
        A("GRAND JUNCTION FORECAST DISCUSSION (the NWS forecaster's own reasoning --")
        A("read it for which model they trust today and why. DO NOT QUOTE IT.):")
        A(bundle["afd_excerpt"][:3000])
        A("")

    cz = bundle.get("caic_zone")
    if cz:
        A(f"CAIC ZONE: {cz.get('zone_name')} -- link it, never interpret it.")
        A("")

    missing = bundle.get("missing") or []
    if missing:
        A("DATA YOU DO NOT HAVE TODAY (say nothing about these; do not estimate):")
        for m in missing:
            err = (bundle.get("sources", {}).get(m) or {}).get("error")
            A(f"  - {m}: {err}")
        A("")

    return "\n".join(L)


def build_messages(bundle, post_type="school_call", recent_posts=None,
                   yesterday_forecast=None, extra_instruction=None):
    """Assemble the full model input."""
    system = load_system_prompt()
    parts = [render_bundle(bundle, post_type)]

    if recent_posts:
        parts.append("YOUR LAST FEW POSTS (do not repeat their openers, "
                     "phrasing or structure):\n" +
                     "\n---\n".join(p[:600] for p in recent_posts[-4:]))

    if yesterday_forecast:
        parts.append(
            "YESTERDAY YOU FORECAST THIS, and here is what actually happened. "
            "If you missed, say so plainly, give the physical mechanism, and "
            "find the upside. Do not apologize:\n"
            + json.dumps(yesterday_forecast, indent=2))

    task = {
        "school_call": (
            "Write the morning school call. It publishes at 5:45am and the "
            "districts decide by 6:30, so lead with what a parent driving the "
            "501 or the 240 needs. Give the snow line in feet. Walk the bands "
            "in order. Say plainly which routes are the question this morning, "
            "and that the districts decide by 6:30 -- never announce a closure."),
        "evening": (
            "Write the evening look. Pattern first, then the next 3-5 days. No "
            "snow amounts beyond day 3."),
        "storm_setup": (
            "Write the storm setup post. Emotion-first opener with the brake in "
            "the same sentence. Name the pattern in local terms. Go model by "
            "model with your verdict on each. Hard clock windows. Amounts by "
            "band as ranges. Mandatory caveat block."),
        "totals": (
            "Write the totals post. Lead with a reaction, then the reports, "
            "then the honest scoring of what you called. End with the question."),
        "life_safety": (
            "Write the life-safety post. Threat plainly in sentence one with the "
            "NWS product named and its exact valid times. Bound it "
            "geographically so people outside the box can relax. One plain "
            "imperative. Link the official product. Keep it under 200 words and "
            "keep it flat -- no caps, no emoji, no exclamation points."),
    }.get(post_type, "Write today's post.")

    parts.append("TASK: " + task)
    if extra_instruction:
        parts.append("ALSO: " + extra_instruction)

    return [{"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(parts)}]


def compose(bundle, llm, post_type="school_call", **kw):
    """`llm` is any callable taking messages -> string. Injected for testability."""
    return llm(build_messages(bundle, post_type=post_type, **kw))
