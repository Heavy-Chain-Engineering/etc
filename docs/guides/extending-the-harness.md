# Extending the Harness

How to add new capabilities to the etc engineering harness. This covers adding agents, hardening existing ones, extending the SDLC workflow, adding hooks, standards, and invariants.

## Adding a New Agent

### 1. Create the Agent File

Create `agents/<agent-name>.md` with this structure:

```markdown
---
name: agent-name
description: >
  One-paragraph description of what this agent does, when to use it, and when NOT to use it.
  Include 2-3 example blocks showing trigger → action → commentary.

  <example>
  Context: When the agent should be invoked.
  user: "Example user message"
  assistant: "How Claude should respond by invoking this agent"
  <commentary>Why this is the right trigger for this agent.</commentary>
  </example>

model: opus | sonnet
maxTurns: 15-200
tools: Read, Edit, Write, Bash, Grep, Glob
disallowedTools: [Write, Edit, NotebookEdit]  # for review-only agents
---

You are a [Role Name] — one-sentence identity statement.

## Before Starting (Non-Negotiable)

Read these files in order:
1. `~/.claude/standards/...` — relevant standards
2. Project-specific files

## Your Responsibilities

Numbered list of what this agent owns.

## Process

### Step 1: ...
### Step 2: ...

## Concrete Heuristics

Numbered checklists the agent can mechanically follow.

## Output Format

How the agent should structure its deliverables.

## Boundaries

### You DO
- ...

### You Do NOT
- ...

## Error Recovery

- IF [condition]: [action]

## Coordination

- **Reports to:** SEM
- **Receives from:** [upstream agents]
- **Validates with:** [downstream agents]
- **Escalates to:** [escalation targets]
- **Handoff format:** [what the output looks like]
```

### 2. Choose the Right Model

| Agent Type | Model | Rationale |
|-----------|-------|-----------|
| Review/checklist agents | `sonnet` | Mechanical verification, cost-efficient |
| Implementation agents | `opus` | Judgment-heavy, needs to write good code |
| Design/strategy agents | `opus` | Needs architectural reasoning |
| Orchestration (SEM) | `opus` | Complex multi-agent coordination |

### 3. Set Guardrails

- **`maxTurns`** — prevents runaway agents. Review agents: 15. Implementation: 50. SEM: 200.
- **`disallowedTools`** — review-only agents should have `[Write, Edit, NotebookEdit]` to prevent them from modifying code.
- **`tools`** — only grant what the agent needs. Don't give Bash to agents that don't need shell access.

### 4. Install the Agent

Copy the agent file to the active agents directory:

```bash
cp agents/my-agent.md ~/.claude/agents/my-agent.md
```

Or run the installer: `./install.sh`

### 5. Wire into the SDLC

If the agent belongs to a phase team, update:
- `~/.claude/standards/process/sdlc-phases.md` — add to the relevant phase team table
- `agents/sem.md` — add to the SEM's phase teams table

### 6. Verify

Test the agent by invoking it directly: "Use the [agent-name] agent to [task]."

---

## Hardening an Existing Agent

Use the 10-point hardening checklist from `docs/research/agent-hardening-research.md`:

| # | Criterion | What to Check |
|---|-----------|---------------|
| 1 | Examples in description | At least 2 `<example>` blocks with context/user/assistant/commentary |
| 2 | Before Starting section | Non-negotiable file reads before any action |
| 3 | Numbered process steps | Clear sequential workflow |
| 4 | Concrete heuristics | Checklists with specific, verifiable items |
| 5 | Output format | Structured deliverable format (tables, templates) |
| 6 | Boundaries (DO / Do NOT) | Explicit scope limits |
| 7 | Error recovery | IF/THEN patterns for common failures |
| 8 | Coordination section | Reports to, receives from, escalates to, handoff format |
| 9 | 80-200 lines | Long enough to be useful, short enough to fit context |
| 10 | Model selection | sonnet for mechanical, opus for judgment |

**Process:**
1. Read the agent file
2. Score against each criterion (pass/fail)
3. For each fail, add the missing section using the template above
4. Verify line count is 80-200
5. Test the agent on a real task to confirm it behaves correctly
6. Sync to `~/.claude/agents/`

---

## Adding a New SDLC Phase

### 1. Update the Phase Order

Edit `.sdlc/tracker.py` — add the phase name to `PHASE_ORDER` list in the correct position.

### 2. Add DoD Template

