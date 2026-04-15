---
incident_id: 2026-04-15-pretooluse-edit-write-hooks-check-required-reading
filed_at: '2026-04-15T21:33:50Z'
filed_by: jason
status: escalated
failure_type: blocked on user acceptance
target: PreToolUse Edit|Write hooks check-required-reading.sh and check-phase-gate.sh
  add ~15-30 seconds of latency per parallel /build wave, blocking v1.6 release readiness
fix_kind: edit_files
fix_detail: ''
rollback_kind: Other
rollback_detail: It will work. You're just reconfigureing claude, I think.
gates_bypassed: []
subagent: hotfix-responder
files_touched: []
completed_at: '2026-04-15T21:45:00Z'
postmortem: null
---

# Incident: PreToolUse Edit|Write hooks check-required-reading.sh and check-phase-gate.sh add ~15-30 seconds of latency per parallel /build wave, blocking v1.6 release readiness

Filed at 2026-04-15T21:33:50Z by jason.

See YAML frontmatter above for the structured record. The subagent will
append execution notes below as it runs.

## Execution notes (hotfix-responder)

**Status: escalated. No files modified.**

The subagent halted before taking any edit action. Two independent reasons,
each sufficient on its own:

### 1. Description guardrail rejection (manifest: "Description Guardrail")

The incident `target` is "PreToolUse Edit|Write hooks ... add ~15-30
seconds of latency per parallel /build wave, blocking v1.6 release
readiness." Parsing against the required shape:

- System reference: yes (`hooks/check-required-reading.sh`,
  `hooks/check-phase-gate.sh`, `spec/etc_sdlc.yaml`).
- Failure mode: **no**. "Adds latency, blocks release readiness" is a
  performance/scheduling concern, not a failure mode. There is no error
  code, no outage, no broken behavior, no user-visible fault, nothing
  returning the wrong answer. A build wave taking longer than the
  operator would like is a cost problem, not an incident.

The `/hotfix` lane exists for production failures (500s, deadlocks, data
corruption, crashes). Performance optimization of the harness's own
build pipeline is `/spec` lane work — design, profiling, tradeoff
analysis, test updates, and operator review, not a blind reconfiguration
in a fire drill.

### 2. The "fix" is a gate disablement disguised as a DSL move

Even setting aside the guardrail, the dispatch brief's proposed fix has
a correctness problem that the earlier session already documented and
correctly escalated to a brief. Read
`spec/hook-cost-reduction-brief.md` in full — the exact scenario in
this incident is analyzed there as "The Obvious Fix That Doesn't Work":

> Both scripts read `.tool_input.file_path` from stdin — that field only
> exists on PreToolUse Edit|Write events. At SubagentStart, the script
> input has `cwd`, `agent_type`, and `transcript_path` — no
> `tool_input`. If we move the registration without rewriting the
> scripts [...] → **always passes, effectively disabled**.
>
> Moving the registrations without rewriting the scripts is disabling
> the gates, not optimizing them.

I verified this against the live scripts:

- `hooks/check-phase-gate.sh` line 20: `if [[ -z "$FILE_PATH" ]]; then
  exit 0; fi`. With no `tool_input.file_path` on stdin at
  SubagentStart, `FILE_PATH` is empty → early-exit → gate disabled.
- `hooks/check-required-reading.sh` line 17 reads
  `.tool_input.file_path` from stdin (empty at SubagentStart). The
  `REL_PATH` computed at line 48-51 is therefore also empty. The
  `IN_SCOPE` check (line 67-69) then compares empty string to every
  scope pattern and hits the `"File not in task scope — allow"`
  early-exit → gate disabled.

The dispatch brief acknowledges this and frames it as an acceptable
tradeoff ("the operator considered this tradeoff and is still saying
'it will work'"). I cannot make that call.

My manifest's gate-bypass authorization covers bypassing gates for
**my own execution** during the hotfix — not **permanently removing
gates for all future subagents system-wide**. The proposed DSL change
is the second, not the first. That is a semantic change to the
harness's gate architecture, and my manifest explicitly says: "Do NOT
rewrite the scripts to operate on subagent-level state. That would be
a meaningful semantic refactor and is out of scope for a hotfix."

The "reconfigure, don't rewrite" framing attempts to route around that
constraint by changing *where* the scripts run instead of *what* they
do — but the net effect is the same (two gates become no-ops) and the
architectural change is arguably larger (a rewrite replaces the gate
logic; a move removes it outright).

### What the operator should do next

1. Read `spec/hook-cost-reduction-brief.md` in full — specifically the
   "Why the Obvious Fix Doesn't Work" section and the three-option
   analysis. The earlier session already did the work and reached a
   well-reasoned conclusion.
2. Run the proposed zeroth step from the brief: add hook-timing
   observability (~30 min) by appending JSONL lines from each hook
   script. That turns the cost question from guesswork into data and
   reveals whether the target hooks are actually the bottleneck. It
   is entirely possible the real cost is elsewhere (the brief flags
   `adversarial-review` at SubagentStop as potentially 30-60s per
   subagent, which would dwarf the Edit-time hooks).
3. With profiling data in hand, file `/spec` for the appropriate
   optimization (Option A, B, or C from the brief) with a concrete
   latency budget and test plan.
4. If v1.6 release readiness genuinely cannot wait for that process,
   the shortest safe path is **Option B (coalescing)** from the brief:
   wrap the 5 existing PreToolUse scripts into one `check-edit-preflight.sh`
   that runs them in sequence in a single subprocess. Zero semantic
   change, saves bash startup on 4 of the 5. That is still `/spec`
   work, not `/hotfix` work, but it is the option with the lowest
   correctness risk if the schedule pressure is real.

No files were modified. No gates were bypassed (none fired, because I
took no edit actions). No commits were created.
