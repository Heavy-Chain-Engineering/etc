#!/bin/bash
# hooks/check-seam-evidence.sh
#
# Verify-phase hook for integration seam evidence.
# Parses SEAMS.md from the project root, checks evidence at the declared
# level (L1/L2/L3) for each seam entry, and blocks if any check fails.
#
# This hook runs at the Stop event (verify phase), not per-edit.
# It is structural — it checks that test files exist and contain expected
# markers/imports, never executes the tests.
#
# Exit codes:
#   0 = all seam evidence checks pass (or no SEAMS.md / no entries)
#   2 = one or more evidence checks failed

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# If we can't determine the project directory, allow the operation
if [[ -z "$CWD" || "$CWD" == "." ]]; then
  exit 0
fi

# Case-sensitive SEAMS.md existence check (macOS APFS is case-insensitive)
has_seams_file() {
  local dir="$1"
  [[ -d "$dir" ]] || return 1
  ls "$dir" 2>/dev/null | grep -qE '^SEAMS\.md$'
}

SEAMS_FILE="${CWD}/SEAMS.md"

if ! has_seams_file "$CWD"; then
  echo "No SEAMS.md found -- seam evidence checks skipped" >&2
  exit 0
fi

# Safety valve: limit number of entries to prevent DoS
MAX_ENTRIES=200
ENTRY_COUNT=0

