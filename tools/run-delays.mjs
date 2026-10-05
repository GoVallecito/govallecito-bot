#!/usr/bin/env node
// tools/run-delays.mjs -- how LATE each forecast run started, not how many ran.
//
// The blind spot that cost a month: every audit counted how many scheduled
// runs arrived and none measured how late they were. This reads the run IDs
// out of state/logs/forecast-<date>.log, asks the Actions API when each run was
// created, and reports its delay against what triggered it.
//
//   node tools/run-delays.mjs --date=2026-10-01      one day (default: today, Denver)
//   node tools/run-delays.mjs --all                  every retained log
//   --repo=owner/name   --runs-file=f.json   --canary-file=f.json   (tests)
//
// WHAT THE NUMBERS MEAN -- read this before trusting any of them:
//
//   dispatch  Exact. The Worker in trigger/ fires on the hour at the Denver
//             hours in its ATTEMPT_HOURS (05-08), so the delay is created_at
//             minus the last of those at or before it. A dispatch more than 15
//             minutes after one is a hand-run from the Actions tab: "manual".
//
//   schedule  A LOWER BOUND, and usually a useless one. The morning cron has a
//             slot every 15 minutes, so a run three hours late still starts
//             within 15 minutes of SOME slot. "Distance to the nearest slot"
//             cannot see lateness at all; this is how a "median 4.1 minutes,
//             punctual" reading came out of runs that were hours late. Shown
//             as ">=Nm (lower bound)" so nobody mistakes it for a delay.
//
//   canary    Exact. verify.yml and engagement-check.yml each have ONE cron a
//             day, so there is only one slot a run can belong to. They share
//             the scheduler, and this repo's concurrency group, with the
//             forecaster. Their delay IS the scheduler's delay on that day.
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ATTEMPT_HOURS } from '../trigger/morning-trigger.js';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const TZ = 'America/Denver';
export const FIRE_AT = ATTEMPT_HOURS.map(h => `${String(h).padStart(2, '0')}:00`);   // single source: trigger/
export const WINDOW = [4, 9];                      // scripts/wx/constants.py SCHOOL_CALL_WINDOW
const MIN = 60_000;

// --- time helpers ------------------------------------------------------------
function denverParts(ms) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(ms)).map(x => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, hh: +p.hour, mm: +p.minute, ss: +p.second,
           hhmm: `${p.hour}:${p.minute}` };
}
export const denverDate = ms => denverParts(ms).date;
export const denverClock = ms => { const p = denverParts(ms); return `${p.hhmm}:${String(p.ss).padStart(2, '0')}`; };

export function fmtDelay(ms) {
  const neg = ms < 0; ms = Math.abs(ms);
  const h = Math.floor(ms / 3_600_000), m = Math.floor(ms / MIN) % 60, s = Math.floor(ms / 1000) % 60;
  const body = h ? `${h}h${String(m).padStart(2, '0')}m` : m ? `${m}m${String(s).padStart(2, '0')}s` : `${s}s`;
  return (neg ? '-' : '+') + body;
}

// --- cron ------------------------------------------------------------------
function field(spec, lo, hi) {
  const out = new Set();
  for (const part of spec.split(',')) {
    const [range, stepS] = part.split('/');
    const step = stepS ? +stepS : 1;
    let a, b;
    if (range === '*') [a, b] = [lo, hi];
    else if (range.includes('-')) [a, b] = range.split('-').map(Number);
    else { a = +range; b = stepS ? hi : a; }
    for (let v = a; v <= b; v += step) out.add(v);
  }
  return out;
}
export function parseCron(expr) {
  const [mi, h, dom, mon, dow] = expr.trim().split(/\s+/);
  return { expr, mi: field(mi, 0, 59), h: field(h, 0, 23), dom: field(dom, 1, 31),
           mon: field(mon, 1, 12), dow: field(dow, 0, 6) };
}
const matches = (c, d) => c.mi.has(d.getUTCMinutes()) && c.h.has(d.getUTCHours()) &&
  c.dom.has(d.getUTCDate()) && c.mon.has(d.getUTCMonth() + 1) && c.dow.has(d.getUTCDay());

/** Last instant <= ms (minute resolution, UTC) matching any of the crons. */
export function lastSlot(crons, ms, maxBackMs = 26 * 3_600_000) {
  const start = Math.floor(ms / MIN) * MIN;
  for (let t = start; t >= start - maxBackMs; t -= MIN) {
    const d = new Date(t);
    const hit = crons.find(c => matches(c, d));
    if (hit) return { at: t, cron: hit.expr };
  }
  return null;
}

