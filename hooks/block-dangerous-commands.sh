#!/bin/bash
# hooks/block-dangerous-commands.sh
#
# PreToolUse hook for Bash operations.
# Blocks destructive shell commands that could cause irreversible damage.
# The equivalent of "production access requires approval."
#
# Exit codes:
#   0 = allow the command
#   2 = block the command (with reason to stderr)
#
# ── SCOPING NOTE: gh DELIVERY commands are deliberately NOT blocked here ──────
# Security review F-2026-06-12 (MEDIUM) asked whether this hook should block
# `gh` delivery (gh pr create/merge/close, gh release create, gh repo delete)
# so a prompt-injected janitor fix-subagent cannot cross the delivery trust
# boundary it is forbidden to cross (agents/janitor.md: "the orchestrator is
# the only component that crosses the trust boundary ... its single crossing is
# gh on the operator's existing auth; you never do").
#
# It must NOT be done in this hook. This gate (spec/etc_sdlc.yaml
# `safety-guardrails`) is event=PreToolUse, matcher="Bash" with NO agent
# scoping — it fires on EVERY Bash call, in the MAIN orchestrator session as
# well as in subagents. The orchestrator's LEGITIMATE delivery runs through
# this exact hook: `/janitor` opens its PR with `gh pr create [--draft]`
# (skills/janitor/SKILL.md), `/pull-tickets` runs `gh pr create`
# (skills/pull-tickets/SKILL.md), and /build ships PRs. A blanket gh-delivery
# block would brick all three.
#
# The PreToolUse Bash payload carries no reliable main-session-vs-subagent
# discriminator (only commands/cwd/client/transcript_path — the transcript path
# identifies a session, not whether it is a subagent's; hook_payload.py's
# "subagent" kind keys off the Task/Agent spawn tool, not Bash-within-a-
# subagent). With no discriminator, the correct fix is a SUBAGENT-SCOPED hook
# (e.g. a hook wired to fire only inside the janitor fix-subagent's context, or
# tightening the janitor agent toolset so Bash cannot reach gh), NOT a rule in
# this global gate. That is a wiring/design decision for the operator. The
# regression tests pinning "gh delivery is ALLOWED by this hook" exist so a
# future blanket block added here fails loudly and routes the fix to the right
# layer. See tests/test_block_dangerous_commands.py::test_gh_*.

INPUT=$(cat)
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
PAYLOAD_HELPER="${HOOK_DIR}/helpers/hook_payload.py"
COMMANDS=$(printf '%s' "$INPUT" | python3 "$PAYLOAD_HELPER" commands) || exit 2

if [[ -z "$COMMANDS" ]]; then
  exit 0
fi

check_command() {
local COMMAND="$1"

# ── Destructive file operations ──────────────────────────────────────────
# Block rm with recursive flag (-r, -rf, -fr, --recursive) on broad targets.
# Single file rm (even with -f) is allowed — -f just suppresses "not found" warnings.
if echo "$COMMAND" | grep -qE '^\s*rm\s+(-[a-zA-Z]*r[a-zA-Z]*\s|--recursive)'; then
	  # Allow rm -rf on known-safe targets (build artifacts, caches)
	  if echo "$COMMAND" | grep -qE 'rm\s+.*\b(node_modules|__pycache__|\.tdd-dirty|dist/|build/|\.pytest_cache|\.mypy_cache|\.ruff_cache)\b'; then
	    return 0
	  fi
  echo "BLOCKED: Recursive rm command. Specify exact files or ask the user for confirmation." >&2
  exit 2
fi

# ── Destructive git operations ───────────────────────────────────────────
# --force([^-]|$) deliberately exempts --force-with-lease: it is the safe
# remediation this very message recommends, and the old bare-substring
# match blocked it too (audit init 8). Bare --force and -f still block.
if echo "$COMMAND" | grep -qE 'git\s+push\s+.*--force([^-]|$)|git\s+push\s+-f\b'; then
  echo "BLOCKED: Force push can destroy remote history. Use --force-with-lease or ask the user." >&2
  exit 2
fi

if echo "$COMMAND" | grep -qE 'git\s+reset\s+--hard'; then
  echo "BLOCKED: Hard reset discards uncommitted work. Stash first or ask the user." >&2
  exit 2
fi

if echo "$COMMAND" | grep -qE 'git\s+clean\s+.*-f'; then
  echo "BLOCKED: git clean -f permanently deletes untracked files. Ask the user." >&2
  exit 2
fi

if echo "$COMMAND" | grep -qE 'git\s+checkout\s+--\s+\.|git\s+restore\s+--\s+\.'; then
  echo "BLOCKED: Discarding all unstaged changes. Ask the user." >&2
  exit 2
fi

# ── Database destruction ─────────────────────────────────────────────────
if echo "$COMMAND" | grep -qiE 'DROP\s+(TABLE|DATABASE|SCHEMA|INDEX)|TRUNCATE\s+TABLE|DELETE\s+FROM\s+\w+\s*;?\s*$'; then
  echo "BLOCKED: Destructive database operation. This requires explicit user approval." >&2
  exit 2
fi

# ── System-level danger ──────────────────────────────────────────────────
if echo "$COMMAND" | grep -qE '>\s*/dev/sd|mkfs\.|dd\s+if=|chmod\s+-R\s+777|chown\s+-R'; then
  echo "BLOCKED: System-level destructive operation. Ask the user." >&2
  exit 2
fi

# ── Undisciplined git staging ─────────────────────────────────────────────
if echo "$COMMAND" | grep -qE 'git\s+add\s+(-A\b|--all\b|\.(\s|$))'; then
  echo "BLOCKED: 'git add -A' / 'git add .' stages everything blindly — including secrets, junk, and unintended files." >&2
  echo "Stage specific files by name: git add file1.py file2.py" >&2
  exit 2
fi

# ── Skip hooks / bypass safety ───────────────────────────────────────────
if echo "$COMMAND" | grep -qE -- '--no-verify|--skip-hooks|--dangerously'; then
  echo "BLOCKED: Attempting to bypass safety checks. The harness exists for a reason." >&2
  exit 2
fi
}

while IFS= read -r COMMAND; do
  [[ -z "$COMMAND" ]] && continue
  check_command "$COMMAND"
done <<< "$COMMANDS"

exit 0
