// tools/draft-lint.test.mjs -- run with `npm test`.
//
// Every fixture is clean.md with exactly one thing broken, and must trip
// exactly that one rule. Asserting the full set of rule keys, not just that the
// expected one is present, is what catches a rule that starts firing on text it
// has no business with.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const LINT = join(here, 'draft-lint.mjs');
const FIX = join(here, 'fixtures');
const DATE = '2026-09-15'; // a Tuesday

function run(file, extra = []) {
  const r = spawnSync(process.execPath,
    [LINT, join(FIX, file), `--date=${DATE}`, `--history=${join(FIX, 'history')}`, '--json', ...extra],
    { encoding: 'utf8' });
  const out = r.status === 2 ? null : JSON.parse(r.stdout);
  return { code: r.status, out, fails: out ? [...new Set(out.fails.map(f => f[0]))] : [],
           warns: out ? [...new Set(out.warns.map(w => w[0]))] : [] };
}

test('clean.md passes with no fails and no warns', () => {
  const r = run('clean.md');
  assert.equal(r.code, 0);
  assert.deepEqual(r.fails, []);
  assert.deepEqual(r.warns, []);
  assert.equal(r.out.stats.personal, 1);
});

const cases = {
  'em-dash.md': 'em-dash',               // shipped 2026-09-08: "this one -- Euro, GFS"
  'em-dash-unicode.md': 'em-dash',
  'road-status.md': 'road-status',       // shipped 2026-09-08: "The passes are dry."
  // shipped 2026-09-21: a surface claim with the verb left out, and about a
  // valley road rather than a pass. Issue #32.
  'road-status-adjective.md': 'road-status',
  'personal-zero.md': 'personal-count',
  'personal-two.md': 'personal-count',
  'bare-percent.md': 'bare-percent',     // shipped 2026-09-08: "Pop's at 4%"
  'weekday.md': 'weekday',
  'date-stamp.md': 'date-stamp',
  'snow-line.md': 'snow-line',
  'repeat-open.md': 'repeat-open',
  'repeat-close.md': 'repeat-close',
};

for (const [file, key] of Object.entries(cases)) {
  test(`${file} trips exactly ${key}`, () => {
    const r = run(file);
    assert.equal(r.code, 1);
    assert.deepEqual(r.fails, [key]);
  });
}

// Two of the four `road-status` review issues were this file's fault, not the
// composer's: correctly hedged forecast copy that rule 2 failed anyway. The
// header rule applies -- where this file and system.md disagree, the persona
// wins and this file is wrong.
test('"enough to wet pavement" is a forecast, not a road report', () => {
  // "wet" as an infinitive verb. Issue #33.
  const r = run('road-status-infinitive.md');
  assert.equal(r.code, 0);
  assert.deepEqual(r.fails, []);
});

test("\"I'd plan for wet roads\" is the phrasing system.md asks for", () => {
  // system.md gives "I'd expect dry pavement by the 6:30 call" as the correct
  // repair, and this file used to fail it. Issue #34.
  const r = run('road-status-hedged.md');
  assert.equal(r.code, 0);
  assert.deepEqual(r.fails, []);
});

test('the hedge cannot launder an unhedged clause beside it', () => {
  const src = readFileSync(join(FIX, 'clean.md'), 'utf8').replace(
    /^Coal Bank and Molas should stay dry through the morning\./m,
    'Coal Bank should stay dry and Molas is clear right now.');
  const tmp = join(FIX, 'road-status-mixed.md');
  writeFileSync(tmp, src);
  try {
    const r = run('road-status-mixed.md');
    assert.equal(r.code, 1);
    assert.deepEqual(r.fails, ['road-status']);
  } finally { rmSync(tmp); }
});

test('unknowable.md warns but does not fail', () => {
  const r = run('unknowable.md');
  assert.equal(r.code, 0);
  assert.deepEqual(r.fails, []);
  assert.deepEqual(r.warns, ['unknowable']);
});

test('a snow line above 14,000 ft passes when the brief itself says so', () => {
  const r = run('snow-line-grounded.md');
  assert.equal(r.code, 0);
  assert.deepEqual(r.fails, []);
});

test('the shipped strings are caught verbatim', () => {
  const md = spawnSync(process.execPath,
    [LINT, join(FIX, 'road-status.md'), `--date=${DATE}`, '--history=none'], { encoding: 'utf8' }).stdout;
  assert.match(md, /The passes are dry/);
  assert.match(spawnSync(process.execPath,
    [LINT, join(FIX, 'bare-percent.md'), `--date=${DATE}`], { encoding: 'utf8' }).stdout, /Pop's at 4%/);
});

test('missing --date is a usage error', () => {
  const r = spawnSync(process.execPath, [LINT, join(FIX, 'clean.md')], { encoding: 'utf8' });
  assert.equal(r.status, 2);
});
