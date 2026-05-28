#!/bin/bash
# hooks/check-completion-discipline.sh
#
# Stop hook — enforces standards/process/completion-discipline.md.
#
# Sequences two checks that were previously parallel and racing:
#
#   Step 1. If .tdd-dirty is present, run the CI gate inline (pytest +
#           mypy + ruff + invariants). On pass, clear .tdd-dirty. On
#           fail, block with the CI output.
#
#   Step 2. If any task in .etc_sdlc/features/*/tasks/*.yaml has
#           status: in_progress, block — work is mid-flight.
#
# If both steps pass, allow the stop silently.
#
# This hook is language-agnostic — it does NOT regex on quit-phrases.
# The model can phrase its stop however it wants; what matters is
# whether the state of work is finished or formally handed off.
#
# History: this hook absorbs the previous ci-gate.sh Stop hook. They
# were peers under the same Stop event and fired in parallel, racing
# to check and clear the .tdd-dirty marker. Merging the sequence into
# a single hook makes the order deterministic.
#
# Exit codes:
#   0 = allow stop (no unfinished-work signals)
#   1 = block stop (CI failed)
#   2 = block stop (task in_progress; stderr has remediation)

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."')

# Install-dir locator. The hook lives at <install_dir>/hooks/foo.sh, so
# ../scripts and ../standards are the install siblings regardless of
# target_dir (~/.claude default, ~/.claude-etc dual setup, etc.).
_ETC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# If we can't determine cwd, allow — we can't evaluate state without it.
if [[ -z "$CWD" || "$CWD" == "." ]]; then
  exit 0
fi

# ═══════════════════════════════════════════════════════════════════════
# Step 1.5: Residual diagnostic-dismissal scan (F021 AC-011, Stop side)
#
# Scans the FULL conversation transcript (from transcript_path in hook
# input JSON) for <new-diagnostics> system reminders that lack a
# subsequent evidence block within DIAGNOSTIC_INVESTIGATION_TURNS
# (default 5, env-overrideable) turns AFTER the reminder.
#
# Emits one Pattern B stderr warning PER residual missing-evidence
# pattern. NEVER modifies the exit code — this is a warning-only
# residual sweep. The structural block lives at Step 6c (ADR-F021-005).
#
# Security:
#   - Rejects transcript_path containing ".." (path traversal).
#   - Invokes python3 via argv list (no shell-string expansion of
#     user-supplied content on the command line) per design.md §Security.
#   - Read-only transcript access.
#
# Compatibility: POSIX sh / bash 3.2+ safe. All JSONL parsing,
# window slicing, and evidence validation are delegated to Python
# (avoiding bash 3 vs 4 mapfile incompatibility on macOS).
# ═══════════════════════════════════════════════════════════════════════

# ── Extract transcript_path from hook input JSON ──────────────────────
DIAG_TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)

# ── Locate scripts/diagnostic_evidence.py ────────────────────────────
# Resolution order: (1) $CWD/scripts/, (2) hook's parent directory/scripts/
DIAG_HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
DIAG_REPO_ROOT="$(dirname "$DIAG_HOOK_DIR")"
DIAG_MODULE_PATH=""
if [[ -f "${CWD}/scripts/diagnostic_evidence.py" ]]; then
  DIAG_MODULE_PATH="${CWD}/scripts/diagnostic_evidence.py"
elif [[ -f "${DIAG_REPO_ROOT}/scripts/diagnostic_evidence.py" ]]; then
  DIAG_MODULE_PATH="${DIAG_REPO_ROOT}/scripts/diagnostic_evidence.py"
fi

# ── Sanitize DIAGNOSTIC_INVESTIGATION_TURNS ──────────────────────────
# Accept only a plain non-negative integer; fall back to default 5.
_DIAG_TURNS_RAW="${DIAGNOSTIC_INVESTIGATION_TURNS:-5}"
if [[ "$_DIAG_TURNS_RAW" =~ ^[0-9]+$ ]]; then
  DIAG_WINDOW="$_DIAG_TURNS_RAW"
else
  DIAG_WINDOW=5
fi

