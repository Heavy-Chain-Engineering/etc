# F012 — Auto-checkpoint Stop hook

**Status:** spec
**Author role:** Engineer (Jason Vertrees / HCE)
**Author:** drafted from venlink-platform proposal 2026-05-11; threshold + framing adjusted by operator
**Date:** 2026-05-13

## Problem

The `/checkpoint` skill's Constraints section says "if context utilization
exceeds 60%, suggest /checkpoint then /compact" — but this is a passive
suggestion the model must remember to act on. In long autonomous sessions
the rule never triggers. Hours of orchestration state get lost on context
compaction or browser crash between manual `/checkpoint` invocations.

Venlink-platform operator session 2026-05-11 lost F011 orchestration state
(21 leaf tasks, 3 remediations, wave planning, 2 deployed-env bugs, agent
truncation patterns, operating_locations decision, ADR-050 intent) because
the last `/checkpoint` save was at 14:09 and the session ran late afternoon
without re-triggering the passive rule.

The harness already has the architectural slot: Claude Code's `Stop` hook
array is the natural place to enforce a "verify state preserved before
allowing a stop" discipline. etc ships several Stop hooks already
(`check-seam-evidence.sh`, `check-completion-discipline.sh`) but none
for checkpoint freshness.

## Solution

Ship `hooks/auto-checkpoint.sh` — a Stop hook that fires when **both**
conditions hold:

1. `context_window.used_percentage >= 85` (tunable via `CHECKPOINT_CTX_THRESHOLD`).
2. `.etc_sdlc/checkpoint.md` mtime is more than 30 minutes ago, **or** the file is absent (tunable via `CHECKPOINT_STALE_MINUTES`).

Both conditions met → exit code 2 with a stderr message instructing Claude
to run `/checkpoint` before stopping. Claude Code's Stop-hook contract
surfaces exit-2 messages to the model and blocks the session stop, giving
the model a chance to act.

Either condition unmet → exit 0 silently, normal stop proceeds.

### Threshold rationale (85%, not 60%)

The venlink proposal defaulted to 60%, which is appropriate for a 200K
context window (120K tokens = "approaching headroom limit"). Etc's
primary operators run opus 4.7 with 1M context (`claude-opus-4-7[1m]`).
At 1M, 60% = 600K tokens — far too conservative; would fire on most
moderate sessions. At 85% = 850K tokens with 150K headroom, the hook
fires when there's still real working room but the operator should
save state before further work.

Operators on smaller windows (Sonnet, standard Opus 200K) can lower the
threshold via `CHECKPOINT_CTX_THRESHOLD` env var per their needs. The
percentage-of-context-used framing is window-size-agnostic by design.

## Why a Stop hook, not a slash command

A Stop hook fires at the natural action boundary (the model is about to
end its turn). Three reasons this is the right surface:

1. **Same architecture as existing checkpoint discipline.**
   `check-completion-discipline.sh` is already a Stop hook that blocks
   on `.tdd-dirty` markers or in-progress tasks. Adding checkpoint
   freshness to the Stop array is structurally cheap and consistent.
2. **Hooks cannot invoke skills.** A slash command would need the model
   to remember to run it — exactly the passive-rule failure mode this
   feature exists to solve. A blocking exit-2 message is the only way
   to force the model's hand at the session boundary.
3. **Settings.json is operator-owned.** `~/.claude/settings.json` is in
   sandbox `denyWrite` by policy; etc cannot patch it during install.
   The hook script can ship to `hooks/auto-checkpoint.sh` (etc-managed);
   the wiring is an operator paste documented in install.sh INFO output
   and README.

## Acceptance Criteria

