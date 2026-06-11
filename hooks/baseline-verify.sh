#!/bin/bash
# hooks/baseline-verify.sh
#
# Architecture-baseline conformance dispatcher (ENFORCE stage,
# F-2026-06-10-brownfield-architecture-baseline).
#
# Conductor-invoked script (NOT a Stop hook — clone of runtime-verify.sh per
# ADR-004 + GA-A02). The conductor (/build wave gate, /rule-sweep post-sweep
# check) owns gate semantics; this dispatcher only RUNS the per-profile checkers
# and aggregates their per-rule verdicts. It mirrors hooks/runtime-verify.sh:
# repo-root anchoring via git rev-parse, iteration over .etc_sdlc/profiles.lock,
# and the install-dir sibling fallback for the per-profile script path.
#
# Contract (ADR-004 / design.md API Contracts §2), v1 additive-only:
#   stdin  : {"repo_root": <str>, "rule_ids": [<str>] | null, "cwd": <str>}
#            rule_ids == null (or absent) selects ALL mechanizable rules.
#   per-profile stdin  : {"repo_root": <str>, "rules": [{"rule_id","statement"}]}
#                        (thinned jq projection; JSON on stdin, never shell args)
#   per-profile stdout : {"results": [{"rule_id","status","evidence"}, ...]}
#                        status is the closed enum pass|fail|no-check.
#   stdout : {"results": [...]}  — every active profile's results aggregated.
#
# Rule materialization (layer-boundaries.md): bash never parses the baseline
# YAML. scripts/baseline.py is the SINGLE format owner; this dispatcher imports
# it (resolved CWD-first then install-dir sibling) to project the mechanizable,
# selected rules into the per-profile stdin. A missing/malformed baseline or an
# unresolvable baseline.py degrades to warn-and-skip with empty results.
#
# Warn-and-skip (bracketed stderr, non-fatal — F020-003 format):
#   - profiles.lock absent/empty
#   - a profile's baseline-verify.sh is missing
#   - the baseline file is missing/malformed, or baseline.py is unresolvable
#
# Per-profile time cap: default 600s, override via BASELINE_VERIFY_TIMEOUT.
# A profile exceeding the cap records each SELECTED rule_id as
# {status:"fail", evidence:"timeout >Ns"} and continues (synthetic fails).
#
# Unknown status normalization (AC-10 / design Contract Declarations):
#   any results[].status outside {pass,fail,no-check} is rewritten to "fail"
#   (fail-closed) before aggregation, with the original value preserved in
#   evidence. Verdicts live in JSON, never in the exit code.
#
# Exit codes:
#   0 = dispatched (ALWAYS, including every warn-and-skip / degrade path);
#       per-rule verdicts live in the aggregated `results`, not the exit code.

set -uo pipefail

# Per-profile time cap (seconds). Module constant; env-overridable.
BASELINE_VERIFY_TIMEOUT="${BASELINE_VERIFY_TIMEOUT:-600}"

INPUT=$(cat)
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // "."')

# repo_root precedence: explicit .repo_root, else git-toplevel from cwd, else cwd
# (mirrors runtime-verify's #48 anchor but honors the explicit field this
# contract carries).
EXPLICIT_ROOT=$(printf '%s' "$INPUT" | jq -r '.repo_root // empty')
if [ -n "$EXPLICIT_ROOT" ]; then
  PROJECT_ROOT="$EXPLICIT_ROOT"
else
  PROJECT_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || echo "$CWD")
fi

# etc install dir (this hook's grandparent): the sibling fallback for both the
# per-profile script and scripts/baseline.py.
ETC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Aggregated results array (JSON), built up across profiles.
AGGREGATE='[]'

emit() {
  echo "{\"results\": ${AGGREGATE}}"
}

# ── Materialize the selected mechanizable rules via baseline.py ─────────────
#
# baseline.py is the single owner of the baseline format (no bash YAML parse).
# Resolve it project-first then install-dir sibling, then have it emit the
# mechanizable rules matching the rule_ids selection (null = all) as a compact
# JSON array of {rule_id, statement}. Any failure → warn-and-skip empty.

resolve_baseline_py() {
  local p="${PROJECT_ROOT}/scripts/baseline.py"
  if [ ! -f "$p" ]; then
    p="${ETC_DIR}/scripts/baseline.py"
  fi
  printf '%s' "$p"
}

