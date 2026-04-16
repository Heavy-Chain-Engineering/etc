#!/bin/bash
# hooks/check-concepts.sh
#
# Verify-phase hook for cross-boundary CONCEPT entries in INVARIANTS.md.
# Parses CONCEPT-NNN headings (not INV-NNN — those are handled by
# check-invariants.sh at PreToolUse time) and runs their verify commands.
#
# CONCEPT verify commands scan multiple directories and are inherently
# slower than single-file INV checks, so this hook runs at verify phase
# only, never per-edit.
#
# Convention: A verify command that produces NON-EMPTY stdout indicates a violation.
#             Empty stdout means the concept holds.
#
# Exit codes:
#   0 = all concepts hold (or no INVARIANTS.md / no CONCEPT entries)
#   2 = concept violated

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# If we can't determine the project directory, allow the operation
if [[ -z "$CWD" || "$CWD" == "." ]]; then
  exit 0
fi

# Case-sensitive INVARIANTS.md existence check.
# Reuses the same pattern as check-invariants.sh to avoid matching
# lowercase invariants.md on case-insensitive filesystems (macOS APFS).
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

# Parse CONCEPT verify commands from an INVARIANTS.md file.
# Looks for ## CONCEPT-NNN: headings and their **Verify:** lines.
# Returns: "CONCEPT-ID|command" pairs, one per line.
# Ignores INV-NNN headings — those are handled by check-invariants.sh.
parse_concepts() {
  local file="$1"
  local current_id=""

  while IFS= read -r line; do
    # Match concept heading: ## CONCEPT-NNN: description
    if [[ "$line" =~ ^##[[:space:]]+(CONCEPT-[0-9]+): ]]; then
      current_id="${BASH_REMATCH[1]}"
    fi

    # Reset current_id if we hit an INV heading (don't capture INV verify commands)
    if [[ "$line" =~ ^##[[:space:]]+(INV-[0-9]+): ]]; then
      current_id=""
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
  # Parse concepts — if parsing fails, warn but don't block
  PARSED=$(parse_concepts "$inv_file" 2>/dev/null)
  if [[ $? -ne 0 ]]; then
    echo "WARNING: Could not parse ${inv_file}, skipping" >&2
    continue
  fi

  while IFS='|' read -r concept_id verify_cmd; do
    # Skip empty lines
    [[ -z "$concept_id" || -z "$verify_cmd" ]] && continue

    # Run the verify command from the project root.
    RESULT=$(cd "$CWD" && eval "$verify_cmd" 2>/dev/null) || true

    # Non-empty output = violation found
    if [[ -n "$RESULT" ]]; then
      VIOLATIONS+=("${concept_id}")
      echo "CONCEPT VIOLATION [${concept_id}]: Verify command found violations:" >&2
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
  echo "BLOCKED: ${#VIOLATIONS[@]} concept(s) violated: ${VIOLATIONS[*]}" >&2
  echo "Fix the violations or add '# concept-exempt: CONCEPT-NNN' to exempt specific lines." >&2
  exit 2
fi

exit 0
