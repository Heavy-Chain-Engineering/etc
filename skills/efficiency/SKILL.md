---
name: efficiency
description: Chief Efficiency Officer operator commands. Review proposals queued by the Stop-hook reflection layer (F019), read today's efficiency report, query operator velocity baseline, mute threshold-push interrupts. All observations are evidence-based — every proposal cites data points and operator baseline; no hallucinated narrative.
---

# /efficiency — Operator commands for the Chief Efficiency Officer

The Chief Efficiency Officer (F019) is a Stop-hook reflection layer that
observes operator efficiency, computes active-engagement against baseline,
and writes evidence-cited proposals to a queue + daily report. This skill
is the operator-facing command surface for reviewing those outputs.

The CEO does NOT block work. It observes, reflects, and proposes. The
operator decides what to do with each observation.

## Usage

```
/efficiency review    -- walk queued proposals one at a time, Pattern A
/efficiency today     -- print today's rolling efficiency report
/efficiency baseline  -- show operator velocity baseline (sdlc_timing.py)
/efficiency mute --until <iso8601> --reason "<text>"  -- silence threshold-push for a window
```

## Workflow

### `/efficiency review`

Reads `.etc_sdlc/efficiency/proposals/*.md` (oldest first). For each
proposal, displays the data-cited observation to the operator and asks
via Pattern A (`AskUserQuestion`):

```
AskUserQuestion(
  questions: [{
    question: "Proposal: <proposal title>. <data points summary>. What to do?",
    header: "Proposal",
    multiSelect: false,
    options: [
      {
        label: "Accept (move to accepted/, plan a response)",
        description: "The observation is correct and worth acting on. Moves the proposal to accepted/ for future reference. Operator decides the response separately."
      },
      {
        label: "Dismiss (false positive)",
        description: "The observation is wrong, the data is misleading, or there's a legitimate reason for the apparent anomaly. Moves the proposal to dismissed/ — kept for false-positive-rate tracking but not surfaced again."
      },
      {
        label: "Mark for follow-up feature",
        description: "The observation is correct AND warrants a harness feature. Creates a task in the task list referencing the proposal and moves the proposal to followups/."
      },
      {
        label: "Skip — review later",
        description: "Leave in the queue; come back to it."
      }
    ]
  }]
)
```

After processing each proposal, move to the next one. When the queue is
empty, render the summary:

```
Reviewed N proposals. Accepted: A. Dismissed: D. Marked for follow-up: F. Skipped: S.
```

### `/efficiency today`

Reads `.etc_sdlc/efficiency/daily/<current-date>.md` and prints it to
stdout. If today's file doesn't exist yet, print: "No efficiency
observations recorded today. Stop hook fires on every turn end."

### `/efficiency baseline`

Invokes `python3 ~/.claude/scripts/sdlc_timing.py --baseline` and prints
the output. Convenience wrapper.

### `/efficiency mute --until <iso8601> --reason "<text>"`

Writes `.etc_sdlc/efficiency/mute.yaml`:

```yaml
until: 2026-05-15T18:00:00Z
reason: "Long-running debug session on regression X — expecting > 3h active"
muted_at: 2026-05-15T10:00:00Z
```

Reason MUST be non-empty (re-ask via Pattern B if empty). The mute file
is read by the CEO Stop hook on every fire — when present and `until` is
in the future, threshold-push is suppressed (daily report still updates).

## Constraints

- The CEO is observation-only. This skill does NOT modify hook behavior,
  re-tune thresholds, or alter the data layer. Configuration changes
  happen via env vars (`CEO_IDLE_THRESHOLD_MINUTES`, `CEO_SIGMA_PUSH`,
  etc.) on the operator's shell, not via this skill.
- **Evidence-based discipline applies to operator review too.** When
  dismissing a proposal as "false positive," the operator should glance
  at the cited data points — many "false positives" are actually correct
  observations the operator hadn't internalized.
- Dismissed proposals are NOT deleted. They're moved to `dismissed/<date>.md`
  for false-positive-rate tracking. If dismiss rate exceeds 50% of
  proposals, the CEO thresholds are wrong and need tuning (operator
  responsibility for v1; auto-tuning is v2).

## See also

- F019 spec: `spec/chief-efficiency-officer.md`
- `hooks/chief-efficiency-officer.sh` — the Stop hook
- `hooks/sandbox-bypass-tracker.sh` — PreToolUse hook for bypass counting
- `scripts/sdlc_timing.py` — operator velocity baseline data source
- Anthropic *How Claude Code Works in Large Codebases* — the Stop-hook
  reflection pattern this skill consumes
