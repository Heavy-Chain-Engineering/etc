#!/bin/bash
# hooks/tier-0-design-preflight.sh
#
# PreToolUse hook for Edit|Write operations.
# Conditional tier-0 preflight for PRODUCT.md + DESIGN.md (F011 BR-006,
# ADR-F011-003). NEW hook — NOT an extension of the existing-but-missing
# tier-0-preflight hook (per ADR-F011-003: separate concern).
#
# Behavior:
#   1. Read the Edit/Write tool's target file_path from stdin (JSON payload).
#   2. Walk parent directories looking for an enclosing feature directory
#      under .etc_sdlc/features/*/ with a state.yaml.
#   3. If no enclosing feature dir found OR state.yaml missing OR
#      design_phase block absent OR tier_0_promoted != true → exit 0 (allow).
#   4. If tier_0_promoted is true AND (PRODUCT.md OR DESIGN.md missing at
#      repo root) → exit 2 (block) with stderr message naming the missing
#      file(s).
#
# Read-only: this hook NEVER writes or modifies state.yaml or any other file.
# It only reads the Edit/Write event tool inputs + state.yaml + checks
# repo-root file existence.
#
# Exit codes:
#   0 = allow the operation
#   2 = block the operation (with message to stderr)

set -u

# ── Step 1: Read tool input from stdin (PreToolUse contract) ────────────
INPUT=$(cat)

# Parse JSON. Prefer jq (used by sibling hooks like check-tier-0.sh); fall
# back to python3 if jq is unavailable. Both are POSIX-portable expectations
# for this repo's hook runtime.
parse_json_field() {
  # $1 = jq-style path expression (e.g., '.tool_input.file_path')
  # Reads $INPUT from environment.
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$INPUT" | jq -r "$1 // empty"
  else
    # python3 fallback: translate jq path to python dict lookup.
    # Only supports the two paths we use below.
    printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
path = '$1'
# Strip leading '.'
parts = [p for p in path.lstrip('.').split('.') if p]
cur = data
for p in parts:
    if isinstance(cur, dict) and p in cur:
        cur = cur[p]
    else:
        cur = ''
        break
if cur is None:
    cur = ''
print(cur)
"
  fi
}

FILE_PATH=$(parse_json_field '.tool_input.file_path')
CWD=$(parse_json_field '.cwd')

# If no file_path in the event, nothing to check — allow.
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

# ── Step 2: Walk parent dirs looking for an enclosing feature directory ─
# Pattern: <ancestor>/.etc_sdlc/features/<slug>/state.yaml
#
# Algorithm: start from the directory of FILE_PATH and walk upward. At each
# level, check whether the path includes ".etc_sdlc/features/<slug>/" as a
# segment. We resolve the absolute path first so relative paths work.

# Resolve FILE_PATH to absolute. If the file doesn't exist yet (Write
# creating a new file), use the dirname; if even the dirname doesn't exist,
# fall back to CWD-relative resolution.
if [ -e "$FILE_PATH" ]; then
  ABS_TARGET=$(cd "$(dirname "$FILE_PATH")" 2>/dev/null && pwd -P)/$(basename "$FILE_PATH")
elif [ -n "${CWD:-}" ] && [ -d "$CWD" ]; then
  # Treat FILE_PATH as relative to CWD if not absolute.
  case "$FILE_PATH" in
    /*) ABS_TARGET="$FILE_PATH" ;;
    *)  ABS_TARGET="$CWD/$FILE_PATH" ;;
  esac
else
  ABS_TARGET="$FILE_PATH"
fi

# Walk upward from the target's parent directory looking for a state.yaml
# inside a .etc_sdlc/features/<slug>/ ancestor. We look for the LITERAL
# segment ".etc_sdlc/features/<slug>/state.yaml" closest to the target.
FEATURE_STATE_YAML=""
DIR=$(dirname "$ABS_TARGET")
# Bound the walk to avoid infinite loops on edge filesystems.
GUARD=0
while [ "$DIR" != "/" ] && [ -n "$DIR" ] && [ "$GUARD" -lt 64 ]; do
  GUARD=$((GUARD + 1))
  # Case 1: the target is itself inside a feature dir. Look for the closest
  # ancestor whose parent is ".etc_sdlc/features".
  PARENT=$(dirname "$DIR")
  if [ "$(basename "$PARENT")" = "features" ] && [ "$(basename "$(dirname "$PARENT")")" = ".etc_sdlc" ]; then
    if [ -f "$DIR/state.yaml" ]; then
      FEATURE_STATE_YAML="$DIR/state.yaml"
      break
    fi
  fi
  # Case 2: the target lives outside features/ but a sibling/ancestor
  # .etc_sdlc/features/*/state.yaml may be relevant. We do NOT walk into
  # arbitrary feature dirs from here; per the contract, the hook only
  # cares about the CLOSEST ENCLOSING feature dir. If the walk reaches a
  # directory that contains .etc_sdlc/ but the target is not inside a
  # feature, the target is outside any feature dir — exit 0.
  DIR=$(dirname "$DIR")
