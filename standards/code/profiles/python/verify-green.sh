#!/bin/bash
# standards/code/profiles/python/verify-green.sh
#
# Python-profile verify-green gate. Runs the verification chain:
#   1. Tests with coverage (uv run pytest --cov --cov-fail-under=98)
#   2. Type checking (uv run mypy src/)
#   3. Linting (uv run ruff check src/ tests/)
#
# Contract: this script assumes verification IS needed (top-level
# hooks/verify-green.sh handles the .tdd-dirty gate). It just runs the
# Python chain.
#
# Stdin: standard Claude Code hook JSON payload (used only for CWD)
# Exit:  0 = green | 2 = failure
#
# Migrated from the previous monolithic hooks/verify-green.sh as part of
# F020. Body is byte-identical to the prior python toolchain branch — no
# behavioral change for Python operators (F020 BR-007 zero-regression).

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

cd "$CWD" || exit 0

# Run tests with coverage
echo "[python/verify-green] Running pytest with coverage..." >&2
TEST_OUTPUT=$(uv run pytest --cov --cov-fail-under=98 -x --tb=short -q 2>&1)
TEST_EXIT=$?

if [ $TEST_EXIT -ne 0 ]; then
  echo "[python/verify-green] FAILED: Tests failed or coverage below 98%." >&2
  echo "$TEST_OUTPUT" | tail -30 >&2
  exit 2
fi

# Run type checking
echo "[python/verify-green] Running mypy..." >&2
MYPY_OUTPUT=$(uv run mypy src/ 2>&1)
MYPY_EXIT=$?

if [ $MYPY_EXIT -ne 0 ]; then
  echo "[python/verify-green] FAILED: Type checking errors." >&2
  echo "$MYPY_OUTPUT" | tail -20 >&2
  exit 2
fi

# Run linting
echo "[python/verify-green] Running ruff check..." >&2
LINT_OUTPUT=$(uv run ruff check src/ tests/ 2>&1)
LINT_EXIT=$?

if [ $LINT_EXIT -ne 0 ]; then
  echo "[python/verify-green] FAILED: Lint violations." >&2
  echo "$LINT_OUTPUT" | tail -20 >&2
  exit 2
fi

echo "[python/verify-green] All green: tests + types + lint." >&2
exit 0
