#!/bin/bash
# hooks/check-completion-discipline.sh
#
# Stop hook — enforces standards/process/completion-discipline.md.
#
# Sequences two checks that were previously parallel and racing:
#
#   Step 1. If .tdd-dirty is present, run the CI gate inline (pytest +
#           mypy + ruff + invariants). On pass, clear .tdd-dirty. On
#           fail, block with the CI output.
#
#   Step 2. If any task in .etc_sdlc/features/*/tasks/*.yaml has
#           status: in_progress, block — work is mid-flight.
#
# If both steps pass, allow the stop silently.
#
# This hook is language-agnostic — it does NOT regex on quit-phrases.
# The model can phrase its stop however it wants; what matters is
# whether the state of work is finished or formally handed off.
#
# History: this hook absorbs the previous ci-gate.sh Stop hook. They
# were peers under the same Stop event and fired in parallel, racing
# to check and clear the .tdd-dirty marker. Merging the sequence into
# a single hook makes the order deterministic.
#
# Exit codes:
#   0 = allow stop (no unfinished-work signals)
#   1 = block stop (CI failed)
#   2 = block stop (task in_progress; stderr has remediation)

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# If we can't determine cwd, allow — we can't evaluate state without it.
if [[ -z "$CWD" || "$CWD" == "." ]]; then
  exit 0
fi

# ═══════════════════════════════════════════════════════════════════════
# Step 1: CI gate (run when .tdd-dirty is present)
# ═══════════════════════════════════════════════════════════════════════

DIRTY="${CWD}/.tdd-dirty"