done

# No enclosing feature directory found → target is outside any feature →
# nothing to enforce → allow.
if [ -z "$FEATURE_STATE_YAML" ] || [ ! -f "$FEATURE_STATE_YAML" ]; then
  exit 0
fi

# ── Step 3: Read state.yaml.design_phase.tier_0_promoted ───────────────
# YAML parsing via python3 (more reliably available than yq). The hook is
# read-only — we open state.yaml for reading only.
TIER_0_PROMOTED=$(python3 -c "
import sys
path = '$FEATURE_STATE_YAML'
try:
    with open(path, 'r', encoding='utf-8') as fh:
        text = fh.read()
except OSError:
    print('')
    sys.exit(0)

# Prefer PyYAML if available; fall back to a minimal hand-parse that
# tolerates the small subset of YAML state.yaml uses.
try:
    import yaml  # type: ignore
    data = yaml.safe_load(text) or {}
    dp = data.get('design_phase') if isinstance(data, dict) else None
    if isinstance(dp, dict):
        val = dp.get('tier_0_promoted')
        if val is True:
            print('true')
        else:
            print('')
    else:
        print('')
except Exception:
    # Hand-parse: look for a 'design_phase:' block and a 'tier_0_promoted:'
    # line nested under it. Two-space indent is the convention.
    in_block = False
    promoted = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith('#'):
            continue
        # Top-level key boundary: a line that starts at column 0 and ends
        # with ':' (no indent, no nesting).
        if line[:1] not in (' ', '\t'):
            in_block = line.split(':', 1)[0].strip() == 'design_phase'
            continue
        if in_block:
            stripped = line.strip()
            if stripped.startswith('tier_0_promoted:'):
                value = stripped.split(':', 1)[1].strip().lower()
                if value in ('true', 'yes', 'on', '1'):
                    promoted = True
                break
    print('true' if promoted else '')
")

# Empty / not-true → allow (state.yaml missing, design_phase absent, or
# tier_0_promoted is false/absent).
if [ "$TIER_0_PROMOTED" != "true" ]; then
  exit 0
fi

# ── Step 4: tier_0_promoted == true — enforce PRODUCT.md + DESIGN.md ───
# Locate repo root. Prefer git top-level (matches sibling check-tier-0.sh);
# fall back to walking up from the feature directory.
REPO_ROOT=""
FEATURE_DIR=$(dirname "$FEATURE_STATE_YAML")
if [ -n "${CWD:-}" ] && [ -d "$CWD" ]; then
  REPO_ROOT=$(cd "$CWD" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || true)
fi
if [ -z "$REPO_ROOT" ]; then
  REPO_ROOT=$(cd "$FEATURE_DIR" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null || true)
fi
if [ -z "$REPO_ROOT" ]; then
  # Fall back: walk up from the feature dir looking for .etc_sdlc/.
  CAND="$FEATURE_DIR"
  GUARD=0
  while [ "$CAND" != "/" ] && [ -n "$CAND" ] && [ "$GUARD" -lt 64 ]; do
    GUARD=$((GUARD + 1))
    if [ -d "$CAND/.etc_sdlc" ]; then
      REPO_ROOT="$CAND"
      break
    fi
    CAND=$(dirname "$CAND")
  done
fi
if [ -z "$REPO_ROOT" ]; then
  # Cannot locate repo root — fail open (allow) rather than blocking on
  # uncertainty. Operator-level trust model per ADR-F011-003.
  exit 0
fi

MISSING=""
if [ ! -f "$REPO_ROOT/PRODUCT.md" ]; then
  MISSING="$MISSING PRODUCT.md"
fi
if [ ! -f "$REPO_ROOT/DESIGN.md" ]; then
  MISSING="$MISSING DESIGN.md"
fi

if [ -z "$MISSING" ]; then
  # Both files present — allow.
  exit 0
fi

# ── Step 5: Block with an operator-friendly stderr message ──────────────
{
  echo "BLOCKED: tier-0 design preflight (F011 BR-006)."
  echo ""
  echo "This feature has state.yaml.design_phase.tier_0_promoted: true,"
  echo "which requires PRODUCT.md AND DESIGN.md at the repo root before"
  echo "Edit/Write operations are allowed."
  echo ""
  echo "Feature state.yaml: $FEATURE_STATE_YAML"
  echo "Repo root:          $REPO_ROOT"
  echo ""
  echo "Missing file(s):"
  for m in $MISSING; do
    echo "  - $REPO_ROOT/$m"
  done
  echo ""
  echo "Fix: run /design (etc F011+) to generate the missing file(s) via"
  echo "/impeccable teach, or install impeccable and run /impeccable teach"
  echo "directly. See docs/adrs/F011-003-conditional-tier-0-promotion.md"
  echo "for the rationale."
} >&2

exit 2
