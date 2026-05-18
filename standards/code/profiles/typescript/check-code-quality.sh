#!/bin/bash
# standards/code/profiles/typescript/check-code-quality.sh
#
# TypeScript-profile code-quality gate. PreToolUse fast-block checks for
# obvious anti-patterns. The slow gate (`verify-green.sh`) runs eslint
# end-to-end; this gate catches the worst offenders before they land.
#
# Sub-checks:
#   CQ-TS-001: Empty function bodies (`function … { }`, `=> { }`, `():
#              type {}`)
#              Maps to eslint @typescript-eslint/no-empty-function.
#   CQ-TS-002: Module-level `let` for non-reassigned bindings is
#              caught by `prefer-const` in verify-green; skip at
#              PreToolUse to avoid false positives on partial edits.
#
# Contract:
#   Stdin: standard Claude Code hook JSON payload (file_path, cwd)
#   Exit:  0 = allow | 2 = block (violations found)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Skip non-typescript files (defensive — dispatch already filtered)
case "$FILE_PATH" in
  *.ts|*.tsx|*.mts|*.cts) : ;;
  *) exit 0 ;;
esac

# Skip type-declaration files — they legitimately have empty bodies
case "$FILE_PATH" in
  *.d.ts) exit 0 ;;
esac

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

# CQ-TS-001: Empty function bodies — matches:
#   function name(...): T {}
#   function name(...): T { }
#   () => {}
#   async () => {}
# Skips bodies containing a newline or non-whitespace content.
# Regex: opening paren + optional return type + `{` + only whitespace + `}`
VIOLATIONS=$(grep -nE '(function[[:space:]]+[a-zA-Z_$][a-zA-Z0-9_$]*\([^)]*\)[[:space:]]*(:[^{]*)?[[:space:]]*\{[[:space:]]*\}|=>[[:space:]]*\{[[:space:]]*\})' "$FILE_PATH" 2>/dev/null || true)

if [[ -n "$VIOLATIONS" ]]; then
  COUNT=$(echo "$VIOLATIONS" | wc -l | tr -d ' ')
  echo "" >&2
  echo "TYPESCRIPT CODE QUALITY VIOLATIONS (${COUNT}):" >&2
  echo "$VIOLATIONS" | head -10 | while IFS=: read -r line content; do
    echo "  CQ-TS-001:${line}: No-op / empty function body — ${content## }" >&2
  done
  echo "" >&2
  echo "  Fix: add a meaningful body, or mark as abstract / interface." >&2
  echo "  eslint equivalent: @typescript-eslint/no-empty-function" >&2
  echo "" >&2
  exit 2
fi

exit 0
