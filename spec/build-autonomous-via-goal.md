# F014 — /build --autonomous via Claude Code /goal

**Status:** spec
**Author role:** Engineer (Jason / HCE)
**Date:** 2026-05-13

## Problem

Today's `/build` pauses 3-4 times per feature for operator approval (Steps 3 + 5 + escalation prompts). For 10 developers shipping daily, that's 30-40 confirmation prompts per day across the team. Anthropic shipped `/goal` — a session-scoped completion-condition checker (Haiku-evaluator wraps a prompt-based Stop hook) that loops Claude through "another turn" until a stated condition is met. It's the right primitive for autonomous /build execution.

## Solution

Add `--autonomous` flag to `/build`:

```
/build .etc_sdlc/features/F<NNN>-<slug>/spec.md --autonomous
/build .etc_sdlc/features/F<NNN>-<slug>/spec.md --autonomous --max-turns 50
/build --resume --autonomous
```

When `--autonomous` is set:

1. **Step 2 (SETUP)** derives a goal condition from `state.yaml` and spec.md AC count, sets `/goal <condition>`. Default `--max-turns` is 50.
2. **Step 3 (DECOMPOSE)** skips the Pattern A "Task breakdown looks right?" confirmation. Auto-proceeds.
3. **Step 5 (PLAN WAVES)** skips the Pattern A "Proceed with wave execution?" confirmation. Auto-proceeds with "Execute all waves".
4. **Step 7 (VERIFY)** — on NON-COMPLIANT, /goal's evaluator-after-each-turn drives the remediation cycle naturally (Claude reads the spec-enforcer output, dispatches remediation, returns; evaluator re-checks; loop until COMPLIANT or max-turns exhausted).
5. **Terminal close** clears the goal (`/goal --clear` or equivalent).
6. **`--max-turns N`** bounds runaway loops. Default 50. Hard cap regardless of operator override = 200.

## Goal Condition Derivation

Derived deterministically from state.yaml + spec.md:

```
F<NNN> spec-enforcer returns COMPLIANT for feature <feature_id>;
all <N> ACs in <feature_path>/spec.md are SATISFIED;
git tag etc/feature/F<NNN>/release exists;
pytest reports 0 failures;
feature directory at .etc_sdlc/features/shipped/F<NNN>-<slug>/.
```

Operator override: `--goal-condition "<custom string>"`.

## Acceptance Criteria

- **AC-01:** `--autonomous` flag is documented in skills/build/SKILL.md Usage section.
- **AC-02:** When `--autonomous` is set, Step 2 derives a goal condition deterministically from `state.yaml` and writes the /goal invocation. The goal condition format matches the template above.
- **AC-03:** When `--autonomous` is set, Step 3 SKIPS the Pattern A breakdown-confirmation AskUserQuestion and auto-proceeds to scoring (Step 4).
- **AC-04:** When `--autonomous` is set, Step 5 SKIPS the Pattern A wave-execution-confirmation AskUserQuestion and auto-proceeds with the equivalent of "Execute all waves".
- **AC-05:** When `--autonomous` is set, Step 7 NON-COMPLIANT routes to remediation without operator pause — the /goal evaluator-loop is the operator surrogate.
- **AC-06:** `--max-turns N` is documented in Usage; defaults to 50; hard-capped at 200 regardless of operator override. SKILL.md warns about runaway loops at higher caps.
- **AC-07:** `--goal-condition "<override>"` is documented as an escape hatch for operators who need a non-default condition.
- **AC-08:** Terminal-phase close (after release tag is written) clears the /goal so a follow-up session does not inherit a stale autonomous loop.
- **AC-09:** `--autonomous --resume` reuses the original goal condition from `state.yaml.build.autonomous.goal_condition` (does NOT re-derive).
- **AC-10:** When `disableAllHooks: true` is in managed settings, /goal is unavailable; `/build --autonomous` falls back to interactive mode with a friendly warning rather than hard-failing.
- **AC-11:** state.yaml.build gains an `autonomous` block when this mode is engaged: `mode: autonomous | interactive`, `max_turns`, `goal_condition`, `started_at`. Used by --resume.
- **AC-12:** tests/test_build_autonomous_skill.py contains grep-style contract tests covering AC-01 (flag in Usage), AC-02-AC-09 (skill-text contains required phrases), AC-11 (state.yaml schema doc).
- **AC-13:** README "Skills" section /build entry mentions --autonomous + max-turns. F014 row added to shipping table.

## Out of Scope

- **Multi-feature autonomous queue** (R3 from memory/project-goal-feature-integration.md). Defer until F015 (cross-feature collision detection) ships.
- **Goal-driven /spec or /architect.** Their Socratic loops require human author judgment.
- **Goal-driven /hotfix.** Anti-abuse defenses are deliberate.
- **Custom Stop-hook authoring beyond /goal.** Operators can still write Stop hooks via settings.json.
- **Cost-transparency reporting** at terminal close (cumulative evaluator-token spend). Worth doing eventually but deferred to a follow-up — small enhancement, not core to autonomous mode.

## Technical Notes

- `/goal` ships with Claude Code (2026-05 release). Requires trusted workspace. Disabled if `disableAllHooks` is set in managed policy.
- The Haiku-evaluator runs after every turn and reads conversation transcript — NOT on-disk state. So the goal condition must be expressible from what Claude has surfaced ("Claude has reported `pytest 0 failures`" rather than "dist/ is byte-identical"). Goal-condition derivation respects this.
- This feature changes ONLY skills/build/SKILL.md and tests. It does not modify any other skill, agent, hook, or compiled artifact.
- F014 is independent of F015 (cross-feature collision detection) for single-feature autonomy. R3 (multi-feature queue) depends on F015.

## Source

- `memory/project-goal-feature-integration.md` (2026-05-12 analysis)
- Anthropic /goal docs: https://code.claude.com/docs/en/goal
- venlink-platform operator session 2026-05-12 (proposal pasted)
