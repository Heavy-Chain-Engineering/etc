# Spec Enforcement Agent — Design

**Date:** 2026-02-28
**Status:** Approved
**Problem:** No agent owns "does this output match what the spec said to build?" Enforcement is distributed across guardrails (schema), verifier (tests), and code-reviewer (quality), but none compare deliverables against PRD requirements.

## Decision

Build a **dual-mode spec enforcer**: a guardrail rule in the middleware pipeline (runs on every output) and a standalone agent definition (for deeper SEM-directed analysis at phase gates).

### Failure modes addressed

1. **Spec drift** — implementation subtly diverges from PRD
2. **Acceptance gap** — code passes tests but doesn't satisfy acceptance criteria
3. **Cross-phase corruption** — requirements degrade through handoffs (PRD → design → tasks → code)

## Architecture

### Component 1: `SpecComplianceRule` (guardrail rule)

A new `GuardrailRule` subclass in `guardrails.py`. Follows the `DomainFidelityRule` pattern — LLM-based check via PydanticAI with structured output and test injection support.

**Severity:** Critical (hard block — non-compliant outputs are rejected)

**Input (via context dict):**
- `prd`: str — the PRD text
- `acceptance_criteria`: list[str] — acceptance criteria
- `task_description`: str — what this agent was asked to do

**Opt-in pattern:** Only fires when context contains `prd` and `acceptance_criteria`. Passes silently otherwise (same as `DomainFidelityRule` with `domain_axioms`).

**Output structure:**
```python
{
    "violations": [
        {
            "requirement": "User must be able to filter by date range",
            "verdict": "NOT_SATISFIED",
            "evidence": "Output implements keyword search only, no date filtering",
            "output_excerpt": "..."
        }
    ],
    "coverage": {
        "total_requirements": 5,
        "satisfied": 3,
        "not_satisfied": 1,
        "not_applicable": 1
    }
}
```

**Adversarial prompt:** The LLM is told to find violations, not confirm compliance. Must cite specific requirements and specific output excerpts for each violation.

**Context cost mitigation:** The rule uses `task_description` to filter acceptance criteria to only the requirements relevant to the current task. A full PRD may have 50 requirements; a single task maps to 2-3.

### Component 2: `spec-enforcer.md` (agent definition)

Standalone agent for SEM-directed deep analysis. Read-only (no Write/Edit tools). Adversarial personality.

**Tools:** Read, Grep, Glob, Bash
**Model:** sonnet
**MaxTurns:** 15

**Output format:**
```
SPEC COMPLIANCE: [scope]

PRD: [prd path]
Acceptance Criteria: [N total]

VIOLATIONS:
[V1] requirement — "User must be able to filter by date range"
  Expected: Date range filter on search results
  Actual: No date filtering implemented
  Evidence: [excerpt from output]

SATISFIED:
[S1] "User must see paginated results" — PASS

VERDICT: COMPLIANT | NON-COMPLIANT
  Satisfied: N/N | Violations: N
```

## Integration

- **GuardrailMiddleware:** Add `SpecComplianceRule` to default rule list
- **SEM:** Must pass `prd` and `acceptance_criteria` in context when spawning agents (new requirement)
- **Database:** No schema changes. Uses existing `guardrail_checks` table
- **Events:** Critical failures emit `GUARDRAIL_VIOLATION` via existing `emit_guardrail_violation`

## Boundaries

| Does | Does Not |
|------|----------|
| Compare output against PRD requirements | Fix non-compliant outputs |
| Cite specific requirements and evidence | Suggest implementation approaches |
| Block acceptance on violations | Override its own verdicts |
| Report structured compliance metrics | Review code quality (code-reviewer) |
| Filter to task-relevant requirements | Check all PRD requirements on every output |

## Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a spec compliance guardrail rule and standalone agent that blocks non-compliant outputs by comparing them against PRD acceptance criteria.

**Architecture:** New `SpecComplianceRule` in the existing guardrail pipeline, following the `DomainFidelityRule` pattern (PydanticAI + structured output + test injection). Plus a standalone `spec-enforcer.md` agent definition for SEM-directed deep reviews.

