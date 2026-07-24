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

1. Pulls current weather, lake storage, streamflow, and fire-restriction /
   nearby-wildfire status from **govallecito.com's own live-conditions
   backend** (the same Cloudflare Worker the website's own pages read from)
   -- so the bot and the site report identical numbers instead of computing
   their own similar-but-slightly-different versions. Weather, lake, and
   streamflow each automatically fall back to their original independent
   government sources (NWS, Colorado DWR, USGS) if that backend is ever
   unreachable; fire status has no such fallback (there's no independent
   live source for it) and honestly reports "delayed" instead on the rare
   occasion the Worker is down. See "Where the data comes from" below.
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

## Where the data comes from

Weather, lake level, streamflow, and fire-restriction/wildfire status all
come primarily from **govallecito.com's own live-conditions Worker**
(`govallecito-conditions.dkontje.workers.dev/data/conditions.json`) -- the
same backend the website's own pages already read from. This was a
deliberate change (2026-07-24): using the site's own numbers is the most
direct way to guarantee the bot and the website always agree, instead of
each independently computing a similar-but-not-always-identical figure from
raw government APIs.

That single-upstream design trades away some redundancy, so three of the
four sections have an automatic fallback if the Worker is ever unreachable
or returns stale/malformed data for that section:

- **Weather** falls back to a direct National Weather Service call.
- **Streamflow** falls back to the single USGS Vallecito Creek gauge (the
  Worker's own figure combines Pine River + Vallecito Creek, which is why
  the post says "combined inflow" normally but "(Vallecito Creek)" only
  during a fallback -- the wording changes along with what's actually being
  measured, never mismatched).
- **Lake level** falls back to a direct Colorado DWR query.
- **Fire restriction status / nearby wildfires** has **no fallback** --
  there's no independent live source for it (that's exactly why
  `config/fire_status.json` existed before this change). If the Worker is
  down, fire status honestly reports "data delayed" that cycle rather than
  silently serving old information from an unmaintained file. If this
  tradeoff turns out to be wrong in practice, restoring a file-based
  fallback is a one-line change -- ask Claude.

**`config/fire_status.json` is no longer read by the bot.** It's kept in
the repo as a historical record, but hand-editing it no longer changes any
post, and no longer triggers the emergency-alert workflow (see "Emergency
alerts" below). You don't need to maintain it anymore -- fire stage and
wildfire proximity are now automatic, sourced the same place the website's
own fire-status display gets them.

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
line" should appear).

A genuinely NEW nearby-wildfire report always wins that slot over a seasonal
photo -- safety first, unchanged. That's *not* the same as "any day a wildfire
is within 50mi," though (changed 2026-07-24): once fire/wildfire data started
coming live from your Worker instead of a hand-maintained config file that in
practice never had a real entry, "wildfire within 50mi" stopped being rare --
during fire season it can be true for weeks straight, which would have meant
the safety note (correctly) winning that slot every single post and silently
shutting the seasonal-photo feature out the entire time. `generate_post_text.py`
now remembers (`state/daily_post_state.json`) the last nearby-wildfire count it
already told the public about and only leads with the safety note when that
count goes UP -- a routine status update about a fire you've already reported
(containment ticking up, say) no longer blocks the seasonal photo. See
`_decide_wildfire_situational_line()`'s docstring for the exact rule.

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
for 7am/2pm, no manual approval step. It looks at four sources every time
it runs:

1. **The National Weather Service's public active-alerts feed**, filtered to
   an explicit allowlist of event types that map to flood, fire, evacuation,
   or disaster (`fetch_conditions.ALERT_EVENT_CATEGORIES`) -- deliberately
   not "anything Severe," which would also fire on routine winter-storm or
   thunderstorm warnings that aren't what this feature is for.
2. **`config/emergency_override.json`** -- a manual flag you set by hand,
   right here in this repo, for anything the NWS feed can't see (see the
   coverage gap below). Set `active: true`, fill in
   `category`/`headline`/`details`/`source`, save.
