# Conditional Onboarding Injection

`hooks/inject-standards.sh` emits a system-overlay block at every SubagentStart event.
As of F024, three sections of that overlay are **conditional**: emitted only when role or
task properties indicate they are relevant. This standard is the normative reference for
which sections are conditional, the gating predicate for each, the safe-default policy,
and the detection mechanisms the hook uses.

## Status: MANDATORY

## Applies to: hooks/inject-standards.sh; any operator modifying section presence in the subagent system overlay

## Base sections — always emitted

The following 9 sections are **invariant**: they appear in every dispatch regardless of
role or task. They are never gated, never suppressed, and never reordered.

1. `### User Interaction (subagents escalate; do not invoke directly)`
2. `### TDD (Red/Green/Refactor)`
3. `### Code Standards`
4. `### Architectural Rules`
5. `### Process`
6. `### Research Discipline`
7. `### Completion Discipline`
8. `### Diagnostic Discipline`
9. `### Sandbox Discipline`

Sections 8–9 are non-negotiable because they govern diagnostic dismissal and sandbox
behavior — failure modes that occur regardless of role or task type.

The trailing injections (Active Task context, Project Invariants, Known Antipatterns) are
already conditional via `[[ -f ]]` / `[[ -d ]]` guards that predate F024. F024 does not
modify those guards.

## Conditional sections

### 1. Git Commit Discipline

**Heading in overlay:** `### Git Commit Discipline`

**Gating predicate:** Emitted ONLY when `agent_type` ∈
`{backend-developer, frontend-developer, devops-engineer}`.

**Rationale:** The section addresses shared-git-index races in parallel-fan-out. Roles
that do not write production code in `src/` (technical-writer drafting ADRs,
spec-enforcer reading the repo, code-reviewer reading without writing) do not hit this
race class. Injecting the section into non-developer dispatches is irrelevant noise.

**Safe default:** When `agent_type` is absent, null, the literal string `"unknown"`, or
any value not in the allow-list — emit the section. Unknown role identity is likelier to
be a developer role than not; an un-covered git-index race is worse than one extra
injected section. (Per ADR-F024-002 — `docs/adrs/F024-002-safe-default-policy.md`.)

### 2. Stub-Marker Grep Contract

**Heading in overlay:** `### Stub-Marker Grep Contract for spec-enforcer`

**Gating predicate:** Emitted ONLY when `agent_type == "spec-enforcer"`.

**Rationale:** The contract documents spec-enforcer's verify-time grep behavior
exclusively. Non-enforcer agents do not run the grep; the section adds noise to every
other dispatch without benefit.

**Safe default:** When `agent_type` is absent, null, `"unknown"`, or any non-spec-enforcer
value — suppress the section. The section is verbose and role-specific; over-injection
here costs more than under-injection. This is the asymmetric exception to the Git Commit
safe-default rule. (Per ADR-F024-002 — `docs/adrs/F024-002-safe-default-policy.md`.)

### 3. User-Flow Completeness for User-Facing ACs

**Heading in overlay:** `### User-Flow Completeness for User-Facing ACs`

**Gating predicate:** Emitted ONLY when the active in-progress task's YAML contains at
least one acceptance criterion matching the User-flow sentence pattern:

```
As <actor>, navigate from
```

Specifically: the literal substring `As ` appears and, later in the same sentence (before
the next `.` or newline), the literal substring `, navigate from` appears.

The scan is restricted to the `acceptance_criteria:` YAML field. Other task fields
(`description`, `requires_reading`, etc.) are not scanned.

Only the FIRST in-progress task is scanned (consistent with the existing task-loop
behavior at lines 172-184 of `hooks/inject-standards.sh`).

**Safe default:** When no task YAML is present, when the task YAML cannot be parsed (YAML
error), or when `cwd` is missing from the SubagentStart payload — emit the section. User-
flow wiring rules are fundamental for user-facing tasks; missing task context is not a
reliable signal that the rule is irrelevant. Stderr WARN is emitted on malformed YAML;
the hook still exits 0.

## Detection mechanisms

### Role detection

The hook reads `agent_type` from the SubagentStart JSON payload received on stdin.
Extraction is at line 14 of `hooks/inject-standards.sh` via `jq -r`. No eval, no command
interpolation — special characters in `agent_type` are safely string-compared only.

The developer-role allow-list is a bash array literal in the hook:

```bash
_DEVELOPER_ROLES=("backend-developer" "frontend-developer" "devops-engineer")
```

