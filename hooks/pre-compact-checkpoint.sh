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
# then the install-dir sibling) and ALWAYS exits 0 — even if the python
# script is missing or errors (fail-open; never block compaction).
#
# No jq dependency (Windows-portability lesson: auto-checkpoint.sh's hard
# jq dependency broke fresh Windows installs). CWD for script resolution
# is read via a small inline python fallback.
#
# Exit code: 0 in every path EXCEPT the one intentional manual-compact block
# (the python writer returns 2 to abort a manual /compact that lacks a fresh
# reasoned checkpoint — BR-002). The wrapper PROPAGATES the child's exit code
# so that block reaches Claude Code; it does not hard-code exit 0.

INPUT=$(cat)

# Derive cwd from the hook JSON without jq (pure python fallback).
CWD=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("cwd","."))' 2>/dev/null || echo ".")

# Locate the checkpoint writer: prefer repo-local, then install-dir
# sibling (../scripts from this hook). Works under any --target-dir.
_ETC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT=""
if [[ -f "${CWD}/scripts/precompact_checkpoint.py" ]]; then
  SCRIPT="${CWD}/scripts/precompact_checkpoint.py"
elif [[ -f "${_ETC_DIR}/scripts/precompact_checkpoint.py" ]]; then
  SCRIPT="${_ETC_DIR}/scripts/precompact_checkpoint.py"
fi

# Fail-open: if the script can't be resolved, do nothing and let
# compaction proceed.
if [[ -z "$SCRIPT" ]]; then
  exit 0
fi

# Replay the original stdin to the python writer and PROPAGATE its exit code.
# The writer is fail-open (exit 0) on every uncontrolled error; the ONLY
# nonzero it returns is the intentional manual-compact block (exit 2), which
# must reach Claude Code to abort the compaction.
printf '%s' "$INPUT" | python3 "$SCRIPT"
exit $?
