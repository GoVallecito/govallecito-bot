# CLAUDE.md

Orientation for Claude Code sessions in this repo. Everything below was read out
of the code, the workflows, `README.md`, `README-WX.md`, `SETUP.md` and
`scripts/wx/prompts/system.md`. When this file and those disagree, they win and
this file is wrong.

## What this is

Two automated publishers for **GoVallecito**, sharing one repo, one `DRY_RUN`
switch, one Actions runner and one `state/` directory:

1. **The conditions bot** (`scripts/`) — posts a branded 1080x1080 "conditions
   card" (lake level, weather, fire status, streamflow) to the GoVallecito
   Facebook Page twice a day, plus an independent emergency-alert path.
2. **The Vallecito Forecaster** (`scripts/wx/`) — an elevation-band forecast for
   **Durango (6,500'), Bayfield (6,900'), Vallecito (7,650'+), the Weminuche
   (10,000'+)** and the passes, written by an LLM from a provenance-carrying data
   bundle, published to `site/weather/` (govallecito.com) and the Facebook Page.

**Who reads it:** people who live around Vallecito Lake, Bayfield and Durango,
Colorado. The 5:45am "school call" is read by parents deciding whether to put a
kid on a bus up the 501, before the districts decide at 6:30. Treat every change
to output as safety-relevant: a wrong forecast at 5:45am is not recoverable,
silence is.

## Architecture map

```
scripts/                 the conditions bot (main.py is the entry point)
  fetch_conditions.py    weather/lake/flow/fire, via govallecito.com's Worker
  generate_post_text.py  caption + card data; also the emergency-alert variant
  render_card.py         the 1080x1080 card (PIL + numpy)
  check_emergency.py     the every-10-minutes alert path
  check_engagement.py    48h+ engagement -> state/content_preferences.json
scripts/wx/              the forecaster
  constants.py           zones (COZ019 Vallecito, COZ022 Durango/Bayfield),
                         bands, TIMEZONE, SLOT_WINDOWS, school calendar
  sources/               nws, openmeteo (the elevation engine), snotel, water,
                         caic, cdot, cocorahs, http (SourceResult provenance)
  snowline.py            the signature derivation; ships UNCALIBRATED
  bundle.py              assembles the day's data, names what is MISSING
  compose.py             renders the brief + builds the model messages
  prompts/system.md      THE PERSONA. Most of the quality lives here.
  guardrails.py          the gate: PASS / REVIEW / BLOCK
  sanitize.py            strips em dashes and other machine tells pre-gate
  site.py                site markdown, feed.json, _pending staging, promote
  publish.py             Facebook page/group (respects DRY_RUN)
  notify.py              opens the "[review] <slot> draft for <date>" issue
  ledger.py              per-day idempotency: one post per slot per day
  verify.py / run_verify.py     scoring + snow-line calibration
  run_forecast.py        orchestrator Actions calls
  run_storm_watch.py, selftest.py, promote_draft.py, email_digest.py
tools/
  draft-lint.mjs         deterministic draft linter (Node 20+, zero deps)
  draft-lint.test.mjs    its fixtures-based self-test (`npm test`), and the
                         cross-gate parity check over fixtures/road-cases.json
  road-gate-probe.py     runs that corpus through guardrails, so `npm test`
                         (the only suite CI runs) checks BOTH road gates
  fixtures/road-cases.json  the shared road-status corpus
  lint-review-issue.sh   prepends the lint verdict to the review issue
  daily-audit.sh         the daily deterministic review
state/                   the ONLY memory across runs; workflows commit it back
site/weather/            published forecasts + feed.json (the site reads this)
site/weather/_pending/   HELD drafts, awaiting promotion. The feed ignores them.
site-astro/              copies of the Astro pages that belong in the SITE repo
config/                  hand-edited inputs (emergency_override.json, almanac)
tests/                   217 offline pytest tests, no network, no API key
```

## Workflows (all in `.github/workflows/`)

Cron is UTC; Mountain equivalents given for MDT (UTC-6) and MST (UTC-7). Most
runners re-check the clock in `America/Denver` themselves, so schedules survive
DST without YAML edits.

| Workflow | Schedule (UTC → MT) | What it does | Publishes? |
|---|---|---|---|
| `daily-post.yml` | `0 * * * *` hourly | Conditions card; `scripts/main.py` acts only in the 7am and 2pm Denver hours | **Yes**, FB Page (unless `DRY_RUN`); commits state |
| `emergency-alert.yml` | `*/10 * * * *`; also **push to `main` touching `config/emergency_override.json`** | Flood/fire/evac/disaster check, posts at once | **Yes**, FB Page (unless `DRY_RUN`); commits state |
| `engagement-check.yml` | `0 10` → 04:00 MDT / 03:00 MST | Engagement on 48h+ posts, recomputes preferences | No; commits state |
| `forecast.yml` | `5,20,35,50 11-15` → 05:05–09:50 MDT / 04:05–08:50 MST; `5,35 1-6` → 19:05–00:35 MDT / 18:05–23:35 MST; `45 * * * *` heartbeat | The forecaster. Windows + ledger, because GitHub drops scheduled runs | **Yes**, `site/weather/` + FB Page on PASS; commits `state/` and `site/`; pings `SITE_DEPLOY_HOOK` |
| `verify.yml` | `30 15` → 09:30 MDT / 08:30 MST | Scores yesterday, adds a calibration point, drafts the totals post | Same gate as forecast; commits state |
| `storm-watch.yml` | `10 17`, `10 22`, `10 03` → ~11:10/16:10/21:10 MDT (~10:10/15:10/20:10 MST) | Storm setup post when a system shows 2–5 days out | Same gate as forecast; commits state |
| `daily-audit.yml` | `15 15` and `15 16` → 09:15/10:15 MDT, 08:15/09:15 MST (script skips runs before 09:00 local) | Runs `npm test`, lints the day's draft onto its review issue, or opens a `[miss]` issue | No public output; issues only |
| `wx-selftest.yml` | `17 13 * * 1` → Mon 07:17 MDT / 06:17 MST | Live endpoint check; writes `state/selftest-latest.md` | No; commits state |
| `site-publish.yml` | **manual only** | `promote_draft.py`: moves one reviewed post from `_pending/` to `site/weather/`, rebuilds the feed | **Yes**, to the site only |

## The draft pipeline, end to end

1. **Slot check** — `run_forecast.determine_slot`: is the local hour inside
   `SLOT_WINDOWS` (`school_call` 05–09, `evening` 19–22), is the slot enabled
   (`WX_SLOTS`, default `school_call` only), and has `ledger.py` already spent
   this day+slot?
2. **Bundle** — `bundle.build()` fetches every source, carries provenance, and
   lists what is missing. `guardrails.require_or_abort()` is the dead-man switch:
   no alerts or a missing required band aborts **before** the model is called.
3. **Compose** — `compose.render_bundle()` turns the bundle into a compact
   labelled brief (never raw JSON) and states every absence out loud; the persona
   is `scripts/wx/prompts/system.md`.
4. **Sanitize + gate** — `sanitize.clean()` then `guardrails.evaluate()` returns
   PASS / REVIEW / BLOCK. A BLOCK that is about the *writing* rather than the
   *data* (`guardrails.text_fixable`) gets exactly one rewrite with
   `correction_note()`.
5. **Hold** — on REVIEW or BLOCK: archive to `state/drafts/`, stage the exact
   post to `site/weather/_pending/`, and `notify.review_requested()` opens a
   `[review]`/`[block]` issue. The day is spent **only after** a human was told.
6. **draft-lint** — `tools/lint-review-issue.sh` runs `tools/draft-lint.mjs` on
   the staged draft and prepends the verdict to that issue, labelling it
   `lint-clean` or `lint-failed`. `daily-audit.yml` repeats this daily.
7. **Publish** — on PASS: `site.publish()` writes the markdown and rebuilds
   `feed.json`, then the card and the Facebook post. A held draft goes live only
   via `promote_draft.py` / the `site-publish.yml` workflow — never recomposed,
   because the thing reviewed must be the thing published.

**Current policy: first 30 days, review everything.** `WX_FIRST_30_DAYS`
(repo variable; **defaults to true** when unset) makes `guardrails.evaluate()`
escalate every draft to REVIEW — `scripts/wx/guardrails.py:398`, read in
`run_forecast.py:233`, `run_verify.py:84`, `run_storm_watch.py:83`. Documented in
`SETUP.md` step 3 and `README-WX.md`. Nothing auto-publishes while it is on.

## Hard rules

- **Never edit `state/` by hand.** It is workflow-committed memory (ledger,
  forecast log, calibration, drafts, run logs). The one documented exception is
  `state/home_gauge.json`, which the owner maintains by hand (`state/README.md`).
- **Secrets by NAME only, never values.** In use: `FB_PAGE_ACCESS_TOKEN`,
  `ANTHROPIC_API_KEY`, `CDOT_API_KEY`, `SITE_DEPLOY_HOOK`,
  `HEALTHCHECK_URL_{FORECAST,VERIFY,STORM_WATCH,SELFTEST,DAILY_POST,EMERGENCY_ALERT,ENGAGEMENT_CHECK}`,
  the built-in `GITHUB_TOKEN`, and `SMTP_USER`/`SMTP_PASSWORD` for the digest.
  Variables: `DRY_RUN`, `FB_PAGE_ID`, `FB_GROUP_ID`, `WX_FIRST_30_DAYS`,
  `WX_SITE_DIR`, `WX_MODEL`, `WX_SLOTS`. Never print, commit or echo a value.
- **Road status is CDOT's, never ours** (see PR #35). There is no public CDOT
  feed, so the passes are *forecast*. A draft may never say what a road **is** —
  not "the passes are dry", not "dry roads for the bus run", not "clear
  conditions", not present progressive ("are getting wet pavement"). Only
  forecast/conditional: "should", "I'd expect", "looks like it'll", then link
  cotrip.org for status. Enforced in three places that must agree:
  `guardrails.road_status_claim()`, the roads block in `compose.render_bundle()`,
  and rule 2 of `tools/draft-lint.mjs`. The guardrail relaxes automatically if
  real CDOT data ever lands in the bundle.
  **Both gates are pinned to one corpus, `tools/fixtures/road-cases.json`** —
  add a case there, never to a single suite. They are also checked against the
  drafts this repo has actually recorded: nothing in `site/weather/` may be
  flagged (it published, so a flag is a false positive on known good copy), and
  held drafts must match `tests/fixtures/road_baseline.json` sentence for
  sentence. After an intended change run
  `tests/fixtures/road_baseline_refresh.py` and read the diff — that diff is
  the review. These rules are shallow syntax done
  with regexes, so a change that looks local usually is not: five review rounds
  on PR #37 found 31 defects, about two thirds of them regressions introduced by
  the previous round's fix. The corpus is what holds that rate down, and each
  case carries a note saying what it guards.
- **Other non-negotiables** (persona + gate, BLOCK unless noted): never claim a
  meteorology credential; never state a number, event or trend the brief does not
  contain; never a bare percentage (only "% of median" / "of full pool"); never
  announce a school closure or speak for the NWS; no politics; no lake-effect
  snow at Vallecito; no em/en dashes; "Florida" is fluh-REE-duh; no gauge or
  snow-stake *figure* unless `state/home_gauge.json` has one. Life-safety alerts,
  burn scars (416 / Missionary Ridge) and avalanches always escalate to REVIEW —
  link CAIC, never interpret it.
- Where `guardrails.py` and `draft-lint.mjs` disagree, **`prompts/system.md`
  decides** and the linter is the one that is wrong (both files say so).

## How to test

```bash
pip install -r requirements.txt && pip install pytest   # pytest is not pinned
python -m pytest tests/ -q      # 217 passed, offline, no keys, no network
npm test                        # 70 subtests: node --test tools/draft-lint.test.mjs
```

Both were run in this repo and both pass. In Claude Code on the web,
`.claude/hooks/session-start.sh` installs the dependencies for you, so normally
the `pip` line is not needed. It runs **async**, so a very early first command can
still hit `No module named pytest` — run the `pip` line, or wait a few seconds and
retry. Node needs nothing installed: `package.json` declares zero dependencies.

On Windows use `py -m pytest tests/ -q`
and `py -m pip …`; Windows ships no IANA tz database, so `zoneinfo` cannot resolve
`America/Denver` and `constants.py` fails at import without `tzdata` — it is
already in `requirements.txt` behind a `sys_platform == "win32"` marker.

## Cost rule: $0 extra spend

The owner's budget for extra spend is **zero**. Therefore:

- **Never call the Anthropic API and never run the live composer.**
  `scripts/wx/run_forecast.py`, `run_verify.py` and `run_storm_watch.py` call a
  paid API key. **`DRY_RUN=true` does not help** — it only gates the Facebook
  post; the model call happens first and bills either way.
- Verify changes with **fixtures and injected fakes only**. `compose.compose()`
  and `run(llm=...)` take the LLM as an argument precisely so the whole pipeline
  is testable offline; `tests/` and `tools/fixtures/` cover the gate, the linter,
  the site writer and the runners.
- **Never add `ANTHROPIC_API_KEY` to a cloud/session environment.**
- **Do not trigger workflows manually** (no `gh workflow run`, no dispatch).
  `forecast`/`verify`/`storm-watch` bill the API; `wx-selftest` hits live
  endpoints; the posting workflows can reach Facebook.

## Working conventions

- **Branch + PR against `main`. Never push to `main` directly.** Bot commits on
  `main` carry `[skip ci]`; keep it that way if you ever touch them.
- Merging a PR triggers **nothing** on its own — every workflow here is `schedule`
  or `workflow_dispatch` — **except `emergency-alert.yml`, which fires on a push
  to `main` that changes `config/emergency_override.json`.** Treat any edit to
  that file as live.
- Forecast-quality fixes usually belong in `scripts/wx/prompts/system.md` first;
  add the mechanical backstop in `guardrails.py` and mirror it in
  `draft-lint.mjs` with a fixture in `tools/fixtures/`.
- No adapter in `scripts/wx/sources/` was ever developed against a live server;
  `wx-selftest.yml` is the only real test of them. Don't "fix" a source from a
  hunch about its shape.
- The repo is deliberately public (unlimited Actions minutes; the every-10-minutes
  alert schedule alone would blow a private repo's free tier). Nothing sensitive
  goes in the tree.
