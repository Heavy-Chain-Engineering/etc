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

# Payload parsing goes through the Codex-aware normalizer, NOT raw jq:
# raw `.tool_input.file_path` is empty under Codex apply_patch payloads,
# which made this BLOCKING gate silently fail open for the exact
# schema-drift it was built to stop (audit init 8).
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD_HELPER="${HOOK_DIR}/helpers/hook_payload.py"
EDITED_FILES=$(printf '%s' "$INPUT" | python3 "$PAYLOAD_HELPER" files) || exit 0
CWD=$(printf '%s' "$INPUT" | python3 "$PAYLOAD_HELPER" cwd) || CWD="."
[[ -z "$CWD" ]] && CWD="."

# Keep only value-hypothesis.yaml targets (a payload can carry several files)
FILE_PATH=""
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  [[ "$f" == *value-hypothesis.yaml ]] && FILE_PATH="$f" && break
done <<< "$EDITED_FILES"

# Allow when no value-hypothesis.yaml is among the edited files
if [[ -z "$FILE_PATH" ]]; then exit 0; fi

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
