#!/usr/bin/env bash
# tools/lint-review-issue.sh -- put the draft-lint verdict at the top of the
# review issue this forecast run just opened, and label it.
#
# Called from .github/workflows/forecast.yml after the forecaster. Reads the
# run's own log for the two lines run_forecast.py prints when it holds a draft:
#   staged for review -> site/weather/_pending/<date>-<slug>.md
#   Review issue opened: https://github.com/<repo>/issues/<n>
# Neither line means no draft was held this run, which is most runs.
#
# This must never fail the forecast job. A bad draft is still shown, labelled
# bad; a lint or GitHub hiccup is a warning, not a red X on the forecaster.
set -uo pipefail

LOG="${1:-state/last-run-forecast.log}"
MARK="<!-- draft-lint -->"
warn() { echo "::warning::$*"; exit 0; }

[ -f "$LOG" ] || { echo "no $LOG; nothing to lint"; exit 0; }
issue_url=$(sed -n 's/^Review issue opened: //p' "$LOG" | tail -1)
draft=$(sed -n 's/^staged for review -> //p' "$LOG" | tail -1)
if [ -z "$issue_url" ] || [ -z "$draft" ] || [ ! -f "$draft" ]; then
  echo "no draft was held for review this run; nothing to lint"
  exit 0
fi
num="${issue_url##*/}"
date=$(sed -n 's/^forDate: "\([0-9-]*\)"$/\1/p' "$draft" | head -1)
[ -n "$date" ] || date=$(basename "$draft" | cut -c1-10)

lint_md=$(node tools/draft-lint.mjs "$draft" --date="$date" --history=state/drafts)
code=$?
case $code in
  0) label=lint-clean ;;
  1) label=lint-failed ;;
  *) warn "draft-lint could not run on $draft (exit $code)" ;;
esac
echo "$lint_md"

gh label create lint-clean  --color 0e8a16 --description "draft-lint found nothing to fix" --force >/dev/null \
  || warn "could not create label lint-clean"
gh label create lint-failed --color d93f0b --description "draft-lint found something to fix" --force >/dev/null \
  || warn "could not create label lint-failed"

tmp=$(mktemp -d)
gh issue view "$num" --json body -q .body > "$tmp/body.md" || warn "could not read issue #$num"
if grep -qF "$MARK" "$tmp/body.md"; then
  echo "issue #$num already carries a lint result; labelling only"
else
  { echo "$MARK"; echo "$lint_md"; echo; echo "---"; echo; cat "$tmp/body.md"; } > "$tmp/new.md"
  gh issue edit "$num" --body-file "$tmp/new.md" >/dev/null || warn "could not update issue #$num"
fi
gh issue edit "$num" --add-label "$label" >/dev/null || warn "could not label issue #$num"
echo "issue #$num: $label"