# Only attempt scan if we have all prerequisites.
if [[ -n "$DIAG_TRANSCRIPT" ]] \
  && [[ "$DIAG_TRANSCRIPT" != *".."* ]] \
  && [[ -f "$(realpath "$DIAG_TRANSCRIPT" 2>/dev/null || echo '')" ]] \
  && command -v python3 >/dev/null 2>&1 \
  && [[ -n "$DIAG_MODULE_PATH" ]]; then

  # Canonicalize path (security: no traversal).
  DIAG_TRANSCRIPT_REAL=$(realpath "$DIAG_TRANSCRIPT" 2>/dev/null)

  # ── Delegate full-transcript scan to Python ───────────────────────────
  # Python handles: JSONL parsing, window per-reminder forward-scan,
  # evidence validation via validate_block, audit-log emission via
  # emit_event, and WARN: signal output.
  #
  # Output protocol: each stdout line is one of:
  #   WARN:<turn_index>   — emit Pattern B stderr warning for that turn.
  # Audit-log rows are written inside Python directly (no shell roundtrip).
  DIAG_SCAN_OUTPUT=$(python3 -c "
import sys
import json
import importlib.util
import pathlib

transcript_path = sys.argv[1]
cwd             = pathlib.Path(sys.argv[2])
window          = int(sys.argv[3])
module_path     = pathlib.Path(sys.argv[4])

# Load diagnostic_evidence module.
spec = importlib.util.spec_from_file_location('diagnostic_evidence', module_path)
mod  = importlib.util.module_from_spec(spec)
sys.modules['diagnostic_evidence'] = mod
spec.loader.exec_module(mod)

# Resolve feature_id (best-effort; None when unresolvable).
feature_id = None
active_dir = cwd / '.etc_sdlc' / 'features' / 'active'
if active_dir.is_dir():
    candidates = sorted(
        d.name for d in active_dir.iterdir()
        if d.is_dir() and d.name.startswith('F')
    )
    if candidates:
        feature_id = candidates[-1]

# Read FULL transcript JSONL; skip malformed lines (graceful degradation).
entries = []
try:
    with open(transcript_path, encoding='utf-8') as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entries.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
except OSError:
    sys.exit(0)

total = len(entries)
if total == 0:
    sys.exit(0)

def _extract_text(content):
    '''Flatten content (string or list of blocks) to a plain string.'''
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get('text', '') or block.get('content', '')))
            elif isinstance(block, str):
                parts.append(block)
        return '\n'.join(parts)
    return str(content)

# Scan EVERY entry in the FULL transcript (full-transcript residual sweep,
# unlike the PreToolUse hook which scans only the last WINDOW entries).
for idx, entry in enumerate(entries):
    text = _extract_text(entry.get('content', ''))
    if '<new-diagnostics>' not in text:
        continue

    # Reminder found at idx. Collect next `window` turns for the corpus.
    subsequent_parts = [
        _extract_text(e.get('content', ''))
        for e in entries[idx + 1: idx + 1 + window]
    ]
    subsequent_text = '\n'.join(subsequent_parts)

    result = mod.validate_block(subsequent_text)

    if result.valid:
        evidence_type = (result.parsed or {}).get('evidence_type', None)
        payload = {
            'feature_id': feature_id,
            'tool_name': 'stop-hook',
            'evidence_type': evidence_type,
            'decision': 'accepted',
        }
        try:
            mod.emit_event('diagnostic_dismissal_with_evidence', payload, cwd)
        except Exception as exc:
            print(f'check-completion-discipline step-1.5: audit-log write failed: {exc}',
                  file=sys.stderr)
    else:
        payload = {
            'feature_id': feature_id,
            'tool_name': 'stop-hook',
            'evidence_type': None,
            'decision': 'unresolved',
            'reason': 'investigation_window_incomplete',
        }
        try:
            mod.emit_event('diagnostic_dismissal_missing_evidence', payload, cwd)
        except Exception as exc:
            print(f'check-completion-discipline step-1.5: audit-log write failed: {exc}',
                  file=sys.stderr)
        # Signal the bash layer to emit the Pattern B warning.
        print(f'WARN:{idx}')
