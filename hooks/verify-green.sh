#!/bin/bash
# ~/.claude/hooks/verify-green.sh
#
# Stop hook. Runs when an agent is about to finish responding.
# If .tdd-dirty exists (production code was modified), runs full verification:
#   1. Tests + coverage (98% threshold)
#   2. Type checking (mypy)
#   3. Linting (ruff)
#
# Exit codes:
#   0 = verification passed (or no dirty marker)
#   2 = verification failed (blocks completion)

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

if [ -f "${CWD}/.tdd-dirty" ]; then
  cd "$CWD" || exit 0

  # Run tests with coverage
  echo "Running tests with coverage..." >&2
  TEST_OUTPUT=$(uv run pytest --cov --cov-fail-under=98 -x --tb=short -q 2>&1)
  TEST_EXIT=$?

  if [ $TEST_EXIT -ne 0 ]; then
    echo "VERIFICATION FAILED: Tests failed or coverage below 98%." >&2
    echo "$TEST_OUTPUT" | tail -30 >&2
    exit 2
  fi

  # Run type checking
  echo "Running type checker..." >&2
  MYPY_OUTPUT=$(uv run mypy src/ 2>&1)
  MYPY_EXIT=$?

  if [ $MYPY_EXIT -ne 0 ]; then
    echo "VERIFICATION FAILED: Type checking errors." >&2
    echo "$MYPY_OUTPUT" | tail -20 >&2
    exit 2
  fi

  # Run linting
  echo "Running linter..." >&2
  LINT_OUTPUT=$(uv run ruff check src/ tests/ 2>&1)
  LINT_EXIT=$?

  if [ $LINT_EXIT -ne 0 ]; then
    echo "VERIFICATION FAILED: Lint violations." >&2
    echo "$LINT_OUTPUT" | tail -20 >&2
    exit 2
  fi

  # All checks passed — clean up the dirty marker
  rm -f "${CWD}/.tdd-dirty"
  echo "Verification passed: tests, types, lint all green." >&2
fi

exit 0