3. **`restriction.override` on your own govallecito-conditions Worker** -- a
   SECOND, independent manual flag, this one living in your Worker's own
   code rather than this repo (see "A second manual override lives in your
   Worker now" below). Set it `true` there and this workflow picks it up on
   its next poll.
4. **An escalation in the fire-restriction stage or nearby-wildfire count**
   that `fetch_conditions.fetch_fire_status()` reads from that same Worker
   (see "Where the data comes from" above) -- fully automatic now. You don't
   have to do anything for this one; if La Plata County / San Juan National
   Forest raises the restriction stage, or a new wildfire shows up nearby,
   and your Worker picks that up, this workflow posts about it on its own.
   A stage or wildfire-count *decrease* is deliberately not alert-worthy --
   that's good news, not an emergency, and it already shows up in the next
   scheduled post same as always.

**Two response speeds, and it's worth knowing which applies:**

- Editing `config/emergency_override.json` and pushing that change to
  GitHub (including editing the file directly on github.com, which counts
  as a push) triggers this workflow within **seconds**.
- Everything else -- the NWS feed, the automatic fire/wildfire escalation
  check, and your Worker's `restriction.override` flag -- is only checked on
  the **10-minute poll**, so any of those three can take up to that long to
  be noticed and posted. `restriction.override` in particular does NOT get
  the instant-push speed above, even though it's also "a flag you set by
  hand" -- it lives in your Worker's own code, outside this repo, so GitHub
  has no way to know the moment you deploy a change to it.

**A gap worth knowing about, not glossed over:** the NWS feed only carries
what NWS itself (or another agency relaying through IPAWS) has published. A
county sheriff's evacuation order issued only through La Plata County's own
resident notification system -- **LPC Alerts**, the system that replaced
CodeRED -- will not appear there; as of this system too, there is no free
public API or feed for it (confirmed 2026-07-24). Two manual backstops exist
for exactly that gap: `config/emergency_override.json` (edit a file in this
repo) and your Worker's `restriction.override` (edit code you already
maintain). Use whichever's easier to reach in the moment -- they don't
conflict, and either one gets an evacuation notice posted immediately even
though nothing in this bot can see LPC Alerts directly.

**A second manual override lives in your Worker now.** You mentioned wanting
to connect this directly to the county's evacuation system, and that isn't
possible today -- LPC Alerts has no public feed. `restriction.override` is
the closest practical substitute: a flag on the same `restriction` object
your Worker already returns in `conditions.json`. Set `override: true` in
your Worker's own source and this workflow treats it exactly like
`config/emergency_override.json`. Optional companion fields, read
defensively (missing ones just fall back to generic alert text, so flipping
`override` alone is enough to produce a real post):
   - `overrideCategory` -- one of `flood` / `fire` / `evacuation` / `disaster`
   - `overrideHeadline` -- short headline
   - `overrideDetails` -- longer description
   - `overrideSource` -- attribution shown in the post
   - `overrideSourceUrl` -- link included in the post if present

This lives entirely in your Worker's own code, which Claude has no access to
or visibility into -- you'd need to add these fields yourself (or paste the
Worker's source into a future session for help) whenever you want to use
this path.

**Same `DRY_RUN` switch as everything else.** This is deliberate: David
asked for alerts to post "without review," meaning no person has to approve
each one -- it does not mean bypassing the same dry-run safety net that
governs the two scheduled posts. Testing this workflow safely and going
live with it both happen through the one `DRY_RUN` repo variable already set
up in step 4 below; there's no separate switch to remember.

**It won't re-post the same thing every 10 minutes.** A state file
(`state/emergency_alert_state.json`) remembers what's already been posted
about -- a still-active NWS alert, an unchanged manual override (either
kind), an unchanged fire stage -- so only genuinely new information
triggers another post. On this repo's very first-ever run, an already-elevated fire stage is
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

