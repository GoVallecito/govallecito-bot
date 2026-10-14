/**
 * wx-morning-trigger -- fires the Vallecito morning forecast, and alarms on silence.
 *
 * WHY THIS EXISTS. GitHub's cron is the only scheduler GitHub offers and it is the
 * thing that fails: across 2026-09-18..29 only about 17% of forecast.yml's requested
 * slots executed, and 2026-09-28 and 09-29 produced no morning post at all. The runs
 * that do execute arrive hours LATE (verify.yml, one cron a day: median 199 min) and
 * the forecaster's own window check discards them. (An earlier note here called them
 * punctual, "median 4.1 min from their slot"; with a slot every 15 minutes, distance
 * to the nearest slot cannot see lateness.) workflow_dispatch goes through a
 * different path and starts in seconds, so this worker dispatches on Cloudflare's clock.
 *
 * DESIGN NOTES, so the next person does not undo them by accident:
 *
 * - Cloudflare cron is UTC. Rather than encode an offset in the cron expression --
 *   the mistake that cost 2026-09-29 -- the cron fires hourly across the widest
 *   possible span and THIS CODE decides, from the real tz database via Intl, what
 *   the Denver local hour is. DST needs no edit, ever.
 * - `slot` is sent as the empty string, NEVER "school_call". A non-empty slot takes
 *   run_forecast.determine_slot's FORCE_SLOT branch, which skips the clock check and
 *   (outside the window) sets WX_DRY_LEDGER, so the run would publish without
 *   claiming the ledger and a later run could post the day twice.
 * - `dry_run` is sent explicitly as "false". The REST dispatch endpoint applies the
 *   workflow's DECLARED defaults when inputs are omitted. That default was "true"
 *   until 2026-10 (now "false"; keep sending it anyway), and "true" makes
 *   run_forecast._site_publish_allowed() return False: the run would
 *   compose, pass the review panel, log MAGISTRATE APPROVED and publish nothing,
 *   looking green the whole way.
 * - Attempts are restricted to local hours 5,6,7,8. Not 4: _PUBLISH_TIME promises
 *   5:45am and compose.EARLY_STAMP_ALLOWANCE_MINUTES is 45, so a run composing at
 *   05:00 or later stamps the promise honestly, while 04:xx would stamp the real
 *   clock. Not 12 or later: run_forecast._target_date returns TOMORROW once the hour
 *   is >= 12, so an afternoon dispatch would claim the next morning's slot and
 *   silence it.
 * - The feed is checked before every dispatch, so once the day's post is up the
 *   worker stops firing. Extra dispatches would be harmless (the ledger no-ops them)
 *   but they queue in the shared concurrency group, which is the suspected reason
 *   scheduled runs go missing.
 */

const REPO = "GoVallecito/govallecito-bot";
const WORKFLOW = "forecast.yml";

/* SECOND JOB (2026-10-14): start the emergency-alert system-health check every hour.
 * system-health.yml asks GitHub for "7 * * * *" and GitHub delivered it every 3-8 hours
 * (Oct 7-13), while its limits (worker-lpcalerts/health-logic.js: canary and report 150
 * min, emergency run 180 min) assume hourly. So govallecito.com/data/health.json, the page
 * UptimeRobot watches, read FAIL most of every day with nothing broken, and the
 * health-alert issue + healthchecks.io /fail fired every day or two (#84 #89 #93 #100
 * #104, all the same stale-run line). A monitor that is red by default cannot report a
 * real outage. Same fix as the forecast: workflow_dispatch on Cloudflare's clock.
 * GitHub's own hourly cron stays as the backup; an extra run is harmless (the repo is
 * public, so Actions minutes are free, and each run takes ~20 s). Uses the same
 * GITHUB_TOKEN (Actions: read and write on this repo) the forecast dispatch uses. */
export const HEALTH_CRON = "7 * * * *";
export const HEALTH_WORKFLOW = "system-health.yml";

/** Which job a firing belongs to. Cloudflare passes the cron expression that fired. */
export function jobFor(cron) {
  return cron === HEALTH_CRON ? "health" : "morning";
}
const FEED = `https://raw.githubusercontent.com/${REPO}/main/site/weather/feed.json`;

export const ATTEMPT_HOURS = [5, 6, 7, 8];
export const WINDOW_CLOSE = 9;          // SCHOOL_CALL_WINDOW (4, 9), close exclusive