export function workflowCrons(file) {
  const src = readFileSync(file, 'utf8');
  return [...src.matchAll(/^\s*-\s*cron:\s*["']([^"']+)["']/gm)].map(m => parseCron(m[1]));
}

/** Last Worker fire time (FIRE_AT, Denver) at or before ms, as epoch ms. */
export function lastFire(ms) {
  for (let t = Math.floor(ms / MIN) * MIN; t >= ms - 26 * 3_600_000; t -= MIN) {
    if (FIRE_AT.includes(denverParts(t).hhmm)) return t;
  }
  return null;
}

// --- logs ------------------------------------------------------------------
export function classify(body) {
  if (/site feed -> /.test(body)) return 'PUBLISHED';
  if (/site publish is off for this run/.test(body)) return 'APPROVED, NOT PUBLISHED (dry run)';
  if (/HELD FOR REVIEW/.test(body)) return 'held for review';
  if (/BLOCKED -- nothing published/.test(body)) return 'blocked';
  if (/^Traceback/m.test(body)) return 'CRASHED';
  if (/already went out/.test(body)) return 'ledger no-op';
  if (/outside every posting window|is not a posting hour/.test(body)) return 'outside window';
  if (/is not in WX_SLOTS/.test(body)) return 'slot disabled';
  const exit = body.match(/^exit=(\d+)/m);
  return exit && exit[1] !== '0' ? `exit ${exit[1]}` : '?';
}

/** [{id, loggedAt, outcome}] from one forecast-<date>.log. */
export function parseLog(text) {
  const out = [];
  const re = /^=== (\S+) run (\d+) ===$/gm;
  const heads = [...text.matchAll(re)];
  heads.forEach((m, i) => {
    const body = text.slice(m.index + m[0].length, i + 1 < heads.length ? heads[i + 1].index : undefined);
    out.push({ id: m[2], loggedAt: m[1], outcome: classify(body) });
  });
  return out;
}

// --- GitHub ----------------------------------------------------------------
function ghRuns(repo, workflow, fromDate, toDate) {
  const q = `repos/${repo}/actions/workflows/${workflow}/runs?per_page=100&created=${fromDate}..${toDate}`;
  const out = execFileSync('gh', ['api', '--paginate', q, '--jq',
    '.workflow_runs[] | {id, event, created_at, run_started_at}'], { encoding: 'utf8' });
  return out.split('\n').filter(Boolean).map(l => JSON.parse(l));
}
const shiftDate = (d, n) => new Date(Date.parse(`${d}T12:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);

// --- report ------------------------------------------------------------------
export function analyse(date, logRuns, apiRuns, crons) {
  const byId = new Map(apiRuns.map(r => [String(r.id), r]));
  const rows = logRuns.map(l => {
    const a = byId.get(l.id);
    if (!a) return { ...l, trigger: '?', delay: 'not in API', local: l.loggedAt.slice(11, 19) + ' (log)' };
    const created = Date.parse(a.created_at);
    const started = Date.parse(a.run_started_at || a.created_at);
    const row = { ...l, created, local: denverClock(created), queued: fmtDelay(started - created) };
    if (a.event === 'workflow_dispatch') {
      const f = lastFire(created);
      if (f !== null && created - f <= 15 * MIN) {
        Object.assign(row, { trigger: `dispatch ${denverParts(f).hhmm}`, delayMs: created - f,
                             delay: fmtDelay(created - f) });
      } else Object.assign(row, { trigger: 'manual', delay: '-' });
    } else if (a.event === 'schedule') {
      const s = lastSlot(crons, created);
      Object.assign(row, { trigger: 'schedule',
        delay: s ? `>=${fmtDelay(created - s.at).slice(1)} (lower bound)` : '?' });
    } else Object.assign(row, { trigger: a.event, delay: '-' });
    return row;
  });
  return rows.sort((x, y) => (x.created ?? 0) - (y.created ?? 0));
}

export function canaryLines(canaries) {
  // canaries: [{workflow, cron, runs:[{event, created_at}]}] -> most recent scheduled run each
  return canaries.map(({ workflow, cron, runs }) => {
    const sched = runs.filter(r => r.event === 'schedule')
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
    if (!sched) return `- \`${workflow}\` (\`${cron}\` UTC): no scheduled run found in range.`;
    const t = Date.parse(sched.created_at);
    const s = lastSlot([parseCron(cron)], t);
    return `- \`${workflow}\` (\`${cron}\` UTC, one slot a day): run of ${denverDate(t)} started ` +
      `**${fmtDelay(t - s.at)}** after its slot.`;
  });
}

