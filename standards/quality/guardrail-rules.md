# Guardrail Rules -- Post-Output Quality Validation

Status: MANDATORY for code output, RECOMMENDED for documents

Guardrail rules validate agent output after execution. Unlike pre-execution gates
(TDD, invariants, required reading), guardrails catch issues in what was produced.

These rules are enforced by the ci-pipeline agent hook at Stop time and by the
task-completion agent hook when tasks are marked done.

## Rule Catalog

### GR-001: Anti-Pattern Scan (Severity: CRITICAL)

Detects common anti-patterns in code and specification output:

| Pattern | Why It Is Bad |
|---------|-------------|
| Boolean flag sets (3+ is_/has_/can_ identifiers) | Indicates a state machine masquerading as boolean flags |
| Hardcoded enum lists | Should be a database-backed or configuration-driven enum |
| Legacy field mapping tables | Indicates leaking legacy concepts into the new domain model |

Applies to: research reports, PRDs, code
Action on violation: Block and require refactoring

### GR-002: Output Schema Validation (Severity: HIGH)

Agent outputs must contain required sections based on output type:

| Output Type | Required Sections |
|-------------|-------------------|
| Research report | Summary, Findings, Recommendations |
| PRD | Requirements, Scope |
| Code | At least one function or class definition |
| ADR | Context, Decision, Consequences |
| Test file | At least one test function or test class |

Action on violation: Block and specify which sections are missing

### GR-003: Spec Compliance (Severity: CRITICAL)

Agent output must satisfy the acceptance criteria from the originating PRD or task
file. This is an LLM-based check -- the verifier agent compares the deliverable
against each acceptance criterion and reports which criteria are satisfied, which
are not (with specific gaps), and whether the output contradicts any requirement.

Applies to: All output types when a PRD or task file exists
Action on violation: Block with specific unmet criteria listed

### GR-004: Domain Fidelity (Severity: CRITICAL)

Agent output must not contradict domain axioms. Domain axioms are loaded from
spec/domain-model.md and source materials classified as domain_truth.

This is an LLM-based check. The verifier compares output against axioms and flags
only clear contradictions (not omissions).

Applies to: All specification and implementation output
Action on violation: Block -- domain contradictions cascade through all downstream work

### GR-005: Security Scan (Severity: HIGH)

Regex-based detection of common security vulnerabilities in code output:
- String interpolation in SQL queries (f-strings, percent-formatting, .format())
- Credential assignments with literal string values (8+ characters)
- Direct unsafe DOM manipulation
- Unsafe deserialization without explicit safe loaders

Applies to: Code output only
Action on violation: Block and identify the specific vulnerability

### GR-006: Coverage Gate (Severity: HIGH)

Test coverage must meet the project threshold (default: 98%). The verifier parses
coverage output from pytest-cov or coverage.py.

Applies to: Code output when tests exist
Action on violation: Block with coverage percentage and deficit

### GR-007: TDD Verification (Severity: MEDIUM)

When implementation code is written, corresponding test code must also be present.
Checks for test definitions alongside implementation definitions.

Applies to: Code output
Action on violation: Warn (medium severity) -- the pre-execution TDD hook should
have caught this, so a post-execution violation indicates the hook was bypassed

## Retry on Guardrail Failure

When a guardrail blocks output, the system follows this pattern:

1. First failure: Block with detailed violation feedback. The agent receives
   the violation details and attempts to fix the issue.
2. Second failure (same rule): Block again with accumulated context from both
   attempts. The agent gets one more chance.
3. Third failure: Escalate with continue=false and stopReason.
   The agent is killed and the failure is surfaced to the human.

This mirrors a real code review cycle: reviewer sends feedback, developer fixes,
reviewer checks again. After 2-3 rounds, it escalates to a lead.
