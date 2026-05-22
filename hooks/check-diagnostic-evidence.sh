#!/bin/bash
# hooks/check-diagnostic-evidence.sh
#
# F021 PreToolUse hook — Diagnostic-Dismissal Discipline (agent-discipline track).
#
# Reads the Claude Code PreToolUse JSON from stdin, extracts
# `transcript_path`, scans the last DIAGNOSTIC_INVESTIGATION_TURNS (default
# 5) entries backward for `<new-diagnostics>` system reminders, and for
# each reminder checks whether a subsequent evidence block exists in the
# turns that follow the reminder (within the same window).
#
# On missing evidence: emits Pattern B stderr warning (never blocks).
# On valid evidence:   emits diagnostic_dismissal_with_evidence to audit log.
#
# Exit codes:
#   0 always — never blocks. Degrades gracefully on every failure path.
#
# Security boundaries (design.md):
#   - Rejects transcript_path containing ".." (path traversal).
#   - Invokes python3 via argv list form (never shell-string concat).
#   - Read-only transcript access.
#
# Dependencies: bash, jq, python3 (with scripts/diagnostic_evidence.py
# importable from CWD or the hook's parent directory).

INPUT=$(cat)

# ── Extract fields from Claude Code PreToolUse JSON ───────────────────────
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
CWD=$(echo "$INPUT" | jq -r '.cwd // "."' 2>/dev/null)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"' 2>/dev/null)

# ── Validate DIAGNOSTIC_INVESTIGATION_TURNS ───────────────────────────────
# Sanitize: accept only a plain non-negative integer; fall back to 5.
[[ "${DIAGNOSTIC_INVESTIGATION_TURNS:-5}" =~ ^[0-9]+$ ]] \
  || DIAGNOSTIC_INVESTIGATION_TURNS=5
WINDOW="${DIAGNOSTIC_INVESTIGATION_TURNS:-5}"

# ── Graceful degradation: missing transcript_path ────────────────────────
if [[ -z "$TRANSCRIPT" ]]; then
  exit 0
fi

# ── Security: reject path traversal ──────────────────────────────────────
if [[ "$TRANSCRIPT" == *".."* ]]; then
  echo "check-diagnostic-evidence: transcript_path contains '..'; skipping" >&2
  exit 0
fi

# ── Graceful degradation: transcript file must exist and be readable ──────
if [[ ! -f "$TRANSCRIPT" ]]; then
  exit 0
fi

# ── Verify python3 is available ───────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "check-diagnostic-evidence: python3 not available; skipping evidence check" >&2
  exit 0
fi

# ── Locate scripts/diagnostic_evidence.py ────────────────────────────────
# Resolution order:
#   1. $CWD/scripts/diagnostic_evidence.py   (installed harness)
#   2. Hook's parent directory / scripts/     (dev/test run from repo root)
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT_CANDIDATE="$(dirname "$HOOK_DIR")"
MODULE_PATH=""
if [[ -f "${CWD}/scripts/diagnostic_evidence.py" ]]; then
  MODULE_PATH="${CWD}/scripts/diagnostic_evidence.py"
elif [[ -f "${REPO_ROOT_CANDIDATE}/scripts/diagnostic_evidence.py" ]]; then
  MODULE_PATH="${REPO_ROOT_CANDIDATE}/scripts/diagnostic_evidence.py"
fi

if [[ -z "$MODULE_PATH" ]]; then
  echo "check-diagnostic-evidence: scripts/diagnostic_evidence.py not found; skipping" >&2
  exit 0
fi

