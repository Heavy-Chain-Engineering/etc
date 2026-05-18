#!/bin/bash
# standards/code/profiles/go/check-test-exists.sh
#
# Go-profile TDD gate. Edit/Write on a production .go file under
# `cmd/`, `pkg/`, or `internal/` is blocked unless a sibling _test.go
# file exists. Go's testing convention is foo.go + foo_test.go in the
# same package directory.
#
# Contract:
#   Stdin: standard Claude Code hook JSON payload (file_path, cwd)
#   Exit:  0 = allow | 2 = block (sibling _test.go missing)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Make path relative to project root
REL_PATH="$FILE_PATH"
if [[ "$FILE_PATH" == /* ]]; then
  REL_PATH="${FILE_PATH#$CWD/}"
fi

# Only gate production source — cmd/, pkg/, internal/ are the conventional
# Go layouts. Files at repo root (e.g. main.go for tiny tools) are also
# gated.
case "$REL_PATH" in
  cmd/*|pkg/*|internal/*|*.go) : ;;
  *) exit 0 ;;
esac

BASENAME=$(basename "$FILE_PATH")

# Skip non-.go files
if [[ "$BASENAME" != *.go ]]; then
  exit 0
fi

# Skip the test files themselves (don't recurse)
if [[ "$BASENAME" == *_test.go ]]; then
  exit 0
fi

# Skip generated, doc, and convention files
case "$BASENAME" in
  doc.go|main.go|zz_generated_*.go|*_generated.go|*.pb.go) exit 0 ;;
esac

# Strip .go to get the base name
MODULE="${BASENAME%.go}"

# Look for sibling _test.go in same package directory
DIR=$(dirname "$FILE_PATH")
SIBLING="${DIR}/${MODULE}_test.go"

if [ -f "$SIBLING" ]; then
  exit 0
fi

# Also accept any *_test.go in the same dir that might exercise this file
# (Go tests are by package, not by file; a single test file can cover
# many sources).
if find "$DIR" -maxdepth 1 -name "*_test.go" 2>/dev/null | grep -q .; then
  exit 0
fi

echo "[go/check-test-exists] BLOCKED: No test file found for '${MODULE}'. Write a failing test first (Red/Green TDD)." >&2
echo "Expected: ${SIBLING} (or any *_test.go in ${DIR})" >&2
exit 2
