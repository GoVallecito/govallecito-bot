# Panel unblock: why nothing posted for eight days, and what changed

Repo-safe.

Branch: `panel-unblock`. Behavior fix to the review panel and the run
bookkeeping. The composer's voice, the persona rulebook, the data sources and
the Facebook path are untouched.

## What happened

From **2026-09-19 to 2026-09-26** the forecaster composed a draft every
morning and the review panel held all eight. Nothing reached the website in
that time; the last published post is **2026-09-18**. Every run exited zero,
so the logs looked ordinary and nothing counted the gap.

Four defects, and they compounded in that order.

## The four fixes

### 1. The repetition check was reading held drafts, not published posts

`bundle._recent_post_shapes()` globbed `state/drafts/`, which archives **every**
draft whether it published or not. Its docstring claimed that stayed "true to
what actually went out"; that stopped being true on 09-19, the first day a
draft was held.

Those shapes go to the editor as "RECENT OPENERS AND CLOSERS", and the editor
is told the opener, the pivot and the closing question must not reuse the
construction of any recent post. So from 09-19 on, every draft was judged
against posts **no reader had ever seen**, and each hold added another phantom
to the avoid list. A hold made the next hold more likely. On 09-26 the editor
rejected the closer for echoing 2026-09-20, a draft still sitting unpublished
in `_pending/`.

It now reads published posts from the site directory, stripping front matter
before taking the first and last line. `_pending/` is a subdirectory of the
site dir, so held drafts are excluded by construction. Signature, return shape
(`date`/`opened`/`closed`), timestamp-stripping and the `n=6` default are
unchanged. `run_forecast._recent_published_bodies()` was already correct and is
untouched.

### 2. The final round threw away the fixes it was holding

The magistrate's last-round prompt said *"THIS IS THE FINAL ROUND. If it is not
publishable as written, REJECT rather than REVISE."* It obeyed literally. On
09-26 it wrote: *"While all four issues are fixable with simple edits, the
rules for this round require rejection."* Every one of those four arrived with
an exact replacement string from the editor.

The final round now spends that work. After the ruling, any issue carrying a
concrete replacement is applied to the draft by **literal string substitution**
(no extra model call, so nothing new can be invented), the deterministic rule
gate re-runs on the patched text, and the post publishes only if that gate
returns **PASS** and no fact-checker objection survived the patch. A suggestion
whose quoted sentence is no longer present is skipped, not guessed at.

Reject stays reachable: a draft whose remaining issues carry no replacement, or
that still fails the gate, is held exactly as before. An unsupported number
with no suggested fix still holds the post.

The transcript records this under **"Final-round edits applied to the writer's
text"**, which states plainly that the published text is not byte-identical to
what the writer composed, and lists every substitution, every skip, and the
gate result on the patched text.

### 3. The editor was overruling the rule gate on road language

On 09-26 the editor flagged two sentences `[critical]`:

> Coal Bank, Molas and Red Mountain should stay dry through the weekend.
> Wolf Creek could see wet pavement Sunday evening.

Both are conditional. Both are exactly what `guardrails.py` asks for, and the
gate passed them: the transcript's rule-gate section reads "nothing flagged".
Those two false positives are what the magistrate leaned on to reject.

`EDITOR_SYSTEM` no longer lists road tense as something the editor checks. It
now says the automated gate decides road and pass tense, that the editor must
not raise a road-tense issue at any severity, and that anything hedged with
should / would / could / might / I'd expect / looks like is correct by
construction. Its other checks are unchanged.

`edit_review()` also receives the gate verdict now and is told not to
re-litigate a rule the gate passed.

### 4. A forced test run consumed the next day's slot

On 2026-09-24 at 22:02 a `FORCE_SLOT` smoke test composed a school call for
09-25 and recorded the slot in the ledger. Its draft was discarded in commit
`e6b2bbe`, but the ledger entry stayed, so every real morning run on 09-25
exited with *"school_call for 2026-09-25 already went out at
2026-09-24T22:02:12-06:00"*. **2026-09-25 has no post at all**, published or
staged: a test consumed the morning.

