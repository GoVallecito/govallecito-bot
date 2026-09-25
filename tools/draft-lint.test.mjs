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
  // valley road rather than a pass. Issue #30.
  'road-status-adjective.md': 'road-status',
  // A closure is not hedgeable: "will likely be closed" is not a hedged
  // version of a fact we hold, it is invention about a CDOT decision.
  'road-status-closure.md': 'road-status',
  // A conditional addressed to the reader picks out an audience; it does not
  // make the claim after it contingent.
  'road-status-reader-addressed.md': 'road-status',
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
  // "wet" as an infinitive verb. Issue #32.
  const r = run('road-status-infinitive.md');
  assert.equal(r.code, 0);
  assert.deepEqual(r.fails, []);
});

test("\"I'd plan for wet roads\" is the phrasing system.md asks for", () => {
  // system.md gives "I'd expect dry pavement by the 6:30 call" as the correct
  // repair, and this file used to fail it. Issue #33.
  const r = run('road-status-hedged.md');
  assert.equal(r.code, 0);
  assert.deepEqual(r.fails, []);
});

test('reader-addressed advice with no road claim still passes', () => {
  // The persona writes these constantly. "If you're getting out on a trail
  // today its a good window for it" is from a shipped post.
  const src = readFileSync(join(FIX, 'clean.md'), 'utf8').replace(
    /^Coal Bank and Molas should stay dry through the morning\./m,
    "If you're running the 550 today, check CDOT before you go, and I'd expect " +
    'wet pavement by the 6:30 call.');
  const tmp = join(FIX, 'road-status-reader-ok.md');
  writeFileSync(tmp, src);
  try {
    const r = run('road-status-reader-ok.md');
    assert.equal(r.code, 0);
    assert.deepEqual(r.fails, []);
  } finally { rmSync(tmp); }
});

test('a weather-contingent conditional still exempts the sentence', () => {
  const src = readFileSync(join(FIX, 'clean.md'), 'utf8').replace(
    /^Coal Bank and Molas should stay dry through the morning\./m,
    'If that band sets up, the 550 is icy by 6am and Molas is slick.');
  const tmp = join(FIX, 'road-status-weather-if.md');
  writeFileSync(tmp, src);
  try {
    const r = run('road-status-weather-if.md');
    assert.equal(r.code, 0);
    assert.deepEqual(r.fails, []);
  } finally { rmSync(tmp); }
});

// The seven a code review found on the branch, mirrored from
// tests/test_guardrails.py so the two gates cannot drift apart again.
function withBody(text) {
  return readFileSync(join(FIX, 'clean.md'), 'utf8').replace(
    /^Coal Bank and Molas should stay dry through the morning\./m, text);
}
function lintBody(name, text) {
  const tmp = join(FIX, name);
  writeFileSync(tmp, withBody(text));
  try { return run(name); } finally { rmSync(tmp); }
}

for (const [label, text] of [
  // "close" is the adjective, and "passes" is a verb. Both were hedge-exempt
  // fails on ordinary weather prose.
  ['close-adjective', 'Coal Bank and Molas are close to the freezing line this morning.'],
  ['passes-verb', 'The cold front passes through around noon, closing out the showers.'],
  // A bare "and" splits coordinated noun phrases and strips the modal.
  ['coordination', "I'd expect wet pavement in town and icy roads on the 550."],
]) {
  test(`${label} is not a road-status claim`, () => {
    const r = lintBody(`road-status-${label}.md`, text);
    assert.deepEqual(r.fails, []);
    assert.equal(r.code, 0);
  });
}

for (const [label, text] of [
  // A time window says when, never whether -- and the verbless forms this
  // rule exists to catch never carry the copula the old guard keyed on.
  ['verbless-window', 'Dry roads all day.'],
  ['verbless-window2', 'Wet pavement through the morning.'],
  // A newline ends a sentence; collapsing it let one "if" exempt two lines.
  ['newline', 'If that band sets up we could see 2-3 inches\nThe passes are dry right now.'],
  // The inverted conditional is reader-addressed too.
  ['inverted-conditional', "Should you be heading over Molas, it's closed."],
  // The foot-mark exclusion must not swallow the possessive.
  ['possessive-closure', "The 550's closed this morning."],
  ['possessive-surface', "The 501's fine for the bus run."],
]) {
  test(`${label} is caught`, () => {
    const r = lintBody(`road-status-${label}.md`, text);
    assert.deepEqual(r.fails, ['road-status']);
    assert.equal(r.code, 1);
  });
}

// A second review round found four of the seven fixes above incomplete, two of
// them self-defeating. Cases are taken from the corpus idiom, not invented.
for (const [label, text] of [
  // `(?:be\s+)?(?:close)` put the adjective back in the same hunk that removed it.
  ['modal-be-close', 'The snow line will be close to 11,000 feet on the passes.'],
  // "run" is a noun: "bus run"/"school run" appears 33x in the corpus.
  ['bus-run', "I'd expect wet pavement in town and icy roads for the bus run."],
  ['school-run', "I'd expect slick spots and wet roads for the school run."],
  // A noun phrase is not a road-status claim.
  ['gravel', 'Vallecito Road, fine gravel past the turn.'],
]) {
  test(`${label} is not a road-status claim`, () => {
    const r = lintBody(`road-status-${label}.md`, text);
    assert.deepEqual(r.fails, []);
    assert.equal(r.code, 0);
  });
}

