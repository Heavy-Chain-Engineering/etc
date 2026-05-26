#!/bin/bash
# hooks/pre-compact-checkpoint.sh
#
# PreCompact hook — auto-checkpoints session state before every /compact
# (manual or auto). etc's first PreCompact hook.
#
# F-2026-05-26-compact-autocheckpoint (#36).
#
# Thin wrapper: passes the original hook JSON through to
# scripts/precompact_checkpoint.py, which does ALL JSON parsing and the
# actual write/append. The wrapper resolves the script (repo-local first,
# then global ~/.claude install) and ALWAYS exits 0 — even if the python
# script is missing or errors (fail-open; never block compaction).
#
# No jq dependency (Windows-portability lesson: auto-checkpoint.sh's hard
# jq dependency broke fresh Windows installs). CWD for script resolution
# is read via a small inline python fallback.
#
# Exit code: always 0.

INPUT=$(cat)

# Derive cwd from the hook JSON without jq (pure python fallback).
CWD=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("cwd","."))' 2>/dev/null || echo ".")

# Locate the checkpoint writer: prefer repo-local, then global install.
SCRIPT=""
if [[ -f "${CWD}/scripts/precompact_checkpoint.py" ]]; then
  SCRIPT="${CWD}/scripts/precompact_checkpoint.py"
elif [[ -f "${HOME}/.claude/scripts/precompact_checkpoint.py" ]]; then
  SCRIPT="${HOME}/.claude/scripts/precompact_checkpoint.py"
fi

# Fail-open: if the script can't be resolved, do nothing and let
# compaction proceed.
if [[ -z "$SCRIPT" ]]; then
  exit 0
fi

# Replay the original stdin to the python writer. Tolerate any failure.
printf '%s' "$INPUT" | python3 "$SCRIPT" || true

exit 0
