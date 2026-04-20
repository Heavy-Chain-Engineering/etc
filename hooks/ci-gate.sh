#!/bin/bash
# hooks/ci-gate.sh
#
# Stop hook — lightweight CI gate that replaces the Sonnet 4.5 agent.
#
# The old agent-type hook spun up a Sonnet model on EVERY stop event,
# even conversational turns with zero code changes. This bash script
# checks the .tdd-dirty marker first — if no production code was
# modified, exit 0 immediately (zero latency, zero cost).
#
# When code WAS modified, run the mechanical checks directly:
#   1. pytest (if tests/ exists)
#   2. mypy (if configured)
#   3. ruff (if configured)
#   4. INVARIANTS.md verify commands (if file exists)
#
# Exit codes:
#   0 = allow stop (all checks pass or no code modified)
#   1 = block stop (a check failed; stderr has the details)

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

DIRTY="${CWD}/.tdd-dirty"

# ── Fast path: no code modified ─────────────────────────────────────────
if [[ ! -f "$DIRTY" ]]; then
  exit 0
fi

# ── Slow path: production code was modified, run CI ─────────────────────
FAILURES=()

# 1. Test suite
if [[ -d "${CWD}/tests" ]] || [[ -d "${CWD}/test" ]]; then
  TEST_OUTPUT=$(cd "$CWD" && python3 -m pytest -q 2>&1)
  TEST_EXIT=$?
  if [[ $TEST_EXIT -ne 0 ]]; then
    FAILURES+=("TESTS FAILED (exit $TEST_EXIT)")
    echo "── pytest output ──" >&2
    echo "$TEST_OUTPUT" | tail -20 >&2
    echo "" >&2
  fi
fi

# Discover Python source directories that actually exist.
# Checking hardcoded paths like `src/` fails on projects that use a
# different layout (e.g., flat `hooks/` `scripts/` `tests/`). We let
# ruff and mypy read their own config from pyproject.toml when no
# explicit paths are passed.
PY_DIRS=()
for d in src tests hooks scripts platform/src; do
  [[ -d "${CWD}/${d}" ]] && PY_DIRS+=("$d")
done

# 2. Type checking (only if mypy is configured)
if [[ -f "${CWD}/pyproject.toml" ]] && grep -q '\[tool\.mypy\]' "${CWD}/pyproject.toml" 2>/dev/null; then
  if command -v mypy &>/dev/null && [[ ${#PY_DIRS[@]} -gt 0 ]]; then
    MYPY_OUTPUT=$(cd "$CWD" && python3 -m mypy "${PY_DIRS[@]}" 2>&1)
    MYPY_EXIT=$?
    if [[ $MYPY_EXIT -ne 0 ]]; then
      FAILURES+=("TYPE CHECK FAILED (exit $MYPY_EXIT)")
      echo "── mypy output ──" >&2
      echo "$MYPY_OUTPUT" | tail -10 >&2
      echo "" >&2
    fi
  fi
fi

# 3. Linting (only if ruff is configured)
if [[ -f "${CWD}/pyproject.toml" ]] && grep -q '\[tool\.ruff\]' "${CWD}/pyproject.toml" 2>/dev/null; then
  if command -v ruff &>/dev/null && [[ ${#PY_DIRS[@]} -gt 0 ]]; then
    RUFF_OUTPUT=$(cd "$CWD" && ruff check "${PY_DIRS[@]}" 2>&1)
    RUFF_EXIT=$?
    if [[ $RUFF_EXIT -ne 0 ]]; then
      FAILURES+=("LINT FAILED (exit $RUFF_EXIT)")
      echo "── ruff output ──" >&2
      echo "$RUFF_OUTPUT" | tail -10 >&2
      echo "" >&2
    fi
  fi
fi

# 4. Invariant verify commands
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

# ── Report ──────────────────────────────────────────────────────────────
if [[ ${#FAILURES[@]} -gt 0 ]]; then
  echo "CI GATE FAILED: ${FAILURES[*]}" >&2
  echo "Fix the failures above before completing this task." >&2
  exit 1
fi

# All checks passed — clean up the dirty marker
rm -f "$DIRTY"
exit 0
