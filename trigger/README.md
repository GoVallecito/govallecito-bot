# wx-morning-trigger

A Cloudflare Worker that dispatches `forecast.yml` on Cloudflare's clock, and alarms
when the morning post does not happen.

**Why this exists.** GitHub's cron is the only scheduler GitHub offers and it is the
thing that fails: across 2026-09-18..29 about **17%** of `forecast.yml`'s requested
slots executed, and 2026-09-28 and 09-29 produced no morning post at all. The runs
that *do* execute are punctual (median 4.1 minutes from their slot), so this is a
delivery problem, not a timing one, and its cause is still unestablished.
`workflow_dispatch` goes through a different path and starts within seconds.

GitHub's own crons stay exactly as they are. They are the backup, and they are free:
the ledger no-ops a second run for a slot that already posted.

---

## Owner checklist -- these four need your credentials

Do them in this order. Nothing works until all four are done.

### 1. Create a fine-grained personal access token

github.com → **Settings** → **Developer settings** → **Personal access tokens** →
**Fine-grained tokens**.

- **Repository access:** only `GoVallecito/govallecito-bot`
- **Permissions:** `Actions: Read and write`, and nothing else
  (Metadata: read is added for you automatically)

**Put the expiry date in your calendar.** Expiry is *silent*: once the token lapses
the dispatch starts returning **404, not 401**, because GitHub hides repositories a
token cannot see rather than admitting the token is bad. Nothing in the worker can
tell that apart from "the workflow was deleted". The watchdog in the next section is
what actually catches it — but a calendar entry catches it *before* a silent morning.

### 2. Store the token in Cloudflare

Never in the repo.

```
cd trigger
wrangler secret put GITHUB_TOKEN
```

### 3. Create the healthchecks.io check

Free account at healthchecks.io.

- **Name:** `vallecito-morning-post`
- **Schedule:** cron `0 9 * * *`
- **Timezone:** `America/Denver`
- **Grace:** 1 hour

Copy its ping URL, then:

```
wrangler secret put HEALTHCHECK_URL
```

Set an email (or SMS) notification channel on the account before you finish, or the
check will detect failures perfectly and have nowhere to tell you.

### 4. Deploy

```
cd trigger
wrangler deploy
```

Then open the Cloudflare dashboard → the worker → **Settings** → **Triggers** and
confirm the cron `0 11-16 * * *` is attached.

**Do not skip that confirmation.** `wrangler deploy --dry-run` does *not* validate
cron expressions — verified on wrangler 4.144.0, where a deliberately bogus
`crons = ["not-a-cron"]` still exits 0 with no error. The dashboard is the only place
the attached trigger can be seen.

---

## How the watchdog covers everything

The worker checks the live feed on **every** firing:

- Post for today already published → ping the healthcheck, stop dispatching.
- No post yet, and the local hour is 5, 6, 7 or 8 → dispatch `forecast.yml`.
- Local 09:00 and still no post → ping `/fail`. It does **not** dispatch: a post
  stamped for this morning that lands after 9 reads stale.
- Worker dead, deleted, or never deployed → nothing pings at all, and healthchecks
  alarms on the **missing** ping at 10:00 Denver.

That single check therefore catches all of:

- an expired or revoked token
- a broken, undeployed or deleted worker
- a deleted cron trigger
- GitHub being down
- the dispatch being rejected
- **the review panel holding the draft** — a held post never reaches the feed

Alerting on the *absence of the expected thing* rather than the presence of an error
is the rule the last month kept proving.

### `HEALTHCHECK_URL_FORECAST` is a different, much weaker thing

The repo secret `HEALTHCHECK_URL_FORECAST` is **deliberately still unset**, and should
stay that way. `forecast.yml`'s heartbeat step pings on *job success*, and every
out-of-window run exits 0 successfully — so it would ping all day long and never
alarm, no matter how many mornings went silent. It would watch the job, not the post.

The check above watches for the **POST**, which is the thing that matters.

---

## Smoke test: the first thing to check on a silent morning

`morning-trigger.js` exposes a `fetch` handler that reports what a firing *right now*
would do, and dispatches nothing.

```
curl https://<worker>.workers.dev/
```

Fill in the real hostname after the first deploy. It returns the UTC time, the Denver
date and hour, the decided action (`attempt` / `watchdog` / `skip`), whether today's
post is already published, and whether each secret is configured.

`tokenConfigured: false` or `healthcheckConfigured: false` means a `wrangler secret
put` never landed.

---

## Local test

No network, no token, no Cloudflare account:

```
cd trigger
node worker.test.mjs ../site/weather/feed.json
```

Expect `ALL PASS`, exit 0, 29 `ok` lines. It covers both DST offsets, the 2026-11-01
and 2027-03-14 transition days, and the feed check against the real live `feed.json`.

**If a check fails, fix the code, not the test.**

---

## Four load-bearing constraints -- do not undo these

Each is a bug that has already happened, or was one step away.

1. **`slot` is sent as `""`, never `"school_call"`.** A non-empty slot takes
   `determine_slot`'s `FORCE_SLOT` branch, which skips the clock check and (outside
   the window) sets `WX_DRY_LEDGER`, so the run would publish *without claiming the
   ledger* and a later run could post the same day twice. That exact mechanism spent
   2026-09-25's morning.

2. **`dry_run` is sent explicitly as `"false"`.** The REST dispatch endpoint applies
   the workflow's *declared* defaults when `inputs` is omitted, and that default is
   `"true"` — which makes `_site_publish_allowed()` return False
   (`scripts/wx/run_forecast.py:604-612`). The run would compose, clear the panel, log
   `MAGISTRATE APPROVED` and publish nothing, looking green the whole way.

3. **Attempts are confined to local hours 5, 6, 7, 8.** Not 4: `_PUBLISH_TIME`
   promises 5:45am and `EARLY_STAMP_ALLOWANCE_MINUTES` is 45, so a run composing from
   05:00 stamps the promise honestly while 04:xx would stamp the real clock. Not 12 or
   later: `_target_date` (`run_forecast.py:135-139`) returns **tomorrow** once the
   local hour is >= 12, so an afternoon dispatch would claim and silence the next
   morning.

4. **The cron is `0 11-16 * * *` UTC and the offset is resolved in code**, via `Intl`
   with `America/Denver`. Do **not** move the DST logic into the cron expression.
   Encoding an offset in a cron range is precisely the bug that cost 2026-09-29.

---

## Secrets hygiene

`trigger/.dev.vars` is gitignored. Never commit a token or a ping URL — a healthchecks
ping URL is a credential too: anyone holding it can fake a heartbeat and suppress the
alarm.
