#!/bin/bash
# standards/code/profiles/typescript/verify-green.sh
#
# TypeScript-profile verify-green gate. Runs:
#   1. Tests          — npm test (delegates to whatever's in package.json scripts)
#   2. Type checking  — npx tsc --noEmit
#   3. Linting        — npx eslint
#
# Skips a step cleanly when the relevant tool isn't configured (no
# tsconfig.json → skip tsc; no .eslintrc → skip eslint). Each step emits
# a clear ERROR per F020 EC-007 if the tool is in scope but uninstalled.
#
# Stdin: standard Claude Code hook JSON payload (CWD only)
# Exit:  0 = green (or step skipped cleanly) | 2 = failure

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

cd "$CWD" || exit 0

# ── 1. Tests ──────────────────────────────────────────────────────────
if [ -f package.json ] && grep -q '"test"' package.json 2>/dev/null; then
  echo "[typescript/verify-green] Running npm test..." >&2
  TEST_OUTPUT=$(npm test --silent 2>&1)
  TEST_EXIT=$?
  if [ $TEST_EXIT -ne 0 ]; then
    echo "[typescript/verify-green] FAILED: Test runner exited non-zero." >&2
    echo "$TEST_OUTPUT" | tail -30 >&2
    exit 2
  fi
else
  echo "[typescript/verify-green] No 'test' script in package.json; skipping tests." >&2
fi

# ── 2. Type checking ──────────────────────────────────────────────────
if [ -f tsconfig.json ]; then
  if ! command -v npx &> /dev/null; then
    echo "[typescript/verify-green] ERROR: tsconfig.json present but npx not on PATH. Install Node.js." >&2
    exit 1
  fi
  echo "[typescript/verify-green] Running tsc --noEmit..." >&2
  TSC_OUTPUT=$(npx --no-install tsc --noEmit 2>&1)
  TSC_EXIT=$?
  if [ $TSC_EXIT -ne 0 ]; then
    if echo "$TSC_OUTPUT" | grep -q 'not found'; then
      echo "[typescript/verify-green] ERROR: tsconfig.json present but typescript not in node_modules. Run 'npm install'." >&2
      exit 1
    fi
    echo "[typescript/verify-green] FAILED: Type checking errors." >&2
    echo "$TSC_OUTPUT" | tail -30 >&2
    exit 2
  fi
fi

# ── 3. Linting ────────────────────────────────────────────────────────
ESLINT_CONFIG=""
for c in .eslintrc.js .eslintrc.cjs .eslintrc.json .eslintrc.yml .eslintrc.yaml eslint.config.js eslint.config.mjs eslint.config.cjs; do
  if [ -f "$c" ]; then
    ESLINT_CONFIG="$c"
    break
  fi
done
# Also accept "eslintConfig" in package.json
if [ -z "$ESLINT_CONFIG" ] && [ -f package.json ] && grep -q '"eslintConfig"' package.json 2>/dev/null; then
  ESLINT_CONFIG="package.json"
fi

if [ -n "$ESLINT_CONFIG" ]; then
  echo "[typescript/verify-green] Running eslint (config: ${ESLINT_CONFIG})..." >&2
  LINT_OUTPUT=$(npx --no-install eslint . 2>&1)
  LINT_EXIT=$?
  if [ $LINT_EXIT -ne 0 ]; then
    if echo "$LINT_OUTPUT" | grep -q 'not found'; then
      echo "[typescript/verify-green] ERROR: eslint config present but eslint not in node_modules. Run 'npm install'." >&2
      exit 1
    fi
    echo "[typescript/verify-green] FAILED: Lint violations." >&2
    echo "$LINT_OUTPUT" | tail -30 >&2
    exit 2
  fi
else
  echo "[typescript/verify-green] No eslint config detected; skipping lint." >&2
fi

echo "[typescript/verify-green] All green: tests + types + lint." >&2
exit 0
