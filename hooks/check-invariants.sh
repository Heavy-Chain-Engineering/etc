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
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

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

# Always check project root
if has_invariants_file "$CWD"; then
  INVARIANT_FILES+=("${CWD}/INVARIANTS.md")
fi

# Walk up from the file's directory to find component-level INVARIANTS.md files
if [[ -n "$FILE_PATH" ]]; then
  # Make path absolute if needed
  if [[ "$FILE_PATH" != /* ]]; then
    FILE_PATH="${CWD}/${FILE_PATH}"
  fi

  DIR=$(dirname "$FILE_PATH")
  # Walk from file's directory up to (but not including) CWD, collecting INVARIANTS.md
  while [[ "$DIR" != "$CWD" && "$DIR" != "/" && "$DIR" != "." ]]; do
    if has_invariants_file "$DIR"; then
      # Avoid duplicates
      ALREADY_ADDED=false
      for existing in "${INVARIANT_FILES[@]}"; do
        if [[ "$existing" == "${DIR}/INVARIANTS.md" ]]; then
          ALREADY_ADDED=true
          break
        fi
      done
      if [[ "$ALREADY_ADDED" == false ]]; then
        INVARIANT_FILES+=("${DIR}/INVARIANTS.md")
      fi
    fi
    DIR=$(dirname "$DIR")
  done
fi

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