BASELINE_PY="$(resolve_baseline_py)"
if [ ! -f "$BASELINE_PY" ]; then
  echo "[baseline-verify] WARN: scripts/baseline.py not found (looked in project and ${ETC_DIR}); skipping." >&2
  emit
  exit 0
fi

# rule_ids as a JSON value ("null" when absent/null) handed to the projector.
RULE_IDS_JSON=$(printf '%s' "$INPUT" | jq -c '.rule_ids // null')

# The projector reads the baseline through baseline.load() (format owner),
# filters to mechanizable rules, applies the rule_ids selection, and prints a
# compact JSON array of {rule_id, statement} on stdout.
#
# Exit-code protocol (so the dispatcher can tell "baseline absent/malformed →
# warn-and-skip" from "baseline present, zero mechanizable rules → run, empty
# results"):
#   exit 0  + stdout JSON array  -> the baseline loaded; the array (possibly
#                                   empty) is the authoritative selected ruleset.
#   exit 3                       -> baseline absent / malformed / unloadable, or
#                                   the format owner could not be imported; the
#                                   dispatcher warn-and-skips.
RULES_JSON=$(
  REPO_ROOT="$PROJECT_ROOT" RULE_IDS_JSON="$RULE_IDS_JSON" \
  python3 - "$BASELINE_PY" <<'PY' 2>/dev/null
import json
import os
import sys
import importlib.util
from pathlib import Path

_DEGRADE = 3  # baseline absent / malformed / format owner unloadable

baseline_py = sys.argv[1]
spec = importlib.util.spec_from_file_location("baseline", baseline_py)
try:
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
except Exception:
    sys.exit(_DEGRADE)

repo_root = os.environ.get("REPO_ROOT", ".")
path = Path(repo_root) / mod.BASELINE_RELATIVE_PATH

try:
    data = mod.load(path)
except Exception:
    # Missing file, malformed YAML, or schema violation -> degrade.
    sys.exit(_DEGRADE)

if not data:
    # load() returns None for a future schema_version (warn-and-skip) -> degrade.
    sys.exit(_DEGRADE)

try:
    wanted = json.loads(os.environ.get("RULE_IDS_JSON", "null"))
except Exception:
    wanted = None
wanted_set = set(wanted) if isinstance(wanted, list) else None

out = []
for rule in data.get("rules", []):
    if not isinstance(rule, dict):
        continue
    if not rule.get("mechanizable", False):
        continue
    rid = rule.get("id")
    if rid is None:
        continue
    if wanted_set is not None and rid not in wanted_set:
        continue
    out.append({"rule_id": rid, "statement": str(rule.get("statement", ""))})

print(json.dumps(out))
PY
)
PROJECTOR_EXIT=$?
if [ "$PROJECTOR_EXIT" -ne 0 ]; then
  echo "[baseline-verify] WARN: no usable architecture-baseline at ${PROJECT_ROOT} (absent, malformed, or unloadable); skipping verification." >&2
  emit
  exit 0
fi
# Defensive: a zero exit must still carry a JSON array on stdout.
if ! printf '%s' "$RULES_JSON" | jq -e 'type == "array"' >/dev/null 2>&1; then
  echo "[baseline-verify] WARN: could not read mechanizable rules from baseline at ${PROJECT_ROOT}; skipping." >&2
  emit
  exit 0
fi

SELECTED_COUNT=$(printf '%s' "$RULES_JSON" | jq 'length')

# The thinned per-profile stdin contract (JSON on stdin, never shell args).
PROFILE_INPUT=$(jq -c -n --arg rr "$PROJECT_ROOT" --argjson rules "$RULES_JSON" \
  '{repo_root: $rr, rules: $rules}')

# ── profiles.lock iteration (parity with runtime-verify) ────────────────────

LOCK="${PROJECT_ROOT}/.etc_sdlc/profiles.lock"
if [ ! -f "$LOCK" ]; then
  echo "[baseline-verify] WARN: no profiles.lock found at ${LOCK}; skipping verification." >&2
  emit
  exit 0
fi