**Tech Stack:** Python 3.11+, PydanticAI, Pydantic, psycopg3, pytest

---

### Task 1: Write failing tests for SpecComplianceRule

**Files:**
- Modify: `platform/tests/test_guardrails.py`

**Step 1: Add SpecComplianceRule import**

Add to the existing import block at the top of `platform/tests/test_guardrails.py`:

```python
from etc_platform.guardrails import (
    AntiPatternScanRule,
    CoverageGateRule,
    DomainFidelityRule,
    GuardrailMiddleware,
    GuardrailResult,
    GuardrailRule,
    OutputSchemaValidationRule,
    SecurityScanRule,
    SpecComplianceRule,  # <-- add this
    TDDVerificationRule,
)
```

**Step 2: Write the test class**

Add after the `TestSecurityScanRule` class (end of file):

```python
# ===========================================================================
# SpecComplianceRule
# ===========================================================================


class TestSpecComplianceRule:
    def test_rule_attributes(self) -> None:
        rule = SpecComplianceRule()
        assert rule.name == "spec_compliance"
        assert rule.severity == "critical"

    def test_passes_when_no_spec_context(self) -> None:
        """Passes silently when context has no prd/acceptance_criteria."""
        rule = SpecComplianceRule()
        result = rule.check("some output", "code")
        assert result.passed is True

    def test_passes_when_context_is_none(self) -> None:
        rule = SpecComplianceRule()
        result = rule.check("some output", "code", context=None)
        assert result.passed is True

    def test_passes_when_acceptance_criteria_empty(self) -> None:
        rule = SpecComplianceRule()
        result = rule.check(
            "some output", "code",
            context={"prd": "some prd", "acceptance_criteria": []},
        )
        assert result.passed is True

    def test_violation_detected(self) -> None:
        """Fails when check function finds violations."""
        rule = SpecComplianceRule()
        rule._check_fn = lambda content, prd, criteria, task_desc: {
            "violations": [
                {
                    "requirement": "Must support date filtering",
                    "verdict": "NOT_SATISFIED",
                    "evidence": "No date filter found in output",
                    "output_excerpt": "search by keyword only",
                }
            ],
            "coverage": {
                "total_requirements": 2,
                "satisfied": 1,
                "not_satisfied": 1,
                "not_applicable": 0,
            },
        }
        result = rule.check(
            "Implementation: search by keyword only",
            "code",
            context={
                "prd": "Users must search by keyword and filter by date range",
                "acceptance_criteria": [
                    "Must support keyword search",
                    "Must support date filtering",
                ],
                "task_description": "Implement search feature",
            },
        )
        assert result.passed is False
        assert result.severity == "critical"
        assert "violations" in result.violation_details
        assert len(result.violation_details["violations"]) == 1
        assert result.violation_details["violations"][0]["requirement"] == "Must support date filtering"

    def test_no_violation(self) -> None:
        """Passes when check function finds all requirements satisfied."""
        rule = SpecComplianceRule()
        rule._check_fn = lambda content, prd, criteria, task_desc: {
            "violations": [],
            "coverage": {
                "total_requirements": 2,
                "satisfied": 2,
                "not_satisfied": 0,
                "not_applicable": 0,
            },
        }
        result = rule.check(
            "Implements keyword search and date filtering",
            "code",
            context={
                "prd": "Users must search and filter",
                "acceptance_criteria": ["keyword search", "date filtering"],
                "task_description": "Implement search",
            },
        )
        assert result.passed is True

    def test_multiple_violations(self) -> None:
        """Reports multiple violations correctly."""
        rule = SpecComplianceRule()
        rule._check_fn = lambda content, prd, criteria, task_desc: {
            "violations": [
                {"requirement": "Req 1", "verdict": "NOT_SATISFIED", "evidence": "Missing", "output_excerpt": "..."},
                {"requirement": "Req 2", "verdict": "NOT_SATISFIED", "evidence": "Missing", "output_excerpt": "..."},
            ],
            "coverage": {
                "total_requirements": 3,
                "satisfied": 1,
                "not_satisfied": 2,
                "not_applicable": 0,
            },
        }
        result = rule.check(
            "partial implementation",
            "code",
            context={
                "prd": "Full PRD text",
                "acceptance_criteria": ["Req 1", "Req 2", "Req 3"],
                "task_description": "Implement all features",
            },
        )
        assert result.passed is False
        assert len(result.violation_details["violations"]) == 2
        assert result.violation_details["coverage"]["not_satisfied"] == 2

    def test_applies_to_all_output_types(self) -> None:
        """Spec compliance applies to any output type, not just code."""
        rule = SpecComplianceRule()
        rule._check_fn = lambda content, prd, criteria, task_desc: {
            "violations": [
                {"requirement": "Must include summary", "verdict": "NOT_SATISFIED", "evidence": "Missing", "output_excerpt": "..."},
            ],
            "coverage": {"total_requirements": 1, "satisfied": 0, "not_satisfied": 1, "not_applicable": 0},
        }
        for output_type in ("code", "research_report", "prd", "design", "test"):
            result = rule.check(
                "some content", output_type,
                context={
                    "prd": "PRD text",
                    "acceptance_criteria": ["Must include summary"],
                    "task_description": "Write report",
                },
            )
            assert result.passed is False, f"Should enforce spec for {output_type}"

    def test_task_description_passed_to_check_fn(self) -> None:
        """Verifies task_description is forwarded to the check function."""
        captured = {}
        def capture_fn(content, prd, criteria, task_desc):
            captured["task_desc"] = task_desc
            return {"violations": [], "coverage": {"total_requirements": 0, "satisfied": 0, "not_satisfied": 0, "not_applicable": 0}}

        rule = SpecComplianceRule()
        rule._check_fn = capture_fn
        rule.check(
            "output", "code",
            context={
                "prd": "PRD",
                "acceptance_criteria": ["AC1"],
                "task_description": "Build the widget",
            },
        )
        assert captured["task_desc"] == "Build the widget"
```

