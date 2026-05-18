#!/bin/bash
# standards/code/profiles/go/verify-green.sh
#
# Go-profile verify-green gate. Runs:
#   1. Tests          — go test ./...
#   2. Vetting        — go vet ./...
#   3. Formatting     — gofmt -l (zero unformatted files)
#   4. Linting        — golangci-lint run (when installed)
#
# Skips a step cleanly when the relevant tool isn't installed (no `go`
# on PATH → skip entire profile; no `golangci-lint` → skip lint step
# with WARN per F020 EC-007). Each step emits a clear ERROR if its
# tool is required but uninstalled.
#
# Stdin: standard Claude Code hook JSON payload (CWD only)
# Exit:  0 = green (or step skipped cleanly) | 2 = failure

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

cd "$CWD" || exit 0

# Sanity: a go.mod must exist for go tooling to work
if [ ! -f go.mod ]; then
  echo "[go/verify-green] No go.mod found; skipping." >&2
  exit 0
fi

# `go` itself must be available — if not, this is ERROR (the profile
# claims this project but its primary toolchain is missing).
if ! command -v go &> /dev/null; then
  echo "[go/verify-green] ERROR: go.mod present but 'go' not on PATH. Install Go from https://go.dev/dl/." >&2
  exit 1
fi

# ── 1. Tests ──────────────────────────────────────────────────────────
echo "[go/verify-green] Running go test ./..." >&2
TEST_OUTPUT=$(go test ./... 2>&1)
TEST_EXIT=$?
if [ $TEST_EXIT -ne 0 ]; then
  echo "[go/verify-green] FAILED: tests exited $TEST_EXIT." >&2
  echo "$TEST_OUTPUT" | tail -30 >&2
  exit 2
fi

# ── 2. Vet ────────────────────────────────────────────────────────────
echo "[go/verify-green] Running go vet ./..." >&2
VET_OUTPUT=$(go vet ./... 2>&1)
VET_EXIT=$?
if [ $VET_EXIT -ne 0 ]; then
  echo "[go/verify-green] FAILED: go vet exited $VET_EXIT." >&2
  echo "$VET_OUTPUT" | tail -30 >&2
  exit 2
fi

# ── 3. Formatting ─────────────────────────────────────────────────────
# gofmt -l prints any unformatted files; output must be empty.
UNFORMATTED=$(gofmt -l . 2>/dev/null | grep -v '^vendor/' || true)
if [ -n "$UNFORMATTED" ]; then
  echo "[go/verify-green] FAILED: unformatted files (run 'gofmt -w'):" >&2
  echo "$UNFORMATTED" >&2
  exit 2
fi

# ── 4. Linting (only if golangci-lint is installed) ───────────────────
if command -v golangci-lint &> /dev/null; then
  echo "[go/verify-green] Running golangci-lint run..." >&2
  LINT_OUTPUT=$(golangci-lint run 2>&1)
  LINT_EXIT=$?
  if [ $LINT_EXIT -ne 0 ]; then
    echo "[go/verify-green] FAILED: golangci-lint violations." >&2
    echo "$LINT_OUTPUT" | tail -30 >&2
    exit 2
  fi
else
  echo "[go/verify-green] WARN: golangci-lint not installed; skipping lint." >&2
fi

echo "[go/verify-green] All green: tests + vet + fmt + lint." >&2
exit 0