/** Denver wall-clock date and hour, from the real tz database. */
export function denverParts(now) {
  const f = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Denver",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
  const p = Object.fromEntries(f.formatToParts(now).map(x => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, hour: +p.hour, minute: +p.minute };
}

/** What this firing should do. */
export function decide(now) {
  const { date, hour } = denverParts(now);
  if (ATTEMPT_HOURS.includes(hour)) return { action: "attempt", date, hour };
  if (hour === WINDOW_CLOSE) return { action: "watchdog", date, hour };
  return { action: "skip", date, hour };
}

/** Is the morning post for `localDate` already published? */
export function hasPostFor(feedJson, localDate) {
  const posts = (feedJson && feedJson.posts) || [];
  return posts.some(p => p.forDate === localDate && p.postType === "school_call");
}

async function feedHasToday(localDate) {
  // raw.githubusercontent caches for a few minutes; bust it and bypass the
  // Workers cache too. Never use jsdelivr here: it lags a day and caused a
  // false "no draft" alarm on 2026-09-19.
  const res = await fetch(`${FEED}?t=${Date.now()}`, {
    cache: "no-store",
    headers: { "User-Agent": "wx-morning-trigger" },
  });
  if (!res.ok) throw new Error(`feed fetch ${res.status}`);
  return hasPostFor(await res.json(), localDate);
}

async function dispatch(token, workflow = WORKFLOW, inputs = { slot: "", dry_run: "false" }) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        // GitHub rejects API requests with no User-Agent.
        "User-Agent": "wx-morning-trigger",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    },
  );
  // 204 No Content is success, and carries no run id, so "the API accepted it"
  // is NOT "a run executed". Only the feed check proves a post happened.
  if (res.status !== 204) {
    throw new Error(`dispatch ${res.status}: ${(await res.text()).slice(0, 300)}`);
  }
}

async function ping(url, suffix = "", body = "") {
  if (!url) return;
  try {
    await fetch(url + suffix, { method: "POST", body: body.slice(0, 900) });
  } catch (e) {
    console.log(`healthcheck ping failed: ${e.message}`);   // never fatal
  }
}

export default {
  async scheduled(event, env, ctx) {
    if (jobFor(event.cron) === "health") {
      // Not the morning logic at all: no feed check, no window, never touches the
      // morning healthcheck ping. If this stops working, system-health's own
      // healthchecks.io heartbeat goes overdue and alarms -- that is its backstop.
      try {
        await dispatch(env.GITHUB_TOKEN, HEALTH_WORKFLOW, {});
        console.log(`dispatched ${HEALTH_WORKFLOW}`);
      } catch (e) {
        console.log(`HEALTH DISPATCH FAILED: ${e.message}`);
        throw e;
      }
      return;
    }
    const now = new Date(event.scheduledTime ?? Date.now());
    const { action, date, hour } = decide(now);
    console.log(`fired ${now.toISOString()} -> Denver ${date} ${hour}:00, action=${action}`);
    if (action === "skip") return;

    try {
      if (await feedHasToday(date)) {
        console.log(`post for ${date} is already published; nothing to do`);
        await ping(env.HEALTHCHECK_URL, "", `post for ${date} published`);
        return;
      }
    } catch (e) {
      // A feed read failure must not stop the dispatch: publishing late beats
      // not publishing. It DOES suppress the success ping, so silence alarms.
      console.log(`feed check failed (${e.message}); dispatching anyway`);
      if (action === "watchdog") {
        await ping(env.HEALTHCHECK_URL, "/fail", `feed unreadable at ${hour}:00: ${e.message}`);
        return;
      }
    }

    if (action === "watchdog") {
      // Window closed with no post. Say so loudly; do not dispatch, a post
      // stamped for this morning that lands after 9 reads stale.
      const msg = `no school_call for ${date} and the window has closed`;
      console.log(`WATCHDOG: ${msg}`);
      await ping(env.HEALTHCHECK_URL, "/fail", msg);
      return;
    }

    try {
      await dispatch(env.GITHUB_TOKEN);
      console.log(`dispatched forecast.yml for ${date} at local ${hour}:00`);
    } catch (e) {
      console.log(`DISPATCH FAILED: ${e.message}`);
      await ping(env.HEALTHCHECK_URL, "/fail", `dispatch failed at ${hour}:00: ${e.message}`);
      throw e;   // surface it in the Cloudflare dashboard too
    }
  },

  // Manual smoke test: `curl https://<worker>.workers.dev/` reports what a
  // firing right now WOULD do, and touches nothing.
  async fetch(req, env) {
    const now = new Date();
    const d = decide(now);
    let feed = "not checked";
    try { feed = (await feedHasToday(d.date)) ? "published" : "not yet"; }
    catch (e) { feed = `unreadable: ${e.message}`; }
    return Response.json({
      utc: now.toISOString(), denver: d, todaysPost: feed,
      tokenConfigured: Boolean(env.GITHUB_TOKEN),
      healthDispatch: `${HEALTH_WORKFLOW} on cron "${HEALTH_CRON}"`,
      healthcheckConfigured: Boolean(env.HEALTHCHECK_URL),
    }, { headers: { "cache-control": "no-store" } });
  },
};