" \
    "$DIAG_TRANSCRIPT_REAL" "$CWD" "$DIAG_WINDOW" "$DIAG_MODULE_PATH" \
    2>/dev/null)
  DIAG_SCAN_EXIT=$?

  if [[ $DIAG_SCAN_EXIT -ne 0 ]]; then
    # Python scan failed — degrade gracefully; Step 1.5 never blocks.
    true
  else
    # ── Process WARN signals: emit Pattern B stderr warning ───────────────
    # Pattern B format (per spec AC-011):
    #   \n\n---\n\n**▶ Note:** Residual diagnostic dismissal without
    #   evidence (see standards/process/diagnostic-discipline.md).
    #   Tool: <tool_name>. Turn: <turn>.
    while IFS= read -r diag_signal; do
      [[ -z "$diag_signal" ]] && continue
      if [[ "$diag_signal" == WARN:* ]]; then
        WARN_TURN="${diag_signal#WARN:}"
        printf '\n\n---\n\n**▶ Note:** Residual diagnostic dismissal without evidence (see standards/process/diagnostic-discipline.md). Tool: stop-hook. Turn: %s. missing evidence: no parseable evidence block found within %d turns after <new-diagnostics> reminder.\n' \
          "$WARN_TURN" "$DIAG_WINDOW" >&2
      fi
    done <<< "$DIAG_SCAN_OUTPUT"
  fi
fi
# Step 1.5 ends here. Exit code is NOT modified.

# ═══════════════════════════════════════════════════════════════════════
# Profile-dispatch front-end (F022 generalization — F020-ADR-005 pattern)
#
# Mirrors hooks/verify-green.sh dispatch shape.
# For each active profile P, invokes:
#   standards/code/profiles/<P>/check-completion-discipline.sh
# No-profile path: stderr WARN + exit 0 per F020-ADR-003.
# BR-009: emits one profile_dispatch JSONL row per profile to
#   .etc_sdlc/efficiency/turn-events.jsonl (best-effort; write failure
#   is silent and NEVER changes the exit code).
# ═══════════════════════════════════════════════════════════════════════

_PROFILE_HOOK_NAME="check-completion-discipline"
_LOCK="${CWD}/.etc_sdlc/profiles.lock"

_emit_profile_dispatch_event() {
  # Best-effort JSONL append. Args: $1=profiles_json $2=outcome
  local log_dir="${CWD}/.etc_sdlc/efficiency"
  local log_file="${log_dir}/turn-events.jsonl"
  local profiles_json="$1"
  local outcome="$2"
  # Use Python stdlib for POSIX-atomic append and ISO-8601 timestamp.
  python3 - "$log_file" "$log_dir" "$profiles_json" "$outcome" \
    "$_PROFILE_HOOK_NAME" 2>/dev/null <<'PYEOF'
import sys, json, pathlib, datetime
log_file  = pathlib.Path(sys.argv[1])
log_dir   = pathlib.Path(sys.argv[2])
profiles_raw = sys.argv[3]
outcome   = sys.argv[4]
hook_name = sys.argv[5]
try:
    profiles = json.loads(profiles_raw)
except Exception:
    profiles = [p.strip() for p in profiles_raw.split(',') if p.strip()]
try:
    log_dir.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event_type": "profile_dispatch",
        "hook": hook_name,
        "profiles": profiles,
        "outcome": outcome,
    }
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
except Exception:
    pass
PYEOF
}

if [[ ! -f "$_LOCK" ]]; then
  echo "[${_PROFILE_HOOK_NAME}] WARN: no profiles.lock found at ${_LOCK}; skipping profile dispatch." >&2
elif [[ $(grep -c '^[a-z]' "$_LOCK" 2>/dev/null || echo 0) -eq 0 ]]; then
  echo "[${_PROFILE_HOOK_NAME}] WARN: profiles.lock is empty; skipping profile dispatch." >&2
else
  _PROFILES_JSON="["
  _FIRST=1
  while IFS= read -r _PROFILE; do
    _PROFILE=$(echo "$_PROFILE" | tr -d '[:space:]')
    [[ -z "$_PROFILE" ]] && continue
    [[ $_FIRST -eq 0 ]] && _PROFILES_JSON="${_PROFILES_JSON},"
    _PROFILES_JSON="${_PROFILES_JSON}\"${_PROFILE}\""
    _FIRST=0
  done < "$_LOCK"
  _PROFILES_JSON="${_PROFILES_JSON}]"

  while IFS= read -r _PROFILE; do
    _PROFILE=$(echo "$_PROFILE" | tr -d '[:space:]')
    [[ -z "$_PROFILE" ]] && continue

    _GATE="${CWD}/standards/code/profiles/${_PROFILE}/${_PROFILE_HOOK_NAME}.sh"
    if [[ ! -f "$_GATE" ]]; then
      _GATE="${_ETC_DIR}/standards/code/profiles/${_PROFILE}/${_PROFILE_HOOK_NAME}.sh"
    fi

    if [[ -f "$_GATE" ]]; then
      echo "[${_PROFILE_HOOK_NAME}] Running ${_PROFILE} profile..." >&2
      _GATE_OUTPUT=$(echo "$INPUT" | bash "$_GATE" 2>&1)
      _GATE_EXIT=$?
      echo "$_GATE_OUTPUT" >&2
      if [[ $_GATE_EXIT -ne 0 ]]; then
        _emit_profile_dispatch_event "$_PROFILES_JSON" "fail"
        exit $_GATE_EXIT
      fi
    else
      echo "[${_PROFILE_HOOK_NAME}] WARN: profile '${_PROFILE}' has no ${_PROFILE_HOOK_NAME}.sh (looked under ${CWD}/standards/code/profiles/${_PROFILE}/ and ${_ETC_DIR}/standards/code/profiles/${_PROFILE}/)" >&2
    fi
  done < "$_LOCK"

  _emit_profile_dispatch_event "$_PROFILES_JSON" "pass"
