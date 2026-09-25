#!/usr/bin/env node
// tools/draft-lint.mjs -- deterministic quality gate for the morning forecast draft.
//
// Zero dependencies, Node 20+. No network, no model. The same draft always
// produces the same verdict, which is the whole reason this lives in CI rather
// than in a scheduled model run.
//
//   node tools/draft-lint.mjs <draftfile> --date=YYYY-MM-DD [--history=state/drafts] [--json]
//
// Exit 0 = clean (warnings allowed), 1 = one or more FAILs, 2 = usage error.
//
// Reads both on-disk shapes the forecaster writes:
//   site/weather/_pending/<date>-<slug>.md   front matter, one JSON value per key
//   state/drafts/<date>-<slot>.md            "# Weekday, date, slot" header, then ---
//
// Every rule below is a rule from scripts/wx/prompts/system.md. Where the
// wording here and the persona disagree, the persona wins and this file is wrong.
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const WEEKDAYS = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
const MONTHS = ['January','February','March','April','May','June','July','August',
                'September','October','November','December'];

// The persona opens every post with this: `11/04/26 5:52am: Morning, its Wednesday.`
const STAMP = /^(\d{2})\/(\d{2})\/(\d{2})\s+\d{1,2}:\d{2}\s*[ap]m:\s*/i;