Edit `.sdlc/dod-templates.json` — add an entry for the new phase with its definition-of-done items (3-5 items).

### 3. Define the Phase

Edit `~/.claude/standards/process/sdlc-phases.md`:
- Add a `### [Phase Name] Phase` section with: Purpose, Team, Process (numbered steps), Output, How to invoke
- Add the phase to the Team Composition Summary table

### 4. Update the SEM

Edit `agents/sem.md`:
- Add the phase to the Phase Teams table
- Add a `### [Phase] Phase Pattern` section describing the SEM's specific behavior during this phase

### 5. Sync and Test

```bash
cp .sdlc/tracker.py ~/.claude/sdlc/tracker.py
cp .sdlc/dod-templates.json ~/.claude/sdlc/dod-templates.json
cp agents/sem.md ~/.claude/agents/sem.md

# Test initialization with the new phase
cd /tmp && mkdir test-project && cd test-project
python3 ~/.claude/sdlc/tracker.py init
python3 ~/.claude/sdlc/tracker.py status
```

Verify the new phase appears in the state and has the correct DoD items.

---

## Adding a New Hook

Hooks run automatically before or after tool use (Edit, Write, etc.).

### 1. Create the Hook Script

Create `hooks/<hook-name>.sh`:

```bash
#!/usr/bin/env bash
set -uo pipefail

# Hook receives tool arguments via environment variables:
#   $TOOL_NAME — the tool being called (Edit, Write, etc.)
#   $FILE_PATH — the file being modified (if applicable)

# Exit codes:
#   0 = pass (allow the operation)
#   2 = block (prevent the operation, show message to agent)

# Your check logic here
if some_condition_fails; then
    echo "BLOCKED: reason why"
    exit 2
fi
```

### 2. Register the Hook

Edit `settings-hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/<hook-name>.sh",
            "timeout": 10000,
            "statusMessage": "Running check..."
          }
        ]
      }
    ]
  }
}
```

### 3. Install

Copy to the active hooks directory:

```bash
cp hooks/<hook-name>.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/<hook-name>.sh
```

---

## Adding a New Standard

Standards are reference documents that agents read during their "Before Starting" phase.

### 1. Create the Standard

Create `standards/<category>/<standard-name>.md`:

```markdown
# Standard Name

## Status: MANDATORY | REFERENCE
## Applies to: [list of agents that should read this]

[Content]
```

Categories: `code/`, `testing/`, `process/`, `security/`, `architecture/`, `quality/`

### 2. Wire into Agents

Update the "Before Starting" section of each relevant agent to include:
```
N. `~/.claude/standards/<category>/<standard-name>.md` — description
```

### 3. Install

```bash
cp standards/<category>/<standard-name>.md ~/.claude/standards/<category>/
```

---

## Adding a New Invariant

Invariants are machine-verifiable constraints enforced by the `check-invariants.sh` hook.

### 1. Add to INVARIANTS.md

In the project's `INVARIANTS.md` (or create one):

```markdown
## INV-NNN: Short description of the constraint
- **Layers:** agent-instructions, hook, test
- **Verify:** `shell command that produces empty stdout on pass`
- **Fail action:** Block edit | Block merge | Warn
- **Rationale:** Why this constraint exists.
```

The verify command MUST:
- Produce **empty stdout** when the invariant holds
- Produce **non-empty stdout** (the violations) when it's broken
- Be a single-line shell command (pipes are fine)

### 2. Test It

```bash
# Should produce empty output (pass):
eval "your verify command"

# Intentionally break the invariant, verify it catches it:
# (make a temporary change, run the command, confirm output)
```

### 3. Cascading

Invariants cascade from project root to subdirectories. A component can have its own `INVARIANTS.md` that adds constraints specific to that component. The hook walks up the directory tree and collects all invariants files.

---

## Quick Reference: What to Update for Each Extension Type

| Extension | Files to Update |
|-----------|----------------|
| New agent | `agents/<name>.md`, `~/.claude/agents/<name>.md`, `sdlc-phases.md` (if phase team), `sem.md` (if phase team) |
| Harden agent | `agents/<name>.md`, `~/.claude/agents/<name>.md` |
| New SDLC phase | `tracker.py`, `dod-templates.json`, `sdlc-phases.md`, `sem.md` |
| New hook | `hooks/<name>.sh`, `settings-hooks.json` |
| New standard | `standards/<cat>/<name>.md`, agent "Before Starting" sections |
| New invariant | Project's `INVARIANTS.md` |