# Count active (lowercase-leading) profile lines. `grep -c` exits 1 with a "0"
# on stdout when nothing matches, which combined with `|| echo 0` would emit a
# two-line "0\n0" and break the integer test — so capture the count from a
# pipeline whose own exit status is ignored, then default an empty result to 0.
ACTIVE_COUNT=$(grep -c '^[a-z]' "$LOCK" 2>/dev/null; true)
ACTIVE_COUNT="${ACTIVE_COUNT:-0}"
if [ "$ACTIVE_COUNT" -eq 0 ] 2>/dev/null || [ -z "$ACTIVE_COUNT" ]; then
  echo "[baseline-verify] WARN: profiles.lock is empty; skipping verification." >&2
  emit
  exit 0
fi

# Resolve a profile's baseline-verify.sh, project-scope first then install-dir.
resolve_gate() {
  local profile="$1"
  local gate="${PROJECT_ROOT}/standards/code/profiles/${profile}/baseline-verify.sh"
  if [ ! -f "$gate" ]; then
    gate="${ETC_DIR}/standards/code/profiles/${profile}/baseline-verify.sh"
  fi
  printf '%s' "$gate"
}

# Build a fail/timeout results array for every SELECTED rule of a timed-out
# profile (synthetic fails — verdicts live in JSON).
timeout_results() {
  printf '%s' "$PROFILE_INPUT" | jq -c \
    --arg evidence "timeout >${BASELINE_VERIFY_TIMEOUT}s" \
    '[.rules[] | {rule_id: .rule_id, status: "fail", evidence: $evidence}]'
}

# Normalize a profile's results array: rewrite any status outside the closed
# enum {pass,fail,no-check} to "fail" (fail-closed, AC-10), preserving the
# original value in evidence so the audit trail survives.
normalize_results() {
  jq -c '
    map(
      .status as $s
      | if ($s | type == "string") and ((["pass","fail","no-check"] | index($s)) != null)
        then .
        else .status = "fail"
             | .evidence = ((.evidence // "") + " [normalized from unknown status: " + ($s | tostring) + "]")
        end
    )'
}

while IFS= read -r PROFILE; do
  PROFILE=$(printf '%s' "$PROFILE" | tr -d '[:space:]')
  [ -z "$PROFILE" ] && continue

  # Security: profile names from profiles.lock are attacker-influenced data and
  # are interpolated into the gate path (resolve_gate). Whitespace-stripping is
  # not enough — a `../../tmp/evil` entry would escape standards/code/profiles/.
  # Validate against the same strict identifier regex scripts/detect_profiles.py
  # uses (^[a-z][a-z0-9_-]*$); skip any non-conforming name before it is used.
  if ! [[ "$PROFILE" =~ ^[a-z][a-z0-9_-]*$ ]]; then
    echo "[baseline-verify] WARN: skipping malformed profile name '${PROFILE}'" >&2
    continue
  fi

  GATE="$(resolve_gate "$PROFILE")"
  if [ ! -f "$GATE" ]; then
    echo "[baseline-verify] WARN: profile '${PROFILE}' has no baseline-verify.sh at ${GATE}" >&2
    continue
  fi

  echo "[baseline-verify] Running ${PROFILE} profile over ${SELECTED_COUNT} rule(s) (cap ${BASELINE_VERIFY_TIMEOUT}s)..." >&2
  GATE_OUTPUT=$(printf '%s' "$PROFILE_INPUT" | timeout "${BASELINE_VERIFY_TIMEOUT}s" bash "$GATE" 2>/dev/null)
  GATE_EXIT=$?

  if [ "$GATE_EXIT" -eq 124 ]; then
    # timeout(1) returns 124 when the time cap is exceeded.
    echo "[baseline-verify] WARN: profile '${PROFILE}' exceeded ${BASELINE_VERIFY_TIMEOUT}s cap; recording fail." >&2
    PROFILE_RESULTS="$(timeout_results)"
  else
    # Read per-rule status from the profile's stdout, not its exit code.
    PROFILE_RESULTS=$(printf '%s' "$GATE_OUTPUT" | jq -c '.results // empty' 2>/dev/null)
    if [ -z "$PROFILE_RESULTS" ]; then
      echo "[baseline-verify] WARN: profile '${PROFILE}' produced no parseable results; skipping." >&2
      continue
    fi
    PROFILE_RESULTS=$(printf '%s' "$PROFILE_RESULTS" | normalize_results)
  fi

  AGGREGATE=$(jq -c -n --argjson a "$AGGREGATE" --argjson b "$PROFILE_RESULTS" '$a + $b')
done < "$LOCK"

emit
exit 0
