# GoVallecito daily conditions bot

Posts a branded "conditions card" (lake level, weather, fire status, streamflow)
to the GoVallecito Facebook Page twice a day, automatically, forever, for free.
On a rotating cadence, some posts also carry a real, safely-licensed seasonal
photo and a cited fact (hummingbird migration, elk rut, fall color, etc.). A
second workflow checks back on each post 48+ hours later, and -- slowly, once
there's enough data to mean anything -- nudges future posts toward whatever's
actually working.

This document is written for David, who is not going to be writing any of the
Python code himself. It tells you exactly what to click, in order. Everything
technical is already built; what's left is four accounts/credentials only you
can create, because Claude is never allowed to enter passwords or handle your
credentials directly.

**Read the "Known limitations, honestly" section near the bottom before you
trust this with zero supervision.** Nothing in this project is fake or
half-built, but several things noted there were built from documentation
rather than a live test, because the sandbox that wrote this code doesn't have
internet access to the real APIs it calls -- GitHub Actions does, so the first
real runs are also the first real test.

## What it actually does

Every hour, a free GitHub Actions job wakes up, checks the time in Colorado,
and does nothing unless it's ~7am or ~2pm local time. When it is, it:

1. Pulls current weather from the National Weather Service, streamflow from
   USGS, lake storage from Colorado's Division of Water Resources, and fire
   restriction status from a file in this repo that you update by hand.
2. On roughly 1-2 days a week (see "Images and the seasonal almanac" below),
   also checks whether today matches a researched seasonal topic, and if so
   tries to pull a real public-domain photo to go with it.
3. Turns all of that into caption text and a 1080x1080 branded image,
   following the style guide (`docs/daily-post-template-style-guide.md`) so
   every post has the same bones even though the numbers (and occasional
   photo) change. The card's layout is fixed -- long text is always
   shortened to fit it, the card never grows to fit long text -- and the
   exact same (possibly shortened) wording is used in both the caption and
   the image, so the two can never say different things. See "Text always
   fits the card, on purpose" below.
4. Posts to the Facebook Page -- or, while `DRY_RUN` is on, just saves it so
   you can look before anything goes live.
5. A separate daily workflow checks back on posts that are 48+ hours old,
   records how they did, and gradually adjusts future posts toward what's
   working (see "How the engagement learning works" below -- and it really is
   gradual; don't expect this to mean anything for the first couple of
   months).
6. A third, independent workflow checks every ~10 minutes for active flood/
   fire/evacuation/disaster conditions and posts about them the moment one's
   detected -- no waiting for the 7am/2pm schedule, no approval step. See
   "Emergency alerts" below; this is the one part of the system that doesn't
   wait for anything.

## Images and the seasonal almanac

You asked for images pulled from either a public-domain outside source or
your own downloaded photos. On the "connect a folder" question, you declined
access to your Pictures folder this round -- totally fine, so this version
runs on public-domain sourcing only. If you want your own photos in the mix
later, that just needs a folder connected in a future session; nothing about
the current design would need to change to add it.

Since local photos weren't available, images come from **Wikimedia Commons**,
live, at post time -- searched by category (e.g. `Category:Selasphorus rufus`
for rufous hummingbirds) and filtered to only images explicitly marked public
domain or CC0. This is the one part of the whole system I'd flag as
higher-stakes than the rest: getting a data field wrong just means a post
says "delayed"; getting a license check wrong means posting an image that
isn't actually free to use. So it fails closed on purpose -- if a license
can't be positively confirmed safe, or the API doesn't behave as expected,
you get the plain data card with no photo that day, not a risky guess. See
the big comment at the top of `scripts/fetch_image.py` for exactly what's
confirmed vs. not.