if [[ -f "$DIRTY" ]]; then
  FAILURES=()

  # Discover Python source directories that actually exist.
  PY_DIRS=()
  for d in src tests hooks scripts platform/src; do
    [[ -d "${CWD}/${d}" ]] && PY_DIRS+=("$d")
  done

  # Detect uv-managed Python projects so we invoke the repo's pinned
  # toolchain (pinned ruff, pinned pytest, project venv) instead of
  # whatever happens to be on $PATH. System ruff/pytest on a dev box can
  # lag behind the repo pins and produce false-positive gate failures
  # (e.g. system ruff refusing `target-version = "py314"`).
  if [[ -f "${CWD}/uv.lock" ]] || { [[ -f "${CWD}/pyproject.toml" ]] && grep -q '^\[tool\.uv\]' "${CWD}/pyproject.toml" 2>/dev/null; }; then
    PY_RUNNER=("uv" "run")
  else
    PY_RUNNER=()
  fi

  # Decide whether this directory is actually a Python project. Empty
  # `tests/` dirs (e.g. a frontend bootstrap that happens to create one)
  # used to weaponize the gate — pytest would find nothing, exit 5, and
  # block the stop event on a non-Python project.
  IS_PY_PROJECT=0
  if [[ -f "${CWD}/uv.lock" ]] || [[ -f "${CWD}/pytest.ini" ]] || [[ -f "${CWD}/setup.cfg" ]]; then
    IS_PY_PROJECT=1
  elif [[ -f "${CWD}/pyproject.toml" ]] && grep -Eq '^\[(project|tool\.poetry|tool\.pytest\.ini_options|tool\.uv)\]' "${CWD}/pyproject.toml" 2>/dev/null; then
    IS_PY_PROJECT=1
  fi

  # 1a. Test suite
  if [[ $IS_PY_PROJECT -eq 1 ]] && { [[ -d "${CWD}/tests" ]] || [[ -d "${CWD}/test" ]]; }; then
    TEST_OUTPUT=$(cd "$CWD" && "${PY_RUNNER[@]}" python3 -m pytest -q 2>&1)
    TEST_EXIT=$?
    if [[ $TEST_EXIT -ne 0 ]]; then
      FAILURES+=("TESTS FAILED (exit $TEST_EXIT)")
      echo "── pytest output ──" >&2
      echo "$TEST_OUTPUT" | tail -20 >&2
      echo "" >&2
    fi
  fi

  # 1b. Type checking (only if mypy is configured)
  if [[ -f "${CWD}/pyproject.toml" ]] && grep -q '\[tool\.mypy\]' "${CWD}/pyproject.toml" 2>/dev/null; then
    if [[ ${#PY_DIRS[@]} -gt 0 ]]; then
      MYPY_OUTPUT=$(cd "$CWD" && "${PY_RUNNER[@]}" python3 -m mypy "${PY_DIRS[@]}" 2>&1)
      MYPY_EXIT=$?
      if [[ $MYPY_EXIT -ne 0 ]]; then
        FAILURES+=("TYPE CHECK FAILED (exit $MYPY_EXIT)")
        echo "── mypy output ──" >&2
        echo "$MYPY_OUTPUT" | tail -10 >&2
        echo "" >&2
      fi
    fi
  fi

  # 1c. Linting (only if ruff is configured)
  if [[ -f "${CWD}/pyproject.toml" ]] && grep -q '\[tool\.ruff\]' "${CWD}/pyproject.toml" 2>/dev/null; then
    if [[ ${#PY_DIRS[@]} -gt 0 ]]; then
      RUFF_OUTPUT=$(cd "$CWD" && "${PY_RUNNER[@]}" ruff check "${PY_DIRS[@]}" 2>&1)
      RUFF_EXIT=$?
      if [[ $RUFF_EXIT -ne 0 ]]; then
        FAILURES+=("LINT FAILED (exit $RUFF_EXIT)")
        echo "── ruff output ──" >&2
        echo "$RUFF_OUTPUT" | tail -10 >&2
        echo "" >&2
      fi
    fi
  fi

  # 1d. Invariant verify commands
  INVARIANTS="${CWD}/INVARIANTS.md"
  if [[ -f "$INVARIANTS" ]]; then
    while IFS= read -r line; do
      if [[ "$line" =~ \*\*Verify:\*\*[[:space:]]*\`(.+)\` ]]; then
        CMD="${BASH_REMATCH[1]}"
        RESULT=$(cd "$CWD" && eval "$CMD" 2>/dev/null) || true
        if [[ -n "$RESULT" ]]; then
          FAILURES+=("INVARIANT VIOLATED")
          echo "── invariant violation ──" >&2
          echo "$RESULT" | head -5 >&2
          echo "" >&2
        fi
      fi
    done < "$INVARIANTS"
  fi

  # CI gate decision
  if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo "CI GATE FAILED: ${FAILURES[*]}" >&2
    echo "Fix the failures above before completing this task." >&2
    exit 1
  fi

  # All CI checks passed — clear the dirty marker
  rm -f "$DIRTY"
fi

# ═══════════════════════════════════════════════════════════════════════
# Step 2: in_progress task check
# ═══════════════════════════════════════════════════════════════════════

SIGNAL_INPROGRESS_COUNT=0
TASKS_GLOB="${CWD}/.etc_sdlc/features"
if [[ -d "$TASKS_GLOB" ]]; then
  # F009-lifecycle-gap fix: scan flat path AND active/ subdirectory.
  # The naive "$TASKS_GLOB"/*/tasks/*.yaml glob misses features under
  # active/, which is where the allocator places new in-flight work.
  # The shipped/ subdirectory is intentionally NOT scanned — shipped
  # features are done and shouldn't have in_progress tasks anyway.
  SIGNAL_INPROGRESS_COUNT=$(grep -rhE '^status:[[:space:]]*in_progress[[:space:]]*$' \
    "$TASKS_GLOB"/*/tasks/*.yaml \
    "$TASKS_GLOB"/active/*/tasks/*.yaml \
    2>/dev/null | wc -l | tr -d ' ')
fi

if [[ "$SIGNAL_INPROGRESS_COUNT" -eq 0 ]]; then
  # No unfinished-work signals; allow the stop.
  exit 0
fi

# ── Block with actionable message ───────────────────────────────────────

echo "" >&2
echo "COMPLETION DISCIPLINE: Unfinished work detected." >&2
echo "" >&2
echo "Signals:" >&2
echo "  - ${SIGNAL_INPROGRESS_COUNT} task(s) have status: in_progress" >&2
echo "" >&2
echo "You cannot stop the session while work is mid-flight." >&2
echo "Valid paths out (pick one):" >&2
echo "" >&2
echo "  1. Complete the work." >&2
echo "     - Update task status to 'completed' via:" >&2
echo "         python3 ~/.claude/scripts/tasks.py set-status <id> completed" >&2
echo "" >&2
echo "  2. Formally escalate." >&2
echo "     - Produce an ## ESCALATION block per" >&2
echo "       standards/process/completion-discipline.md rule 2" >&2
echo "     - Mark affected task(s) escalated:" >&2
echo "         python3 ~/.claude/scripts/tasks.py set-status <id> escalated" >&2
echo "" >&2
echo "  3. Formally block on an external dependency." >&2
echo "     - python3 ~/.claude/scripts/tasks.py set-status <id> blocked" >&2
echo "" >&2
echo "You do not quit conversationally. See" >&2
echo "standards/process/completion-discipline.md for the full standard." >&2
echo "" >&2

exit 2
