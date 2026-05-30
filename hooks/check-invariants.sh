#!/bin/bash
# hooks/check-invariants.sh
#
# PreToolUse hook for Edit|Write operations.
# Reads INVARIANTS.md from the project root (and component directories),
# extracts verify commands, and blocks operations if any invariant is violated.
#
# Convention: A verify command that produces NON-EMPTY stdout indicates a violation.
#             Empty stdout means the invariant holds.
#
# Exit codes:
#   0 = allow the operation (no violations or no INVARIANTS.md)
#   2 = block the operation (invariant violated)

INPUT=$(cat)

PYTHON=""
python3 -c "" 2>/dev/null && PYTHON=python3
if [[ -z "$PYTHON" ]]; then
  python -c "" 2>/dev/null && PYTHON=python
fi
[[ -z "$PYTHON" ]] && exit 0

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD_HELPER="${HOOK_DIR}/helpers/hook_payload.py"
CWD=$(printf '%s' "$INPUT" | "$PYTHON" "$PAYLOAD_HELPER" cwd) || exit 2
EDITED_FILES=$(printf '%s' "$INPUT" | "$PYTHON" "$PAYLOAD_HELPER" files) || exit 2

# Normalize Windows backslashes to forward slashes so prefix-stripping and
# pattern matching work the same as on macOS/Linux. No-op on POSIX paths.
CWD="${CWD//\\//}"

# If we can't determine the project directory, allow the operation
if [[ -z "$CWD" || "$CWD" == "." ]]; then
  exit 0
fi

# Case-sensitive INVARIANTS.md existence check.
#
# On macOS (APFS) and Windows (NTFS/exFAT), `[[ -f "INVARIANTS.md" ]]` matches
# lowercase `invariants.md` because the filesystem is case-insensitive. That
# caused the hook to parse standards/process/invariants.md (a standards
# document about invariants) as if it were an invariant registry and
# execute its example verify commands. The fix: use `ls` to list the
# directory and grep for the EXACT filename case.
has_invariants_file() {
  local dir="$1"
  [[ -d "$dir" ]] || return 1
  ls "$dir" 2>/dev/null | grep -qE '^INVARIANTS\.md$'
}

# Collect all INVARIANTS.md files to check (project root + component ancestors)
INVARIANT_FILES=()

add_invariant_file() {
  local candidate="$1"
  local existing=""

  for existing in "${INVARIANT_FILES[@]}"; do
    if [[ "$existing" == "$candidate" ]]; then
      return
    fi
  done
  INVARIANT_FILES+=("$candidate")
}

# Always check project root
if has_invariants_file "$CWD"; then
  add_invariant_file "${CWD}/INVARIANTS.md"
fi

# Walk up from each edited file's directory to find component-level
# INVARIANTS.md files.
while IFS= read -r FILE_PATH; do
  [[ -z "$FILE_PATH" ]] && continue
  FILE_PATH="${FILE_PATH//\\//}"

  if [[ "$FILE_PATH" != /* ]] && [[ ! "$FILE_PATH" =~ ^[A-Za-z]:/ ]]; then
    FILE_PATH="${CWD}/${FILE_PATH}"
  fi

  DIR=$(dirname "$FILE_PATH")
  while [[ "$DIR" != "$CWD" && "$DIR" != "/" && "$DIR" != "." ]]; do
    if has_invariants_file "$DIR"; then
      add_invariant_file "${DIR}/INVARIANTS.md"
    fi
    DIR=$(dirname "$DIR")
  done
done <<< "$EDITED_FILES"

# No INVARIANTS.md files found — pass silently
if [[ ${#INVARIANT_FILES[@]} -eq 0 ]]; then
  exit 0
fi

# Parse verify commands from an INVARIANTS.md file.
# Looks for lines matching: - **Verify:** `command here`
# Returns: "INV-ID|command" pairs, one per line
parse_invariants() {
  local file="$1"
  local current_id=""

  while IFS= read -r line; do
    # Match invariant heading: ## INV-NNN: description
    if [[ "$line" =~ ^##[[:space:]]+(INV-[0-9]+): ]]; then
      current_id="${BASH_REMATCH[1]}"
    fi

    # Match verify line: - **Verify:** `command`
    if [[ "$line" =~ \*\*Verify:\*\*[[:space:]]*\`(.+)\` ]]; then
      local cmd="${BASH_REMATCH[1]}"
      if [[ -n "$current_id" && -n "$cmd" ]]; then
        echo "${current_id}|${cmd}"
      fi
    fi
  done < "$file"
}

# Track violations
VIOLATIONS=()

for inv_file in "${INVARIANT_FILES[@]}"; do
  # Parse invariants — if parsing fails, warn but don't block
  PARSED=$(parse_invariants "$inv_file" 2>/dev/null)
  if [[ $? -ne 0 ]]; then
    echo "WARNING: Could not parse ${inv_file}, skipping" >&2
    continue
  fi

  while IFS='|' read -r inv_id verify_cmd; do
    # Skip empty lines
    [[ -z "$inv_id" || -z "$verify_cmd" ]] && continue

    # Run the verify command from the project root.
    # The hook itself has a timeout in settings-hooks.json (10s),
    # so per-command timeout is handled at that level.
    # Verify commands should be fast (grep-based) per the standard.
    RESULT=$(cd "$CWD" && eval "$verify_cmd" 2>/dev/null) || true

    # Non-empty output = violation found
    if [[ -n "$RESULT" ]]; then
      VIOLATIONS+=("${inv_id}")
      echo "INVARIANT VIOLATION [${inv_id}]: Verify command found violations:" >&2
      echo "$RESULT" | head -5 >&2
      RESULT_LINES=$(echo "$RESULT" | wc -l | tr -d ' ')
      if [[ "$RESULT_LINES" -gt 5 ]]; then
        echo "  ... and $((RESULT_LINES - 5)) more" >&2
      fi
    fi
  done <<< "$PARSED"
done

if [[ ${#VIOLATIONS[@]} -gt 0 ]]; then
  echo "" >&2
  echo "BLOCKED: ${#VIOLATIONS[@]} invariant(s) violated: ${VIOLATIONS[*]}" >&2
  echo "Fix the violations or add '# invariant-exempt: INV-NNN' to exempt specific lines." >&2
  exit 2
fi

exit 0
