"""Guardrail middleware — checks every agent output before acceptance.

MVP rules:
- anti_pattern_scan: detects re-engineering anti-patterns in research/PRD outputs
- output_schema_validation: ensures outputs contain required sections
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

import psycopg


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class GuardrailResult:
    """Result from a single guardrail rule check."""

    rule_name: str
    passed: bool
    severity: str  # critical, high, medium, low
    violation_details: dict | None = None


# ---------------------------------------------------------------------------
# Base rule
# ---------------------------------------------------------------------------


class GuardrailRule:
    """Base class for guardrail rules."""

    name: str
    severity: str

    def check(
        self,
        content: str,
        output_type: str,
        context: dict | None = None,
    ) -> GuardrailResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Anti-pattern scan rule
# ---------------------------------------------------------------------------

# Regex: 3+ boolean-style identifiers (is_*, has_*, can_*) in proximity
_BOOLEAN_FLAG_RE = re.compile(
    r"(?:(?:is|has|can|should)_\w+[\s,;]+){2,}(?:is|has|can|should)_\w+",
    re.IGNORECASE,
)

# Regex: Hardcoded enum-like list assignments, e.g. STATUS = ['active', 'inactive', ...]
_HARDCODED_ENUM_RE = re.compile(
    r"\w+\s*=\s*\[(?:\s*['\"][^'\"]+['\"][\s,]*){2,}\]",
    re.IGNORECASE,
)

# Regex: Legacy field mapping tables, e.g. legacy_field -> new_field
_LEGACY_MAPPING_RE = re.compile(
    r"(?:\w+\s*->\s*\w+[\s,;]*){3,}",
    re.IGNORECASE,
)

_APPLICABLE_TYPES = {"research_report", "prd"}


class AntiPatternScanRule(GuardrailRule):
    """Scans output content for common anti-patterns in re-engineering projects."""

    name = "anti_pattern_scan"
    severity = "critical"

    def check(
        self,
        content: str,
        output_type: str,
        context: dict | None = None,
    ) -> GuardrailResult:
        """Scan for anti-patterns. Only applies to research_report and prd output types."""
        if output_type not in _APPLICABLE_TYPES:
            return GuardrailResult(
                rule_name=self.name,
                passed=True,
                severity=self.severity,
            )

        violations: dict[str, list[str]] = {}

        boolean_matches = _BOOLEAN_FLAG_RE.findall(content)
        if boolean_matches:
            violations["boolean_flag_sets"] = boolean_matches

        enum_matches = _HARDCODED_ENUM_RE.findall(content)
        if enum_matches:
            violations["hardcoded_enums"] = enum_matches

        mapping_matches = _LEGACY_MAPPING_RE.findall(content)
        if mapping_matches:
            violations["legacy_mappings"] = mapping_matches

        if violations:
            return GuardrailResult(
                rule_name=self.name,
                passed=False,
                severity=self.severity,
                violation_details=violations,
            )

        return GuardrailResult(
            rule_name=self.name,
            passed=True,
            severity=self.severity,
        )


# ---------------------------------------------------------------------------
# Output schema validation rule
# ---------------------------------------------------------------------------

_REQUIRED_SECTIONS: dict[str, list[str]] = {
    "research_report": ["## Summary", "## Findings", "## Recommendations"],
    "prd": ["## Requirements", "## Scope"],
}

# Code must contain at least one function or class definition
_CODE_DEF_RE = re.compile(r"^\s*(?:def |class )\w+", re.MULTILINE)


class OutputSchemaValidationRule(GuardrailRule):
    """Validates that agent outputs have required sections based on output_type."""

    name = "output_schema_validation"
    severity = "high"

    def check(
        self,
        content: str,
        output_type: str,
        context: dict | None = None,
    ) -> GuardrailResult:
        required = _REQUIRED_SECTIONS.get(output_type)

        if required is not None:
            missing = [s for s in required if s not in content]
            if missing:
                return GuardrailResult(
                    rule_name=self.name,
                    passed=False,
                    severity=self.severity,
                    violation_details={"missing_sections": missing},
                )
            return GuardrailResult(
                rule_name=self.name,
                passed=True,
                severity=self.severity,
            )

        if output_type == "code":
            if not _CODE_DEF_RE.search(content):
                return GuardrailResult(
                    rule_name=self.name,
                    passed=False,
                    severity=self.severity,
                    violation_details={
                        "missing_sections": ["function or class definition"],
                    },
                )
            return GuardrailResult(
                rule_name=self.name,
                passed=True,
                severity=self.severity,
            )

        # Unknown / other types pass by default
        return GuardrailResult(
            rule_name=self.name,
            passed=True,
            severity=self.severity,
        )


# ---------------------------------------------------------------------------
# Domain fidelity rule
# ---------------------------------------------------------------------------


class DomainFidelityRule(GuardrailRule):
    """Checks agent output against domain axioms for contradictions.

    Domain axioms are loaded from the ``context`` dict passed to ``check()``
    (key: ``domain_axioms``).  These originate from source materials with
    priority='primary' or classification='domain_truth'.

    A lightweight LLM call via PydanticAI compares the agent output against
    the axioms. For testing, inject a synchronous callable via ``_check_fn``
    to avoid real LLM calls.
    """

    name = "domain_fidelity_check"
    severity = "critical"

    def __init__(self, model: str = "anthropic:claude-haiku-4-5-20251001") -> None:
        self.model = model
        self._check_fn: Callable | None = None  # Allow injection for testing

    def check(
        self,
        content: str,
        output_type: str,
        context: dict | None = None,
    ) -> GuardrailResult:
        if context is None or "domain_axioms" not in context:
            return GuardrailResult(
                rule_name=self.name,
                passed=True,
                severity=self.severity,
            )

        axioms = context["domain_axioms"]
        if not axioms:
            return GuardrailResult(
                rule_name=self.name,
                passed=True,
                severity=self.severity,
            )

        # Use injected check function (for testing) or real LLM call
        if self._check_fn is not None:
            violations = self._check_fn(content, axioms)
        else:
            violations = self._llm_check(content, axioms)

        if violations:
            return GuardrailResult(
                rule_name=self.name,
                passed=False,
                severity=self.severity,
                violation_details={"axiom_violations": violations},
            )

        return GuardrailResult(
            rule_name=self.name,
            passed=True,
            severity=self.severity,
        )

    def _llm_check(self, content: str, axioms: list[str]) -> list[dict]:
        """Call LLM to check content against domain axioms."""
        from pydantic import BaseModel
        from pydantic_ai import Agent

        class FidelityCheck(BaseModel):
            violations_found: bool
            violations: list[dict]  # Each: {"axiom": str, "contradiction": str, "excerpt": str}

        axiom_text = "\n".join(f"- {a}" for a in axioms)

        agent: Agent[None, FidelityCheck] = Agent(
            self.model,
            output_type=FidelityCheck,
            system_prompt=(
                "You are a domain fidelity checker. Given domain axioms and agent output, "
                "identify any contradictions. Be precise: only flag clear contradictions, "
                "not omissions or tangential mentions. For each violation, cite the specific "
                "axiom and the specific excerpt from the output that contradicts it."
            ),
            defer_model_check=True,
        )

        prompt = (
            f"Domain Axioms:\n{axiom_text}\n\n"
            f"Agent Output:\n{content}\n\n"
            "Does the agent output contradict any of these domain axioms? "
            "If yes, list each violation with the axiom, the contradiction, and the exact excerpt."
        )

        result = agent.run_sync(prompt)
        if result.output.violations_found:
            return result.output.violations
        return []


# ---------------------------------------------------------------------------
# Coverage gate rule
# ---------------------------------------------------------------------------


class CoverageGateRule(GuardrailRule):
    """Checks that test coverage meets a configurable threshold.

    Only applicable to output_type = "code". Parses coverage percentage
    from context or runs pytest --cov if a project path is provided.
    """

    name = "coverage_gate"
    severity = "high"

    def __init__(self, threshold: float = 80.0) -> None:
        self.threshold = threshold

    def check(
        self,
        content: str,
        output_type: str,
        context: dict | None = None,
    ) -> GuardrailResult:
        """Check coverage. Only applies to code output type."""
        if output_type != "code":
            return GuardrailResult(
                rule_name=self.name,
                passed=True,
                severity=self.severity,
            )

        # Look for coverage info in context
        if context and "coverage_percent" in context:
            coverage = context["coverage_percent"]
        else:
            # Try to parse coverage from content (e.g., pytest output)
            coverage = self._parse_coverage(content)

        if coverage is None:
            # Can't determine coverage — pass with warning
            return GuardrailResult(
                rule_name=self.name,
                passed=True,
                severity=self.severity,
                violation_details={"warning": "Could not determine coverage"},
            )

        if coverage < self.threshold:
            return GuardrailResult(
                rule_name=self.name,
                passed=False,
                severity=self.severity,
                violation_details={
                    "coverage_percent": coverage,
                    "threshold": self.threshold,
                    "deficit": round(self.threshold - coverage, 1),
                },
            )

        return GuardrailResult(
            rule_name=self.name,
            passed=True,
            severity=self.severity,
        )

    @staticmethod
    def _parse_coverage(content: str) -> float | None:
        """Try to extract coverage percentage from content."""
        # Match common pytest-cov output: "TOTAL    xxx   xxx    xx%"
        match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", content)
        if match:
            return float(match.group(1))
        # Match "Coverage: xx%" or "coverage: xx%"
        match = re.search(r"[Cc]overage:\s*(\d+(?:\.\d+)?)%", content)
        if match:
            return float(match.group(1))
        return None


# ---------------------------------------------------------------------------
# TDD verification rule
# ---------------------------------------------------------------------------


class TDDVerificationRule(GuardrailRule):
    """Verifies that code output includes tests alongside implementation.

    Checks that code content contains both test definitions and implementation
    definitions, suggesting TDD practice. Severity: medium.
    """

    name = "tdd_verification"
    severity = "medium"

    # Regex for test file patterns
    _TEST_PATTERN = re.compile(
        r"(?:def test_\w+|class Test\w+|@pytest\.mark|assert\s+\w+)",
        re.MULTILINE,
    )

    # Regex for implementation patterns
    _IMPL_PATTERN = re.compile(
        r"(?:^class (?!Test)\w+|^def (?!test_)\w+)",
        re.MULTILINE,
    )

    def check(
        self,
        content: str,
        output_type: str,
        context: dict | None = None,
    ) -> GuardrailResult:
        if output_type != "code":
            return GuardrailResult(
                rule_name=self.name,
                passed=True,
                severity=self.severity,
            )

        # Check context for explicit test info
        if context and "has_tests" in context:
            if context["has_tests"]:
                return GuardrailResult(
                    rule_name=self.name,
                    passed=True,
                    severity=self.severity,
                )
            else:
                return GuardrailResult(
                    rule_name=self.name,
                    passed=False,
                    severity=self.severity,
                    violation_details={"reason": "No tests found in agent output"},
                )

        # Check if context mentions test files in files_written
        if context and "files_written" in context:
            files = context["files_written"]
            has_test_files = any(
                "test_" in f or f.startswith("tests/") for f in files
            )
            has_impl_files = any(
                "test_" not in f and not f.startswith("tests/")
                for f in files
                if f.endswith(".py")
            )
            if has_impl_files and not has_test_files:
                return GuardrailResult(
                    rule_name=self.name,
                    passed=False,
                    severity=self.severity,
                    violation_details={
                        "reason": "Implementation files written without corresponding test files",
                        "impl_files": [
                            f for f in files if "test_" not in f and f.endswith(".py")
                        ],
                    },
                )

        # Fallback: scan content for test patterns
        has_tests = bool(self._TEST_PATTERN.search(content))
        has_impl = bool(self._IMPL_PATTERN.search(content))

        if has_impl and not has_tests:
            return GuardrailResult(
                rule_name=self.name,
                passed=False,
                severity=self.severity,
                violation_details={
                    "reason": "Implementation code found without test code",
                },
            )

        return GuardrailResult(
            rule_name=self.name,
            passed=True,
            severity=self.severity,
        )


# ---------------------------------------------------------------------------
# Security scan rule
# ---------------------------------------------------------------------------

# Regex patterns for common security vulnerabilities
_SQL_INJECTION_RE = re.compile(
    r"""(?:execute|cursor\.execute|\.query)\s*\(\s*(?:f['""]|['""].*%s.*\+|['""].*\.format)""",
    re.IGNORECASE,
)

_HARDCODED_SECRET_RE = re.compile(
    r"""(?:password|secret|api_key|api_secret|token|private_key)\s*=\s*['"][^'"]{8,}['"]""",
    re.IGNORECASE,
)

_XSS_RE = re.compile(
    r"""(?:innerHTML|outerHTML|document\.write)\s*[=\(]""",
    re.IGNORECASE,
)

# Detects unsafe deserialization patterns (pickle, yaml without Loader, eval)
_INSECURE_DESERIALIZE_RE = re.compile(
    r"""(?:pickle\.loads?|yaml\.load\s*\([^)]*\)(?!\s*,\s*Loader)|eval\s*\()""",
    re.IGNORECASE,
)


class SecurityScanRule(GuardrailRule):
    """Scans generated code for basic OWASP security patterns."""

    name = "security_scan"
    severity = "high"

    _PATTERNS: list[tuple[str, re.Pattern]] = [
        ("sql_injection", _SQL_INJECTION_RE),
        ("hardcoded_secrets", _HARDCODED_SECRET_RE),
        ("xss", _XSS_RE),
        ("insecure_deserialization", _INSECURE_DESERIALIZE_RE),
    ]

    def check(
        self,
        content: str,
        output_type: str,
        context: dict | None = None,
    ) -> GuardrailResult:
        if output_type != "code":
            return GuardrailResult(
                rule_name=self.name,
                passed=True,
                severity=self.severity,
            )

        violations: dict[str, list[str]] = {}
        for vuln_name, pattern in self._PATTERNS:
            matches = pattern.findall(content)
            if matches:
                violations[vuln_name] = matches

        if violations:
            return GuardrailResult(
                rule_name=self.name,
                passed=False,
                severity=self.severity,
                violation_details=violations,
            )

        return GuardrailResult(
            rule_name=self.name,
            passed=True,
            severity=self.severity,
        )


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


# ---------------------------------------------------------------------------
# Violation event emission
# ---------------------------------------------------------------------------


def emit_guardrail_violation(
    conn: psycopg.Connection,
    project_id: UUID,
    output_id: UUID,
    node_id: UUID,
    results: list[GuardrailResult],
) -> None:
    """Emit a GUARDRAIL_VIOLATION event for critical failures.

    Only emits if at least one result is a critical-severity failure.
    """
    from etc_platform.events import EventType, emit_event

    critical_failures = [
        r for r in results if not r.passed and r.severity == "critical"
    ]
    if not critical_failures:
        return

    violation_details = []
    for r in critical_failures:
        violation_details.append({
            "rule_name": r.rule_name,
            "severity": r.severity,
            "violation_details": r.violation_details,
        })

    emit_event(
        conn=conn,
        project_id=project_id,
        event_type=EventType.GUARDRAIL_VIOLATION,
        actor="guardrail_middleware",
        payload={
            "output_id": str(output_id),
            "node_id": str(node_id),
            "critical_failures": violation_details,
        },
    )


# ---------------------------------------------------------------------------
# Override support
# ---------------------------------------------------------------------------


def override_guardrail_check(
    conn: psycopg.Connection,
    check_id: UUID,
    reason: str,
    overridden_by: str = "human",
) -> bool:
    """Override a failed guardrail check with justification.

    Sets passed=True, records the override reason and who overrode it.
    Re-evaluates the parent agent_output acceptance.
    Returns True if the override was applied.
    """
    now = datetime.now(timezone.utc)

    # Update the check
    result = conn.execute(
        """
        UPDATE guardrail_checks
        SET passed = TRUE,
            override_reason = %s,
            overridden_by = %s,
            overridden_at = %s
        WHERE id = %s AND passed = FALSE
        RETURNING output_id
        """,
        (reason, overridden_by, now, check_id),
    )
    row = result.fetchone()
    if row is None:
        return False

    output_id = row["output_id"]

    # Re-evaluate acceptance: check if any critical failures remain
    remaining_failures = conn.execute(
        """
        SELECT COUNT(*) as cnt FROM guardrail_checks
        WHERE output_id = %s AND passed = FALSE AND severity = 'critical'
        """,
        (output_id,),
    ).fetchone()

    if remaining_failures["cnt"] == 0:
        conn.execute(
            "UPDATE agent_outputs SET accepted = TRUE WHERE id = %s",
            (output_id,),
        )

    return True


def list_guardrail_checks(
    conn: psycopg.Connection,
    project_id: UUID,
    failed_only: bool = False,
) -> list[dict]:
    """List guardrail checks for a project's current phase outputs."""
    query = """
        SELECT gc.id, gc.rule_name, gc.passed, gc.severity,
               gc.violation_details, gc.checked_at,
               gc.override_reason, gc.overridden_by, gc.overridden_at,
               ao.output_type, ao.file_path,
               ar.agent_type, en.name as node_name
        FROM guardrail_checks gc
        JOIN agent_outputs ao ON gc.output_id = ao.id
        JOIN agent_runs ar ON ao.run_id = ar.id
        JOIN execution_nodes en ON ar.node_id = en.id
        JOIN execution_graphs eg ON en.graph_id = eg.id
        WHERE eg.project_id = %s
    """
    params: list = [project_id]

    if failed_only:
        query += " AND gc.passed = FALSE"

    query += " ORDER BY gc.checked_at DESC"

    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class GuardrailMiddleware:
    """Orchestrates guardrail rule execution, recording, and retrieval."""

    def __init__(self, rules: list[GuardrailRule] | None = None) -> None:
        self.rules: list[GuardrailRule] = rules or [
            AntiPatternScanRule(),
            OutputSchemaValidationRule(),
        ]

    def run_checks(
        self,
        content: str,
        output_type: str,
        context: dict | None = None,
    ) -> list[GuardrailResult]:
        """Run all guardrail rules against the content."""
        return [rule.check(content, output_type, context) for rule in self.rules]

    def record_checks(
        self,
        conn: psycopg.Connection,
        output_id: UUID,
        results: list[GuardrailResult],
    ) -> None:
        """Record guardrail check results in the database.

        - Insert each result into guardrail_checks.
        - Update agent_outputs.accepted (False if any critical rule fails).
        - Update agent_outputs.guardrail_results with a JSON summary.
        """
        for r in results:
            conn.execute(
                """
                INSERT INTO guardrail_checks (output_id, rule_name, passed, severity, violation_details)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    output_id,
                    r.rule_name,
                    r.passed,
                    r.severity,
                    json.dumps(r.violation_details) if r.violation_details else None,
                ),
            )

        # Determine acceptance: rejected if any critical rule fails
        has_critical_fail = any(
            not r.passed and r.severity == "critical" for r in results
        )
        accepted = not has_critical_fail

        summary = {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [
                {
                    "rule_name": r.rule_name,
                    "passed": r.passed,
                    "severity": r.severity,
                }
                for r in results
            ],
        }

        conn.execute(
            """
            UPDATE agent_outputs
            SET accepted = %s, guardrail_results = %s
            WHERE id = %s
            """,
            (accepted, json.dumps(summary), output_id),
        )

    def check_and_record(
        self,
        conn: psycopg.Connection,
        output_id: UUID,
        content: str,
        output_type: str,
        context: dict | None = None,
        node_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> list[GuardrailResult]:
        """Run checks and record results. Emits GUARDRAIL_VIOLATION on critical failures.

        When ``node_id`` and ``project_id`` are provided, a GUARDRAIL_VIOLATION
        event is emitted for any critical-severity failures.
        """
        results = self.run_checks(content, output_type, context)
        self.record_checks(conn, output_id, results)

        # Emit violation event if critical failures and we have the needed IDs
        if node_id is not None and project_id is not None:
            emit_guardrail_violation(conn, project_id, output_id, node_id, results)

        return results

    @staticmethod
    def get_check_results(conn: psycopg.Connection, output_id: UUID) -> list[dict]:
        """Get all guardrail check results for an output."""
        rows = conn.execute(
            """
            SELECT rule_name, passed, severity, violation_details, checked_at
            FROM guardrail_checks
            WHERE output_id = %s
            ORDER BY checked_at
            """,
            (output_id,),
        ).fetchall()
        return [dict(row) for row in rows]
