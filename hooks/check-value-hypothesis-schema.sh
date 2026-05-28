#!/bin/bash
# hooks/check-value-hypothesis-schema.sh
#
# PostToolUse hook for Edit|Write operations.
# Validates that value-hypothesis.yaml files conform to the canonical v1
# schema (BR-005 / AC-004) defined by scripts/value_hypothesis.py.
#
# Why this exists: between F012 and F019 (2026-05-13..15) eight features
# shipped with an alternative who/what/why schema. .etc_sdlc/* is
# gitignored, so PR review never saw it. The canonical validator only ran
# at /metrics time. This hook closes the gap at write time so the drift
# can't recur.
#
# Trigger: PostToolUse on Edit or Write where the target path ends in
# `value-hypothesis.yaml`.
#
# Exit codes:
#   0 = allow (schema-valid, or path is not a value-hypothesis.yaml)
#   2 = block (schema-invalid)

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Allow when no file path or path is not a value-hypothesis.yaml
if [[ -z "$FILE_PATH" ]]; then exit 0; fi
if [[ "$FILE_PATH" != *value-hypothesis.yaml ]]; then exit 0; fi

# Resolve to absolute
if [[ "$FILE_PATH" != /* ]]; then
  FILE_PATH="${CWD}/${FILE_PATH}"
fi

# Security: reject traversal
if [[ "$FILE_PATH" == *..* ]]; then exit 0; fi

# Skip if file does not exist (Edit can no-op; nothing to validate)
if [[ ! -f "$FILE_PATH" ]]; then exit 0; fi

# Locate the validator. Prefer the local checkout's scripts/ when available
# (running inside etc itself); fall back to the install-dir sibling
# (../scripts from this hook). Works under any --target-dir.
_ETC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR=""
if [[ -f "${CWD}/scripts/value_hypothesis.py" ]]; then
  VALIDATOR="${CWD}/scripts/value_hypothesis.py"
elif [[ -f "${_ETC_DIR}/scripts/value_hypothesis.py" ]]; then
  VALIDATOR="${_ETC_DIR}/scripts/value_hypothesis.py"
fi

# If no validator found, allow (graceful degrade; not every project has etc)
if [[ -z "$VALIDATOR" ]]; then exit 0; fi

# Run the validator
OUTPUT=$(python3 "$VALIDATOR" validate "$FILE_PATH" 2>&1)
STATUS=$?

if [[ $STATUS -eq 0 ]]; then
  exit 0
fi

# Schema-invalid. Block with explanation.
cat >&2 <<EOF
[check-value-hypothesis-schema] $FILE_PATH does not conform to the canonical
v1 value-hypothesis schema (BR-005).

Validator output:
  $OUTPUT

Required top-level fields (BR-005 / AC-004):
  schema_version: 1
  feature_id: F<NNN>
  spec_author_role: <role>          # or legacy author_role for F001-F009
  who: <target user / cohort>
  current_cost: <baseline pain in human terms>
  predicted:
    metric: <measurable thing>
    direction: increase | decrease
    threshold: <numeric>
    window_days: <int>
  how_we_know: <measurement plan>
  status: pending
  validation:
    measured_at: null
    measured_value: null
    evidence: null

Reference: scripts/value_hypothesis.py (REQUIRED_FIELDS constant) and
skills/spec/SKILL.md (Step "Build the value-hypothesis dict").

If you intentionally need a different shape, /spec it first — do not
freelance the schema in a write.
EOF
exit 2
