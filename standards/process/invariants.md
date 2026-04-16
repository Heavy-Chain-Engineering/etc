# Project Invariants Standard

## Status: ACTIVE
## Applies to: All agents, all phases

## Overview

Invariants are non-negotiable project rules that are **enforced**, not just documented.
A spec that nothing enforces is just a wish. Invariants are encoded across multiple
independent enforcement layers so that an agent has to fail at **every single layer**
to ship a violation.

Every project SHOULD have an `INVARIANTS.md` file at its root. Components MAY have
their own `INVARIANTS.md` files that add additional constraints specific to that
component's domain.

## What Invariants Are

- **Non-negotiable rules** that must always hold true in the codebase
- **Machine-verifiable** — each invariant includes a command that checks compliance
- **Layered** — enforced by multiple independent mechanisms (hooks, tests, agent instructions, CI)
- **Additive** — component invariants add to project invariants; they never override or relax them

Invariants are NOT:
- Style preferences (use a linter for that)
- Guidelines that sometimes have exceptions (those are standards)
- Aspirational goals (those are roadmap items)

## INVARIANTS.md File Format

The file is human-readable Markdown that is also machine-parseable. Each invariant is
a level-2 heading with a specific structure.

### Required Fields

```markdown
## INV-001: Short description of the invariant
- **Layers:** comma-separated list of enforcement layers
- **Verify:** `shell command that returns non-empty output on VIOLATION`
- **Fail action:** Block merge | Warn | Block edit
```

### Field Definitions

| Field | Description |
|-------|-------------|
| **ID** | Unique identifier in the heading, format `INV-NNN` |
| **Description** | Human-readable explanation after the colon |
| **Layers** | Which enforcement mechanisms check this invariant |
| **Verify** | A shell command. **Non-empty stdout = violation found.** Empty stdout = pass. |
| **Fail action** | What happens on violation: `Block merge`, `Block edit`, or `Warn` |

### Optional Fields

```markdown
- **Rationale:** Why this invariant exists
- **Exempt:** `# invariant-exempt: INV-001` comment pattern to exempt specific lines
- **Scope:** Which files/directories this applies to (default: entire project)
```

### Enforcement Layers

| Layer | Mechanism | When |
|-------|-----------|------|
| `agent-instructions` | CLAUDE.md or agent prompt includes the rule | Before code generation |
| `hook` | Claude Code PreToolUse hook (`check-invariants.sh`) | On every Edit/Write |
| `test` | Pytest/unittest validates the invariant | On test run |
| `ci` | CI pipeline checks invariants | On push/PR |
| `runtime` | Application-level validation | At execution time |
| `db` | Database constraints (triggers, CHECK, FK) | On data write |

The more layers an invariant has, the harder it is to violate. Critical invariants
(security, data integrity) should have 3+ layers.

## Cascading

Invariants cascade from broad to narrow scope. All levels are additive.

```
~/.claude/INVARIANTS.md          # Global engineering invariants (all projects)
  └── project/INVARIANTS.md      # Project-level invariants
       └── project/src/auth/INVARIANTS.md   # Component-level invariants
```

When the enforcement hook runs, it collects invariants from:
1. The project root `INVARIANTS.md`
2. Any `INVARIANTS.md` in ancestor directories of the file being edited, up to the project root

Component invariants **add** constraints. They cannot relax or override parent invariants.

## Invariant Categories

### Architecture
Layer boundaries, dependency direction, module isolation.
```markdown
## INV-010: No circular imports between top-level packages
- **Layers:** hook, test, ci
- **Verify:** `python -c "import importlib; ..."`
- **Fail action:** Block merge
```

### Data
Validation rules, nullable constraints, schema compliance.
```markdown
## INV-020: All database models must have created_at and updated_at
- **Layers:** hook, test, db
- **Verify:** `grep -rn 'class.*Model' src/models/ | xargs grep -L 'created_at'`
- **Fail action:** Block merge
```

### Security
Authentication requirements, input sanitization, secrets handling.
```markdown
## INV-030: All API endpoints require authentication
- **Layers:** agent-instructions, hook, test
- **Verify:** `grep -rn '@router' src/ | grep -v 'Depends(get_current_user)' | grep -v '/health'`
- **Fail action:** Block merge
```

### Testing
Coverage thresholds, required test types, test-to-code ratios.
```markdown
## INV-040: Every module in src/ has a corresponding test file
- **Layers:** hook, ci
- **Verify:** `for f in src/**/*.py; do test -f "tests/test_$(basename $f)" || echo "$f"; done`
- **Fail action:** Block edit
```

## Writing Good Verify Commands

1. **Return non-empty output on violation, empty on pass.** The hook treats any stdout as a failure.
2. **Keep commands fast.** Grep-based checks are ideal. Avoid commands that compile, install, or make network calls.
3. **Use the exempt pattern.** Allow `# invariant-exempt: INV-NNN` comments for intentional exceptions.
4. **Be specific.** Narrow the file glob to only the relevant directories.
5. **Test your verify command.** Run it manually — it should produce output only when the invariant is actually violated.

