// tools/draft-lint.test.mjs -- run with `npm test`.
//
// Every fixture is clean.md with exactly one thing broken, and must trip
// exactly that one rule. Asserting the full set of rule keys, not just that the
// expected one is present, is what catches a rule that starts firing on text it
// has no business with.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
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