// Local proper nouns that turn a clause into a road/pass report.
const ROADS = [
  'Coal Bank','Molas','Red Mountain','Wolf Creek','Cumbres','Lizard Head','Hesperus',
  'US 160','US-160','Highway 160','the 160','US 550','US-550','Highway 550','the 550',
  'CO 172','Highway 172','the 172','County Road 501','CR 501','the 501',
  'County Road 500','CR 500','the 500','CR 240','the 240','Florida Road',
  'Vallecito Road','Bayfield Parkway','Elmore',
  'Middle Mountain Road','Missionary Ridge Road'
];
// "passes" is also the verb for weather moving through. Two forms, and no
// guessing from the surrounding words: a determiner immediately before, or a
// copula immediately after. That covers "the passes", "The passes over the
// divide are closed", "The high passes are closed" and a bare "Passes are
// closed", while "the front passes midday" is neither. An earlier cut allowed
// a word of slack plus a list of words only a moving system takes; it read
// "the front passes" as a road and threw away "The passes over the divide".
// Mirrors guardrails._ROAD_NAME.
const PASS_NOUN = /(?:\b(?:the|these|those|both|all|either|our)\s+pass(?:es)?\b|\bpass(?:es)?(?=\s+(?:is|are|'s|was|were|remains?|stays?|looks?)))/i;
// A bare route number, which the list above only caught when it carried its
// article. The article was there because "the 160 cfs" style numbers bite:
// this persona writes elevations as "(6,500')" and flows as "running 160 cfs",
// and a word boundary sits on both sides of the number in each. Excluding
// those two contexts directly is what lets the number go bare -- nothing may
// run into it from the left, which is what the comma in "6,500" does, and no
// unit may follow it. Mirrors guardrails._ROUTE; the two are meant to agree.
// The apostrophe is the FOOT MARK, 7,650', and must not also swallow the
// possessive -- "The 550's closed this morning" is the most direct closure
// claim there is. So a quote only excludes when it is not followed by an s.
const ROUTE_NUMBER = /(?<![\d,])\b(?:550|160|172|240|500|501)\b(?!\s*(?:cfs|ft|feet|af|%|,\d|"|'(?!s\b)))/i;
const ROAD_STATE = /(?:\b(?:is|are|remain|remains|sit|sits|stay|stays)|\w's)\s+(?:still\s+|both\s+|all\s+|already\s+|completely\s+)?(?:dry|wet|icy|slick|snow[- ]?packed|clear|closed|open|plowed|bare|greasy|sanded|passable|impassable|fine|good|clean)\b/i;
// A surface claim with no verb at all: "clear roads and dry pavement."
//
// The `to` lookbehind: "wet" is a verb at least as often as an adjective here,
// and "enough to wet pavement for the evening commute" forecasts what the rain
// will do rather than reporting what the road is. An infinitive is never a
// present-tense claim. 2026-09-22 failed on that sentence.
const ROAD_NOUN = /(?<!\bto )\b(?:clear|dry|wet|icy|bare|slick|snow[- ]?packed|open|closed)\s+(?:roads?|pavement|highways?|blacktop)\b/i;
// The telegraphic form, noun then adjective, copula dropped. system.md forbids
// "Roads wet, no ice." BY NAME and this file did not catch it -- guardrails
// grew the rule and the lint never did, so the two gates disagreed on a
// sentence the persona names as the canonical mistake. The trailing lookahead
// keeps it to that clipped register, so "Vallecito Road, fine gravel past the
// turn" is an ordinary noun phrase. Mirrors guardrails._ROAD_TELEGRAPHIC_CLAIM.
// A coordination ends the claim as surely as punctuation: "roads wet and icy
// on the 550" states "roads wet" whatever follows. That used to come free from
// clause splitting on a bare "and", which no longer happens.
const ROAD_TELEGRAPHIC = /\b(?:roads?|pavement|highways?|blacktop)\s+(?:dry|wet|icy|slick|snow[- ]?packed|clear|closed|open|plowed|bare|greasy|sanded|passable|impassable|fine|good|clean)\s*(?=[,.;:!?]|\s+(?:and|but)\b|$)/i;
// A CLOSURE is not hedgeable: it is the one road claim the hedges below do not
// apply to. The conditional opener still exempts it. A surface forecast is a weather
// claim, so hedging is what makes it honest; whether a gate is down is CDOT's
// decision, there is no feed for it, and "Wolf Creek will likely be closed"
// reads at 5:45am like "Wolf Creek is closed". Chain law and traction law are
// deliberately absent: system.md and constants.py both hold up "expect
// traction law by morning" as the product. Mirrors guardrails.CLOSURE_CLAIMS.
// NOT a bare "close": it is the ordinary adjective far more often than a verb
// here -- "the snow line ends up close to 11,000 feet on the passes" -- and
// because this rule is hedge-exempt a match is an unrecoverable fail on the
// product's signature sentence.
// The modal branch has NO optional "be": "will be close to 11,000 feet" is the
// adjective again, and `(?:be\s+)?` in front of a bare "close" re-admits exactly
// what dropping the bare alternative removed. "will be closed" needs no help --
// the copula branch already has `be` and `closed`. "close out"/"closing out" is
// weather, not a road. The `to close` branch keeps the infinitive that dropping
// the bare alternative had also dropped ("is set to close", "going to close").
const CLOSURE = /(?:\b(?:is|are|'s|re|was|were|be|been|being|gets?|got|stays?|stayed|remains?|remained)\s+(?:still\s+|already\s+|back\s+|all\s+)?(?:closed|open|shut)\b|\b(?:will|would|may|might|could|should|gonna)\s+(?:close|shut|reopen)\b|\bto\s+(?:close\b(?!\s+(?:out|to)\b)|shut|reopen)\b|\bclos(?:es|ing|ed)\b(?!\s+out\b)|\breopen(?:s|ed|ing)?\b|\bshuts?\b)/i;
// Hedges, in two tiers, because they are not all the same thing.
//
// A MODAL turns the clause into a forecast outright. system.md gives "I'd
// expect dry pavement by the 6:30 call" as the CORRECT repair, so `'d` and
// "plan for" have to count; without them this file failed the very phrasing
// the persona prescribes. 2026-09-23 failed on "I'd plan for wet roads and
// maybe some ponding by the afternoon commute." Per the header: where this
// file and the persona disagree, this file is wrong.
const MODAL_HEDGE = /\b(should|shouldn't|will|won't|\w+'ll|\w+'d|would|expect|expected|likely|probably|could|may|might|if|watch for|look for|plan (?:on|for)|forecast)\b/i;
// A time window used to hedge as well, and it says WHEN, never WHETHER: "The
// passes are dry through the morning" asserts they are dry right now. Exempting
// clauses with a present indicative did not save it, because the verbless forms
// this rule exists to catch never have one -- "Dry roads all day" passed while
// "Roads are wet tonight" failed. A time window now hedges nothing.
//
// A clause with no finite verb is not a claim of its own: it is the back half
// of a coordination, and it inherits the hedge governing the front. clauses()
// breaks on a bare "and", which also splits coordinated noun phrases and
// strips the modal off -- "I'd expect wet pavement in town and icy roads on
// the 550" left "icy roads on the 550" to be judged alone.
// A modal, and nothing else. Three review rounds went into trying to carry a
// hedge across a coordination, and every version was wrong: deciding whether a
// fragment is a second predicate or a second object needs to tell a noun from a
// verb, and "run", "look", "stay" and "pick" are all both. clauses() no longer
// splits on a bare "and", so the coordination stays with its modal.
const hedged = c => MODAL_HEDGE.test(c);
// A sentence that opens conditionally hedges every clause in it, including the
// ones after "and": "If that band sets up, the 550 is icy by 6am and Molas is slick."
const CONDITIONAL_OPEN = /^(?:if|when|once|unless|should)\b/i;
// Unless the conditional is about the READER rather than the weather. "If that
// band sets up" makes what follows contingent; "If you are heading north"
// picks out an audience and then states a flat fact at them, so "If you are
// heading north, Red Mountain is closed" is a closure claim in conditional
// dress. "we" is deliberately absent: "If we do see rain it'd be brief" is
// forecast-contingent. Mirrors guardrails._READER_ADDRESSED.
const READER_ADDRESSED = /^(?:if|when|once|unless|should)\s+(?:you|your|you're|youre|ya|anyone|anybody|someone|somebody|folks|people|drivers?|kids|the kids)\b/i;
const conditional = s => CONDITIONAL_OPEN.test(s) && !READER_ADDRESSED.test(s);
// "if" is also a modal hedge, for the trailing form ("the 550 is icy if that
// band sets up"), and at the head of a reader-addressed sentence it would
// hedge the clause all over again: "If you're running the 550 this morning,
// the pass is icy" is one clause and contains an "if". Drop the opener and
// judge what is left, which is the claim actually being made.
const LEADING_CONDITIONAL = /^(?:if|when|once|unless|should)\s+/i;
const claimBody = s => READER_ADDRESSED.test(s) ? s.replace(LEADING_CONDITIONAL, '') : s;

// Percent must carry a unit: "64% of median", "23% of full pool".
const PCT = /(\d{1,3})\s*%/g;
const PCT_OK_AFTER = /^\s*(of|below|above)\b/i;

// "Exactly one concrete detail from your own morning: the gauge, the snow stake,
// the drive, the dog, the woodpile, the truck, the yard, what the sky looked like
// out the kitchen window." (system.md). The persona is written in the first
// person throughout ("First person, constant"), so a pronoun is NOT a personal
// detail and cannot be used to count them. These anchors are the persona's own
// list. "the drive" is left out on purpose: "the morning drive looks
// straightforward" is forecast copy in nearly every post.
const PERSONAL = /\b(?:(?:rain |my |our |the )gauge|snow stake|(?:the |my )stake|woodpile|(?:the |my )truck|(?:the |my |our )dog|(?:the |my |our )yard|kitchen window|out the window|(?:at|from) the house|(?:the |my )porch|(?:the |my )deck)\b/i;
// "the gauge" is also a stream gauge. Those sentences carry a flow unit.
const STREAM_GAUGE = /\b(?:cfs|usgs|stream|river gauge|gage)\b/i;

const UNKNOWABLE = [
  /\bas we saw\b/i, /\blast night'?s\b/i, /\breports? of\b/i, /\beveryone'?s been\b/i,
  /\bthe last (?:few|couple) (?:days|weeks|months)\b/i, /\bhas been the\b/i,
  /\bdriest since\b/i, /\bwettest since\b/i, /\brecord\b/i, /\btrend(?:ing)?\b/i,
  /\bpeople are saying\b/i, /\bword is\b/i, /\bI heard\b/i,
  /\blast week\b/i, /\blately\b/i, /\ball month\b/i, /\bin years\b/i
];

// --- parsing ----------------------------------------------------------------

function parseDraft(raw) {
  raw = raw.replace(/\r\n/g, '\n');
  const meta = {};
  // site/weather/_pending: front matter, each value JSON (see scripts/wx/site.py write_post).
  if (raw.startsWith('---\n')) {
    const end = raw.indexOf('\n---', 3);
    if (end !== -1) {
      for (const line of raw.slice(4, end).split('\n')) {
        const i = line.indexOf(':');
        if (i < 0) continue;
        const k = line.slice(0, i).trim(), v = line.slice(i + 1).trim();
        try { meta[k] = JSON.parse(v); } catch { meta[k] = v; }
      }
      return { meta, body: raw.slice(raw.indexOf('\n', end + 1) + 1).trim() };
    }
  }
  // state/drafts: "# Monday, 2026-09-14, school_call" / "Verdict: ... | Snow line: 13700 | ..." / ---
  if (raw.startsWith('# ')) {
    const sep = raw.indexOf('\n---\n');
    if (sep !== -1) {
      const head = raw.slice(0, sep);
      const h = head.match(/^# [A-Za-z]+, (\d{4}-\d{2}-\d{2}), (\w+)/);
      if (h) { meta.forDate = h[1]; meta.postType = h[2]; }
      const sl = head.match(/Snow line: (\d+)/);
      if (sl) meta.snowLineFt = Number(sl[1]);
      return { meta, body: raw.slice(sep + 5).trim() };
    }
  }
  return { meta, body: raw.trim() };
}

// A newline ends a sentence as surely as a period does. Collapsing every run
// of whitespace merged an unpunctuated line into the next one, so a single
// conditional opener exempted both. Lines are split first, then sentences.
const sentences = t => t.split('\n')
  .flatMap(l => l.replace(/[^\S\n]+/g, ' ').trim().split(/(?<=[.!?])\s+/))
  .filter(Boolean);
const lines = t => t.split('\n').map(s => s.trim()).filter(Boolean);
const norm = s => s.toLowerCase().replace(/[^a-z0-9 ]/g, '').split(/\s+/).filter(Boolean);
// NOT a bare "and" or "but": those coordinate objects as often as clauses, and
// splitting there strips the governing modal off the second half. The cost is
// that an uncommaed "Coal Bank should stay dry and Molas is clear right now"
// is one hedged clause and is missed; with the comma the persona usually
// writes it still splits and is caught. Deliberate -- a false fail on the
// phrasing system.md prescribes is the more expensive error.
const clauses = s => s.split(/,\s*(?:and|but)\s+|;\s*/i).filter(Boolean);
const q = s => `"${s.trim()}"`;

function jaccard(a, b) {
  const A = new Set(norm(a)), B = new Set(norm(b));
  if (!A.size || !B.size) return 0;
  let hit = 0; for (const w of A) if (B.has(w)) hit++;
  return hit / (A.size + B.size - hit);
}

const openingOf = body => (lines(body)[0] ?? '').replace(STAMP, '');
const closingOf = body => { const L = lines(body); return L.length > 1 ? L[L.length - 1] : ''; };

// --- rules ------------------------------------------------------------------

function lint(raw, dateStr, historyDir) {
  const { meta, body: text } = parseDraft(raw);
  const fails = [], warns = [], S = sentences(text);

  // 1. Em dashes and ASCII stand-ins.
  for (const s of S) {
    if (/[\u2014\u2013]/.test(s)) fails.push(['em-dash', `Contains an em/en dash: ${q(s)}`]);
    else if (/\s--\s|\w--\w|\s--\w|\w--\s/.test(s)) fails.push(['em-dash', `Contains "--": ${q(s)}`]);
  }

  // 2. Road and pass conditions. Judged per clause, so a "should" in one half
  // of a sentence cannot launder "the 501 is fine" in the other. A closure is
  // checked first and the hedges do not apply to it -- see CLOSURE. A
  // weather-contingent conditional opener still exempts the whole sentence; a
  // reader-addressed one exempts nothing.
  for (const s of S) {
    if (conditional(s)) continue;
    for (const c of clauses(claimBody(s))) {
      const hasRoad = PASS_NOUN.test(c) || ROUTE_NUMBER.test(c) ||
        ROADS.some(r => new RegExp(`\\b${r.replace(/[-]/g, '\\-')}\\b`, 'i').test(c));
      if (hasRoad && CLOSURE.test(c)) {
        fails.push(['road-status', `Road closure claim with no CDOT data: ${q(s)}`]);
        break;
      }
      if (hedged(c)) continue;
      if ((hasRoad && ROAD_STATE.test(c)) || ROAD_NOUN.test(c) ||
          ROAD_TELEGRAPHIC.test(c)) {
        fails.push(['road-status', `Present-tense road condition with no CDOT data: ${q(s)}`]);
        break;
      }
    }
  }

  // 3. Exactly one personal detail, counted per sentence.
  const personal = S.filter(s => PERSONAL.test(s) &&
    !(/gauge/i.test(s.match(PERSONAL)[0]) && STREAM_GAUGE.test(s)));
  if (personal.length === 0) fails.push(['personal-count', 'Zero personal details. Reads as a bot.']);
  else if (personal.length > 1)
    fails.push(['personal-count',
      `${personal.length} personal details (need exactly 1):\n` +
      personal.map(s => `    - ${q(s)}`).join('\n')]);

  // 4. Bare percentages.
  let m; PCT.lastIndex = 0;
  while ((m = PCT.exec(text)) !== null) {
    const tail = text.slice(m.index + m[0].length, m.index + m[0].length + 40);
    if (!PCT_OK_AFTER.test(tail)) {
      const ctx = text.slice(Math.max(0, m.index - 45), m.index + 45).replace(/\s+/g, ' ');
      fails.push(['bare-percent', `Bare percentage "${m[0]}" with no unit: "...${ctx}..."`]);
    }
  }

  // 5. Weekday must match the date. Only a weekday the post claims IS today
  // counts; "another round Tuesday evening" in a Monday post is a forecast.
  const [y, mo, d] = dateStr.split('-').map(Number);
  const expected = WEEKDAYS[new Date(Date.UTC(y, mo - 1, d)).getUTCDay()];
  const todayClaim = new RegExp(`\\b(?:it'?s|it is|today is|today'?s|happy)\\s+(${WEEKDAYS.join('|')})\\b`, 'gi');
  for (const w of text.matchAll(todayClaim)) {
    const said = WEEKDAYS.find(x => x.toLowerCase() === w[1].toLowerCase());
    if (said !== expected)
      fails.push(['weekday', `Post says ${q(w[0])}; ${dateStr} is a ${expected}.`]);
  }

  // 6. Date stamp. The numeric stamp opens every post; a spelled-out date is
  // only checked in the opening line, since later ones are forecast dates.
  const stamp = text.match(STAMP);
  if (stamp && (Number(stamp[1]) !== mo || Number(stamp[2]) !== d || Number(stamp[3]) !== y % 100))
    fails.push(['date-stamp', `Post is stamped ${stamp[0].trim()}; the draft is for ${dateStr}.`]);
  const md = openingOf(text).match(new RegExp(`\\b(${MONTHS.join('|')})\\s+(\\d{1,2})\\b`, 'i'));
  if (md) {
    const mIdx = MONTHS.findIndex(x => x.toLowerCase() === md[1].toLowerCase()) + 1;
    if (mIdx !== mo || Number(md[2]) !== d)
      fails.push(['date-stamp', `Post is stamped ${md[0]}; the draft is for ${dateStr}.`]);
  }

  // 7. Snow line plausibility. Outside 5,000-14,000 ft fails unless the brief
  // itself put it there: late-summer freezing levels really do sit above
  // 14,000 ft (the 2026-09-12 brief said 14,400), and the draft's front matter
  // carries the brief's number, so a quote of it is grounded, not a typo.
  const briefFt = Number.isFinite(meta.snowLineFt) ? meta.snowLineFt : null;
  for (const sm of text.matchAll(/snow[- ]?(?:line|level)\b[^.]{0,60}?(\d{1,2},\d{3}|\d{4,5})\s*(?:ft\b|feet\b|')/gi)) {
    const ft = Number(sm[1].replace(',', ''));
    if (ft >= 5000 && ft <= 14000) continue;
    if (briefFt !== null && Math.abs(ft - briefFt) <= 1000) continue;
    fails.push(['snow-line', `Snow line of ${ft.toLocaleString('en-US')} ft is outside 5,000-14,000 ft` +
      (briefFt !== null ? ` and the brief said ${briefFt.toLocaleString('en-US')} ft` : '') + `: ${q(sm[0])}`]);
  }

  // 8. Claims the post cannot know. WARN, human judgment.
  for (const s of S)
    for (const p of UNKNOWABLE)
      if (p.test(s)) { warns.push(['unknowable', `Possible unknowable claim: ${q(s)}`]); break; }

  // 9. Repeated opening or closing line vs. the last week of the same slot.
  const slot = meta.postType || 'school_call';
  const open = openingOf(text), close = closingOf(text);
  if (historyDir && existsSync(historyDir)) {
    const prior = readdirSync(historyDir)
      .filter(f => /^\d{4}-\d{2}-\d{2}-/.test(f) && f.endsWith(`-${slot}.md`) && f.slice(0, 10) < dateStr)
      .sort().reverse().slice(0, 7);
    for (const f of prior) {
      const pb = parseDraft(readFileSync(join(historyDir, f), 'utf8')).body;
      if (open && jaccard(open, openingOf(pb)) >= 0.6)
        fails.push(['repeat-open', `Opening line repeats ${f}: ${q(open)}`]);
      if (close && jaccard(close, closingOf(pb)) >= 0.6)
        fails.push(['repeat-close', `Closing line repeats ${f}: ${q(close)}`]);
    }
  }

  return { fails, warns, stats: { sentences: S.length, personal: personal.length, words: norm(text).length } };
}

function render(date, res) {
  const pass = res.fails.length === 0;
  const out = [`### Draft lint — ${date} — ${pass ? '✅ PASS' : '❌ ' + res.fails.length + ' FAIL'}`];
  if (res.fails.length) out.push('\n**Must fix**\n' + res.fails.map(([k, v]) => `- \`${k}\` ${v}`).join('\n'));
  if (res.warns.length) out.push('\n**Eyeball these**\n' + res.warns.map(([k, v]) => `- \`${k}\` ${v}`).join('\n'));
  out.push(`\n_${res.stats.words} words, ${res.stats.sentences} sentences, ${res.stats.personal} personal._`);
  return out.join('\n');
}

// --- CLI --------------------------------------------------------------------
const args = process.argv.slice(2);
const file = args.find(a => !a.startsWith('--'));
const date = (args.find(a => a.startsWith('--date=')) || '').split('=')[1];
const hist = (args.find(a => a.startsWith('--history=')) || '--history=state/drafts').split('=')[1];
const asJson = args.includes('--json');
if (!file || !/^\d{4}-\d{2}-\d{2}$/.test(date || '') || !existsSync(file)) {
  console.error('usage: draft-lint.mjs <draftfile> --date=YYYY-MM-DD [--history=dir] [--json]');
  process.exit(2);
}
const res = lint(readFileSync(file, 'utf8'), date, hist);
const pass = res.fails.length === 0;
console.log(asJson ? JSON.stringify({ date, pass, ...res }, null, 2) : render(date, res));
process.exit(pass ? 0 : 1);