**Maintenance cost:** Future roles (e.g., `data-engineer`, `ml-engineer`) require an
explicit entry in `_DEVELOPER_ROLES` to receive Git Commit Discipline. The safe-default
(over-inject on unknown) means a new developer role added without updating the list
receives the section anyway — but updating the list makes intent explicit and greppable.

EC-006 (spec.md): `agent_type == "unknown"` (literal string) is treated identically to
absent — safe defaults per section rules above apply.

EC-007 (spec.md): the allow-list is the maintenance cost of the safe-default-on-unknown
policy. When a new developer role ships, update `_DEVELOPER_ROLES` in the same PR.

### Task-AC scan

The hook finds the first task YAML with `status: in_progress` via the existing loop at
lines 172-184 of `hooks/inject-standards.sh`. F024 adds a content scan of that task's
`acceptance_criteria:` field using a Python subprocess:

```python
import yaml, sys, re
data = yaml.safe_load(sys.stdin)
acs = data.get("acceptance_criteria", [])
pattern = re.compile(r"As .+?, navigate from")
sys.exit(0 if any(pattern.search(str(ac)) for ac in acs) else 1)
```

`yaml.safe_load` only — no `exec`, no `eval`. Malformed YAML triggers stderr WARN and
fall-through to safe-default (emit the section).

EC-001 (spec.md): only the first in-progress task is scanned. Multi-task in-progress is
rare; if a user-flow AC is present in a later task, the dispatch will still show the
developer task's full AC list and the team will catch it.

EC-005 (spec.md): only `acceptance_criteria` is scanned. User-flow sentences appearing
in `description` or `requires_reading` fields do not trigger injection.

## Asymmetric safe-default policy

Two sections have opposite safe defaults. The asymmetry is deliberate and documented in
ADR-F024-002 (`docs/adrs/F024-002-safe-default-policy.md`).

| Section | Unknown-role default | Rationale |
|---|---|---|
| Git Commit Discipline | Emit (over-inject) | Cheap; covers a real git-index race class; developer roles far outnumber non-developer roles in dispatch volume |
| Stub-Marker Grep Contract | Suppress (under-inject) | Verbose; clearly role-specific; cost of over-injection (noise in non-enforcer context) > cost of under-injection (enforcer already has the contract in role manifest) |
| User-Flow Completeness | Emit when task context absent (over-inject) | Cheap; user-flow wiring is fundamental; missing task context is not a reliable signal |

The rule of thumb: **over-inject when the section is cheap and the risk of the gap is
operational** (missed git discipline in a race scenario). **Under-inject when the section
is verbose and the gap risk is zero** (spec-enforcer already has the contract; injecting
it into all other roles is pure noise).

## Section ordering invariant

When all conditional sections are emitted, their position is unchanged from the pre-F024
baseline. When a conditional section is suppressed, the following base section appears
earlier — no base-section reordering occurs.

The full canonical order (all conditionals emitted, i.e., `backend-developer` role +
user-flow task AC):

```
### User Interaction
### TDD (Red/Green/Refactor)
### Code Standards
### Architectural Rules
### Process
### Git Commit Discipline          ← conditional (developer roles)
### Research Discipline
### User-Flow Completeness         ← conditional (user-flow ACs)
### Stub-Marker Grep Contract      ← conditional (spec-enforcer only)
### Completion Discipline
### Diagnostic Discipline
### Sandbox Discipline
[trailing injections: Active Task, INVARIANTS.md, antipatterns.md]
```

## Forward-only

F024 applies to subagent dispatches authored after the F024 release tag. Pre-F024
dispatches were always-emit; F024 makes them sometimes-suppress. The worst-case post-F024
behavior (all conditionals fire → full emission) is byte-equivalent to pre-F024 behavior.
No pre-F024 dispatch is re-issued or retroactively affected.

Legacy specs (F001–F023) whose task YAMLs predate F024 may not carry User-flow sentence
patterns in their ACs. The safe-default (emit on absent task YAML) ensures those
dispatches still receive the section if applicable.

## ADR citations

- **ADR-F024-001 — Conditional system-overlay sections** (`docs/adrs/F024-001-conditional-sections.md`):
  gating predicates, base-sections-invariant boundary, hook-layer placement decision, and
  hardcoded developer-role allow-list rationale.

- **ADR-F024-002 — Safe-default policy: over-inject on unknown for cheap sections, under-inject for verbose role-specific sections** (`docs/adrs/F024-002-safe-default-policy.md`):
  the asymmetric safe-default split, cost model for over- vs. under-injection, and the
  per-section rationale that justifies Git Commit and Stub-Marker having opposite defaults.