# ── Delegate all transcript scanning, validation, and audit-log work to Python
# Python handles JSONL parsing (incl. malformed lines), window slicing,
# evidence validation, audit emission, and warning output — keeping bash
# minimal and avoiding bash 3/4 compatibility issues.
#
# Output protocol: each stdout line is one of:
#   WARN:<tool_name>:<turn_index>      — emit Pattern B warning
#   (audit-log rows emitted directly inside Python; no LOG: protocol needed)
SCAN_OUTPUT=$(python3 -c "
import sys
import json
import importlib.util
import pathlib

transcript_path = sys.argv[1]
cwd             = pathlib.Path(sys.argv[2])
window          = int(sys.argv[3])
tool_name       = sys.argv[4]
module_path     = pathlib.Path(sys.argv[5])

# Load diagnostic_evidence module.
# Register in sys.modules BEFORE exec_module so the dataclass decorator
# can resolve cls.__module__ == 'diagnostic_evidence' correctly.
spec = importlib.util.spec_from_file_location('diagnostic_evidence', module_path)
mod  = importlib.util.module_from_spec(spec)
sys.modules['diagnostic_evidence'] = mod
spec.loader.exec_module(mod)

# Resolve feature_id (best-effort; null when unresolvable).
feature_id = None
active_dir = cwd / '.etc_sdlc' / 'features' / 'active'
if active_dir.is_dir():
    candidates = sorted(
        d.name for d in active_dir.iterdir()
        if d.is_dir() and d.name.startswith('F')
    )
    if candidates:
        feature_id = candidates[-1]

# Read transcript JSONL, skipping malformed lines (graceful degradation).
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

# Slice the investigation window.
start         = max(0, total - window)
window_entries = entries[start:]

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

for idx, entry in enumerate(window_entries):
    text = _extract_text(entry.get('content', ''))
    if '<new-diagnostics>' not in text:
        continue

    abs_idx = start + idx

    # Collect all subsequent text in the window as the validator corpus.
    subsequent_parts = [
        _extract_text(e.get('content', ''))
        for e in window_entries[idx + 1:]
    ]
    subsequent_text = '\n'.join(subsequent_parts)

    result = mod.validate_block(subsequent_text)

    if result.valid:
        evidence_type = (result.parsed or {}).get('evidence_type', None)
        payload = {
            'feature_id': feature_id,
            'tool_name': tool_name,
            'evidence_type': evidence_type,
            'decision': 'accepted',
        }
        try:
            mod.emit_event('diagnostic_dismissal_with_evidence', payload, cwd)
        except Exception as exc:
            print(f'check-diagnostic-evidence: audit-log write failed: {exc}',
                  file=sys.stderr)
    else:
        payload = {
            'feature_id': feature_id,
            'tool_name': tool_name,
            'evidence_type': None,
            'decision': 'unresolved',
            'reason': 'missing_evidence_block',
        }
        try:
            mod.emit_event('diagnostic_dismissal_missing_evidence', payload, cwd)
        except Exception as exc:
            print(f'check-diagnostic-evidence: audit-log write failed: {exc}',
                  file=sys.stderr)
        # Signal the bash layer to emit the Pattern B warning.
        print(f'WARN:{tool_name}:{abs_idx}')
" \
  "$TRANSCRIPT" "$CWD" "$WINDOW" "$TOOL_NAME" "$MODULE_PATH" \
  2>/dev/null)
SCAN_EXIT=$?

if [[ $SCAN_EXIT -ne 0 ]]; then
  # Python scan failed — degrade gracefully.
  echo "check-diagnostic-evidence: scan subprocess error (exit ${SCAN_EXIT}); skipping" >&2
  exit 0
fi

# ── Process WARN signals: emit Pattern B stderr warning ───────────────────
while IFS= read -r signal; do
  [[ -z "$signal" ]] && continue
  if [[ "$signal" == WARN:* ]]; then
    WARN_TOOL=$(echo "$signal" | cut -d: -f2)
    WARN_TURN=$(echo "$signal" | cut -d: -f3)
    printf '\n\n---\n\n**▶ Note:** Diagnostic dismissal detected without evidence block (see standards/process/diagnostic-discipline.md). Tool: %s. Reminder turn: %s. Last %s turns scanned for <new-diagnostics> system reminders.\n' \
      "$WARN_TOOL" "$WARN_TURN" "$WINDOW" >&2
  fi
done <<< "$SCAN_OUTPUT"

exit 0
