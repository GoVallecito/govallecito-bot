# The Vallecito Forecaster (`scripts/wx/`)

An elevation-band forecaster for Vallecito Lake, Bayfield and Durango. Drops
into the existing `govallecito-bot` repo alongside the conditions-card bot and
shares its infrastructure: same GitHub Actions runner, same `DRY_RUN` switch,
same `FB_PAGE_ACCESS_TOKEN`, same state-commit-back pattern, same
concurrency lock. **It changes none of the existing files.**

## Why it is a separate product from the conditions card

The conditions bot answers "what is it doing at the lake right now." A
conditions card with a missing lake level is still a useful post. The
forecaster answers "what will it do, at your elevation, before you decide
whether to drive the 501" — and a forecast built on half its inputs is worse
than silence, because people make school and travel decisions on it at 5:45am.
So this one has a dead-man switch the conditions bot correctly does not need.

## The thesis in one paragraph

A ~5,000 ft spread lives inside one nominal forecast area — Durango 6,500,
Bayfield 6,900, Vallecito 7,650, the Weminuche above 10,000 — and every
national product resolves "Durango" to the airport at 6,689 ft, which is not
even in Durango. Open-Meteo's `elevation` parameter lets one grid cell be
re-derived at four heights, so the post can give a **snow line in feet** and
say what each band actually gets. Bayfield School District's own closure policy
formally singles out "northern bus routes (e.g., Vallecito)" as a separate
weather regime. Nobody serves that. That is the whole product.

## Layout

```
scripts/wx/
  constants.py       verified zone ids, station ids, elevation bands
  sources/
    http.py          one HTTP helper + the SourceResult provenance wrapper
    nws.py           alerts for BOTH zones, the GJT forecast discussion
    openmeteo.py     the elevation-band engine + 4-model spread
    snotel.py        NRCS, home station 843, computed basin percent-of-median
    water.py         USGS streamflow + CDSS reservoir
    caic.py          avalanche zone resolution (by name, never hardcoded)
  snowline.py        the signature derivation. Ships UNCALIBRATED, on purpose.
  bundle.py          assembles the day's data with provenance and gaps named
  compose.py         renders the brief, builds the messages
  prompts/system.md  the persona
  guardrails.py      pass / review / block
  verify.py          the forecast->verify loop and snow-line calibration
  publish.py         site markdown + Facebook page + group
  run_forecast.py    orchestrator (the entry point Actions calls)
  selftest.py        live endpoint check -- RUN THIS FIRST
tests/               39 offline tests, no network required
```

## Three things to understand before trusting it

**1. None of the adapters have ever talked to a real server.** Every weather
host is blocked by an egress allowlist in the environment this was written in —
api.weather.gov, Open-Meteo, SNOTEL, USGS, CDSS, CAIC, all 35 tested. GitHub
Actions has open outbound HTTPS, so `wx-selftest.yml` is the first real test.
Run it before anything else. This is the same honest caveat the existing bot's
README carries about its own lake-level parsing, for the same reason.

**2. The snow line is a heuristic and it says so everywhere it appears.** Snow
falls below the freezing level while it melts; how far below depends on
humidity and precipitation rate. The coefficients in `snowline.py` are
physically reasonable starting values, not fitted constants. Until 20 verified
events exist, calibration stays off and the guardrails require the post to
hedge the number. Calibrating it against your own gauge over a season is the
loop that makes this better than a national model rather than merely closer to
one.

**3. The gate fails toward silence.** Missing a required band aborts the run
before the model is even called. Anything touching a life-safety alert, a burn
scar, or avalanches holds for a human. For the first 30 days everything holds.

## Running it

```bash
python -m pytest tests/ -q                 # offline, no keys needed
python scripts/wx/selftest.py              # live endpoints (needs open egress)
FORCE_SLOT=school_call DRY_RUN=true python scripts/wx/run_forecast.py
```

## Configuration

| Name | Kind | Purpose |
|---|---|---|
| `FB_PAGE_ACCESS_TOKEN` | secret | already exists for the conditions bot |
| `ANTHROPIC_API_KEY` | secret | the composer |
| `DRY_RUN` | variable | already exists; governs both bots |
| `WX_FIRST_30_DAYS` | variable | `true` holds every post for review |
| `WX_SITE_DIR` | variable | where to write the govallecito.com markdown |
| `FB_GROUP_ID` | variable | optional; group publishing is Meta-restricted |
| `CDOT_API_KEY` | secret | optional, and **currently unobtainable** — CDOT withdrew public feed registration. The passes are forecast instead. |
| `WX_MODEL` | variable | optional model override |