The "what's it about" side comes from `config/seasonal_almanac.json` -- a
short, deliberately short list of researched, cited entries (hummingbird
migration, elk rut, aspen color change, bald eagle winter viewing). Short on
purpose: every entry there has a real named source; padding it out with
invented "fun facts" would undercut the entire point of asking for
information from reliable sources. It only covers about 4-5 months of the
year right now -- add more entries the same way (find a real source, cite it)
whenever you want more coverage. A matching photo + fact only gets used on
about 1-2 days a week (the style guide's own cap on how often the "situational
line" should appear), and never on a day when there's an actual nearby
wildfire to report instead -- safety information always wins that slot.

## Text always fits the card, on purpose

The card's dimensions, fonts, and row layout never change from post to post
-- what changes when a field runs long (a wordy fire-restriction summary, an
almanac fact, a wildfire safety note) is the text itself, shortened to fit.
`generate_post_text.py` condenses each free-text field to an empirically
measured, per-field character budget (measured directly against
`render_card.py`'s actual fonts/margins, not guessed) at the one point where
it's first read -- and the exact same shortened string is then used in both
the Facebook caption and the rendered image. That second part is what
matters most: caption and image are built from one shared value, not two
independent ones, so they cannot drift apart. (An earlier version of the
image renderer truncated long values with no ellipsis, so a long fire
restriction could look complete in the image while the caption said more --
that's now fixed at the source, with the image renderer's own
ellipsis-truncation kept as a backstop in case a budget estimate is ever
slightly off.) Two of the four real seasonal-almanac entries
(`hummingbird_migration`, `elk_rut`) were already slightly over the old
unenforced limit before this was added -- this wasn't purely precautionary.

## How the engagement learning works

A second workflow (`engagement-check.yml`) runs daily, finds posts at least
48 hours old, and pulls their current like/comment/share totals from the
Graph API. That builds up `state/post_history.json` over time.

Once a specific hook line has been used at least **15 times** and has
engagement data for all of them, future posts start weighting hook selection
toward whatever's scored better historically -- but softly (weights are
capped between 0.6x and 1.6x of baseline), not "always use the winner." Two
reasons for the cap: a brand new page's early engagement numbers are mostly
noise, not signal, and the style guide deliberately wants hooks to rotate so
posts don't feel copy-pasted -- collapsing to a single "best" hook forever
would fight that on purpose. The same gating applies to whether grounded
(photo+fact) posts happen slightly more or less often than the ~1-2x/week
default, based on whether they're clearly outperforming plain posts.

**Realistic timeline, not a sales pitch:** with 2 posts/day split across 5
morning and 4 afternoon hook lines, a given hook is used roughly once a week.
Hitting 15 uses per hook is a few months out, not a few weeks. Before that
threshold, hook selection is the same deterministic day-of-year rotation as
before -- nothing "learns" prematurely off 3 or 4 data points. You can watch
this fill in yourself: `state/content_preferences.json` doesn't exist at all
until the first engagement check runs, and its `sample_counts` field shows
exactly how far along each hook is.

## Emergency alerts (flood / fire / evacuation / disaster)

A third workflow, independent of the two scheduled daily posts, watches for
genuinely urgent conditions and posts about them immediately -- no waiting
for 7am/2pm, no manual approval step. It looks at three sources every time
it runs:

1. **The National Weather Service's public active-alerts feed**, filtered to
   an explicit allowlist of event types that map to flood, fire, evacuation,
   or disaster (`fetch_conditions.ALERT_EVENT_CATEGORIES`) -- deliberately
   not "anything Severe," which would also fire on routine winter-storm or
   thunderstorm warnings that aren't what this feature is for.
2. **`config/emergency_override.json`** -- a manual flag you set by hand for
   anything the NWS feed can't see (see the coverage gap below). Set
   `active: true`, fill in `category`/`headline`/`details`/`source`, save.
3. **`config/fire_status.json`** -- the same file you already hand-edit for
   routine fire-stage updates. If you bump the stage up, or add a nearby
   wildfire, this workflow treats that as alert-worthy on its own and posts
   about it immediately, even though nothing about how you edit that file
   changes. A stage or wildfire-count *decrease* is deliberately not
   alert-worthy -- that's good news, not an emergency, and it already shows
   up in the next scheduled post same as always.

**Two response speeds, and it's worth knowing which applies:**

- Editing `config/fire_status.json` or `config/emergency_override.json` and
  pushing that change to GitHub (including editing the file directly on
  github.com, which counts as a push) triggers this workflow within
  **seconds**.
- The NWS feed is polled on a schedule, every **10 minutes**, so a
  genuinely new NWS-issued alert can take up to that long to be noticed and
  posted -- not truly instant, but close.

**A gap worth knowing about, not glossed over:** the NWS feed only carries
what NWS itself (or another agency relaying through IPAWS) has published.
A county sheriff's evacuation order issued only through a local
CodeRED/Everbridge-type system, with no IPAWS/WEA relay, will not appear
there -- there is no free public API for that. `config/emergency_override.json`
exists specifically as the manual backstop for that case: if you hear about
an evacuation order through any channel this bot can't see, that file is how
you get it posted immediately anyway.

**Same `DRY_RUN` switch as everything else.** This is deliberate: David
asked for alerts to post "without review," meaning no person has to approve
each one -- it does not mean bypassing the same dry-run safety net that
governs the two scheduled posts. Testing this workflow safely and going
live with it both happen through the one `DRY_RUN` repo variable already set
up in step 4 below; there's no separate switch to remember.

**It won't re-post the same thing every 10 minutes.** A state file
(`state/emergency_alert_state.json`) remembers what's already been posted
about -- a still-active NWS alert, an unchanged manual override, an
unchanged fire stage -- so only genuinely new information triggers another
post. On this repo's very first-ever run, an already-elevated fire stage is
recorded as the starting baseline rather than treated as a brand new
emergency the moment this feature goes live; only increases from that point
on count.

**A real tradeoff, stated plainly:** this workflow shares a concurrency lock
with the two scheduled ones (all three touch the same state files, and
letting two of them write at once is worse than a delay). If a scheduled
post happens to be mid-run when an emergency is detected, the alert queues
behind it instead of posting instantly -- bounded by that other workflow's
own 15-minute timeout, worst case. Judged the better default, but worth
knowing rather than assuming "immediately" is an absolute guarantee.

## One-time setup

### 1. Create a Meta developer app (5 min)

1. Go to [developers.facebook.com](https://developers.facebook.com) and log
   in with your normal Facebook account -- no new password, this reuses your
   existing login.
2. **My Apps -> Create App**. Pick whatever option is closest to "Business"
   or "Other" (Meta shuffles the exact wording sometimes) -- avoid anything
   labeled specifically for games or consumer apps. Name it something like
   "GoVallecito Bot". Create it.
3. That's it for this step -- you don't need to add any "Products" to the
   app for what we're doing.

### 2. Get a Page Access Token (10 min) -- the part to be careful with

This token is effectively a password for posting to your Page. Treat it that
way: it goes into GitHub's *secret* storage (step 4) and nowhere else --
never in a text file, chat message, or email.

1. Go to the [Graph API Explorer](https://developers.facebook.com/tools/explorer).
2. Top right: select the app you just created.
3. Click **Generate Access Token**. When the permissions picker pops up,
   check `pages_show_list`, `pages_read_engagement`, and `pages_manage_posts`,
   then approve.
4. **Before going further**, extend that token so it's long-lived: open the
   [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken),
   paste your token in, and use its "Extend Access Token" button. Copy the
   extended token it gives you back.
5. Back in Graph API Explorer, paste the extended token into the token box,
   type `me/accounts` into the query field, and click Submit.
6. You'll get a JSON list of every Page you administer. Find the entry named
   "GoVallecito" and copy its `access_token` value -- that's the one you
   actually need. Per Meta's own docs, a Page token obtained this way from a
   long-lived user token "does not have an expiration date and only expires
   or is invalidated under certain conditions" -- durable, but not an
   absolute guarantee. If posting ever suddenly starts failing with an auth
   error months from now, regenerating this token is the first thing to try.

**On App Review:** Meta requires "App Review" before some permissions can be
used broadly, but apps in Development Mode can normally use permissions like
`pages_manage_posts` immediately, with no review, for the app's own
admins/developers acting on Pages they personally administer -- which is
exactly this situation. I could not fully confirm this is still Meta's exact
policy as of today by reading their docs (policy pages describe production
rules more than the development-mode exception); you'll find out directly
at step 6 above -- it'll either just work, or Facebook will show you a clear
message that review is required, in which case stop and we'll figure out
that path together rather than guessing further.

### 3. Get this code into a GitHub repo (10 min)

1. If you don't have one, make a free account at [github.com](https://github.com).
2. Click the green **New** button to create a repository. Name it
   `govallecito-bot`. **Make it Public.** This is a change from what an
   earlier version of this README said (it used to recommend Private) --
   the new emergency-alert workflow polls every 10 minutes, all day, which
   alone adds up to roughly 4,000+ Actions minutes/month even though almost
   every run is a few seconds of no-op. That comfortably exceeds the 2,000
   free minutes/month a Private repo gets on GitHub Free; Public repos get
   **unlimited** Actions minutes, at no cost. Nothing in this repo is
   sensitive on its own -- your Facebook token lives in GitHub's encrypted
   Secrets storage (step 4), never in the repo's actual files -- so there's
   no real downside to Public here.
3. On the new (empty) repo's page, use the "uploading an existing file" link
   and drag in everything from the zip you were sent, keeping the folder
   structure intact (`scripts/`, `config/`, `.github/workflows/`,
   `requirements.txt`, `README.md`, `docs/`).

### 4. Add your secret and settings (5 min)

In the repo: **Settings -> Secrets and variables -> Actions**.

- **Secrets tab -> New repository secret**: name `FB_PAGE_ACCESS_TOKEN`,
  value = the token from step 2. That one token covers everything -- posting
  *and* the engagement-check workflow reading likes/comments/shares later;
  nothing extra to create for that part.
- **Variables tab -> New repository variable**: name `DRY_RUN`, value `true`.
  (This is the safety switch -- see below.)
- Optionally also add a variable `FB_PAGE_ID` if you ever need to override
  the default already built into the code (GoVallecito's page ID,
  `1138532512682553`, which isn't sensitive).

**One more setting, easy to miss:** all three workflows commit a small state
file back to the repo after they run (that's how post history, engagement
data, and emergency-alert dedup memory persist between runs -- GitHub
Actions itself throws away everything else after each run). For that to
work, go to **Settings -> Actions -> General -> Workflow permissions** and
select **"Read and write permissions"**, then Save. New GitHub repos often
default to read-only here, in which case the commit-back step fails with a
permission error -- if you ever see that in a failed run's log, this
setting is almost certainly why.

### 5. Test it before trusting it (ongoing, start today)

1. Go to the **Actions** tab. First visit, you may need to click "I
   understand my workflows, go ahead and enable them."
2. Click **Daily Vallecito Conditions Post** on the left, then the **Run
   workflow** dropdown on the right. Set `force_slot` to `morning`, leave
   `dry_run` as `true`, click **Run workflow**.
3. After it finishes (30-60 seconds), open the run and scroll down to
   **Artifacts** -- download `post-output-...`, which contains the exact
   image and caption text it would have posted. Look at it.
4. Do this a few times over the next few days -- try `afternoon` too, and
   let the real hourly schedule run in the background (it's already dry-run
   by default, so nothing goes live yet no matter what).
5. Separately, test the emergency-alert workflow too before trusting it:
   **Actions -> Emergency Alert Check -> Run workflow**, leave `dry_run` as
   `true`. On a normal day this will very likely say "Nothing new to alert
   on" and exit -- that's success, it means the NWS feed call itself didn't
   error. To actually see a rendered alert card without waiting for a real
   flood/fire/evacuation event, temporarily set `active: true` in
   `config/emergency_override.json` with some placeholder text, commit it
   (which also triggers this workflow instantly via its push trigger),
   check the output artifact, then set `active` back to `false` and commit
   again so it stops "alerting" on your test data.
6. Once you're comfortable both workflows look right consistently, flip the
   one switch that governs both: **Settings -> Secrets and variables ->
   Actions -> Variables -> edit `DRY_RUN` -> change to `false`.** That's the
   entire "go live" step, for scheduled posts and emergency alerts alike.
   This matches what you asked for: auto-publish, once it's actually proven
   reliable, not on day one by default.

## Keeping it running

- **Fire status is manual.** There's no public API for restriction stage --
  edit `config/fire_status.json` whenever La Plata County / San Juan
  National Forest changes it. This is the one file you should expect to
  touch regularly. Everything else is fully automatic.
- **GitHub disables scheduled workflows after 60 days of repo inactivity.**
  If posts silently stop with no error, check the Actions tab for a banner
  saying the workflow was disabled, and click to re-enable it. (Committing
  the occasional fire-status update resets this clock as a side effect.)
- If a run fails, GitHub emails the address on your GitHub account
  automatically -- no extra setup needed. The failed run's log will say
  which step broke.

## Known limitations, honestly

- **Lake level parsing is the least-tested part of this.** The Colorado DWR
  endpoint it calls is real and confirmed to exist, but the exact field
  names in `fetch_conditions.fetch_lake_level()` were written from API
  documentation, not a live response -- the sandbox that built this couldn't
  reach dwr.state.co.us to check. Run `scripts/test_data_sources.py` (or a
  `workflow_dispatch` test run) and look at the "raw response" section it
  prints; if lake level comes back empty, the field names likely need a
  small adjustment there.
- **USGS's own reservoir gage (09353000) is not used.** It stopped reporting
  in 2012. Lake level comes from Colorado's state system instead, which is
  also closer to the source govallecito.com itself already credits
  ("USBR/USACE").
- **The Wikimedia Commons image fetch is the least-tested, highest-stakes
  piece of the whole system.** The API query and license-checking logic in
  `scripts/fetch_image.py` are written from Wikimedia's documented, stable
  API conventions, not a live test call -- this sandbox can't reach
  commons.wikimedia.org either. It's built to fail closed (no photo, not a
  risky photo) if anything looks off, but "confirm this actually returns
  good matches for all four almanac categories" is genuinely still an open
  item. Worth specifically checking the first few grounded-post dry runs
  rather than just glancing at the data-only ones.
- **The regular (non-grounded) data card still uses a solid brand-color
  background, not a photo.** That's deliberate -- reliability and legibility
  for what's fundamentally a utility post, and one less thing re-fetched
  twice a day forever. Photos only appear on the ~1-2x/week grounded posts,
  where there's an actual reason (and a real fact) to hang one on.
- **The seasonal almanac only covers about 4-5 months of the year.** Summer
  (hummingbirds), fall (elk, aspen), and winter (eagles) have entries; late
  winter/spring doesn't yet. Grounded posts simply won't happen on days with
  no matching entry -- add more to `config/seasonal_almanac.json` the same
  way (real source, cited) to fill the gap.
- **No duplicate-post protection on the two scheduled daily posts.** Manually
  re-running the workflow during an actual posting hour, or a rare GitHub
  Actions retry, could post twice. Not built for v1. (The emergency-alert
  workflow is different here -- it has its own explicit dedup state, see
  "Emergency alerts" above, precisely because re-posting the same alert
  every 10 minutes would be a much worse failure mode than for a routine
  post.)
- **The engagement-learning loop needs months, not days, to activate.** See
  "How the engagement learning works" above. Below the 15-sample-per-hook
  threshold, nothing changes from pure rotation -- that's intentional, not a
  bug, but worth remembering if you check `state/content_preferences.json`
  early on and it looks like nothing's happening.
- **Engagement numbers are simple totals (likes + comments + shares), not
  reach/impressions.** Full Page Insights (how many people saw a post, not
  just who reacted) needs an additional permission and a bigger API surface
  -- skipped for now to keep the permissions ask in step 2 unchanged from
  what's already documented.
- **No automated wildfire-proximity check.** The "X wildfires nearby" line is
  manually written into `config/fire_status.json`, same as the fire stage
  itself -- not pulled from NIFC or InciWeb live. (There's a real NIFC ArcGIS
  API that could do this later; skipped for now to keep the number of live
  dependencies small while this is new.)
- **Emergency alerts have a real, disclosed coverage gap.** The automated
  half (NWS's active-alerts feed) cannot see a county-issued evacuation order
  that's only distributed through a local CodeRED/Everbridge-type system with
  no IPAWS/WEA relay -- there's no free public API for that. The manual
  override file (`config/emergency_override.json`) is the intended backstop,
  but it only helps if a person notices and edits that file; it is not a
  substitute for following official county emergency-notification channels
  directly.
- **Emergency alerts aren't instant in the literal sense.** A push to
  `config/fire_status.json` or `config/emergency_override.json` triggers a
  check within seconds; the automated NWS-feed side is polled every 10
  minutes, so worst case is about that long. Both can also queue behind a
  scheduled daily-post run that's already in progress, up to that workflow's
  15-minute timeout -- see "Emergency alerts" above for the reasoning.
- **Emergency alerts only fire on escalation, not de-escalation.** A fire
  stage or nearby-wildfire count going down doesn't produce an "all clear"
  post -- only increases are treated as alert-worthy. Restrictions being
  lifted still shows up in the next scheduled post, same as before this
  feature existed.
- **No general severe-weather coverage.** The NWS-alert allowlist is
  deliberately narrow (flood/fire/evacuation/disaster event types only) --
  a Winter Storm Warning or Severe Thunderstorm Warning will not trigger an
  alert post, on purpose, so genuine emergencies don't get lost in more
  routine severe-weather noise. Easy to expand
  (`fetch_conditions.ALERT_EVENT_CATEGORIES`) if you decide you want those
  covered too.
- **7am/2pm aren't data-driven yet.** They're the original instinct, kept
  because the Page has 0 followers and 0 posts so far -- there's no
  engagement data to optimize toward yet. Worth revisiting via Facebook Page
  Insights after a month of real posts.
- **Facebook only.** No Instagram crossposting in this version.

## Repo layout

```
scripts/
  fetch_conditions.py    -- pulls NWS / USGS / Colorado DWR data, reads fire_status.json,
                             pulls NWS active alerts for the emergency-alert workflow
  fetch_image.py         -- searches + downloads a safely-licensed photo from Wikimedia
                             Commons for grounded posts (fails closed -- see its docstring)
  generate_post_text.py  -- turns conditions (+ almanac, + learned preferences) into
                             caption text and image data; also builds the emergency-alert
                             post variant (build_alert_post())
  render_card.py         -- draws the 1080x1080 branded card, plain, with a photo band,
                             or with an alert row (pure PIL, no browser)
  icons.py               -- hand-drawn brand icons (see comment in the file for why
                             not emoji fonts)
  post_to_facebook.py    -- posts to the Graph API, or dry-runs to output/
  post_history.py        -- reads/writes state/post_history.json
  check_engagement.py    -- pulls engagement on 48h+ old posts, recomputes preferences
                             (excludes emergency-alert posts from that math -- see above)
  check_emergency.py     -- orchestrator for the emergency-alert workflow; entry point
                             emergency-alert.yml calls
  main.py                -- orchestrator; entry point the daily-post workflow calls
  test_data_sources.py   -- standalone debug script, prints raw API responses
config/
  fire_status.json           -- manually maintained fire restriction status (also watched
                                 for escalation by the emergency-alert workflow)
  seasonal_almanac.json       -- short, cited list of seasonal facts + Commons categories
  emergency_override.json    -- manual emergency flag for what the NWS feed can't see
state/
  post_history.json             -- every real post: hook used, had an image?, engagement
                                    once checked, plus post_type/alert fields for alerts
  content_preferences.json      -- learned weights (created once there's enough data)
  emergency_alert_state.json    -- dedup memory for the emergency-alert workflow
.github/workflows/
  daily-post.yml          -- the hourly GitHub Actions schedule
  engagement-check.yml    -- the daily engagement-check + learning-update schedule
  emergency-alert.yml     -- the 10-minute poll + instant push-trigger for emergencies
docs/
  daily-post-template-style-guide.md  -- the voice/structure rules this code implements
```