for (const [label, text] of [
  // Only a coordinating "and" carries a hedge across.
  ['semicolon', 'The front should clear by noon; wet roads and icy pavement on the 550.'],
  ['but-clause', 'The front should clear by noon, but wet roads and icy pavement on the 550.'],
  // The determiner needs a word of slack, and the bare copula form counts.
  ['high-passes', 'The high passes are closed this morning.'],
  ['bare-passes', 'Passes are closed.'],
  // The infinitive, which dropping bare "close" had also dropped.
  ['set-to-close', 'Molas is set to close this afternoon.'],
  // system.md forbids this one BY NAME and this file used to miss it entirely.
  ['telegraphic', 'Roads wet, no ice.'],
  // A clause with road + verb + surface asserts on its own.
  ['own-predicate', 'Coal Bank should stay dry, and Molas stays clear.'],
]) {
  test(`${label} is caught`, () => {
    const r = lintBody(`road-status-${label}.md`, text);
    assert.deepEqual(r.fails, ['road-status']);
    assert.equal(r.code, 1);
  });
}

// The accepted cost of not splitting on a bare "and"/"but". Pinned so it is a
// known trade rather than something rediscovered by a later review: the same
// sentence with the comma the persona usually writes is still caught, above.
test('an uncommaed coordination is a known miss', () => {
  const r = lintBody('road-status-uncommaed.md',
    'Coal Bank should stay dry and Molas is clear right now.');
  assert.deepEqual(r.fails, []);
});

// Round four.
for (const [label, text] of [
  // A modal governs what FOLLOWS it; report-then-advice is not hedged.
  ['trailing-modal', 'Roads are wet and it should dry out by noon.'],
  ['trailing-modal2', 'The 550 is icy this morning and you should leave early.'],
  // The pass copula list must accept the same verbs ROAD_STATE does.
  ['passes-run-icy', 'The snowy passes run icy.'],
  // "to close TO" excludes numbers, not traffic.
  ['close-to-traffic', 'Red Mountain is set to close to traffic at six.'],
  // Everything the deleted duplicate rule set uniquely caught.
  ['all-clear', 'Coal Bank and Molas all clear.'],
  ['currently', 'The 550 is currently dry.'],
  ['time-tail', 'Red Mountain all clear this morning.'],
]) {
  test(`${label} is caught`, () => {
    const r = lintBody(`road-status-${label}.md`, text);
    assert.deepEqual(r.fails, ['road-status']);
    assert.equal(r.code, 1);
  });
}

for (const [label, text] of [
  // A proximity window may not cross a coordination: the subject changes.
  ['closure-across-and', 'Molas and Coal Bank both pick up snow and the districts may close.'],
  ['surface-across-and', 'The front moves through Wolf Creek and the ski area is open.'],
  ['proximity', 'Snow piles up on Red Mountain and the window is clear.'],
  ['proximity2', 'Molas and Coal Bank pick up a few inches and the valley stays dry.'],
]) {
  test(`${label} is not a road-status claim`, () => {
    const r = lintBody(`road-status-${label}.md`, text);
    assert.deepEqual(r.fails, []);
    assert.equal(r.code, 0);
  });
}

// Round five.
for (const [label, text] of [
  ['close-to-amount', 'That adds up to close to a foot on Red Mountain by morning.'],
  ['close-to-two-feet', 'Up to close to two feet on Wolf Creek.'],
  // A trailing subordinator scopes backwards, unlike a modal.
  ['trailing-if', 'The 550 is icy if that band sets up.'],
  ['trailing-unless', 'Molas is slick unless the sun gets it.'],
]) {
  test(`${label} is not a road-status claim`, () => {
    const r = lintBody(`road-status-${label}.md`, text);
    assert.deepEqual(r.fails, []);
    assert.equal(r.code, 0);
  });
}

for (const [label, text] of [
  ['expect-to-close', 'They expect to close the 550 overnight.'],
  ['reverse-order', 'All clear on Red Mountain this morning.'],
  ['reverse-order2', 'All clear over Molas and Coal Bank.'],
  ['adj-preposition', 'Red Mountain bare to the top.'],
  ['gets-icy', 'The passes get icy.'],
  ['gets-icy2', 'The 550 gets icy.'],
]) {
  test(`${label} is caught`, () => {
    const r = lintBody(`road-status-${label}.md`, text);
    assert.deepEqual(r.fails, ['road-status']);
    assert.equal(r.code, 1);
  });
}