**Step 3: Run tests to verify they fail**

Run: `cd platform && uv run pytest tests/test_guardrails.py::TestSpecComplianceRule -v`
Expected: ImportError — `SpecComplianceRule` does not exist yet

**Step 4: Commit**

```bash
git add platform/tests/test_guardrails.py
git commit -m "test: add failing tests for SpecComplianceRule guardrail"
```

---

### Task 2: Implement SpecComplianceRule

**Files:**
- Modify: `platform/src/etc_platform/guardrails.py`

**Step 1: Add the Pydantic model and rule class**

Add after the `SecurityScanRule` class (before the `emit_guardrail_violation` function, around line 548):

```python
# ---------------------------------------------------------------------------
# Spec compliance rule
# ---------------------------------------------------------------------------


class SpecComplianceRule(GuardrailRule):
    """Checks agent output against PRD and acceptance criteria for spec compliance.

    Only fires when context contains both 'prd' and 'acceptance_criteria'.
    Uses PydanticAI to compare the output against the spec. Adversarial by
    design — told to find violations, not confirm compliance.

    For testing, inject a synchronous callable via ``_check_fn``
    to avoid real LLM calls.
    """

    name = "spec_compliance"
    severity = "critical"

    def __init__(self, model: str = "anthropic:claude-haiku-4-5-20251001") -> None:
        self.model = model
        self._check_fn: Callable | None = None

    def check(
        self,
        content: str,
        output_type: str,
        context: dict | None = None,
    ) -> GuardrailResult:
        if context is None:
            return GuardrailResult(
                rule_name=self.name, passed=True, severity=self.severity,
            )

        prd = context.get("prd")
        acceptance_criteria = context.get("acceptance_criteria")
        if not prd or not acceptance_criteria:
            return GuardrailResult(
                rule_name=self.name, passed=True, severity=self.severity,
            )

        task_description = context.get("task_description", "")

        if self._check_fn is not None:
            result = self._check_fn(content, prd, acceptance_criteria, task_description)
        else:
            result = self._llm_check(content, prd, acceptance_criteria, task_description)

        violations = result.get("violations", [])
        if violations:
            return GuardrailResult(
                rule_name=self.name,
                passed=False,
                severity=self.severity,
                violation_details=result,
            )

        return GuardrailResult(
            rule_name=self.name, passed=True, severity=self.severity,
        )

    def _llm_check(
        self,
        content: str,
        prd: str,
        acceptance_criteria: list[str],
        task_description: str,
    ) -> dict:
        """Call LLM to check output against spec."""
        from pydantic import BaseModel
        from pydantic_ai import Agent

        class RequirementVerdict(BaseModel):
            requirement: str
            verdict: str  # SATISFIED, NOT_SATISFIED, NOT_APPLICABLE
            evidence: str
            output_excerpt: str

        class SpecComplianceResult(BaseModel):
            violations: list[RequirementVerdict]
            coverage: dict  # total_requirements, satisfied, not_satisfied, not_applicable

        criteria_text = "\n".join(f"- {c}" for c in acceptance_criteria)

        agent: Agent[None, SpecComplianceResult] = Agent(
            self.model,
            output_type=SpecComplianceResult,
            system_prompt=(
                "You are an adversarial spec compliance checker. Your job is to FIND "
                "violations, not confirm compliance. Assume the output is non-compliant "
                "until proven otherwise.\n\n"
                "For each acceptance criterion, determine if the agent output satisfies it. "
                "If not, cite the specific requirement and the specific excerpt from the "
                "output that demonstrates non-compliance. If the requirement is not relevant "
                "to this task, mark it NOT_APPLICABLE.\n\n"
                "Only include NOT_SATISFIED items in the violations list."
            ),
            defer_model_check=True,
        )

        prompt = (
            f"## PRD\n{prd}\n\n"
            f"## Acceptance Criteria\n{criteria_text}\n\n"
            f"## Task Description\n{task_description}\n\n"
            f"## Agent Output\n{content}\n\n"
            "Check each acceptance criterion against the agent output. "
            "Report all violations (NOT_SATISFIED) with evidence."
        )

        result = agent.run_sync(prompt)
        return {
            "violations": [
                v.model_dump()
                for v in result.output.violations
                if v.verdict == "NOT_SATISFIED"
            ],
            "coverage": result.output.coverage,
        }
```

