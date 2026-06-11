#!/bin/bash
# hooks/check-baseline-schema.sh
#
# PostToolUse hook for Edit|Write operations (F-2026-06-10 brownfield
# architecture baseline; design.md API Contract 3).
#
# Validates that an architecture-baseline.yaml write conforms to the canonical
# v1 schema owned by scripts/baseline.py BEFORE the malformed file can poison
# downstream consumers (the /build three-state gate keys on baseline.py status;
# a malformed baseline there is an infrastructure STOP). Closing the gap at
# write time keeps the file honest at the source.
#
# Trigger: PostToolUse on Edit or Write where the target path ends in
# `architecture-baseline.yaml` or `seam-map.yaml`.
#
# Payload-parse posture — FAIL CLOSED (deliberate, per the Codex lesson):
#   This is the WRITE-TIME schema guard. check-value-hypothesis-schema.sh
#   parses with `|| exit 0` (fail OPEN), which the audit flagged: under Codex
#   apply_patch payloads a parse miss silently neutered the blocking gate for
#   the exact drift it was built to stop. This hook uses `|| exit 2` instead —
#   if we cannot even read what was written, we BLOCK rather than wave it
#   through. (design.md API Contract 3 + Technical Constraints.)
#
# Validator dispatch by filename:
#   architecture-baseline.yaml → scripts/baseline.py validate <path>
#   seam-map.yaml              → recognized as in-scope, but baseline.py ships
#       no seam-map validator in this feature (Contract 1 CLI table has no
#       validate-seam subcommand; task 003 adds sync-seams, not validation).
#       Routing a valid seam-map through the architecture-baseline `validate`
#       would FALSE-BLOCK every legitimate seam-map write (it lacks status /
#       claims / inventory / rules) — a cry-wolf gate. So seam-map.yaml
#       degrades to exit 0 here, forward-compatible: when a `validate-seam`
#       subcommand lands, wire it into the dispatch below.
#
# Exit codes:
#   0 = allow (schema-valid; not a baseline file; validator absent; or
#       seam-map degrade)
#   2 = block (schema-invalid architecture-baseline, OR payload unparseable)

INPUT=$(cat)

# ── Payload parse — FAIL CLOSED on parse error (|| exit 2) ───────────────────
# Codex apply_patch payloads carry the path in tool_input.command, not
# tool_input.file_path; the normalizer extracts both Claude and Codex shapes.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD_HELPER="${HOOK_DIR}/helpers/hook_payload.py"
EDITED_FILES=$(printf '%s' "$INPUT" | python3 "$PAYLOAD_HELPER" files) || exit 2
CWD=$(printf '%s' "$INPUT" | python3 "$PAYLOAD_HELPER" cwd) || CWD="."
[[ -z "$CWD" ]] && CWD="."

# Keep the first baseline / seam-map target among the edited files. The helper
# emits cwd-relative paths when the file is under cwd, so suffix-match is the
# robust test (mirrors check-value-hypothesis-schema.sh).
FILE_PATH=""
KIND=""
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  if [[ "$f" == *architecture-baseline.yaml ]]; then
    FILE_PATH="$f"; KIND="baseline"; break
  fi
  if [[ "$f" == *seam-map.yaml ]]; then
    FILE_PATH="$f"; KIND="seam-map"; break
  fi
done <<< "$EDITED_FILES"

# Allow when no in-scope file is among the edited files.
if [[ -z "$FILE_PATH" ]]; then exit 0; fi

# Resolve to absolute (helper returns cwd-relative for under-cwd paths).
if [[ "$FILE_PATH" != /* ]]; then
  FILE_PATH="${CWD}/${FILE_PATH}"
fi

# Security: reject path traversal (directory-traversal defense, mirrors the
# value-hypothesis hook and design.md Security Considerations).
if [[ "$FILE_PATH" == *..* ]]; then exit 0; fi

# Skip if the file does not exist (Edit can no-op; nothing to validate).
if [[ ! -f "$FILE_PATH" ]]; then exit 0; fi

# seam-map.yaml: in-scope but no validator exists in this feature. Degrade to
# allow rather than false-block via the architecture-baseline schema.
if [[ "$KIND" == "seam-map" ]]; then exit 0; fi

# ── Locate scripts/baseline.py: CWD-first, then install-dir sibling ──────────
# Prefer the target project's own checkout (running inside an installed env or
# inside etc itself); fall back to ../scripts from this hook (install dir).
# Works under any --target-dir.
_ETC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR=""
if [[ -f "${CWD}/scripts/baseline.py" ]]; then
  VALIDATOR="${CWD}/scripts/baseline.py"
elif [[ -f "${_ETC_DIR}/scripts/baseline.py" ]]; then
  VALIDATOR="${_ETC_DIR}/scripts/baseline.py"
fi

# No validator found → allow (graceful degrade; not every project has etc).
if [[ -z "$VALIDATOR" ]]; then exit 0; fi

# ── Run the validator ────────────────────────────────────────────────────────
# baseline.py validate: 0 = valid, 1 = missing/unreadable (could-not-evaluate),
# 2 = schema violation (stderr names the offending fields). We only BLOCK on a
# genuine schema violation (2); an evaluation failure (1) degrades to allow so
# the gate never trips on its own IO trouble.
OUTPUT=$(python3 "$VALIDATOR" validate "$FILE_PATH" 2>&1)
STATUS=$?

if [[ $STATUS -ne 2 ]]; then
  exit 0
fi

# Schema-invalid architecture-baseline. Block with the copy-pasteable schema.
cat >&2 <<EOF
[check-baseline-schema] $FILE_PATH does not conform to the canonical v1
architecture-baseline schema (owned by scripts/baseline.py).

Validator output:
  $OUTPUT

Required top-level fields (design.md Data Model):
  schema_version: 1
  status: unratified                # closed enum: unratified | ratified
  confidence:
    score: low                      # closed enum: low | medium | high
    inputs: {}                      # documented inputs; never bare
  inventory: []                     # DISCOVER output: normative artifacts
  claims: []                        # VERIFY output: claim ledger
                                    #   each claim.classification is one of:
                                    #   VERIFIED | STALE | ASPIRATIONAL | CONTRADICTED
  rules: []                         # ENFORCE input; /rule-sweep appends here
  seams: []                         # per-repo mirror of the workspace seam map

Set only on ratification (both, or neither):
  ratified_by: <name>               # non-null iff status: ratified
  ratified_at: <ISO-8601>           # non-null iff status: ratified

Optional (RATIFY output): exemplars, do_not_copy.

Reference: scripts/baseline.py (REQUIRED_FIELDS / validate_schema) and
.etc_sdlc/architecture-baseline.yaml.

Do not hand-edit the baseline format. Drive it through
'/init-project --phase=baseline' (init / ratify) or 'baseline.py append-rule'.
EOF
exit 2