export function render(date, rows, canary) {
  const L = [];
  L.push(`### Run delays, ${date}`, '');
  L.push('| started (Denver) | run | trigger | delay vs trigger | queued | outcome |', '|---|---|---|---|---|---|');
  for (const r of rows) L.push(`| ${r.local} | ${r.id} | ${r.trigger} | ${r.delay} | ${r.queued ?? '-'} | ${r.outcome} |`);
  L.push('');
  const inWin = rows.filter(r => r.created && (h => h >= WINDOW[0] && h < WINDOW[1])(denverParts(r.created).hh));
  const first = inWin[0];
  if (!first) L.push(`**First run in the ${WINDOW[0]}:00-${WINDOW[1]}:00 window:** none. Nothing arrived in time to post.`);
  else {
    // Cloudflare cron plus the Worker's feed check land 1-3 minutes after the hour
    // (measured 2026-09-30: +1m35s to +2m16s). Five minutes is "on time".
    const ok = first.trigger === `dispatch ${FIRE_AT[0]}` && first.delayMs < 5 * MIN;
    L.push(`**First run in the ${WINDOW[0]}:00-${WINDOW[1]}:00 window:** ${first.local}, ${first.trigger}, ` +
      `${first.delay}, ${first.outcome}. ${ok ? 'OK: the dispatched run led, on time.'
        : `NOT the ${FIRE_AT[0]} dispatch within 5 minutes.`}`);
  }
  const spender = rows.find(r => /PUBLISHED|held|blocked|NOT PUBLISHED|CRASHED/.test(r.outcome));
  if (spender) L.push(`**Run that decided the day:** ${spender.local}, ${spender.trigger}: ${spender.outcome}.`);
  const disp = rows.filter(r => r.trigger?.startsWith('dispatch'));
  if (disp.length) L.push(`**Dispatch delays (exact):** ${disp.map(r => `${r.trigger.slice(9)} ${r.delay}`).join(', ')}.`);
  else if (date >= '2026-09-30') L.push('**Dispatch delays:** no dispatched run. Check the Worker: `curl https://wx-morning-trigger.dkontje.workers.dev`.');
  if (canary?.length) L.push('', '**Scheduler latency canaries** (exact; these are what the schedule path is really doing):', ...canary);
  L.push('', '_Schedule-row delays are lower bounds: with a slot every 15 minutes, an hours-late run still looks minutes late._');
  return L.join('\n');
}

// --- main ------------------------------------------------------------------
function main(argv) {
  const arg = k => argv.find(a => a.startsWith(`--${k}=`))?.split('=').slice(1).join('=');
  const repo = arg('repo') || process.env.GITHUB_REPOSITORY || 'GoVallecito/govallecito-bot';
  const logsDir = join(ROOT, 'state', 'logs');
  let dates;
  if (argv.includes('--all')) {
    dates = readdirSync(logsDir).map(f => f.match(/^forecast-(\d{4}-\d{2}-\d{2})\.log$/)?.[1]).filter(Boolean).sort();
  } else dates = [arg('date') || denverDate(Date.now())];

  const crons = workflowCrons(join(ROOT, '.github', 'workflows', 'forecast.yml'));
  const from = shiftDate(dates[0], -1), to = shiftDate(dates.at(-1), 1);
  const apiRuns = arg('runs-file') ? JSON.parse(readFileSync(arg('runs-file'), 'utf8'))
    : ghRuns(repo, 'forecast.yml', from, to);

  let canary = [];
  if (arg('canary-file')) canary = canaryLines(JSON.parse(readFileSync(arg('canary-file'), 'utf8')));
  else if (!arg('runs-file')) {
    canary = canaryLines(['verify.yml', 'engagement-check.yml'].flatMap(wf => {
      const c = workflowCrons(join(ROOT, '.github', 'workflows', wf));
      if (c.length !== 1) return [];      // only a single daily cron is unambiguous
      try { return [{ workflow: wf, cron: c[0].expr, runs: ghRuns(repo, wf, shiftDate(dates.at(-1), -2), to) }]; }
      catch { return []; }
    }));
  }

  const out = dates.map(d => {
    const f = join(logsDir, `forecast-${d}.log`);
    if (!existsSync(f)) return `### Run delays, ${d}\n\nNo \`state/logs/forecast-${d}.log\`. No forecast run logged that day.`;
    return render(d, analyse(d, parseLog(readFileSync(f, 'utf8')), apiRuns, crons), d === dates.at(-1) ? canary : []);
  });
  process.stdout.write(out.join('\n\n') + '\n');
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main(process.argv.slice(2));