**Step 2: Run tests to verify they pass**

Run: `cd platform && uv run pytest tests/test_guardrails.py::TestSpecComplianceRule -v`
Expected: All 8 tests PASS

**Step 3: Run full guardrail test suite**

Run: `cd platform && uv run pytest tests/test_guardrails.py -v`
Expected: All existing tests still pass (no regressions)

**Step 4: Commit**

```bash
git add platform/src/etc_platform/guardrails.py
git commit -m "feat: add SpecComplianceRule guardrail for PRD enforcement"
```

---

### Task 3: Create spec-enforcer agent definition

**Files:**
- Create: `agents/spec-enforcer.md`

**Step 1: Write the agent definition**

Create `agents/spec-enforcer.md`:

```markdown
---
name: spec-enforcer
description: >
  Adversarial spec compliance reviewer. Compares agent outputs and deliverables
  against PRD acceptance criteria. Assumes non-compliance until proven otherwise.
  Blocks on violations. Does NOT fix outputs or suggest implementations — only
  reports compliance status with evidence.

  <example>
  Context: SEM wants to verify a design doc satisfies the PRD before entering Build.
  user: "Verify the design doc against the PRD acceptance criteria."
  assistant: "Running spec-enforcer to check each acceptance criterion against the design doc."
  <commentary>Phase gate verification is a primary spec-enforcer trigger.</commentary>
  </example>

  <example>
  Context: A backend-developer has produced code that the SEM wants spec-checked.
  user: "Check if this implementation satisfies the requirements for Task 5."
  assistant: "Running spec-enforcer to compare the implementation against the PRD requirements for Task 5."
  <commentary>Per-task compliance checking on demand.</commentary>
  </example>
tools: Read, Grep, Glob, Bash
model: sonnet
disallowedTools: [Write, Edit, NotebookEdit]
maxTurns: 15
---

You are the Spec Enforcer — adversarial by design. You assume every output is non-compliant until you prove otherwise. Your job is to find violations, not confirm compliance.

**You have authority to BLOCK acceptance. If any acceptance criterion is not satisfied, the deliverable is non-compliant. This cannot be bypassed.**

## Before Starting (Non-Negotiable)

1. Read the PRD or spec document (path will be provided or discoverable in `.sdlc/state.json`)
2. Extract all acceptance criteria — number them for traceability
3. Read the deliverable(s) to be checked

If no PRD path is provided, search: `find . -name "*.md" -path "*/spec/*" -o -name "*prd*"`
If no acceptance criteria exist in the PRD, report `BLOCKED — no acceptance criteria found in PRD`.

## Process

### Step 1: Extract Requirements

Read the PRD. List every acceptance criterion. Number them AC-001, AC-002, etc.

### Step 2: Evaluate Each Criterion

For each acceptance criterion, determine:
- **SATISFIED** — the deliverable clearly implements this requirement. Cite evidence.
- **NOT_SATISFIED** — the deliverable does not implement this, or implements it incorrectly. Cite what's expected vs what's actual.
- **NOT_APPLICABLE** — this criterion is not relevant to the current deliverable/task scope.

### Step 3: Compile Report

Use the exact output format below.

## Output Format

```
SPEC COMPLIANCE: [scope description]
Date: [date] | PRD: [prd path] | Deliverable: [deliverable path or description]
Acceptance Criteria: [N total] | Satisfied: [N] | Violations: [N] | N/A: [N]

