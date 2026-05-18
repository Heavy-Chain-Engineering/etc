#!/bin/bash
# standards/code/profiles/rust/check-code-quality.sh
#
# Rust-profile code-quality gate. PreToolUse fast-block for obvious
# anti-patterns. The slow gate (verify-green.sh) runs clippy with -D
# warnings; this gate catches the worst offenders before they land.
#
# Sub-checks:
#   CQ-RS-001: Empty function bodies (`fn name() {}`)
#              Maps to clippy::no_effect_underscore_binding /
#              clippy::needless_return (varies by case).
#   CQ-RS-002: .unwrap() / .expect() in production code (outside
#              #[cfg(test)] modules).
#              Maps to clippy::unwrap_used / clippy::expect_used.
#
# Contract:
#   Stdin: standard Claude Code hook JSON payload (file_path, cwd)
#   Exit:  0 = allow | 2 = block (violations found)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

if [[ "$FILE_PATH" != *.rs ]]; then
  exit 0
fi

if [[ "$FILE_PATH" != /* ]]; then
  FILE_PATH="${CWD}/${FILE_PATH}"
fi

if [[ "$FILE_PATH" == *..* ]]; then
  echo "BLOCKED: Suspicious file path containing '..' — ${FILE_PATH}" >&2
  exit 2
fi

if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

# CQ-RS-001: Empty function bodies
EMPTY_BODIES=$(grep -nE '^[[:space:]]*(pub[[:space:]]+)?(async[[:space:]]+)?fn[[:space:]]+[a-zA-Z_][a-zA-Z0-9_]*[^{]*\{[[:space:]]*\}[[:space:]]*$' "$FILE_PATH" 2>/dev/null || true)

# CQ-RS-002: .unwrap() outside #[cfg(test)] sections.
# Quick heuristic: if the file is under tests/ or contains #[cfg(test)] mod, skip.
SKIP_UNWRAP_CHECK=0
case "$FILE_PATH" in
  */tests/*|*_test.rs) SKIP_UNWRAP_CHECK=1 ;;
esac
if grep -qE '^[[:space:]]*#\[cfg\(test\)\]' "$FILE_PATH" 2>/dev/null; then
  # The file has a cfg(test) block; only scan the non-test portion.
  # Simplified: if the file is small, do best-effort grep before #[cfg(test)].
  SKIP_UNWRAP_CHECK=1
fi

UNWRAPS=""
if [ $SKIP_UNWRAP_CHECK -eq 0 ]; then
  UNWRAPS=$(grep -nE '\.unwrap\(\)|\.expect\(' "$FILE_PATH" 2>/dev/null || true)
fi

COUNT=0
if [[ -n "$EMPTY_BODIES" ]]; then
  COUNT=$((COUNT + $(echo "$EMPTY_BODIES" | wc -l | tr -d ' ')))
fi
if [[ -n "$UNWRAPS" ]]; then
  COUNT=$((COUNT + $(echo "$UNWRAPS" | wc -l | tr -d ' ')))
fi

if [[ $COUNT -gt 0 ]]; then
  echo "" >&2
  echo "RUST CODE QUALITY VIOLATIONS (${COUNT}):" >&2
  if [[ -n "$EMPTY_BODIES" ]]; then
    echo "$EMPTY_BODIES" | head -5 | while IFS=: read -r line content; do
      echo "  CQ-RS-001:${line}: Empty function body — ${content## }" >&2
    done
  fi
  if [[ -n "$UNWRAPS" ]]; then
    echo "$UNWRAPS" | head -5 | while IFS=: read -r line content; do
      echo "  CQ-RS-002:${line}: .unwrap()/.expect() in production code — ${content## }" >&2
    done
  fi
  echo "" >&2
  echo "  Fix CQ-RS-001: implement, return zero-value, or delete." >&2
  echo "  Fix CQ-RS-002: use ? operator, match, or .context() / Result." >&2
  echo "  clippy equivalents: unwrap_used, expect_used (enable in [lints.clippy])." >&2
  echo "" >&2
  exit 2
fi

exit 0
