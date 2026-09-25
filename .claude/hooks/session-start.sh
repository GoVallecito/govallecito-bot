#!/bin/bash
# SessionStart hook: make `python -m pytest tests/ -q` and `npm test` work in a
# fresh Claude Code on the web container, with no manual setup step.
#
# WHY THIS EXISTS: requirements.txt is the PRODUCTION dependency list, so it
# deliberately does not carry pytest -- the workflows install it on every run and
# do not need a test runner. A web session starts from that same list and so
# cannot run the suite until pytest is installed by hand. This closes that gap
# without adding a test-only package to what the bots install 56 times a day.
#
# Node needs nothing installed: package.json declares zero dependencies and
# `npm test` is `node --test tools/draft-lint.test.mjs` on the built-in runner.
#
# Nothing here calls the Anthropic API, runs the live composer, or triggers a
# workflow. See CLAUDE.md, "Cost rule: $0 extra spend" -- a session-start hook
# that spent money would be the worst possible place to hide it.
set -euo pipefail

# Local machines already have their own environment; only the web containers
# start empty. This check stays ABOVE the async handshake so a local run prints
# nothing at all.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# ASYNC. The session starts immediately and the install runs behind it, which
# costs a real race: a first turn can reach `python -m pytest` before pytest
# lands, and the failure is the ordinary "No module named pytest". The repair is
# the pip line in CLAUDE.md, or simply waiting a few seconds and re-running.
#
# This JSON must be the FIRST thing on stdout and must come before the slow work,
# or the handshake is not read and the hook blocks the session anyway. Everything
# below it is background output.
echo '{"async": true, "asyncTimeout": 300000}'

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$(dirname "$(dirname "$(readlink -f "$0")")")")}"

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "session-start: no python on PATH; skipping dependency install." >&2
  exit 0
fi

# The container runs as root, and pip's "do not run as root" warning is noise
# here rather than advice. Dropped silently on a pip too old to know the flag.
ROOT_OK=()
if "$PY" -m pip install --help 2>/dev/null | grep -q -- --root-user-action; then
  ROOT_OK=(--root-user-action=ignore)
fi

# Idempotent: both are no-ops once satisfied, which matters because this runs
# again on resume and on clear.
PIP=(--quiet --disable-pip-version-check "${ROOT_OK[@]}")
"$PY" -m pip install "${PIP[@]}" -r requirements.txt
"$PY" -m pip install "${PIP[@]}" pytest

# The draft linter and its self-test need Node 20+ (the forecast workflow pins
# 22). Report rather than fail: the Python suite is still usable without it.
if command -v node >/dev/null 2>&1; then
  node_major="$(node --version | sed 's/^v\([0-9]*\).*/\1/')"
  if [ "${node_major:-0}" -lt 20 ]; then
    echo "session-start: node $(node --version) is below 20; \`npm test\` and" \
         "tools/draft-lint.mjs may not run." >&2
  fi
else
  echo "session-start: no node on PATH; \`npm test\` will not run." >&2
fi

echo "session-start: ready. python -m pytest tests/ -q | npm test"
