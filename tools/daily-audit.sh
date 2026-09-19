#!/usr/bin/env bash
# tools/daily-audit.sh -- the deterministic daily review of the school call.
#
# Run by .github/workflows/daily-audit.yml after the posting window closes.
# Replaces a scheduled model run that read this repo over the network and died
# every morning on an approval prompt nobody was awake to answer. Everything
# here is a file read, a git read, the linter, and gh with GITHUB_TOKEN.
#
#   AUDIT_DATE=YYYY-MM-DD   audit that date instead of today (America/Denver)
#   AUDIT_DRY_RUN=1         print the report, write nothing to GitHub
#   AUDIT_ASSIGNEE=login    who gets the notification (default GoVallecito)
#
# Idempotent: every report carries a hidden marker for its date, and a second
# run that finds one exits quietly. There are two cron entries on purpose.
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-GoVallecito/govallecito-bot}"
ASSIGNEE="${AUDIT_ASSIGNEE:-GoVallecito}"
DRY="${AUDIT_DRY_RUN:-}"
SLOT=school_call
WINDOW_CLOSE=9            # scripts/wx/constants.py: SCHOOL_CALL_WINDOW = (5, 9)
PENDING=site/weather/_pending
SITE=site/weather
HIST=state/drafts
FEED="$SITE/feed.json"