## Cross-Boundary Concepts (CONCEPT-NNN)

In addition to single-context invariants (`INV-NNN`), `INVARIANTS.md` supports
**cross-boundary concept entries** (`CONCEPT-NNN`). These enforce that the same
concept means the same thing across bounded contexts.

### When to Use CONCEPT vs INV

| Property | INV-NNN | CONCEPT-NNN |
|----------|---------|-------------|
| Scope | Single file/directory | Cross-boundary (multiple contexts) |
| Verify target | Files being edited | All files in listed contexts |
| Trigger | PreToolUse (on every Edit) | Verify phase (not per-edit) |
| Hook | `check-invariants.sh` | `check-concepts.sh` |
| Exemption | `# invariant-exempt: INV-NNN` | `# concept-exempt: CONCEPT-NNN` |
| Added by | Developer | Architect (requires multi-context knowledge) |

### CONCEPT Entry Format

```markdown
## CONCEPT-001: Short description of the cross-boundary concept

Prose explanation of what this concept means and why it must be
consistent across boundaries.

- **Contexts:** Comma-separated list of bounded contexts
- **Precondition:** What the caller/consumer must provide
- **Postcondition:** What the provider/producer guarantees
- **Invariant:** The property that must always hold across all contexts
- **Layers:** comma-separated enforcement layers
- **Verify:** `shell command that returns non-empty output on VIOLATION`
- **Fail action:** Block merge | Warn
```

### Design by Contract Fields

Every CONCEPT entry includes three DbC fields (per Jim Snyder's recommendation):

- **Precondition**: obligation of the caller — what must be true before the concept
  is used. "What does the consumer provide?"
- **Postcondition**: obligation of the provider — what is guaranteed after the concept
  is used. "What does the producer deliver?"
- **Invariant**: the property that holds at all times across all listed contexts.
  "What must always be true regardless of caller?"

The dependency direction principle applies: if context A depends on context B's
concept, context B owns the contract.

### Vocabulary Registry

For concepts where the problem is synonym drift, add a vocabulary sub-section:

```markdown
### Vocabulary: canonical_name
| Context | Term | Canonical |
|---------|------|-----------|
| Context A | "term_in_a" | canonical_term |
| Context B | "term_in_b" | canonical_term |
- **Verify:** `python3 scripts/check-vocabulary.py canonical_name`
```

The vocabulary table declares, per bounded context, what terms that context uses
and what canonical term each maps to. The verify script (`scripts/check-vocabulary.py`)
checks that each context's source code uses only the terms declared for that context.

### Enforcement

CONCEPT entries are enforced by `hooks/check-concepts.sh`, which runs at verify
phase (not per-edit). This separation exists because CONCEPT verify commands scan
multiple directories and are inherently slower than single-file INV checks.

The compiler (`compile-sdlc.py`) validates CONCEPT entry syntax during compilation,
checking for all required fields.

## Lifecycle

1. **Propose** — Anyone can propose an invariant via PR
2. **Review** — Team reviews the invariant, its verify command, and its enforcement layers
3. **Activate** — Merge the invariant into `INVARIANTS.md`; it is now enforced
4. **Exempt** — Individual lines can be exempted with `# invariant-exempt: INV-NNN` or `# concept-exempt: CONCEPT-NNN`
5. **Retire** — Remove the invariant from `INVARIANTS.md` when it is no longer relevant
