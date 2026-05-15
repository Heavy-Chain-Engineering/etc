# F019 — Chief Efficiency Officer (Stop-hook reflection layer)

**Status:** spec (review before /build)
**Author role:** Engineer (Jason / HCE)
**Date:** 2026-05-15
**Source:** Operator session 2026-05-14 (reframe: subject = operator, not agent) + Anthropic *How Claude Code Works in Large Codebases* (Stop-hook reflection pattern)
**Supersedes:** Task #18 (stuck-loop detector), task #20 (CEO), task #22 (sandbox discipline audit) — collapsed into this single architectural piece per the design discussion.

## Problem

Three distinct operator-attention failure modes have been observed this session, each generating its own task:

1. **Stuck-loop pattern (venlink 2026-05-12).** Agent generated dozens of pytest variants over 2 days while reporting high confidence. Cost: ~$10k, roadmap blocked. Operator broke the loop via emotional impatience, not harness signal. Task #18.

2. **Operator-efficiency drift.** Operator works long sessions; efficiency can degrade without anyone noticing. No real-time visibility into whether the operator is producing value or treading water. Task #20.

3. **Sandbox-bypass discipline failure (2026-05-15).** Agent preemptively bypasses sandbox to "save time," costing operator attention on every approval prompt. Local optimization, global pessimization. Operator has zero visibility into how often this happens. Task #22.

These look like three different problems. **They have one architectural shape**: there is no harness layer that observes a session, reflects on what happened, and surfaces evidence-based observations to the operator. The existing harness layers ENFORCE current discipline (Stop hooks, gates, blockers); none of them LEARN from the session or propose discipline updates.

Anthropic's *How Claude Code Works in Large Codebases* (2026) names exactly this gap:

> *"A stop hook can reflect on what happened during a session and propose CLAUDE.md updates while the context is fresh."*

etc has zero reflection-style Stop hooks today. All current Stop hooks are enforcement. The Chief Efficiency Officer is the reflection layer.

## Solution

`hooks/chief-efficiency-officer.sh` — a new Stop hook that:

1. **Observes** every Stop event. Captures evidence-based signals only.
2. **Reflects** when patterns warrant it. Periodic reflection at session-end thresholds; not every Stop event.
3. **Proposes** specific evidence-cited observations to the operator via a queue file + daily report.
4. **Escalates rarely** — threshold-push interrupts the next agent turn only when active-engagement on a single problem exceeds operator's baseline by 2σ.

### Architectural constraints (load-bearing)

1. **Subject = operator.** Not the agent. The CEO observes the operator's working patterns; the agent is a tool the operator uses.