# Parse SEAMS.md and extract seam entries.
# Output format: SEAM_ID|PRODUCER|CONSUMER|TEST_PATH|EVIDENCE_LEVEL
# One line per fully-parsed entry.
parse_seams() {
  local file="$1"
  local current_id=""
  local producer=""
  local consumer=""
  local test_path=""
  local evidence=""
  local entry_count=0

  emit_entry() {
    if [[ -n "$current_id" && -n "$producer" && -n "$consumer" && -n "$test_path" && -n "$evidence" ]]; then
      echo "${current_id}|${producer}|${consumer}|${test_path}|${evidence}"
    elif [[ -n "$current_id" ]]; then
      # Missing required fields — warn but don't fail
      local missing=""
      [[ -z "$producer" ]] && missing="${missing} Producer"
      [[ -z "$consumer" ]] && missing="${missing} Consumer"
      [[ -z "$test_path" ]] && missing="${missing} 'Integration test'"
      [[ -z "$evidence" ]] && missing="${missing} 'Evidence level'"
      echo "WARNING: ${current_id}: missing required field(s):${missing} -- skipping" >&2
    fi
  }

  while IFS= read -r line; do
    # Match seam heading: ## SEAM-NNN: or ## SEAM-DEV-NNN:
    if [[ "$line" =~ ^##[[:space:]]+(SEAM(-DEV)?-[0-9]+):[[:space:]]* ]]; then
      # Emit previous entry before starting new one
      emit_entry
      current_id="${BASH_REMATCH[1]}"
      producer=""
      consumer=""
      test_path=""
      evidence=""
      entry_count=$((entry_count + 1))
      if [[ $entry_count -gt $MAX_ENTRIES ]]; then
        echo "WARNING: SEAMS.md has more than ${MAX_ENTRIES} entries -- checking first ${MAX_ENTRIES} only" >&2
        break
      fi
    fi

    # Only parse field lines when inside a seam entry
    [[ -z "$current_id" ]] && continue

    # Match field lines
    if [[ "$line" =~ \*\*Producer:\*\*[[:space:]]*(.*) ]]; then
      producer="${BASH_REMATCH[1]}"
      # Trim trailing whitespace
      producer="${producer%"${producer##*[![:space:]]}"}"
    fi
    if [[ "$line" =~ \*\*Consumer:\*\*[[:space:]]*(.*) ]]; then
      consumer="${BASH_REMATCH[1]}"
      consumer="${consumer%"${consumer##*[![:space:]]}"}"
    fi
    if [[ "$line" =~ \*\*Integration\ test:\*\*[[:space:]]*(.*) ]]; then
      test_path="${BASH_REMATCH[1]}"
      test_path="${test_path%"${test_path##*[![:space:]]}"}"
    fi
    if [[ "$line" =~ \*\*Evidence\ level:\*\*[[:space:]]*(L[0-9]+) ]]; then
      evidence="${BASH_REMATCH[1]}"
    fi
  done < "$file"

  # Emit the last entry
  emit_entry
}

# Convert a directory path to a Python package name.
# Strips src/ prefix, strips trailing slashes, converts / to .
# Examples:
#   src/venlink/iam/  -> venlink.iam
#   src/venlink/relationships/models/ -> venlink.relationships.models
#   tests/fixtures/compliance_data.py -> tests.fixtures.compliance_data
path_to_package() {
  local path="$1"
  # Strip trailing slash
  path="${path%/}"
  # Strip .py extension if present
  path="${path%.py}"
  # Strip src/ prefix
  path="${path#src/}"
  # Convert / to .
  echo "${path//\//.}"
}

# Check L1 evidence: file exists + integration marker
check_l1() {
  local seam_id="$1"
  local test_path="$2"
  local full_path="${CWD}/${test_path}"
  local errors=""

  # Resolve and verify path is under project root
  if [[ -f "$full_path" ]]; then
    local resolved
    resolved=$(realpath "$full_path" 2>/dev/null)
    if [[ "$resolved" != "${CWD}"* ]]; then
      errors="${seam_id}: test file path traversal detected (resolves outside project root)"
      echo "$errors"
      return
    fi
  else
    errors="${seam_id}: test file not found: ${test_path}"
    echo "$errors"
    return
  fi

  # Check for @pytest.mark.integration or pytestmark assignment
  if ! grep -qE '(@pytest\.mark\.integration|pytestmark\s*=.*pytest\.mark\.integration)' "$full_path" 2>/dev/null; then
    errors="${seam_id}: test file exists but has no @pytest.mark.integration marker"
    echo "$errors"
    return
  fi
}

# Check L2 evidence: L1 + imports from both producer and consumer
check_l2() {
  local seam_id="$1"
  local test_path="$2"
  local producer="$3"
  local consumer="$4"

  # Run L1 first
  local l1_errors
  l1_errors=$(check_l1 "$seam_id" "$test_path")
  if [[ -n "$l1_errors" ]]; then
    echo "$l1_errors"
    return
  fi

  local full_path="${CWD}/${test_path}"
  local producer_pkg
  local consumer_pkg
  producer_pkg=$(path_to_package "$producer")
  consumer_pkg=$(path_to_package "$consumer")

  # Check for producer import (from pkg or import pkg)
  if ! grep -qE "(from ${producer_pkg}[. ]|import ${producer_pkg})" "$full_path" 2>/dev/null; then
    echo "${seam_id}: test file missing import from producer package '${producer_pkg}'"
  fi

  # Check for consumer import
  if ! grep -qE "(from ${consumer_pkg}[. ]|import ${consumer_pkg})" "$full_path" 2>/dev/null; then
    echo "${seam_id}: test file missing import from consumer package '${consumer_pkg}'"
  fi
}

# Check L3 evidence: L2 + L3-real marker + no mocks of producer/consumer
check_l3() {
  local seam_id="$1"
  local test_path="$2"
  local producer="$3"
  local consumer="$4"

  # Run L2 first
  local l2_errors
  l2_errors=$(check_l2 "$seam_id" "$test_path" "$producer" "$consumer")
  if [[ -n "$l2_errors" ]]; then
    echo "$l2_errors"
    return
  fi

  local full_path="${CWD}/${test_path}"
  local producer_pkg
  local consumer_pkg
  producer_pkg=$(path_to_package "$producer")
  consumer_pkg=$(path_to_package "$consumer")

  # Check for L3-real marker on its own line
  if ! grep -qE '^\s*# seam-evidence: L3-real\s*$' "$full_path" 2>/dev/null; then
    echo "${seam_id}: test file missing '# seam-evidence: L3-real' marker"
  fi

  # Check for mocks targeting producer package
  local mock_line
  mock_line=$(grep -nE "(mock\.patch.*${producer_pkg}|@patch.*${producer_pkg}|MagicMock.*${producer_pkg}|monkeypatch\.setattr.*${producer_pkg})" "$full_path" 2>/dev/null | head -1)
  if [[ -n "$mock_line" ]]; then
    echo "${seam_id}: L3 violation -- producer package '${producer_pkg}' is mocked at line ${mock_line}"
  fi

  # Check for mocks targeting consumer package
  mock_line=$(grep -nE "(mock\.patch.*${consumer_pkg}|@patch.*${consumer_pkg}|MagicMock.*${consumer_pkg}|monkeypatch\.setattr.*${consumer_pkg})" "$full_path" 2>/dev/null | head -1)
  if [[ -n "$mock_line" ]]; then
    echo "${seam_id}: L3 violation -- consumer package '${consumer_pkg}' is mocked at line ${mock_line}"
  fi
}

# Parse entries — if parsing fails, warn but don't block
PARSED=$(parse_seams "$SEAMS_FILE" 2>"${CWD}/.seam-parse-warnings.tmp")
PARSE_WARNINGS=$(cat "${CWD}/.seam-parse-warnings.tmp" 2>/dev/null)
rm -f "${CWD}/.seam-parse-warnings.tmp"

# Emit parse warnings to stderr
if [[ -n "$PARSE_WARNINGS" ]]; then
  echo "$PARSE_WARNINGS" >&2
fi

# Check if there are any entries
if [[ -z "$PARSED" ]]; then
  echo "SEAMS.md found but contains no seam entries" >&2
  exit 0
fi

# Track all failures
FAILURES=()

while IFS='|' read -r seam_id producer consumer test_path evidence; do
  # Skip empty lines
  [[ -z "$seam_id" ]] && continue

  case "$evidence" in
    L1)
      errors=$(check_l1 "$seam_id" "$test_path")
      ;;
    L2)
      errors=$(check_l2 "$seam_id" "$test_path" "$producer" "$consumer")
      ;;
    L3)
      errors=$(check_l3 "$seam_id" "$test_path" "$producer" "$consumer")
      ;;
    *)
      echo "WARNING: Unknown evidence level '${evidence}' for ${seam_id} -- skipping" >&2
      continue
      ;;
  esac

  if [[ -n "$errors" ]]; then
    while IFS= read -r err_line; do
      [[ -n "$err_line" ]] && FAILURES+=("$err_line")
    done <<< "$errors"
  fi
done <<< "$PARSED"

if [[ ${#FAILURES[@]} -gt 0 ]]; then
  echo "" >&2
  echo "SEAM EVIDENCE FAILURES:" >&2
  for failure in "${FAILURES[@]}"; do
    echo "  - ${failure}" >&2
  done
  echo "" >&2
  # Count unique seam IDs in failures
  FAILED_SEAMS=()
  for failure in "${FAILURES[@]}"; do
    sid="${failure%%:*}"
    # Check if already tracked
    found=false
    for existing in "${FAILED_SEAMS[@]}"; do
      if [[ "$existing" == "$sid" ]]; then
        found=true
        break
      fi
    done
    if [[ "$found" == false ]]; then
      FAILED_SEAMS+=("$sid")
    fi
  done
  echo "BLOCKED: ${#FAILED_SEAMS[@]} seam(s) failed evidence checks: ${FAILED_SEAMS[*]}" >&2
  exit 2
fi

exit 0
