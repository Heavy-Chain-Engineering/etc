#!/bin/bash
# standards/code/profiles/typescript/check-test-exists.sh
#
# TypeScript-profile TDD gate. Edit/Write on a .ts/.tsx source file under
# src/ is blocked unless a sibling test file exists. The TS conventions
# for test-file naming are *.test.ts, *.test.tsx, *.spec.ts, *.spec.tsx.
#
# Contract:
#   Stdin: standard Claude Code hook JSON payload (file_path, cwd)
#   Exit:  0 = allow | 2 = block (test missing for production source)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Make path relative to project root
REL_PATH="$FILE_PATH"
if [[ "$FILE_PATH" == /* ]]; then
  REL_PATH="${FILE_PATH#$CWD/}"
fi

# Skip if not under src/
if [[ "$REL_PATH" != src/* ]]; then
  exit 0
fi

BASENAME=$(basename "$FILE_PATH")

# Skip declaration files (generated, not authored)
if [[ "$BASENAME" == *.d.ts ]]; then
  exit 0
fi

# Skip if the source file IS the test (don't recurse on test files)
if [[ "$BASENAME" == *.test.ts || "$BASENAME" == *.test.tsx || \
      "$BASENAME" == *.spec.ts || "$BASENAME" == *.spec.tsx ]]; then
  exit 0
fi

# Only gate TypeScript files
if [[ "$BASENAME" != *.ts && "$BASENAME" != *.tsx && \
      "$BASENAME" != *.mts && "$BASENAME" != *.cts ]]; then
  exit 0
fi

# Strip the extension to get the module name
MODULE="${BASENAME%.ts}"
MODULE="${MODULE%.tsx}"
MODULE="${MODULE%.mts}"
MODULE="${MODULE%.cts}"

# Look for a sibling test file. TS projects often co-locate tests
# next to source (foo.ts + foo.test.ts) rather than in a separate
# tests/ directory; check both layouts.
DIR=$(dirname "$FILE_PATH")
FOUND=""
for pattern in "${DIR}/${MODULE}.test.ts" "${DIR}/${MODULE}.test.tsx" \
               "${DIR}/${MODULE}.spec.ts" "${DIR}/${MODULE}.spec.tsx"; do
  if [ -f "$pattern" ]; then
    FOUND="$pattern"
    break
  fi
done

# Also check a separate tests/ tree (jest/vitest with rootDir config)
if [ -z "$FOUND" ]; then
  if find "${CWD}/tests" -name "${MODULE}.test.ts" -o -name "${MODULE}.test.tsx" \
                        -o -name "${MODULE}.spec.ts" -o -name "${MODULE}.spec.tsx" 2>/dev/null | grep -q .; then
    FOUND="found-in-tests-tree"
  fi
fi

if [ -z "$FOUND" ]; then
  echo "[typescript/check-test-exists] BLOCKED: No test file found for '${MODULE}'. Write a failing test first (Red/Green TDD)." >&2
  echo "Expected (any of): ${DIR}/${MODULE}.test.ts, ${MODULE}.spec.ts, or under tests/" >&2
  exit 2
fi

exit 0