fi

# ═══════════════════════════════════════════════════════════════════════
# Step 1: CI gate (run when .tdd-dirty is present)
# ═══════════════════════════════════════════════════════════════════════

DIRTY="${CWD}/.tdd-dirty"

if [[ -f "$DIRTY" ]]; then
  FAILURES=()

  # Discover Python source directories that actually exist.
  PY_DIRS=()
  for d in src tests hooks scripts platform/src; do
    [[ -d "${CWD}/${d}" ]] && PY_DIRS+=("$d")
  done

  # Detect uv-managed Python projects so we invoke the repo's pinned
  # toolchain (pinned ruff, pinned pytest, project venv) instead of
  # whatever happens to be on $PATH. System ruff/pytest on a dev box can
  # lag behind the repo pins and produce false-positive gate failures
  # (e.g. system ruff refusing `target-version = "py314"`).
  if [[ -f "${CWD}/uv.lock" ]] || { [[ -f "${CWD}/pyproject.toml" ]] && grep -q '^\[tool\.uv\]' "${CWD}/pyproject.toml" 2>/dev/null; }; then
    PY_RUNNER=("uv" "run")
  else
    PY_RUNNER=()
  fi

  # Decide whether this directory is actually a Python project. Empty
  # `tests/` dirs (e.g. a frontend bootstrap that happens to create one)
  # used to weaponize the gate — pytest would find nothing, exit 5, and
  # block the stop event on a non-Python project.
  IS_PY_PROJECT=0
  if [[ -f "${CWD}/uv.lock" ]] || [[ -f "${CWD}/pytest.ini" ]] || [[ -f "${CWD}/setup.cfg" ]]; then
    IS_PY_PROJECT=1
  elif [[ -f "${CWD}/pyproject.toml" ]] && grep -Eq '^\[(project|tool\.poetry|tool\.pytest\.ini_options|tool\.uv)\]' "${CWD}/pyproject.toml" 2>/dev/null; then
    IS_PY_PROJECT=1
  fi

  # 1a. Test suite
  if [[ $IS_PY_PROJECT -eq 1 ]] && { [[ -d "${CWD}/tests" ]] || [[ -d "${CWD}/test" ]]; }; then
    TEST_OUTPUT=$(cd "$CWD" && "${PY_RUNNER[@]}" python3 -m pytest -q 2>&1)
    TEST_EXIT=$?
    if [[ $TEST_EXIT -ne 0 ]]; then
      FAILURES+=("TESTS FAILED (exit $TEST_EXIT)")
      echo "── pytest output ──" >&2
      echo "$TEST_OUTPUT" | tail -20 >&2
      echo "" >&2
    fi
  fi

  # 1b. Type checking (only if mypy is configured)
  if [[ -f "${CWD}/pyproject.toml" ]] && grep -q '\[tool\.mypy\]' "${CWD}/pyproject.toml" 2>/dev/null; then
    if [[ ${#PY_DIRS[@]} -gt 0 ]]; then
      MYPY_OUTPUT=$(cd "$CWD" && "${PY_RUNNER[@]}" python3 -m mypy "${PY_DIRS[@]}" 2>&1)
      MYPY_EXIT=$?
      if [[ $MYPY_EXIT -ne 0 ]]; then
        FAILURES+=("TYPE CHECK FAILED (exit $MYPY_EXIT)")
        echo "── mypy output ──" >&2
        echo "$MYPY_OUTPUT" | tail -10 >&2
        echo "" >&2
      fi
    fi
  fi

  # 1c. Linting (only if ruff is configured)
  if [[ -f "${CWD}/pyproject.toml" ]] && grep -q '\[tool\.ruff\]' "${CWD}/pyproject.toml" 2>/dev/null; then
    if [[ ${#PY_DIRS[@]} -gt 0 ]]; then
      RUFF_OUTPUT=$(cd "$CWD" && "${PY_RUNNER[@]}" ruff check "${PY_DIRS[@]}" 2>&1)
      RUFF_EXIT=$?
      if [[ $RUFF_EXIT -ne 0 ]]; then
        FAILURES+=("LINT FAILED (exit $RUFF_EXIT)")
        echo "── ruff output ──" >&2
        echo "$RUFF_OUTPUT" | tail -10 >&2
        echo "" >&2
      fi
    fi
  fi

  # 1d. Invariant verify commands
  INVARIANTS="${CWD}/INVARIANTS.md"
  if [[ -f "$INVARIANTS" ]]; then
    while IFS= read -r line; do
      if [[ "$line" =~ \*\*Verify:\*\*[[:space:]]*\`(.+)\` ]]; then
        CMD="${BASH_REMATCH[1]}"
        RESULT=$(cd "$CWD" && eval "$CMD" 2>/dev/null) || true
        if [[ -n "$RESULT" ]]; then
          FAILURES+=("INVARIANT VIOLATED")
          echo "── invariant violation ──" >&2
          echo "$RESULT" | head -5 >&2
          echo "" >&2
        fi
      fi
    done < "$INVARIANTS"
  fi

  # CI gate decision
  if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo "CI GATE FAILED: ${FAILURES[*]}" >&2
    echo "Fix the failures above before completing this task." >&2
    exit 1
  fi

  # All CI checks passed — clear the dirty marker
  rm -f "$DIRTY"
fi

# ═══════════════════════════════════════════════════════════════════════
# Step 2: in_progress task check
# ═══════════════════════════════════════════════════════════════════════

SIGNAL_INPROGRESS_COUNT=0
TASKS_GLOB="${CWD}/.etc_sdlc/features"
if [[ -d "$TASKS_GLOB" ]]; then
  # F009-lifecycle-gap fix: scan flat path AND active/ subdirectory.
  # The naive "$TASKS_GLOB"/*/tasks/*.yaml glob misses features under
  # active/, which is where the allocator places new in-flight work.
  # The shipped/ subdirectory is intentionally NOT scanned — shipped
  # features are done and shouldn't have in_progress tasks anyway.
  SIGNAL_INPROGRESS_COUNT=$(grep -rhE '^status:[[:space:]]*in_progress[[:space:]]*$' \
    "$TASKS_GLOB"/*/tasks/*.yaml \
    "$TASKS_GLOB"/active/*/tasks/*.yaml \
    2>/dev/null | wc -l | tr -d ' ')
fi

if [[ "$SIGNAL_INPROGRESS_COUNT" -eq 0 ]]; then
  # No unfinished-work signals; allow the stop.
  exit 0
fi

# ── Block with actionable message ───────────────────────────────────────

echo "" >&2
echo "COMPLETION DISCIPLINE: Unfinished work detected." >&2
echo "" >&2
echo "Signals:" >&2
echo "  - ${SIGNAL_INPROGRESS_COUNT} task(s) have status: in_progress" >&2
echo "" >&2
echo "You cannot stop the session while work is mid-flight." >&2
echo "Valid paths out (pick one):" >&2
echo "" >&2
echo "  1. Complete the work." >&2
echo "     - Update task status to 'completed' via:" >&2
echo "         python3 ${_ETC_DIR}/scripts/tasks.py set-status <id> completed" >&2
echo "" >&2
echo "  2. Formally escalate." >&2
echo "     - Produce an ## ESCALATION block per" >&2
echo "       standards/process/completion-discipline.md rule 2" >&2
echo "     - Mark affected task(s) escalated:" >&2
echo "         python3 ${_ETC_DIR}/scripts/tasks.py set-status <id> escalated" >&2
echo "" >&2
echo "  3. Formally block on an external dependency." >&2
echo "     - python3 ${_ETC_DIR}/scripts/tasks.py set-status <id> blocked" >&2
echo "" >&2
echo "You do not quit conversationally. See" >&2
echo "standards/process/completion-discipline.md for the full standard." >&2
echo "" >&2

exit 2