New env flag **`WX_DRY_LEDGER`**. When set, `run_forecast` skips the
`ledger.record` call entirely and says so. It **defaults on** whenever
`FORCE_SLOT` is set outside that slot's real window. An explicit value always
wins, so `WX_DRY_LEDGER=false` still lets a deliberate out-of-window run claim
the day. A forced run inside its real window behaves exactly as before.

The log line at the top of every forced run now names which it is:

```
FORCE_SLOT=school_call -- skipping the clock check. 2026-09-24 22:02 MDT is
OUTSIDE its real window; this run will NOT claim the slot (WX_DRY_LEDGER).
```

### 5. The silence

`HEALTHCHECK_URL_FORECAST` **is not set on this repo.** Checked with
`gh secret list`: only `ANTHROPIC_API_KEY` and `FB_PAGE_ACCESS_TOKEN` exist. It
was not created here, because that is not something this branch can or should
do. The consequence is that the heartbeat step has been skipping itself since
it was written, and an unmonitored repo has been indistinguishable from a
healthy one for the whole outage.

Two changes make the gap visible:

- `forecast.yml` gains a **"Heartbeat NOT configured"** step that emits a
  GitHub `::warning` naming the secret whenever it is absent. It shows on every
  run instead of being silently skipped.
- Every run writes **`heldDays`** into `state/forecast-status.md`: consecutive
  days that produced a draft but no published post. Above 2 it also writes a
  **STANDING FAILURE** block saying this is a pipeline problem, not a run of bad
  drafts. Against the current repo it reports **8**, which is the outage exactly.

## The new env flag, in one line

| Flag | Default | Effect |
|---|---|---|
| `WX_DRY_LEDGER` | unset; auto-on for an out-of-window `FORCE_SLOT` run | Skips `ledger.record`, so the run cannot consume a day's slot |

## Verification

- `python -m pytest tests/ -q` -> **329 passed** (313 before; 16 new)
- `npm test` -> **69/69**
- `python scripts/wx/selftest.py` -> 14/16, the two failures pre-existing and
  environmental: CAIC is out of season (documented, re-run mid-Nov), and CDOT
  needs `CDOT_API_KEY`, which is not set on this repo. Neither touches this work.
- No model call was made. Every check here runs offline against fixtures.

New tests: `tests/test_panel_final_round.py` (the 09-26 transcript replayed
verbatim, plus reject-still-reachable and superseded-quote cases) and four new
classes in `tests/test_scheduling.py` covering the published-shapes regression,
the dry ledger, and the held-day counter.

## What David should watch, the first three mornings

1. **Does a post actually land?** `site/weather/` should gain a file each
   morning. The fastest single check is `heldDays:` at the top of
   `state/forecast-status.md`. It should read **0** after the first successful
   morning. If it climbs past 2 again, the pipeline is stuck, not unlucky.

2. **Read the "Final-round edits applied to the writer's text" section** in
   `state/panel/<date>-school_call.md` on any day that approves in round 3.
   That section is the new machinery doing its job, and it is the one place
   where published words differ from what the writer composed. Check that the
   substituted sentences read like the forecaster. If a replacement ever
   introduces a number, that is worth flagging immediately: the editor is given
   the brief specifically to stop that, but this path applies its text
   literally.

3. **Check the editor stopped raising road tense.** In those same transcripts,
   the editor's report should no longer contain road or pass issues at any
   severity. The rule gate section is the authority and should keep reading
   "nothing flagged" for correctly hedged road sentences. If a road issue
   reappears from the editor, the prompt change did not take.

Also worth doing once, when convenient: **create the healthchecks.io check and
set `HEALTHCHECK_URL_FORECAST`**. Until then the workflow warns on every run,
which is better than silence but is not an alarm that reaches you.

## Not done here, on purpose

- `site/weather/_pending/2026-09-26-snow-line-near-11350-ft.md` is still
  staged. The brief said the 09-26 draft had been promoted by hand and was
  live; it has not been. `site/weather/` and `feed.json` both stop at 09-18.
  Promoting it is a publishing decision and was left alone.
- Six stale drafts (09-19 through 09-24) were deleted: they forecast days that
  have passed, so none could ever publish. The directory remains and
  `feed.json` is byte-identical (the feed never indexed `_pending`).
- `WX_FIRST_30_DAYS` untouched. Facebook stays dark. No workflow was run or
  dispatched.