2. **Evidence-based only.** Every observation cites:
   - A specific data point (active engagement time, commit count, sandbox-bypass count, etc.)
   - A specific baseline (operator's own median/p90 from sdlc_timing.py)
   - The gap between observation and baseline
   - **NO vibes. NO "you seem to be struggling." NO hallucinated narrative.**

3. **Active engagement time, not wall-clock.** Sum of (turn_end[N+1] - turn_end[N]) where the gap is ≤ 5 minutes. Larger gaps are sleep/break and don't count toward "time on this problem."

4. **Outcome-focused, not activity-focused.** Measures shipped artifacts (commits, releases, decisions) per unit active time. NOT turn count, NOT LOC typed, NOT tool calls.

5. **Operator-pull always available; threshold-push rare.** `/efficiency review` works any time. Threshold-push fires only on genuine 2σ outlier. Bar for firing is intentionally high.

6. **Voice: Chief of Staff.** Names your stated intent + current activity + the gap. Does NOT prescribe the fix. Operator stays in charge.

7. **Compounds into self-knowledge.** Daily reports accumulate; weekly patterns become visible across multiple sessions. Self-knowledge is the deeper goal beyond any single session optimization.

### Data layer (minimum viable for v1)

`hooks/chief-efficiency-officer.sh` reads from + writes to these state files:

**INPUTS:**

- `.etc_sdlc/efficiency/turn-events.jsonl` (NEW) — appended by a new Stop-hook ordering: chief-efficiency-officer.sh runs FIRST in the Stop chain, captures `{"event_id": <uuid>, "ended_at": <iso8601>, "cwd": <path>}` to JSONL, then later hooks (check-completion-discipline, auto-checkpoint) fire. Append-only.

- Active feature directory (orientation): cascading fallback per the design discussion:
  1. `.etc_sdlc/features/active/F<NNN>-*/state.yaml` — most recently modified
  2. `.etc_sdlc/features/F<NNN>-*/state.yaml` (flat-path fallback) — most recently modified
  3. TodoWrite active task (whatever has status: in_progress at the top of the list)
  4. Most-recently-modified file outside `__pycache__/`, `.coverage*`, `dist/` (heuristic fallback)
  5. None of the above → record `current_task: null` and ask "what are you working on?" in the daily report

- `sdlc_timing.py --baseline` output (existing) — operator's median/p10/p90 for inter-ship gap, used as the baseline for "this active-engagement time vs your norm" comparisons.

- `state.yaml.build.feature` of the active feature (when present) — gives the CEO the feature ID for cross-referencing.

**OUTPUTS:**

- `.etc_sdlc/efficiency/proposals/<timestamp>-<topic>.md` (NEW) — single-line + evidence per proposal. Operator reviews via `/efficiency review`.

- `.etc_sdlc/efficiency/daily/<YYYY-MM-DD>.md` (NEW) — rolling daily report. Updated at every Stop event. Operator reads at end-of-day or any time.

- Optional inject into next agent turn: `.etc_sdlc/efficiency/inject-on-next-turn.md` (NEW) — read by a SessionStart-ish hook (or reinject-context.sh extended) and prepended to next turn's context. Only written on threshold-push (rare).

### Reflection logic (v1)

At every Stop event:

1. **Append turn event** to `turn-events.jsonl`.
2. **Detect current task** via cascading fallback above.
3. **Compute active-engagement-since-task-start** by walking back through `turn-events.jsonl` until either a different task is detected OR a gap > 5 minutes is encountered.
4. **Compute progress signals** since the last Stop event:
   - New `feat()` commit? (look at `git log --since=<prev_stop_iso>`)
   - Non-cache files modified? (`git status` + file-pattern exclusions per the queued lifecycle-gap-fix patterns)
   - Decision artifacts written? (`.etc_sdlc/features/*/decisions/*.md` mtime ≥ prev_stop_iso)
   - Test count changed? (`pytest --collect-only` count delta — best-effort)
5. **Compare active-engagement-on-current-task against baseline** from sdlc_timing.py. Compute z-score.
6. **Compose observations** — each observation is a structured record:

```yaml
observation_id: obs-2026-05-15-08-23-11
observed_at: 2026-05-15T08:23:11Z
current_task: F019
data_points:
  - metric: active_engagement_on_current_task_seconds
    value: 12_240            # 3h 24m
    baseline_median: 1_380   # 23m — sdlc_timing baseline for /spec phase
    baseline_p90: 2_640      # 44m
    z_score: 8.4
  - metric: commits_since_task_start
    value: 0
    expected_for_this_engagement_time: 4  # derived from baseline
  - metric: sandbox_bypasses_since_session_start
    value: 7
    median_per_session: 2
proposal_type: threshold_push   # threshold_push | daily_report_entry | proposal_queue
voice: chief_of_staff           # chief_of_staff | data_only
content: |
  Active engagement on F019: 3h 24m. /spec-phase median across last 18
  features: 23m. Current session is 8.4σ over baseline with 0 commits.
  Sandbox bypasses this session: 7 (median: 2).

  Quick check: still on track? Want to step back?
```

7. **Decide what to do with each observation:**
   - Z-score > 3σ on a critical metric → write to `inject-on-next-turn.md` (threshold-push)
   - Z-score 1-3σ → write to `proposals/<timestamp>-<topic>.md` (proposal queue)
   - Routine (z-score < 1σ) → append to `daily/<date>.md` only (daily report entry)
   - Multiple correlated observations on same task → combine into one proposal

8. **Update daily report** at every Stop event (rolling, append-only within a day).

### Operator-facing commands

`/efficiency review` — walks queued proposals one at a time via Pattern A (Accept / Dismiss / Mark-for-followup-feature). Accepted proposals move to `.etc_sdlc/efficiency/accepted/<date>.md` and inform the operator's next harness change. Dismissed proposals move to `.etc_sdlc/efficiency/dismissed/<date>.md` (silent — but kept for false-positive-rate tracking).

`/efficiency today` — prints the current day's `daily/<date>.md` report.

`/efficiency baseline` — prints operator's current baseline (delegates to `sdlc_timing.py --baseline`).

`/efficiency mute --until <timestamp>` — silence threshold-push interrupts for a defined window (e.g., during a deliberately-long debugging session). Reason is required and logged to `daily/<date>.md` so the silencing itself is observable.

## Acceptance Criteria

### Data capture

- **AC-01:** `hooks/chief-efficiency-officer.sh` exists, executable bash. Stop-hook ordering: runs FIRST among Stop hooks (so it captures turn-end timestamp before other hooks have a chance to fail).
- **AC-02:** Every Stop event appends one line to `.etc_sdlc/efficiency/turn-events.jsonl`: `{"event_id", "ended_at", "cwd", "current_task_id_or_null"}`. Hook never blocks (always exits 0); event capture is the side effect, not the contract.
- **AC-03:** When `jq` is available, parses incoming Stop-hook JSON for context-window data; when absent (Windows / Git Bash), falls back to Python or skips silently. Mirrors F012/F018 portability pattern.
- **AC-04:** Active-engagement computation correctly subtracts gaps > 5 minutes between consecutive turn events. Threshold tunable via `CEO_IDLE_THRESHOLD_MINUTES` (default 5).

### Reflection

- **AC-05:** At every Stop event, the hook computes:
  - Active engagement on current task (per AC-04)
  - Commits since session start (`git log --since=<session_start_iso>`)
  - Sandbox bypasses since session start (count of `Bash` invocations with `dangerouslyDisableSandbox: true` — sourced from a separate `.etc_sdlc/efficiency/sandbox-bypasses.jsonl` log written by a PreToolUse hook OR derivable from session transcript if available)
  - Files modified since last Stop (`git status --porcelain` delta vs prior captured state)

- **AC-06:** Current task detection uses the cascading fallback specified above. When no task can be detected, logs `current_task: null` and emits a daily-report entry asking "what are you working on?"

- **AC-07:** Comparison against sdlc_timing.py baseline. Hook invokes `python3 ~/.claude/scripts/sdlc_timing.py --baseline --json` and reads the operator's median + p10 + p90 inter-ship gap. Z-scores are computed against these.

### Output

- **AC-08:** Every observation is a structured YAML record with explicit `data_points` (metric, value, baseline, z_score). Proposals MUST cite at least one data point with both value AND baseline; observations without baseline grounding are not written.

- **AC-09:** Three output surfaces:
  1. Threshold-push (z-score > 3σ) → `.etc_sdlc/efficiency/inject-on-next-turn.md`. Cleared when consumed by reinject-context-style hook.
  2. Proposal queue (1σ < z < 3σ OR specific anti-pattern signature matched) → `.etc_sdlc/efficiency/proposals/<timestamp>-<topic>.md`.
  3. Daily report (every Stop event, routine entry) → `.etc_sdlc/efficiency/daily/<YYYY-MM-DD>.md`.

- **AC-10:** No proposal contains narrative that isn't grounded in the data_points. Spec-enforcer-style stub-marker grep is applied to proposal content at write time: any text matching `you seem to`, `it looks like`, `probably`, `maybe you` is REJECTED. Only data-cited observations land.

### Operator commands

- **AC-11:** `/efficiency review` reads `proposals/*.md`, walks one at a time via Pattern A. Three options per proposal: Accept (move to `accepted/`), Dismiss (move to `dismissed/`), Mark-for-follow-up (creates a task in the task list referencing the proposal).

- **AC-12:** `/efficiency today` prints `daily/<current_date>.md` to stdout (or a friendly message if no observations today).

- **AC-13:** `/efficiency baseline` invokes `sdlc_timing.py --baseline` and prints to stdout. Convenience wrapper; no new logic.

- **AC-14:** `/efficiency mute --until <timestamp>` writes a mute file at `.etc_sdlc/efficiency/mute.yaml` with `{until: <iso8601>, reason: <text>}`. Reason MUST be non-empty (re-asks if absent). Hook reads this file at every Stop event and skips threshold-push (but still writes daily-report entries) until expiry. Mute is logged to that day's daily report.

### Collapse of prior queued tasks

- **AC-15 (collapses task #18 stuck-loop detector):** Stuck-loop pattern (>5 turns, > active_engagement_threshold without any progress signal) is one of the proposal types. When matched, the proposal cites: turn count, active engagement time, last commit hash, last meaningful file modification. Threshold-push fires when matched.

- **AC-16 (collapses task #22 sandbox-bypass audit):** Sandbox-bypass count per session is one of the captured metrics. When the count exceeds the operator's session baseline + 2σ, a proposal is written explaining "your sandbox-bypass rate this session is N (baseline: M)." This is the audit layer task #22 called for.

### Validation

- **AC-17:** `tests/test_chief_efficiency_officer.py` — at least 20 contract tests covering: turn-event capture, active-engagement computation with idle-gap subtraction, current-task cascading fallback, baseline comparison, proposal data-citation requirement (rejection of un-grounded narrative), three-surface output routing, mute mechanism, `jq`-absent fallback, no-baseline fallback (first session).

- **AC-18:** `tests/test_efficiency_review_command.py` — at least 8 tests covering `/efficiency review` Pattern A flow: accept / dismiss / mark-for-followup; empty queue handling; malformed proposal handling.

### Documentation

- **AC-19:** `skills/efficiency/SKILL.md` (NEW) — documents `/efficiency review`, `/efficiency today`, `/efficiency baseline`, `/efficiency mute`. ~200 LOC.

- **AC-20:** `docs/efficiency/chief-efficiency-officer.md` (NEW) — operator-facing explainer: what the CEO observes, what it doesn't, how to interpret proposals, how to tune thresholds, how the daily report is structured. ~150 LOC.

- **AC-21:** `spec/etc_sdlc.yaml` registers the `efficiency` skill + the `chief-efficiency-officer` Stop hook.

- **AC-22:** README updated: F019 row in shipping table, brief mention in /design skill description, test count updated.

- **AC-23:** `spec/chief-efficiency-officer.md` — PRD copy per F009 convention.

## Out of Scope (v1)

- **Per-feature active-time accounting** beyond the current-task detection. v1 captures session-level active engagement; v2 may attribute time across tasks more precisely.
- **Cross-session retrospectives** beyond the daily report. v2 may add weekly + monthly retrospective views.
- **Cost transparency.** Token spend / dollar cost per outcome — future feature; requires session-level token tracking that Claude Code may or may not expose.
- **Multi-operator comparison.** v1 is single-operator (you). Multi-operator baselines come if HCE customers want to compare operators within a team.
- **Public-API for the dataset.** v1 outputs files; v2 may add an HTTP/MCP surface so external dashboards can pull the data.
- **Auto-tuning thresholds.** v1 uses fixed sigma multipliers; v2 may adapt thresholds to operator behavior over time.
- **Article-recommended quarterly-config-review automation.** Different cadence, different surface. Separate skill (deferred).

## Technical Notes

- **Stop-hook ordering**: this hook MUST run before `check-completion-discipline.sh` and `auto-checkpoint.sh`. The reason: those hooks can `exit 2` and block the Stop event; if they fire first, the CEO never captures the turn event. Use `spec/etc_sdlc.yaml` ordering field (or position in the hook array) to control this.

- **Sandbox-bypass tracking**: requires a separate PreToolUse hook that detects `Bash` invocations with `dangerouslyDisableSandbox: true` and appends to `.etc_sdlc/efficiency/sandbox-bypasses.jsonl`. v1 ships this PreToolUse hook alongside the Stop hook. Schema: `{"event_id", "started_at", "command_snippet", "description"}`. The command_snippet is truncated to 100 chars; the description is captured as-is from the Bash invocation.

- **Idle-gap subtraction**: a 5-minute gap between consecutive Stop events means "operator went away" — not productivity loss. The threshold is tunable via env var, but 5 minutes is the venlink-incident-derived default (the operator confirmed at one point that gaps shorter than this are typical typing/thinking pauses).

- **Cascading fallback for orientation**: handles the case where the operator is between features OR in a non-feature task. v1 doesn't try to be clever; if all four fallbacks fail, the CEO records `null` and asks the operator in the daily report.

- **Baseline cold-start**: on the first few sessions (when sdlc_timing.py has < 5 features), z-score computation is unreliable. The hook skips threshold-push and proposal-queue writes when fewer than 5 features in baseline; only daily-report entries fire. Operator's baseline accumulates naturally.

- **False-positive cost**: every spurious proposal degrades operator trust. The dismiss/accept ratio in `dismissed/` is a signal — if dismissal rate > 50% of proposals, the thresholds need tuning. v1 doesn't auto-tune (out of scope) but the data is captured.

## Resolved Design Decisions (from 2026-05-14/15 conversation)

1. **Interaction model:** Hybrid — operator-pull always available + threshold-push rarely (only on 2σ-3σ z-score, with 3σ+ getting the inject).

2. **Voice:** Chief of Staff (names your stated intent + observed activity + the gap, doesn't prescribe). Escalates to data-only when CoS prompts are dismissed multiple times without behavior change.

3. **Surfaces:** Stack three — inject-into-next-turn (rare), daily report file (continuous), `/efficiency review` command (on-demand). Each for a different urgency level.

4. **Orientation:** Cascading fallback — state.yaml.build.feature → TodoWrite in_progress → most-recent state.yaml mtime → most-recent non-cache file mtime → ask in daily report.

5. **Data layer for v1:** Minimum viable — turn-event log + goal-vs-activity detector + sandbox-bypass counter. Cost transparency and per-task time accounting deferred to v2.

6. **Proposal output format:** Both — queue file (`.etc_sdlc/efficiency/proposals/<timestamp>-<topic>.md`) for granular operator review + daily report (`.etc_sdlc/efficiency/daily/<date>.md`) for aggregate visibility.

7. **Evidence-based constraint:** Every observation cites a data point + a baseline + the gap. Un-grounded narrative is rejected at write time (AC-10). NO hallucination tolerated.

8. **Stop-hook reflection architecture:** Implements Anthropic's published recommendation. Uses existing hook surface (Stop) rather than inventing new patterns. Composes with existing enforcement Stop hooks (check-completion-discipline, auto-checkpoint).

9. **Three queued tasks collapse:** F019 (Chief Efficiency Officer) supersedes task #18 (stuck-loop detector) + task #20 (operator-efficiency watchdog) + task #22 (sandbox-bypass audit) because they share architecture. Each is one proposal-type in the unified hook.

## Risks

1. **False-positive interruptions degrade trust** — mitigated by high firing threshold (3σ for inject, 2σ for proposal queue) + auto-mute mechanism + the dismiss-rate tracking that surfaces if thresholds are wrong.

2. **Baseline cold-start** — first sessions have unreliable baselines; v1 explicitly disables threshold-push and proposal queue when baseline has < 5 features. Daily report still works (informational only).

3. **Sandbox-bypass tracking via PreToolUse hook adds latency** — minimal, the hook just appends one line to a JSONL file; well under 100ms.

4. **Proposal queue growth** — operator might not review proposals frequently; queue could grow. v1 doesn't auto-archive; v2 may add a 30-day archive policy.

5. **Hallucinated proposals slip through if AC-10 grep is too permissive** — the rejection list is conservative; we may need to expand the forbidden-phrases list based on observed failure modes.

6. **The hook itself becomes part of the failure mode** — if `chief-efficiency-officer.sh` fails, Stop events still need to proceed. Hook MUST exit 0 on all internal errors (silent degradation); never block Stop on its own bugs.

## Source

- Operator session 2026-05-14 (the reframe — subject is operator, not agent; active time not wall clock; outcome-focused).
- Operator session 2026-05-15 (the evidence-based constraint — no hallucinated narrative; cite data points and baselines).
- Anthropic *How Claude Code Works in Large Codebases* (2026): Stop-hook reflection pattern.
- Venlink-platform incident 2026-05-12 (stuck-loop pattern documentation).
- Sandbox-bypass discipline memo 2026-05-15 (audit motivation).
- sdlc_timing.py MVP (commit `1a68f8d`) — baseline data layer this feature consumes.
- Three queued tasks (#18, #20, #22) collapsed into this single architectural piece.