- **Fire status is now automatic.** As of 2026-07-24, fire-restriction stage
  and nearby-wildfire data come from govallecito.com's own Worker, the same
  backend the website itself uses -- there's nothing to hand-edit here
  anymore for that. `config/fire_status.json` still exists but is no longer
  read; if you want to go back to hand-maintaining it instead of trusting
  the Worker, that's a one-line code change in
  `fetch_conditions.fetch_fire_status()` -- ask Claude.
- **GitHub disables scheduled workflows after 60 days of repo inactivity.**
  Now that `DRY_RUN` is off, every successful scheduled post commits
  `state/post_history.json` back to the repo, which resets this clock
  automatically, twice a day -- more reliable than the old fire-status-edit
  side effect ever was, since that depended on the county actually changing
  something. Worth knowing anyway: if posts ever silently stop for an
  unrelated reason, check the Actions tab for a banner saying the workflow
  was disabled, and click to re-enable it.
- If a run fails, GitHub emails the address on your GitHub account
  automatically -- no extra setup needed. The failed run's log will say
  which step broke.

## Known limitations, honestly

- **Lake level's direct-DWR fallback path was fixed and confirmed live on
  its first real run.** Lake level is now primarily read from
  govallecito.com's own Worker (see "Where the data comes from" above); the
  original direct Colorado DWR query only runs as a fallback if the Worker
  is unreachable. That fallback path did hit a real 400 error on its first
  production run (2026-07-24) -- root-caused and fixed the same day (wrong
  field names and an unsupported date-range parameter; see the detailed
  comment on `_fetch_lake_level_from_dwr()`). If it ever breaks again, run
  `scripts/test_data_sources.py` (or a `workflow_dispatch` test run) and look
  at the "raw response" section it prints.
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
- **The photo band's crop used to cut subjects' heads off -- fixed
  2026-07-24, but worth understanding the fix's real limits.** The first
  real grounded-post test used a portrait-orientation hummingbird photo
  (subject in the upper third, blurred background filling the rest) --
  exactly the composition this card's crop handles worst, because the photo
  band is much wider than tall (1080x460) and a plain center crop of a
  portrait photo down to that shape reliably lands well below the subject's
  head. The fix (`render_card._smart_crop_offset()`) tries to find where the
  photo actually has detail rather than always cropping dead-center -- but a
  first attempt using pure edge-detection energy was tested against that
  same real photo and FAILED, because it favored a sharp, wide, high-contrast
  foreground object (the feeder rim) over the bird's smaller, finer head
  detail. What's shipped now adds a positional bias toward the upper-middle
  of the frame (a soft prior, not a hard rule -- real content detail can
  still shift the result elsewhere) on top of the edge-detection signal,
  which correctly framed that same test photo's head and eye. This is a
  heuristic, not real subject/face detection -- it should work well for the
  wildlife-closeup style of photo this feature mostly uses, but hasn't been
  proven against all four almanac categories' actual photo styles (a full
  tree canopy for aspen color, for instance, doesn't really have a single
  "subject" the way an animal portrait does). Worth a look whenever a new
  category's grounded post runs for the first time. This also added `numpy`
  to `requirements.txt` -- a small, standard, no-compile dependency, not
  something to worry about.
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
- **Wildfire-proximity checking is now automated** (added 2026-07-24) --
  sourced from govallecito.com's own Worker, which itself blends NIFC/WFIGS
  and NASA FIRMS incident data, filtered to a 50-mile radius. This replaced
  the old manually-written `config/fire_status.json` nearby-wildfires note.
  One real caveat worth knowing: this repo has not independently verified
  the Worker's own wildfire-matching logic (e.g. exactly how it defines
  "nearby" or resolves incident names) -- it trusts the Worker's numbers the
  same way it trusts govallecito.com's own displayed numbers, which was the
  explicit point of this change ("identical reporting"), but it does mean a
  mistake in the Worker's own logic would show up here too.
