// node --test tools/run-delays.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseCron, lastSlot, lastFire, parseLog, analyse, render, canaryLines, fmtDelay, classify }
  from './run-delays.mjs';

const MORNING = ['5,20,35,50 10-15 * * *', '5,35 1-6 * * *', '45 * * * *'].map(parseCron);
const T = s => Date.parse(s);

test('fmtDelay', () => {
  assert.equal(fmtDelay(42_000), '+42s');
  assert.equal(fmtDelay(3 * 60_000 + 5_000), '+3m05s');
  assert.equal(fmtDelay(199 * 60_000), '+3h19m');
});

test('lastSlot finds the latest matching minute across crons', () => {
  assert.equal(new Date(lastSlot(MORNING, T('2026-10-01T11:31:40Z')).at).toISOString(), '2026-10-01T11:20:00.000Z');
  assert.equal(new Date(lastSlot(MORNING, T('2026-10-01T17:10:00Z')).at).toISOString(), '2026-10-01T16:45:00.000Z');
});

test('lastFire maps to the Worker Denver hours in both seasons', () => {
  assert.equal(new Date(lastFire(T('2026-10-01T11:01:35Z'))).toISOString(), '2026-10-01T11:00:00.000Z'); // 05:00 MDT
  assert.equal(new Date(lastFire(T('2026-12-01T12:01:00Z'))).toISOString(), '2026-12-01T12:00:00.000Z'); // 05:00 MST
  assert.equal(new Date(lastFire(T('2026-10-01T14:02:00Z'))).toISOString(), '2026-10-01T14:00:00.000Z'); // 08:00 MDT
});

test('classify recognises the dry-run trap separately from a publish', () => {
  assert.equal(classify('MAGISTRATE APPROVED, but site publish is off for this run (x)'), 'APPROVED, NOT PUBLISHED (dry run)');
  assert.equal(classify('site post -> a\nsite feed -> b'), 'PUBLISHED');
  assert.equal(classify('school_call for 2026-10-01 already went out at x; nothing to do.'), 'ledger no-op');
});

const LOG = `=== 2026-10-01T00:34:10-06:00 run 100 ===
2026-10-01 00:33 MDT is outside every posting window (school_call 4:00-9:00 local). Exiting.
exit=0

=== 2026-10-01T05:34:02-06:00 run 101 ===
=== Vallecito forecast: school_call @ 2026-10-01 05:00 MDT ===
MAGISTRATE APPROVED (ok); publishing to the website
site post -> site/weather/x.md
site feed -> site/weather/feed.json
exit=0

=== 2026-10-01T07:01:01-06:00 run 102 ===
school_call for 2026-10-01 already went out at 2026-10-01T05:33:50-06:00; nothing to do.
exit=0

=== 2026-10-01T09:20:00-06:00 run 103 ===
2026-10-01 09:19 MDT is outside every posting window (school_call 4:00-9:00 local). Exiting.
exit=0
`;
const RUNS = [
  { id: 100, event: 'schedule', created_at: '2026-10-01T06:33:05Z', run_started_at: '2026-10-01T06:33:12Z' },
  { id: 101, event: 'workflow_dispatch', created_at: '2026-10-01T11:00:03Z', run_started_at: '2026-10-01T11:00:09Z' },
  { id: 102, event: 'workflow_dispatch', created_at: '2026-10-01T12:00:02Z', run_started_at: '2026-10-01T12:00:08Z' },
  { id: 103, event: 'schedule', created_at: '2026-10-01T15:19:30Z', run_started_at: '2026-10-01T15:19:40Z' },
];

test('a good morning: dispatch leads within 2 minutes and publishes', () => {
  const rows = analyse('2026-10-01', parseLog(LOG), RUNS, MORNING);
  assert.deepEqual(rows.map(r => r.trigger), ['schedule', 'dispatch 05:00', 'dispatch 06:00', 'schedule']);
  assert.equal(rows[1].delay, '+3s');
  assert.equal(rows[1].outcome, 'PUBLISHED');
  assert.match(rows[3].delay, /^>=14m30s \(lower bound\)$/);
  const md = render('2026-10-01', rows, []);
  assert.match(md, /OK: the dispatched run led, on time\./);
  assert.match(md, /Dispatch delays \(exact\):\*\* 05:00 \+3s, 06:00 \+2s/);
});

test('a bad morning: first in-window run is a late schedule run -> flagged', () => {
  const runs = RUNS.filter(r => r.event === 'schedule')
    .concat({ id: 101, event: 'schedule', created_at: '2026-10-01T11:34:00Z' });
  const md = render('2026-10-01', analyse('2026-10-01', parseLog(LOG), runs, MORNING), []);
  assert.match(md, /NOT the 05:00 dispatch within 5 minutes/);
  assert.match(md, /no dispatched run/);
});

test('canary: one-cron-a-day workflow gives an exact delay', () => {
  const [line] = canaryLines([{ workflow: 'verify.yml', cron: '30 15 * * *',
    runs: [{ event: 'schedule', created_at: '2026-09-30T18:49:00Z' }] }]);
  assert.match(line, /\*\*\+3h19m\*\* after its slot/);
});
