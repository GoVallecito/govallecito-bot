# Setting up the forecaster

Written the same way as the conditions bot's README: for David, who is not
going to be writing the Python. Everything technical is built. What is left is
a handful of things only you can do, in order.

The forecaster lives inside the **existing** `govallecito-bot` repo and changes
none of its files. One `DRY_RUN` switch already governs both.

---

## Step 1 — Put the files in the repo (10 min)

From the zip, copy these in, keeping the folder structure:

```
scripts/wx/                    the forecaster
tests/                         73 tests
.github/workflows/forecast.yml
.github/workflows/verify.yml
.github/workflows/storm-watch.yml
.github/workflows/wx-selftest.yml
state/home_gauge.json          starts as {}
state/README.md
SETUP.md, README-WX.md
site/                          the Astro files -- these go in the WEBSITE repo, not here
```

Nothing overwrites. If GitHub asks about a conflict, stop and tell me.

---

## Step 2 — Run the self-test. Do this before anything else. (5 min)

**Actions → WX Self-Test (live endpoints) → Run workflow.**

Every weather API is blocked from the sandbox this was written in, so none of
this code has ever spoken to a real server. GitHub Actions can. This run is the
first real test, and it is the one that tells you whether the whole idea works.

When it finishes, open the run log and find three things:

**1. `ELEVATION PARAMETER — THE PRODUCT THESIS`.**
You want to see four different temperatures for the four bands. If they are all
the same, Open-Meteo is ignoring the elevation we ask for, the bands are
fiction, and the product does not work as designed. Stop and tell me.

**2. The NWS zone lines.** Vallecito should print `COZ019`, Durango `COZ022`.
If not, the constants need a correction.

**3. The Colorado DWR reservoir result.** This is the least-tested code in
either bot — your existing README flags the same parsing for the same reason.
If it failed, the log prints the field names it actually saw, which makes it a
five-minute fix rather than a mystery.

CoCoRaHS and CDOT will also be exercised. CDOT will say it needs a key; that is
expected until Step 4.

**Do not go further until the elevation check passes.**

---

## Step 3 — Add one secret (5 min)

**Settings → Secrets and variables → Actions → Secrets → New repository secret**

- `ANTHROPIC_API_KEY` — from console.anthropic.com. This is what writes the posts.

Everything else reuses what the conditions bot already has.

**Variables tab**, add:

- `WX_FIRST_30_DAYS` = `true` — holds every post for your review. Leave this on.
- `WX_SITE_DIR` = leave empty for now; it gets set in Step 6.

Also confirm **Settings → Actions → General → Workflow permissions** is set to
**Read and write**. The conditions bot already needs this for its state
commits; the forecaster additionally needs it to open review issues.

---

## Step 4 — The passes (nothing to do)

**An earlier version of this file told you to get a free CDOT key at
data.cotrip.org. That was wrong, and it is why that page gave you an error.**

`data.cotrip.org` is a bare API gateway with no signup page — its root returns
`{"code":404,"message":"The current request is not defined by this API."}`,
which is the correct response to visiting it. Every CDOT developer doc URL
(`cotrip.org/help/117`, `xmlHelp.html`, `xmlFeed.htm`) now redirects to the
COtrip homepage. CDOT's own footer "Data Feeds" link is broken, and Colorado's
open-data catalog still advertises an "API ACCESS" link pointing at the dead
page. There is currently no public way to register.

So the forecaster **forecasts** the passes instead, using the same Open-Meteo
call that drives the elevation bands — Coal Bank 10,640 ft, Molas 10,910 ft,
Red Mountain 11,018 ft, Wolf Creek 10,857 ft — and links CDOT for live status.

It will never say a road is open or closed. That is enforced in
`guardrails.py`, not just asked for in the prompt: a draft claiming a closure,
or chain law, or avalanche control, is blocked outright unless live road data
is actually present. A wrong "closed" sends someone on a three-hour detour; a
wrong "open" sends them at a pass that is shut.

If CDOT ever restores public feed access, add the key as `CDOT_API_KEY` and the
adapter picks it up — the guardrail relaxes automatically once real data is in
the bundle.

## Step 5 — Watch it for a week before it says anything in public (ongoing)