NOW_DATE=$(TZ=America/Denver date +%F)
DATE="${AUDIT_DATE:-$NOW_DATE}"
[[ $DATE =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "AUDIT_DATE must be YYYY-MM-DD, got '$DATE'"; exit 2; }
MARK="<!-- daily-audit:$DATE -->"
tmp=$(mktemp -d)

# The MST cron lands at 08:15 local, inside the window. Let the 09:15 one report.
if [ "$DATE" = "$NOW_DATE" ] && [ "$(TZ=America/Denver date +%-H)" -lt "$WINDOW_CLOSE" ]; then
  echo "The $SLOT window for $DATE is still open (closes ${WINDOW_CLOSE}:00 America/Denver). Nothing to audit yet."
  exit 0
fi

# --- GitHub helpers ----------------------------------------------------------
comments_have_mark() { gh api "repos/$REPO/issues/$1/comments" --paginate --jq '.[].body' | grep -qF "$MARK"; }

ensure_label() { [ -n "$DRY" ] || gh label create "$1" --color "$2" --description "$3" --force >/dev/null || true; }

assign() {
  [ -n "$DRY" ] && { echo "[dry run] would assign #$1 to $ASSIGNEE"; return; }
  gh issue edit "$1" --add-assignee "$ASSIGNEE" >/dev/null || echo "::warning::could not assign #$1 to $ASSIGNEE"
}

comment() {   # issue, body file
  if [ -n "$DRY" ]; then echo "[dry run] would comment the report above on #$1"; return; fi
  gh issue comment "$1" --body-file "$2"
}

open_issue() {   # title, body file, label -> prints number
  if [ -n "$DRY" ]; then echo "[dry run] would open issue with the report above: $1" >&2; echo 0; return; fi
  gh issue create --title "$1" --body-file "$2" --label "$3" | sed 's#.*/##'
}

gh issue list -R "$REPO" --state all --limit 200 --json number,title,body > "$tmp/issues.json"

# --- the parts every report shares -----------------------------------------
if [ -f "$FEED" ]; then
  feed_n=$(jq '(.posts // []) | length' "$FEED")
  feed_line="\`$FEED\` exists with **$feed_n** entries."
else
  feed_n=0
  feed_line="\`$FEED\` does not exist yet. Nothing has been published to the site."
fi

# The last five archived school calls up to and including this date.
last5=()
for f in $(ls "$HIST"/*-"$SLOT".md 2>/dev/null | sort); do
  [[ "$(basename "$f" | cut -c1-10)" > "$DATE" ]] || last5+=("$f")
done
# ${arr[@]: -5} expands to nothing when there are fewer than five.
(( ${#last5[@]} <= 5 )) || last5=("${last5[@]:${#last5[@]}-5}")
clean5=0
for f in "${last5[@]}"; do
  node tools/draft-lint.mjs "$f" --date="$(basename "$f" | cut -c1-10)" --history="$HIST" >/dev/null && clean5=$((clean5 + 1))
done
last5_line="**Last ${#last5[@]} archived drafts:** $clean5 of ${#last5[@]} lint clean."
ready=""
if [ "$feed_n" -ge 5 ] && [ "${#last5[@]}" -eq 5 ] && [ "$clean5" -eq 5 ]; then
  ready="Review period looks ready to end — setting WX_FIRST_30_DAYS to false would make this self-running."
fi

# --- find the day's draft ---------------------------------------------------
find_post() {   # dir -> the first <date>-*.md in it whose postType is the slot
  local f
  for f in "$1/$DATE"-*.md; do
    [ -f "$f" ] && grep -q "^postType: \"$SLOT\"" "$f" && { echo "$f"; return; }
  done
  return 0
}
draft=$(find_post "$PENDING"); where="staged, not yet published"; staged=1
if [ -z "$draft" ]; then draft=$(find_post "$SITE"); where="already published to the site"; staged=0; fi
if [ -z "$draft" ] && [ -f "$HIST/$DATE-$SLOT.md" ]; then
  draft="$HIST/$DATE-$SLOT.md"; where="archived, but never staged for the site"; staged=0
fi

# =============================================================================
# A draft exists: lint it and report on its review issue.
# =============================================================================
if [ -n "$draft" ]; then
  review=$(jq -r --arg d "$DATE" --arg s "$SLOT" \
    '[.[] | select(.title | test("^\\[(review|block)\\] " + $s + " draft for " + $d))] | max_by(.number) | .number // empty' \
    "$tmp/issues.json")

  if [ -n "$review" ] && comments_have_mark "$review"; then
    echo "Already reported $DATE on #$review. Nothing to do."; exit 0
  fi
  if [ -z "$review" ] && jq -e --arg m "$MARK" 'any(.[]; (.body // "") | contains($m))' "$tmp/issues.json" >/dev/null; then
    echo "Already reported $DATE. Nothing to do."; exit 0
  fi

  set +e
  lint_md=$(node tools/draft-lint.mjs "$draft" --date="$DATE" --history="$HIST")
  lint_code=$?
  set -e
  [ "$lint_code" -le 1 ] || { echo "draft-lint could not run on $draft (exit $lint_code)"; exit 1; }

  {
    echo "$MARK"
    echo "## Daily audit, $DATE"
    echo
    echo "**Draft:** \`$draft\` ($where)"
    echo
    echo "$lint_md"
    echo
    echo "**Site feed:** $feed_line"
    echo
    echo "$last5_line"
    [ -z "$ready" ] || { echo; echo "$ready"; }
    if [ "$lint_code" -eq 0 ] && [ "$staged" -eq 1 ]; then
      echo
      echo "Actions tab → \"Publish approved forecast\" → Run workflow → enter $DATE"
    fi
  } > "$tmp/report.md"
  cat "$tmp/report.md"

  if [ "$lint_code" -eq 0 ]; then label=lint-clean; else label=lint-failed; fi
  ensure_label lint-clean  0e8a16 "draft-lint found nothing to fix"
  ensure_label lint-failed d93f0b "draft-lint found something to fix"

  if [ -z "$review" ]; then
    ensure_label wx-audit ededed "daily audit report"
    review=$(open_issue "[audit] $SLOT draft for $DATE" "$tmp/report.md" wx-audit)
  else
    comment "$review" "$tmp/report.md"
  fi
  [ -n "$DRY" ] || gh issue edit "$review" --add-label "$label" >/dev/null || true
  assign "$review"
  exit 0
fi

# =============================================================================
# No draft: work out why, from every forecast run committed today.
# =============================================================================
# state/last-run-forecast.log is overwritten on every run and the hourly
# heartbeat lands after the window, so the working-tree copy nearly always says
# "outside every posting window". Each run commits its log, so read them all.
runs=0; outside=0; crashed=0; composed=0
while read -r sha; do
  [ -n "$sha" ] || continue
  body=$(git show "$sha:state/last-run-forecast.log" 2>/dev/null || true)
  runs=$((runs + 1))
  # "not a posting hour" is the same exit from before the posting windows (2026-09-08).
  grep -qE "outside every posting window|is not a posting hour" <<<"$body" && outside=$((outside + 1))
  grep -q "^Traceback" <<<"$body" && crashed=$((crashed + 1))
  grep -q "^=== Vallecito forecast: " <<<"$body" && composed=$((composed + 1))
done < <(TZ=America/Denver git log --since="$DATE 00:00" --until="$DATE 23:59:59" --format=%H -- state/last-run-forecast.log)

aborted=""; other=""
while read -r sha; do
  [ -n "$sha" ] || continue
  st=$(git show "$sha:state/forecast-status.md" 2>/dev/null || true)
  grep -q "^When: $DATE" <<<"$st" || continue
  state=$(head -1 <<<"$st" | sed 's/^# Forecast run — //')
  if grep -qi "aborted" <<<"$state"; then
    missing=$(sed -n 's/^- Missing sources: //p' <<<"$st" | head -1)
    if [ -z "$missing" ] || [ "$missing" = "none" ]; then
      missing=$(awk '/^## Detail/{f=1; next} f==1 && /^```/{f=2; next} f==2 && /^```/{exit} f==2' <<<"$st" | paste -sd ';' -)
    fi
    [ -n "$aborted" ] || aborted="$missing"
  else
    [ -n "$other" ] || other="$state"
  fi
done < <(TZ=America/Denver git log --since="$DATE 00:00" --until="$DATE 23:59:59" --format=%H -- state/forecast-status.md)

if [ -n "$aborted" ]; then
  cause="aborted, data unavailable"; detail="Missing: $aborted"
elif [ -n "$other" ] || [ "$crashed" -gt 0 ] || [ "$composed" -gt 0 ]; then
  cause="unknown"
  detail="A run got past the clock check and still left no draft."
  [ -z "$other" ] || detail="$detail Last status: \`$other\`."
  [ "$crashed" -eq 0 ] || detail="$detail $crashed run(s) crashed with a Python traceback."
elif [ "$outside" -gt 0 ]; then
  cause="outside every posting window"
  detail="No scheduled run landed inside the 5:00-${WINDOW_CLOSE}:00 local window. GitHub dropped or deferred them; not a code fault."
else
  cause="unknown"; detail="No forecast run committed a log on $DATE at all. Check that the Vallecito Forecast workflow is still enabled."
fi

{
  echo "$MARK"
  echo "## Daily audit, $DATE: no $SLOT draft"
  echo
  echo "**Cause:** $cause"
  echo
  echo "$detail"
  echo
  echo "**Evidence:** $runs forecast run(s) committed a log on $DATE; $outside were outside every posting window, $composed started composing, $crashed crashed."
  echo
  echo "**Site feed:** $feed_line"
  echo
  echo "$last5_line"
  [ -z "$ready" ] || { echo; echo "$ready"; }
  echo
  echo "Where to look: \`state/last-run-forecast.log\`, \`state/forecast-status.md\`, \`state/selftest-latest.md\`."
} > "$tmp/report.md"
cat "$tmp/report.md"

# The forecaster opens its own miss issue once the window closes. Report on it
# rather than beside it.
miss=$(jq -r --arg d "$DATE" --arg s "$SLOT" \
  '[.[] | select(.title | test("^\\[miss\\] .*" + $d))] | max_by(.number) | .number // empty' "$tmp/issues.json")
if [ -n "$miss" ]; then
  if comments_have_mark "$miss" || jq -e --arg m "$MARK" --argjson n "$miss" \
       'any(.[]; .number == $n and ((.body // "") | contains($m)))' "$tmp/issues.json" >/dev/null; then
    echo "Already reported $DATE on #$miss. Nothing to do."; exit 0
  fi
  comment "$miss" "$tmp/report.md"
else
  ensure_label wx-miss ededed "a scheduled post did not go out"
  miss=$(open_issue "[miss] $DATE: ${cause:0:200}" "$tmp/report.md" wx-miss)
fi
assign "$miss"