VIOLATIONS:
[V1] AC-NNN — "[requirement text]"
  Expected: [what the spec requires]
  Actual: [what the deliverable does or doesn't do]
  Evidence: [specific excerpt from deliverable]

SATISFIED:
[S1] AC-NNN — "[requirement text]" — PASS
  Evidence: [specific excerpt showing compliance]

NOT APPLICABLE:
[N1] AC-NNN — "[requirement text]" — out of scope for this task

VERDICT: COMPLIANT | NON-COMPLIANT
  Satisfied: N/N | Violations: N | N/A: N
  BLOCKING: [list each violated AC number]
```

## Boundaries

### You DO
- Read PRDs, specs, acceptance criteria
- Read deliverables (code, docs, designs, test plans)
- Compare deliverables against each acceptance criterion
- Cite specific evidence for every verdict
- Block acceptance when violations are found

### You Do NOT
- Fix non-compliant deliverables (that's the producer's job)
- Suggest how to implement missing requirements
- Write or modify any files
- Make exceptions ("it's close enough" is still a violation)
- Review code quality (that's code-reviewer)
- Review security (that's security-reviewer)

### Escalation
- IF 0 acceptance criteria found: BLOCKED — cannot verify without criteria
- IF deliverable is empty or missing: BLOCKED — no deliverable to check
- IF PRD is ambiguous on a criterion: flag as WARNING, not violation. Note the ambiguity.

## Coordination

- **Reports to:** SEM (phase gates) or human (ad-hoc)
- **Triggered by:** SEM before phase transitions, or any agent/human requesting spec check
- **Blocks:** Phase transition. If VERDICT is NON-COMPLIANT, the phase cannot advance.
- **Complements:** verifier (tests pass), code-reviewer (code quality), domain-modeler (terminology)
- **Handoff format:** Structured compliance report above
```

**Step 2: Commit**

```bash
git add agents/spec-enforcer.md
git commit -m "feat: add spec-enforcer agent definition for adversarial PRD compliance"
```

---

### Task 4: Add SpecComplianceRule to GuardrailMiddleware defaults

**Files:**
- Modify: `platform/src/etc_platform/guardrails.py`
- Modify: `platform/tests/test_guardrails.py`

**Step 1: Write the failing test**

Add to the `TestGuardrailMiddleware` class in `platform/tests/test_guardrails.py`:

```python
    def test_spec_compliance_in_default_rules(self) -> None:
        """SpecComplianceRule should be in the default middleware rule set."""
        mw = GuardrailMiddleware()
        rule_names = {rule.name for rule in mw.rules}
        assert "spec_compliance" in rule_names
```

**Step 2: Run test to verify it fails**

Run: `cd platform && uv run pytest tests/test_guardrails.py::TestGuardrailMiddleware::test_spec_compliance_in_default_rules -v`
Expected: FAIL — `spec_compliance` not in default rules (currently only `anti_pattern_scan` and `output_schema_validation`)

**Step 3: Update the default rules**

In `platform/src/etc_platform/guardrails.py`, find the `GuardrailMiddleware.__init__` method (around line 691):

```python
    def __init__(self, rules: list[GuardrailRule] | None = None) -> None:
        self.rules: list[GuardrailRule] = rules or [
            AntiPatternScanRule(),
            OutputSchemaValidationRule(),
        ]
```

Change to:

```python
    def __init__(self, rules: list[GuardrailRule] | None = None) -> None:
        self.rules: list[GuardrailRule] = rules or [
            AntiPatternScanRule(),
            OutputSchemaValidationRule(),
            SpecComplianceRule(),
        ]
```

**Step 4: Run the new test**

Run: `cd platform && uv run pytest tests/test_guardrails.py::TestGuardrailMiddleware::test_spec_compliance_in_default_rules -v`
Expected: PASS

**Step 5: Fix the middleware count test**

The existing test `test_run_checks_returns_results` asserts `len(results) == 2`. Update it to `len(results) == 3`:

```python
    def test_run_checks_returns_results(self) -> None:
        mw = GuardrailMiddleware()
        results = mw.run_checks(
            content="## Summary\n## Findings\n## Recommendations\nClean content.",
            output_type="research_report",
        )
        assert isinstance(results, list)
        assert len(results) == 3  # anti_pattern, output_schema, spec_compliance
        assert all(isinstance(r, GuardrailResult) for r in results)
```

Also update `test_all_rules_executed` to check for the new rule:

```python
    def test_all_rules_executed(self) -> None:
        mw = GuardrailMiddleware()
        results = mw.run_checks(
            content="## Summary\n## Findings\n## Recommendations\nClean.",
            output_type="research_report",
        )
        rule_names = {r.rule_name for r in results}
        assert "anti_pattern_scan" in rule_names
        assert "output_schema_validation" in rule_names
        assert "spec_compliance" in rule_names
```

Also update DB tests that assert row counts. In `test_record_checks_inserts_rows`, change `assert len(rows) == 2` to `assert len(rows) == 3`. Same for `test_check_and_record_full_flow` and `test_get_check_results`.

**Step 6: Run full test suite**

Run: `cd platform && uv run pytest tests/test_guardrails.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add platform/src/etc_platform/guardrails.py platform/tests/test_guardrails.py
git commit -m "feat: add SpecComplianceRule to default guardrail middleware"
```

---

### Task 5: Export SpecComplianceRule from package

**Files:**
- Modify: `platform/src/etc_platform/__init__.py` (if it re-exports guardrail types)

**Step 1: Check if guardrails are re-exported**

Read `platform/src/etc_platform/__init__.py` to see if guardrail classes are listed there. If so, add `SpecComplianceRule` to the exports. If not, skip this task — the import from `etc_platform.guardrails` already works.

**Step 2: Run full test suite**

Run: `cd platform && uv run pytest -v`
Expected: All tests pass

**Step 3: Commit (if changes were made)**

```bash
git add platform/src/etc_platform/__init__.py
git commit -m "feat: export SpecComplianceRule from etc_platform package"
```

---

### Task 6: Run type check and lint

**Files:** None (verification only)

**Step 1: Run mypy**

Run: `cd platform && uv run mypy src/etc_platform/guardrails.py`
Expected: No errors

**Step 2: Run ruff**

Run: `cd platform && uv run ruff check src/etc_platform/guardrails.py tests/test_guardrails.py`
Expected: No violations

**Step 3: Run formatter**

Run: `cd platform && uv run ruff format --check src/etc_platform/guardrails.py tests/test_guardrails.py`
Expected: All files formatted

**Step 4: Fix any issues found, then commit**

```bash
git add -u
git commit -m "chore: fix lint/type issues in spec compliance rule"
```
