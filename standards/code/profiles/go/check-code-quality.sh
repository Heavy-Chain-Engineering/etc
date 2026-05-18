#!/bin/bash
# standards/code/profiles/go/check-code-quality.sh
#
# Go-profile code-quality gate. PreToolUse fast-block for obvious
# anti-patterns. The slow gate (verify-green.sh) runs go vet +
# golangci-lint; this gate catches the worst offenders before they land.
#
# Sub-checks:
#   CQ-GO-001: Empty function bodies (`func name(...) {}` or `func() {}`)
#              Maps to golangci-lint revive rule `empty-block`.
#
# Contract:
#   Stdin: standard Claude Code hook JSON payload (file_path, cwd)
#   Exit:  0 = allow | 2 = block (violations found)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Skip non-go files (defensive — dispatch already filtered)
if [[ "$FILE_PATH" != *.go ]]; then
  exit 0
fi

# Resolve absolute path
if [[ "$FILE_PATH" != /* ]]; then
  FILE_PATH="${CWD}/${FILE_PATH}"
fi

# Security: reject paths containing ..
if [[ "$FILE_PATH" == *..* ]]; then
  echo "BLOCKED: Suspicious file path containing '..' — ${FILE_PATH}" >&2
  exit 2
fi

# If the file doesn't exist yet, allow (new-file creation path)
if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

# CQ-GO-001: Empty function bodies — matches:
#   func name(args) ReturnType {}
#   func name(args) {}
#   func (r Receiver) name(args) {}
# Skips bodies with any non-whitespace content. Interface declarations
# use `type X interface { ... }` syntax, not `func X() {}`, so they're
# not affected.
VIOLATIONS=$(grep -nE '^[[:space:]]*func[[:space:]]+(\([^)]+\)[[:space:]]+)?[a-zA-Z_][a-zA-Z0-9_]*\([^)]*\)([[:space:]]+[a-zA-Z_][a-zA-Z0-9_*\[\]\.\,[:space:]]*)?[[:space:]]*\{[[:space:]]*\}[[:space:]]*$' "$FILE_PATH" 2>/dev/null || true)

if [[ -n "$VIOLATIONS" ]]; then
  COUNT=$(echo "$VIOLATIONS" | wc -l | tr -d ' ')
  echo "" >&2
  echo "GO CODE QUALITY VIOLATIONS (${COUNT}):" >&2
  echo "$VIOLATIONS" | head -10 | while IFS=: read -r line content; do
    echo "  CQ-GO-001:${line}: Empty function body — ${content## }" >&2
  done
  echo "" >&2
  echo "  Fix: implement the function, return zero-value, or delete it." >&2
  echo "  golangci-lint equivalent: revive empty-block rule" >&2
  echo "" >&2
  exit 2
fi

exit 0