- **Emergency alerts have a real, disclosed coverage gap.** The automated
  half (NWS's active-alerts feed) cannot see a county-issued evacuation order
  that's only distributed through La Plata County's own resident
  notification system -- LPC Alerts, which replaced CodeRED -- since neither
  system has ever exposed a public API or feed (confirmed 2026-07-24). Two
  manual backstops exist (`config/emergency_override.json`, and your Worker's
  `restriction.override` -- see "Emergency alerts" above), but both only help
  if a person notices and sets one of them; neither is a substitute for
  following official county emergency-notification channels directly.
- **Emergency alerts aren't instant in the literal sense.** A push to
  `config/emergency_override.json` triggers a check within seconds; the
  automated NWS feed, the automatic fire/wildfire escalation check, and your
  Worker's `restriction.override` flag are all only checked on the 10-minute
  poll, so worst case is about that long for any of those three. All of
  these can also queue behind a scheduled daily-post run that's already in
  progress, up to that workflow's 15-minute timeout -- see "Emergency
  alerts" above for the reasoning.
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
  fetch_conditions.py    -- pulls weather/lake/streamflow/fire+wildfire data primarily from
                             govallecito.com's own Worker, falling back to direct NWS / USGS /
                             Colorado DWR calls for the first three (fire has no fallback --
                             see its docstring); also pulls NWS active alerts for the
                             emergency-alert workflow
  fetch_image.py         -- searches + downloads a safely-licensed photo from Wikimedia
                             Commons for grounded posts (fails closed -- see its docstring)
  generate_post_text.py  -- turns conditions (+ almanac, + learned preferences) into
                             caption text and image data; also builds the emergency-alert
                             post variant (build_alert_post())
  render_card.py         -- draws the 1080x1080 branded card, plain, with a photo band,
                             or with an alert row (PIL + numpy, no browser); the photo
                             band uses a content-aware crop, not a plain center crop --
                             see _smart_crop_offset()'s docstring (added 2026-07-24)
  icons.py               -- hand-drawn brand icons (see comment in the file for why
                             not emoji fonts)
  post_to_facebook.py    -- posts to the Graph API, or dry-runs to output/
  post_history.py        -- reads/writes state/post_history.json
  check_engagement.py    -- pulls engagement on 48h+ old posts, recomputes preferences
                             (excludes emergency-alert posts from that math -- see above)
  check_emergency.py     -- orchestrator for the emergency-alert workflow (NWS feed,
                             config/emergency_override.json, Worker restriction.override,
                             automatic fire/wildfire escalation); entry point
                             emergency-alert.yml calls
  main.py                -- orchestrator; entry point the daily-post workflow calls
  test_data_sources.py   -- standalone debug script, prints raw API responses
config/
  fire_status.json           -- LEGACY, no longer read (fire status is now automatic via
                                 govallecito.com's own Worker -- see fetch_conditions.py);
                                 kept only as a historical record
  seasonal_almanac.json       -- short, cited list of seasonal facts + Commons categories
  emergency_override.json    -- manual emergency flag for what the NWS feed can't see (one
                                 of two such flags -- see "Emergency alerts" above)
state/
  post_history.json             -- every real post: hook used, had an image?, engagement
                                    once checked, plus post_type/alert fields for alerts
  content_preferences.json      -- learned weights (created once there's enough data)
  emergency_alert_state.json    -- dedup memory for the emergency-alert workflow
  daily_post_state.json         -- last nearby-wildfire count a DAILY post already
                                    reported (added 2026-07-24) -- a separate concern
                                    from emergency_alert_state.json above; see
                                    generate_post_text._decide_wildfire_situational_line()
.github/workflows/
  daily-post.yml          -- the hourly GitHub Actions schedule
  engagement-check.yml    -- the daily engagement-check + learning-update schedule
  emergency-alert.yml     -- the 10-minute poll + instant push-trigger for emergencies
docs/
  daily-post-template-style-guide.md  -- the voice/structure rules this code implements
```
