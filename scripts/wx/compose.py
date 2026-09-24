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
    with open(os.path.join(PROMPT_DIR, "system.md"), encoding="utf-8") as fh:
        return fh.read()


def render_bundle(bundle, post_type="school_call"):
    """Turn the bundle into the compact brief the model actually reads."""
    L = []
    A = L.append

    A(f"POST TYPE: {post_type}")
    A(f"THIS POST IS FOR: {bundle.get('post_for_weekday')}, "
      f"{bundle.get('post_for_date')}")
    A(f"  -> Open with the stamp {bundle.get('post_for_stamp')} and, if you name")
    A(f"     the day, it is {bundle.get('post_for_weekday')}. Use no other weekday.")
    A(f"COMPOSED AT: {bundle.get('generated_at')} (this is NOT necessarily the")
    A(f"  date the post is for, an evening run writes tomorrow's post)")
    A(f"SEASON: {bundle.get('season')}")
    A(f"DAY TYPE: {bundle.get('day_type')} (approximate calendar, hedge it)")
    if bundle.get("day_type") != "school day" and post_type == "school_call":
        A("  -> There is no school run to write about. Do NOT open with a bus,")
        A("     a district decision, or the drive in. Write the same forecast")
        A("     for whoever is actually out today: the drive to town, the boat")
        A("     ramp, hunting camp, the trail, the yard work window.")
    if bundle.get("is_late"):
        A(f"RUNNING LATE: composed at hour {bundle.get('composed_hour')}, past the")
        A("  5am target. Say so plainly in the first line, one short clause, no")
        A("  apology and no explanation. 'Late start this morning,' and move on.")
    A("")

    # Anti-repetition. Three consecutive drafts opened "Morning, its <day>."
    # and closed with a near identical question to the reader.
    recent = bundle.get("recent_posts") or []
    if recent:
        A("YOUR LAST FEW POSTS OPENED AND CLOSED LIKE THIS:")
        for r in recent:
            A(f"  {r.get('date')} opened: {r.get('opened')}")
            A(f"  {r.get('date')} closed: {r.get('closed')}")
        A("  -> These exact sentences are forbidden. Do not reuse their")
        A("     construction with different numbers or nouns swapped in.")
        A("     A new opener, a new pivot, a new closing question, every day.")
        A("")

    # --- alerts first: they change what kind of post this is ---
    alerts = bundle.get("alerts") or []
    if alerts:
        A("ACTIVE NWS ALERTS (from the Grand Junction office):")
        for a in alerts:
            zones = ", ".join(a.get("zones", []))
            zone_note = ""
            if zones == C.ZONE_VALLECITO:
                zone_note = "  [COZ019 ONLY, Vallecito and up, NOT Durango/Bayfield]"
            elif zones == C.ZONE_ANIMAS:
                zone_note = "  [COZ022 ONLY, Durango/Bayfield, NOT Vallecito]"
            A(f"  - {a['event']} ({zones}){zone_note}")
            A(f"    {a.get('headline','')}")
            A(f"    onset {a.get('onset')}  expires {a.get('expires')}")
        A("")
    else:
        A("ACTIVE NWS ALERTS: none for COZ019 or COZ022.")
        A("")

    # --- the snow line: the signature number ---
    sl = bundle.get("snow_line")
    if not sl:
        A("SNOW LINE: no precipitation forecast, so no snow line. Do not state one.")
        A("")
    else:
        if sl.get("above_terrain"):
            # Accurate and useless. See snowline.TERRAIN_CEILING_FT: the figure
            # is a real freezing level minus a real melt offset, but it sits
            # above the highest peak in the San Juans, so it describes ground
            # nobody stands on. Nine days of posts printed one, and to a local
            # reader a snow line above the summits reads as a broken
            # instrument even when the arithmetic behind it is right.
            # No figure appears in this branch, deliberately, not even as an
            # example of what not to write. The entire mechanism here is that
            # the model is not shown the number; spelling it out inside a
            # prohibition hands it back and makes it salient, and a negation
            # is the weakest instruction there is.
            A("SNOW LINE: higher today than anywhere anybody here goes.")
            A("  -> DO NOT STATE A SNOW LINE FIGURE. Not in feet, not rounded,")
            A("     not approximate, not 'well up above the passes'. You have")
            A("     not been given the number. It is above the passes, above")
            A("     the Weminuche, above every road, trail and drainage anyone")
            A("     is on today, so it is rain for all of them and the figure")
            A("     tells a reader nothing. Say that plainly, all rain")
            A("     everywhere including up high, and move on to what actually")
            A("     matters today.")
        else:
            A("SNOW LINE (derived, UNCALIBRATED HEURISTIC, hedge it):")
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

    # --- per-band forecast ---
    A("FORECAST BY ELEVATION BAND (Open-Meteo, elevation-corrected):")
    for key in C.BAND_ORDER:
        b = bundle.get("bands", {}).get(key) or {}
        if not b.get("ok"):
            A(f"  {key}: UNAVAILABLE. Do not forecast for this band")
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
    # The one personal number the post is allowed to use, and usually there
    # is not one. 2026-09-17 said the snow stake at the house was "still
    # sitting at 5 inches" on an all-rain day with the snow line at 14,000 ft.
    # Nothing was behind it. The persona asks for exactly one detail from your
    # own morning and tells you to rotate which one, so when the stake came up
    # the model filled the hole. Saying the hole is there is the fix: an
    # absence that is stated does not get filled in.
    gauge = bundle.get("home_gauge")
    if gauge:
        A("YOUR OWN GAUGE AND STAKE (hand-entered for this morning). These are")
        A("the ONLY numbers you may attribute to your gauge or your stake:")
        for k, v in gauge.items():
            if k == "for_date" or v is None:
                continue
            A(f"  {k}: {v}")
        A("")
    else:
        A("YOUR OWN GAUGE AND STAKE: NO READING TODAY.")
        A("  -> Nobody entered one, so you did not measure anything this")
        A("     morning. Your one personal detail must contain NO measurement")
        A("     today: the sky out the kitchen window, the drive, the dog, the")
        A("     woodpile, the truck, the yard. Never an inch figure for the")
        A("     stake and never a total for the gauge. Saying the gauge is dry")
        A("     or empty is fine; putting a number on it is not.")
        A("")

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

    # --- roads: the absence that was never stated --------------------------
    #
    # This block is unconditional and it is about every road, not only the
    # passes. Both of those were the bug.
    #
    # The road discipline used to live inside `if pass_card` under the heading
    # THE PASSES. A model applies a constraint to what the constraint names, so
    # it governed Coal Bank and Molas and said nothing about the 501, the 240,
    # the bus run or the pavement in town -- which is where four of the last
    # five drafts put their road claim. 2026-09-21 opened a paragraph with
    # "Dry roads for the bus run this morning," which is almost word for word
    # one of the examples system.md lists as forbidden.
    #
    # The old wording also said "say what the passes are GETTING," and got back
    # "The passes are getting wet pavement at most." That was the instruction
    # working as written. Present progressive is present tense, and a reader
    # can drive up and disprove it, which is the persona's own test. Nothing
    # here is phrased in the present.
    #
    # Same mechanism as the gauge block above, for the same reason: an absence
    # that is stated does not get filled in. sources["roads"] has been ok=false
    # every morning since CDOT withdrew public feed registration, but roads is
    # written into the bundle outside record(), so it never enters
    # bundle["missing"] and the DATA YOU DO NOT HAVE list below has never once
    # mentioned it. The forbidden forms are spelled out rather than gestured
    # at, because "do not report road status" and "dry roads for the bus run"
    # do not look like the same sentence to the thing writing them.
    if bundle.get("roads"):
        A("LIVE ROAD STATUS (CDOT). This IS data. State it flat, name CDOT as")
        A("the source, and do not soften it into a forecast.")
    else:
        A("LIVE ROAD STATUS: YOU HAVE NONE. Not for the passes, not for US-550")
        A("or US-160, not for the 501, the 240 or the Florida Road, and not for")
        A("the pavement in town. There is no road-status source in this bundle")
        A("and there was not one yesterday either.")
        A("  -> So you never write what a road IS. Not 'the passes are dry',")
        A("     not 'dry roads for the bus run', not 'wet pavement for the")
        A("     commute', not 'the 501 is fine', not 'clear conditions', and")
        A("     not 'the passes are getting wet pavement'. An adjective sitting")
        A("     in front of 'roads' or 'pavement' is the same claim with the")
        A("     verb left out, and that is the form that keeps getting through.")
        A("  -> Write what they will GET, in the future or the conditional,")
        A("     every time: 'the 501 should be fine for the bus run', \"I'd")
        A("     expect wet pavement by the afternoon commute\", 'Coal Bank")
        A("     should stay rain at pass level'. The test: if a reader could")
        A("     drive out the door and prove you wrong inside ten minutes, you")
        A("     needed 'should', \"I'd expect\" or \"looks like it'll\".")
        A(f"  -> Then send them to CDOT for the status: {C.CDOT_STATUS_URL}")
        A("     The forecast is yours. The status is theirs. Say which is which.")
    A("")

    if bundle.get("pass_card"):
        A("THE PASSES, FORECAST ONLY, under the road rule above. The three")
        A("US-550 passes close as a unit. 'The pass is closed' unqualified")
        A("means Red Mountain in Durango and Wolf Creek in Bayfield.")
        A(bundle["pass_card"])
        if bundle.get("passes_notable"):
            A("  -> A pass is getting enough that it belongs near the top.")
        A("")

    obs = bundle.get("observed")
    if obs:
        A("WHAT ACTUALLY FELL (for the totals post):")
        if obs.get("cocorahs_block"):
            A("  Station reports, already ranked, print these VERBATIM, in this order:")
            for line in obs["cocorahs_block"].splitlines():
                A(f"    {line}")
        for item in obs.get("scored", []):
            for band, d in (item.get("score", {}).get("per_band") or {}).items():
                A(f"  {band}: you called {d['predicted_range_in']}\", it came in "
                  f"{d['observed_in']}\", {d['direction']}")
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
        A(f"CAIC ZONE: {cz.get('zone_name')}, link it, never interpret it.")
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
            "in order. Say plainly which routes the weather puts in question "
            "this morning -- what they will GET, never what they are -- and "
            "that the districts decide by 6:30, never announce a closure."),
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
            "keep it flat, no caps, no emoji, no exclamation points."),
    }.get(post_type, "Write today's post.")

    parts.append("TASK: " + task)
    if extra_instruction:
        parts.append("ALSO: " + extra_instruction)

    return [{"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(parts)}]


def compose(bundle, llm, post_type="school_call", **kw):
    """`llm` is any callable taking messages -> string. Injected for testability."""
    return llm(build_messages(bundle, post_type=post_type, **kw))