**Actions → Vallecito Forecast → Run workflow**, set `slot` to `school_call`,
leave `dry_run` as `true`.

Download the artifact. It contains `draft.txt`, `card.png`, and `bundle.json`.
Read all three. You are looking for four specific things:

- Does the snow line move sensibly as the weather changes?
- Do the four bands actually differ, or does it read like one forecast
  copy-pasted four times?
- Does it sound like someone from here, or like a model doing an accent?
- **Does it ever state a number that is not in `bundle.json`?** That is the one
  unforgivable failure. If you see it even once, tell me.

Do this twice a day for a week, in different weather. When something reads
wrong, the fix is almost always in `scripts/wx/prompts/system.md` — it is plain
English and it is where most of the quality lives. Compare against the 14
sample posts.

---

## Step 6 — Wire it to the website (30 min, in the govallecito.com repo)

Copy `site/src/...` into the Astro project, merge `config.ts` with your existing
content config, then come back here and set the repo variable
`WX_SITE_DIR` = `src/content/weather`.

This is the highest-leverage step in the whole build and it has nothing to do
with weather. Your site has 44 indexed pages and flat internal linking. Dated
daily posts at `/weather/2026-11-04-.../` build the URL hierarchy the audit said
was missing, and they target queries with real intent and no incumbent.

---

## Step 7 — Go live (one switch)

Once a week of held drafts has looked right consistently:

**Settings → Variables → `DRY_RUN` → `false`.**

Note this also un-gates the conditions bot. One switch, both products, by
design — make sure you are happy with both.

Then set `WX_FIRST_30_DAYS` to `false` only when you genuinely trust it. There
is no rush; a held draft you paste by hand is still a published forecast.

**Post once a day, at 5:45am, and never miss.** Not twice. Add the evening slot
only after the morning one has gone a month without failing.

---

## What you maintain by hand

Exactly one file, and it takes ten seconds: **`state/home_gauge.json`**.

```json
{ "2026-11-04": { "new_snow_in": 6.5, "snow_line_observed_ft": 7300 } }
```

`snow_line_observed_ft` is the most valuable number in the system — roughly the
elevation where you could see the change from wet to sticking, up the 501 or
the 240. It is the only direct observation of the thing the forecast is named
for, and it is what calibrates the snow line. An estimate to the nearest
hundred feet beats a blank every time.

Nothing breaks if you skip days. Calibration just takes longer to reach the 20
events it needs before it switches itself on.

---

## What happens on its own

| Workflow | When | What |
|---|---|---|
| **Vallecito Forecast** | hourly, acts at 5:45am and 7:30pm MT | The school call and the evening look |
| **Vallecito Verify** | daily, ~8:30am MT | Scores yesterday, calibrates, drafts the totals post |
| **Vallecito Storm Watch** | 3× daily | Fires a setup post when a system shows up 2–5 days out |
| **WX Self-Test** | Mondays | Tells you if a data source has quietly died |

---

## When something is held for review

You get a **GitHub issue** with the full draft and the reason. It emails you,
it is readable on a phone, and the thread becomes the log you tune the persona
against. Anything under an active NWS warning, anything touching a burn scar,
and anything mentioning avalanches always holds — those are not going to
auto-publish, by design.

---

## Known limitations, honestly

- **No adapter here has ever talked to a real server.** Step 2 is the first
  test. CoCoRaHS and CDOT are the two most likely to need a field-name fix.
- **The snow line is a heuristic, not a measurement.** It ships uncalibrated and
  the guardrails force the post to hedge it until 20 verified events exist.
- **Which CAIC zone contains Vallecito is still unresolved** — the polygons only
  publish in season. Re-run the self-test in mid-November and it will answer.
- **Facebook group posting is probably unavailable.** Meta restricted the API.
  The code tries and fails gracefully; share by hand, which takes eight seconds
  and lets you write the caption yourself anyway.
- **The email path is capped at 50 recipients** on purpose. Past that, bulk
  sending from your Gmail would damage deliverability for the address you
  actually use — move to Kit or Buttondown then.
- **Nothing detects a county evacuation order** issued only through CodeRED.
  Same disclosed gap the conditions bot has, and the same answer: no free public
  API exists for it.
