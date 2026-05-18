#!/bin/bash
# standards/code/profiles/rust/verify-green.sh
#
# Rust-profile verify-green gate. Runs:
#   1. Tests       — cargo test --workspace
#   2. Linting     — cargo clippy --workspace --all-targets -- -D warnings
#   3. Formatting  — cargo fmt --all -- --check
#
# Skips entire profile cleanly when cargo isn't on PATH (no toolchain).
# clippy is part of the standard rustup toolchain; if it's missing,
# emit ERROR per F020 EC-007.
#
# Stdin: standard Claude Code hook JSON payload (CWD only)
# Exit:  0 = green (or step skipped cleanly) | 2 = failure

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

cd "$CWD" || exit 0

if [ ! -f Cargo.toml ]; then
  echo "[rust/verify-green] No Cargo.toml found; skipping." >&2
  exit 0
fi

if ! command -v cargo &> /dev/null; then
  echo "[rust/verify-green] ERROR: Cargo.toml present but 'cargo' not on PATH. Install Rust from https://rustup.rs/." >&2
  exit 1
fi

# ── 1. Tests ──────────────────────────────────────────────────────────
echo "[rust/verify-green] Running cargo test --workspace..." >&2
TEST_OUTPUT=$(cargo test --workspace --no-fail-fast 2>&1)
TEST_EXIT=$?
if [ $TEST_EXIT -ne 0 ]; then
  echo "[rust/verify-green] FAILED: cargo test exited $TEST_EXIT." >&2
  echo "$TEST_OUTPUT" | tail -30 >&2
  exit 2
fi

# ── 2. Linting (clippy ships with rustup) ─────────────────────────────
if cargo clippy --version &> /dev/null; then
  echo "[rust/verify-green] Running cargo clippy --workspace --all-targets -- -D warnings..." >&2
  CLIPPY_OUTPUT=$(cargo clippy --workspace --all-targets -- -D warnings 2>&1)
  CLIPPY_EXIT=$?
  if [ $CLIPPY_EXIT -ne 0 ]; then
    echo "[rust/verify-green] FAILED: clippy lint violations." >&2
    echo "$CLIPPY_OUTPUT" | tail -30 >&2
    exit 2
  fi
else
  echo "[rust/verify-green] ERROR: clippy not installed. Run 'rustup component add clippy'." >&2
  exit 1
fi

# ── 3. Formatting ─────────────────────────────────────────────────────
if cargo fmt --version &> /dev/null; then
  echo "[rust/verify-green] Running cargo fmt --all -- --check..." >&2
  FMT_OUTPUT=$(cargo fmt --all -- --check 2>&1)
  FMT_EXIT=$?
  if [ $FMT_EXIT -ne 0 ]; then
    echo "[rust/verify-green] FAILED: unformatted files (run 'cargo fmt --all')." >&2
    echo "$FMT_OUTPUT" | head -20 >&2
    exit 2
  fi
else
  echo "[rust/verify-green] WARN: rustfmt not installed; skipping format check." >&2
fi

echo "[rust/verify-green] All green: tests + clippy + fmt." >&2
exit 0