test('a traction law forecast is still allowed', () => {
  // constants.py holds "expect traction law by morning" up as the product: it
  // is a consequence of weather we have, unlike a gate coming down.
  const src = readFileSync(join(FIX, 'clean.md'), 'utf8').replace(
    /^Coal Bank and Molas should stay dry through the morning\./m,
    'Coal Bank and Molas pick up 8-14 inches overnight, so expect traction law by morning.');
  const tmp = join(FIX, 'road-status-traction.md');
  writeFileSync(tmp, src);
  try {
    const r = run('road-status-traction.md');
    assert.equal(r.code, 0);
    assert.deepEqual(r.fails, []);
  } finally { rmSync(tmp); }
});

test('the hedge cannot launder an unhedged clause beside it', () => {
  const src = readFileSync(join(FIX, 'clean.md'), 'utf8').replace(
    /^Coal Bank and Molas should stay dry through the morning\./m,
    'Coal Bank should stay dry, and Molas is clear right now.');
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

// --- cross-gate parity -----------------------------------------------------
//
// tools/fixtures/road-cases.json is the shared road-status corpus. This block
// runs it through rule 2, and through the PUBLISHING gate via
// tools/road-gate-probe.py, and requires all three to agree.
//
// It lives here rather than only in tests/test_road_gate_parity.py because
// `npm test` is the only suite CI runs (daily-audit.yml), so this is the one
// place a divergence gets caught automatically. The two gates drifting apart
// is not hypothetical: it is the bug PR #35 was opened for -- draft-lint.mjs
// caught road claims hours later on the review issue that guardrails.py never
// saw, so the rewrite loop that could have fixed them never fired.

const CASES = JSON.parse(readFileSync(join(FIX, 'road-cases.json'), 'utf8')).cases;

// Only rule 2's verdict; a bare sentence dropped into clean.md trips other
// rules (personal-count and friends) that this corpus says nothing about.
const roadVerdict = (name, text) =>
  lintBody(name, text).fails.includes('road-status') ? 'claim' : 'clean';

test('the linter agrees with the road corpus', () => {
  const wrong = [];
  CASES.forEach((c, i) => {
    const got = roadVerdict(`road-cases-${i}.md`, c.text);
    if (got !== c.verdict)
      wrong.push(`  wanted ${c.verdict.padEnd(5)} got ${got.padEnd(5)} ${JSON.stringify(c.text)}\n      ${c.note}`);
  });
  assert.equal(wrong.length, 0,
    `draft-lint.mjs disagrees with tools/fixtures/road-cases.json:\n${wrong.join('\n')}`);
});

test('both gates reach the same verdict on every case', () => {
  // Windows has no `python3`, and CLAUDE.md documents Windows. PYTHON
  // overrides for a venv or a pinned interpreter.
  //
  // Advance on the RESULT, not on the spawn. Windows ships a Microsoft Store
  // `python3.exe` App Execution Alias on PATH by default, and a python.org
  // install does not shadow it because it ships no `python3.exe` at all. That
  // alias spawns without error and exits 9009, so breaking on `!error` would
  // stop at it and never reach `py` -- red on exactly the platform this
  // fallback was added for.
  //
  // Exit 2 is road-gate-probe.py's own "could not load guardrails": that is a
  // real failure to report, not a wrong interpreter, so stop there too rather
  // than masking it by trying the next candidate.
  const candidates = process.env.PYTHON ? [process.env.PYTHON]
    : ['python3', 'python', 'py'];
  let probe = null, last = null;
  for (const exe of candidates) {
    const attempt = spawnSync(exe, [join(here, 'road-gate-probe.py')], { encoding: 'utf8' });
    last = { exe, ...attempt };
    if (!attempt.error && (attempt.status === 0 || attempt.status === 2)) {
      probe = attempt;
      break;
    }
  }
  if (!probe) {
    // Not a silent pass: say so loudly, because a skipped parity check looks
    // exactly like a passing one in the TAP output.
    assert.fail(`no usable python found for tools/road-gate-probe.py. Tried ` +
      `${candidates.join(', ')}; last was ${last?.exe} ` +
      `(${last?.error?.code ?? `exit ${last?.status}`}). One must be on PATH ` +
      'for the cross-gate check, or set PYTHON; guardrails.py needs only the stdlib.');
  }
  assert.equal(probe.status, 0, `road-gate-probe.py exited ${probe.status}: ${probe.stderr}`);

  const gate = JSON.parse(probe.stdout).results;
  assert.equal(gate.length, CASES.length, 'the probe saw a different corpus');

  const disagreements = [];
  CASES.forEach((c, i) => {
    assert.equal(gate[i].text, c.text, 'corpus order changed under the probe');
    const lint = roadVerdict(`road-cases-x-${i}.md`, c.text);
    if (lint !== gate[i].verdict)
      disagreements.push(`  guardrails ${gate[i].verdict.padEnd(5)} lint ${lint.padEnd(5)} ` +
        `${JSON.stringify(c.text)}\n      ${c.note}`);
  });
  assert.equal(disagreements.length, 0,
    'the two gates disagree. system.md decides and the linter is the one that is wrong:\n' +
    disagreements.join('\n'));
});