- **AC-01:** `hooks/auto-checkpoint.sh` exists, is executable bash, has POSIX shebang.
- **AC-02:** Hook reads JSON from stdin via `INPUT=$(cat)`; parses `.context_window.used_percentage` with `jq`, defaulting to 0 if the field is absent or null.
- **AC-03:** Threshold defaults to 85 when `CHECKPOINT_CTX_THRESHOLD` env var is unset; honors the env var when set to any non-empty integer.
- **AC-04:** Staleness threshold defaults to 30 minutes when `CHECKPOINT_STALE_MINUTES` env var is unset; honors the env var when set.
- **AC-05:** Hook reads `.cwd` from input JSON; if absent or null, defaults to `"."` and proceeds without aborting.
- **AC-06:** Context percentage below threshold → hook exits 0 silently, regardless of checkpoint state.
- **AC-07:** Context percentage at/above threshold AND checkpoint file mtime within freshness window → exit 0 silently.
- **AC-08:** Context percentage at/above threshold AND checkpoint file missing → exit 2 with stderr containing the literal string `AUTO-CHECKPOINT REQUIRED` plus the current context percentage and a remediation instruction.
- **AC-09:** Context percentage at/above threshold AND checkpoint file stale (mtime older than stale threshold) → exit 2 with stderr containing actual file age in minutes.
- **AC-10:** Hook handles both BSD/macOS stat (`-f %m`) AND GNU stat (`-c %Y`) for mtime extraction, falling through to a safe 0 default if both fail.
- **AC-11:** `tests/test_auto_checkpoint_hook.py` exercises AC-06 through AC-09 with controlled stdin + temp-file mtime fixtures; all tests pass under `uv run pytest`.
- **AC-12 (revised post-ship):** Hook is declared in `spec/etc_sdlc.yaml` under the `Stop` event with `script: auto-checkpoint.sh` and `timeout: 15`. `compile-sdlc.py` copies `hooks/auto-checkpoint.sh` into `dist/hooks/` (executable) and adds the entry to `dist/settings-hooks.json` under `hooks.Stop`. `install.sh`'s existing `merge_settings()` function (lines 219-253) merges this into the operator's `~/.claude/settings.json` on install — no manual paste required. Pattern matches every other etc-shipped hook. (The original AC-12 specified an INFO-line paste hint; that design conflated the Claude-agent session-time sandbox restriction with install.sh's runtime capability, which has full write access to `~/.claude/`. Corrected pre-fix-up-commit.)
- **AC-13:** `README.md` documents the auto-checkpoint hook: trigger conditions, env vars, and that it's wired automatically by `install.sh` on next run. F012 row added to the "What has been shipping" table.

## Out of Scope

- Automatically invoking `/checkpoint`. Stop hooks cannot invoke skills; the exit-2 block surfaces the message to the model which is responsible for acting on it.
- Bundling with F016 (`/build --autonomous` via `/goal`). F012 is independent of F016; both can ship in either order.
- Cross-checkpoint diffing (i.e., refusing to allow a stop unless the latest checkpoint differs materially from the previous one). Out of scope; staleness suffices.

## Technical Notes

- **Field availability uncertainty:** `.context_window.used_percentage` is read by `statusline.sh` (line 11) from the JSON feed that hooks receive, but the exact Stop-hook input schema is not formally documented in Anthropic public docs as of 2026-05-13. The hook's `// 0` default ensures safe-fail: if the field is absent, threshold-check fails (0 < 85), hook exits 0, normal stop allowed. Operator should validate on first activation by adding `echo "CTX_PCT=${CTX_PCT}" >&2` after the jq line and confirming a non-zero value during a real high-context session.
- **Opt-in by design.** Operator must paste the JSON snippet into `~/.claude/settings.json` after running install.sh. The hook script is shipped but inert until wired in.
- **Rollback** is trivial: remove the third Stop hook object from settings.json + delete `hooks/auto-checkpoint.sh`. The other two Stop hooks are unaffected. No persistent state; the hook only blocks, never modifies disk.

## Dependencies

- `jq` (already required by `check-completion-discipline.sh`)
- `stat` (BSD or GNU; the hook handles both)
- `bash` 4+ (already required by existing hooks)

## Source

- Venlink-platform operator proposal 2026-05-11 (proposal 1: "Auto-Checkpoint Stop Hook"), pasted into etc-system-engineering session 2026-05-13.
- Threshold adjustment (60% → 85%) per operator instruction; rationale documented above.
