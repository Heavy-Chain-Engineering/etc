"""Tests for guardrail middleware — anti-pattern scanning and output schema validation."""

from __future__ import annotations

import json
from uuid import UUID

import psycopg
import pytest

from etc_platform.guardrails import (
    AntiPatternScanRule,
    CoverageGateRule,
    DomainFidelityRule,
    GuardrailMiddleware,
    GuardrailResult,
    GuardrailRule,
    OutputSchemaValidationRule,
    SecurityScanRule,
    SpecComplianceRule,
    TDDVerificationRule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_output_chain(db: psycopg.Connection, output_type: str = "research_report") -> UUID:
    """Create the full FK chain: project -> phase -> graph -> node -> run -> output.

    Returns the output_id.
    """
    project = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('p', '/tmp', 'greenfield') RETURNING id"
    ).fetchone()
    pid = project["id"]

    phase = db.execute(
        "INSERT INTO phases (project_id, name) VALUES (%s, 'Build') RETURNING id",
        (pid,),
    ).fetchone()

    graph = db.execute(
        "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
        "VALUES (%s, %s, 'g', 'running') RETURNING id",
        (pid, phase["id"]),
    ).fetchone()

    node = db.execute(
        "INSERT INTO execution_nodes (graph_id, node_type, name, status) "
        "VALUES (%s, 'leaf', 'n', 'running') RETURNING id",
        (graph["id"],),
    ).fetchone()

    run = db.execute(
        "INSERT INTO agent_runs (node_id, agent_type, model, status) "
        "VALUES (%s, 'researcher', 'test', 'completed') RETURNING id",
        (node["id"],),
    ).fetchone()

    output = db.execute(
        "INSERT INTO agent_outputs (run_id, output_type) VALUES (%s, %s) RETURNING id",
        (run["id"], output_type),
    ).fetchone()

    return output["id"]


# ===========================================================================
# GuardrailResult dataclass
# ===========================================================================


class TestGuardrailResult:
    def test_result_dataclass(self) -> None:
        result = GuardrailResult(
            rule_name="test_rule",
            passed=True,
            severity="low",
        )
        assert result.rule_name == "test_rule"
        assert result.passed is True
        assert result.severity == "low"
        assert result.violation_details is None

    def test_result_with_violations(self) -> None:
        details = {"patterns_found": ["is_active", "has_permission"]}
        result = GuardrailResult(
            rule_name="anti_pattern_scan",
            passed=False,
            severity="critical",
            violation_details=details,
        )
        assert result.passed is False
        assert result.severity == "critical"
        assert result.violation_details == details


# ===========================================================================
# AntiPatternScanRule
# ===========================================================================


class TestAntiPatternScanRule:
    def test_clean_content_passes(self) -> None:
        rule = AntiPatternScanRule()
        result = rule.check(
            content="## Summary\nThis is a clean research report with no anti-patterns.",
            output_type="research_report",
        )
        assert result.passed is True
        assert result.rule_name == "anti_pattern_scan"
        assert result.severity == "critical"

    def test_boolean_flags_detected(self) -> None:
        rule = AntiPatternScanRule()
        content = (
            "The legacy system uses multiple boolean flags:\n"
            "is_active, is_deleted, has_permission, can_edit\n"
            "These should be migrated directly."
        )
        result = rule.check(content=content, output_type="research_report")
        assert result.passed is False
        assert result.violation_details is not None
        assert "boolean_flag_sets" in result.violation_details

    def test_hardcoded_enums_detected(self) -> None:
        rule = AntiPatternScanRule()
        content = (
            "The status field uses hardcoded values:\n"
            "STATUS = ['active', 'inactive', 'pending', 'archived']\n"
            "We should copy this directly."
        )
        result = rule.check(content=content, output_type="prd")
        assert result.passed is False
        assert result.violation_details is not None
        assert "hardcoded_enums" in result.violation_details

    def test_only_applies_to_research_and_prd(self) -> None:
        rule = AntiPatternScanRule()
        # research_report should be checked
        bad_content = "is_active, is_deleted, has_permission, can_edit flags everywhere"
        result_research = rule.check(content=bad_content, output_type="research_report")
        assert result_research.passed is False

        result_prd = rule.check(content=bad_content, output_type="prd")
        assert result_prd.passed is False

    def test_skips_code_output_type(self) -> None:
        rule = AntiPatternScanRule()
        # Code type should always pass (not scanned for anti-patterns)
        content = "is_active = True\nhas_permission = False\ncan_edit = True"
        result = rule.check(content=content, output_type="code")
        assert result.passed is True

    def test_skips_other_output_types(self) -> None:
        rule = AntiPatternScanRule()
        content = "is_active, is_deleted, has_permission, can_edit flags everywhere"
        for output_type in ("test", "adr", "review"):
            result = rule.check(content=content, output_type=output_type)
            assert result.passed is True, f"Should skip {output_type}"


# ===========================================================================
# OutputSchemaValidationRule
# ===========================================================================


class TestOutputSchemaValidation:
    def test_valid_research_report(self) -> None:
        rule = OutputSchemaValidationRule()
        content = (
            "# Research Report\n"
            "## Summary\nThis is the summary.\n"
            "## Findings\nHere are the findings.\n"
            "## Recommendations\nHere are the recommendations.\n"
        )
        result = rule.check(content=content, output_type="research_report")
        assert result.passed is True
        assert result.rule_name == "output_schema_validation"

    def test_invalid_research_report_missing_sections(self) -> None:
        rule = OutputSchemaValidationRule()
        content = "## Summary\nJust a summary, missing Findings and Recommendations."
        result = rule.check(content=content, output_type="research_report")
        assert result.passed is False
        assert result.severity == "high"
        assert result.violation_details is not None
        assert "missing_sections" in result.violation_details

    def test_valid_prd(self) -> None:
        rule = OutputSchemaValidationRule()
        content = (
            "# Product Requirements Document\n"
            "## Requirements\nThese are the requirements.\n"
            "## Scope\nThis is the scope.\n"
        )
        result = rule.check(content=content, output_type="prd")
        assert result.passed is True

    def test_invalid_prd(self) -> None:
        rule = OutputSchemaValidationRule()
        content = "# PRD\nJust a title, missing Requirements and Scope."
        result = rule.check(content=content, output_type="prd")
        assert result.passed is False
        assert result.violation_details is not None
        assert "missing_sections" in result.violation_details

    def test_code_with_function(self) -> None:
        rule = OutputSchemaValidationRule()
        content = "def hello_world():\n    print('hello')\n"
        result = rule.check(content=content, output_type="code")
        assert result.passed is True

    def test_code_with_class(self) -> None:
        rule = OutputSchemaValidationRule()
        content = "class MyClass:\n    pass\n"
        result = rule.check(content=content, output_type="code")
        assert result.passed is True

    def test_code_without_function(self) -> None:
        rule = OutputSchemaValidationRule()
        content = "x = 42\nprint(x)\n"
        result = rule.check(content=content, output_type="code")
        assert result.passed is False
        assert result.violation_details is not None
        assert "missing_sections" in result.violation_details

    def test_unknown_type_passes(self) -> None:
        rule = OutputSchemaValidationRule()
        content = "anything goes here"
        result = rule.check(content=content, output_type="review")
        assert result.passed is True

    def test_test_type_passes(self) -> None:
        rule = OutputSchemaValidationRule()
        content = "anything goes here"
        result = rule.check(content=content, output_type="test")
        assert result.passed is True


# ===========================================================================
# DomainFidelityRule
# ===========================================================================


class TestDomainFidelityRule:
    def test_domain_fidelity_no_context(self) -> None:
        """Passes when no domain axioms provided."""
        rule = DomainFidelityRule()
        result = rule.check("some content", "research_report")
        assert result.passed is True

    def test_domain_fidelity_empty_axioms(self) -> None:
        """Passes when axioms list is empty."""
        rule = DomainFidelityRule()
        result = rule.check("some content", "research_report", context={"domain_axioms": []})
        assert result.passed is True

    def test_domain_fidelity_violation_detected(self) -> None:
        """Fails when check function finds violations."""
        rule = DomainFidelityRule()
        rule._check_fn = lambda content, axioms: [
            {"axiom": "Status is always computed", "contradiction": "Output says status is stored", "excerpt": "status field is persisted"}
        ]
        result = rule.check(
            "The status field is persisted in the database",
            "research_report",
            context={"domain_axioms": ["Status is always computed, never stored"]},
        )
        assert result.passed is False
        assert result.severity == "critical"
        assert "axiom_violations" in result.violation_details
        assert len(result.violation_details["axiom_violations"]) == 1

    def test_domain_fidelity_no_violation(self) -> None:
        """Passes when check function finds no violations."""
        rule = DomainFidelityRule()
        rule._check_fn = lambda content, axioms: []
        result = rule.check(
            "Status is computed dynamically from workflow state",
            "research_report",
            context={"domain_axioms": ["Status is always computed, never stored"]},
        )
        assert result.passed is True

    def test_domain_fidelity_multiple_violations(self) -> None:
        """Reports multiple violations correctly."""
        rule = DomainFidelityRule()
        rule._check_fn = lambda content, axioms: [
            {"axiom": "Axiom 1", "contradiction": "Violated 1", "excerpt": "excerpt 1"},
            {"axiom": "Axiom 2", "contradiction": "Violated 2", "excerpt": "excerpt 2"},
        ]
        result = rule.check(
            "some contradicting content",
            "research_report",
            context={"domain_axioms": ["Axiom 1", "Axiom 2"]},
        )
        assert result.passed is False
        assert len(result.violation_details["axiom_violations"]) == 2

    def test_domain_fidelity_rule_attributes(self) -> None:
        """Rule has correct name and severity."""
        rule = DomainFidelityRule()
        assert rule.name == "domain_fidelity_check"
        assert rule.severity == "critical"


# ===========================================================================
# CoverageGateRule
# ===========================================================================


class TestCoverageGateRule:
    def test_skips_non_code_output(self) -> None:
        rule = CoverageGateRule(threshold=80.0)
        result = rule.check("some content", "research_report")
        assert result.passed is True

    def test_passes_above_threshold(self) -> None:
        rule = CoverageGateRule(threshold=80.0)
        result = rule.check("code", "code", context={"coverage_percent": 95.0})
        assert result.passed is True

    def test_fails_below_threshold(self) -> None:
        rule = CoverageGateRule(threshold=80.0)
        result = rule.check("code", "code", context={"coverage_percent": 65.0})
        assert result.passed is False
        assert result.violation_details["coverage_percent"] == 65.0
        assert result.violation_details["threshold"] == 80.0
        assert result.violation_details["deficit"] == 15.0

    def test_parses_pytest_cov_output(self) -> None:
        rule = CoverageGateRule(threshold=80.0)
        content = "Name    Stmts   Miss  Cover\nTOTAL    500    50    90%"
        result = rule.check(content, "code")
        assert result.passed is True

    def test_parses_coverage_label(self) -> None:
        rule = CoverageGateRule(threshold=80.0)
        content = "Coverage: 75.5%"
        result = rule.check(content, "code")
        assert result.passed is False

    def test_no_coverage_info_passes_with_warning(self) -> None:
        rule = CoverageGateRule(threshold=80.0)
        result = rule.check("just some code", "code")
        assert result.passed is True
        assert result.violation_details["warning"] == "Could not determine coverage"

    def test_custom_threshold(self) -> None:
        rule = CoverageGateRule(threshold=95.0)
        result = rule.check("code", "code", context={"coverage_percent": 90.0})
        assert result.passed is False

    def test_rule_attributes(self) -> None:
        rule = CoverageGateRule()
        assert rule.name == "coverage_gate"
        assert rule.severity == "high"
        assert rule.threshold == 80.0


# ===========================================================================
# TDDVerificationRule
# ===========================================================================


class TestTDDVerificationRule:
    def test_skips_non_code_output(self) -> None:
        rule = TDDVerificationRule()
        result = rule.check("def some_function(): pass", "research_report")
        assert result.passed is True

    def test_passes_with_tests_in_content(self) -> None:
        rule = TDDVerificationRule()
        code = """
def test_add():
    assert add(1, 2) == 3

def add(a, b):
    return a + b
"""
        result = rule.check(code, "code")
        assert result.passed is True

    def test_fails_impl_without_tests(self) -> None:
        rule = TDDVerificationRule()
        code = """
class UserService:
    def get_user(self, user_id):
        return self.db.query(user_id)
"""
        result = rule.check(code, "code")
        assert result.passed is False
        assert "without test code" in result.violation_details["reason"]

    def test_passes_with_context_has_tests_true(self) -> None:
        rule = TDDVerificationRule()
        result = rule.check("impl code", "code", context={"has_tests": True})
        assert result.passed is True

    def test_fails_with_context_has_tests_false(self) -> None:
        rule = TDDVerificationRule()
        result = rule.check("impl code", "code", context={"has_tests": False})
        assert result.passed is False

    def test_fails_with_impl_files_no_test_files(self) -> None:
        rule = TDDVerificationRule()
        result = rule.check("code", "code", context={
            "files_written": ["src/service.py", "src/models.py"],
        })
        assert result.passed is False
        assert "impl_files" in result.violation_details

    def test_passes_with_test_and_impl_files(self) -> None:
        rule = TDDVerificationRule()
        result = rule.check("code", "code", context={
            "files_written": ["src/service.py", "tests/test_service.py"],
        })
        assert result.passed is True

    def test_rule_attributes(self) -> None:
        rule = TDDVerificationRule()
        assert rule.name == "tdd_verification"
        assert rule.severity == "medium"


# ===========================================================================
# GuardrailMiddleware
# ===========================================================================


class TestGuardrailMiddleware:
    def test_run_checks_returns_results(self) -> None:
        mw = GuardrailMiddleware()
        results = mw.run_checks(
            content="## Summary\n## Findings\n## Recommendations\nClean content.",
            output_type="research_report",
        )
        assert isinstance(results, list)
        assert len(results) == 2  # default two rules
        assert all(isinstance(r, GuardrailResult) for r in results)

    def test_all_rules_executed(self) -> None:
        mw = GuardrailMiddleware()
        results = mw.run_checks(
            content="## Summary\n## Findings\n## Recommendations\nClean.",
            output_type="research_report",
        )
        rule_names = {r.rule_name for r in results}
        assert "anti_pattern_scan" in rule_names
        assert "output_schema_validation" in rule_names

    def test_custom_rules(self) -> None:
        """Middleware accepts a custom list of rules."""
        mw = GuardrailMiddleware(rules=[OutputSchemaValidationRule()])
        results = mw.run_checks(content="## Summary\n", output_type="research_report")
        assert len(results) == 1
        assert results[0].rule_name == "output_schema_validation"

    def test_record_checks_inserts_rows(self, db: psycopg.Connection) -> None:
        output_id = _setup_output_chain(db)
        mw = GuardrailMiddleware()
        results = mw.run_checks(
            content="## Summary\n## Findings\n## Recommendations\nClean report.",
            output_type="research_report",
        )
        mw.record_checks(db, output_id, results)

        rows = db.execute(
            "SELECT rule_name, passed, severity FROM guardrail_checks WHERE output_id = %s",
            (output_id,),
        ).fetchall()
        assert len(rows) == 2
        rule_names = {r["rule_name"] for r in rows}
        assert "anti_pattern_scan" in rule_names
        assert "output_schema_validation" in rule_names

    def test_record_checks_rejects_on_critical_fail(self, db: psycopg.Connection) -> None:
        output_id = _setup_output_chain(db)
        mw = GuardrailMiddleware()

        # Content with boolean flag anti-pattern -> critical fail
        bad_content = (
            "## Summary\n## Findings\n## Recommendations\n"
            "is_active, is_deleted, has_permission, can_edit flags detected."
        )
        results = mw.run_checks(content=bad_content, output_type="research_report")

        # Confirm we have at least one critical failure
        critical_fails = [r for r in results if not r.passed and r.severity == "critical"]
        assert len(critical_fails) > 0

        mw.record_checks(db, output_id, results)

        output = db.execute(
            "SELECT accepted, guardrail_results FROM agent_outputs WHERE id = %s",
            (output_id,),
        ).fetchone()
        assert output is not None
        assert output["accepted"] is False

        # guardrail_results should be a JSONB summary
        gr = output["guardrail_results"]
        assert isinstance(gr, dict) or isinstance(gr, str)

    def test_record_checks_accepts_on_all_pass(self, db: psycopg.Connection) -> None:
        output_id = _setup_output_chain(db)
        mw = GuardrailMiddleware()
        results = mw.run_checks(
            content="## Summary\n## Findings\n## Recommendations\nClean report.",
            output_type="research_report",
        )
        # All should pass
        assert all(r.passed for r in results)

        mw.record_checks(db, output_id, results)

        output = db.execute(
            "SELECT accepted FROM agent_outputs WHERE id = %s",
            (output_id,),
        ).fetchone()
        assert output is not None
        assert output["accepted"] is True

    def test_check_and_record_full_flow(self, db: psycopg.Connection) -> None:
        output_id = _setup_output_chain(db)
        mw = GuardrailMiddleware()

        results = mw.check_and_record(
            conn=db,
            output_id=output_id,
            content="## Summary\n## Findings\n## Recommendations\nAll good.",
            output_type="research_report",
        )

        assert isinstance(results, list)
        assert len(results) == 2

        # Verify DB was written
        rows = db.execute(
            "SELECT * FROM guardrail_checks WHERE output_id = %s", (output_id,)
        ).fetchall()
        assert len(rows) == 2

        output = db.execute(
            "SELECT accepted FROM agent_outputs WHERE id = %s", (output_id,)
        ).fetchone()
        assert output["accepted"] is True

    def test_get_check_results(self, db: psycopg.Connection) -> None:
        output_id = _setup_output_chain(db)
        mw = GuardrailMiddleware()
        mw.check_and_record(
            conn=db,
            output_id=output_id,
            content="## Summary\n## Findings\n## Recommendations\nOK.",
            output_type="research_report",
        )

        results = GuardrailMiddleware.get_check_results(db, output_id)
        assert isinstance(results, list)
        assert len(results) == 2
        # Each result should be a dict with expected keys
        for r in results:
            assert "rule_name" in r
            assert "passed" in r
            assert "severity" in r


# ===========================================================================
# SecurityScanRule
# ===========================================================================


class TestSecurityScanRule:
    def test_skips_non_code_output(self) -> None:
        rule = SecurityScanRule()
        result = rule.check("password = 'hunter2secret'", "research_report")
        assert result.passed is True

    def test_detects_sql_injection_fstring(self) -> None:
        rule = SecurityScanRule()
        code = 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'
        result = rule.check(code, "code")
        assert result.passed is False
        assert "sql_injection" in result.violation_details

    def test_detects_hardcoded_secrets(self) -> None:
        rule = SecurityScanRule()
        code = 'api_key = "sk-1234567890abcdef"'
        result = rule.check(code, "code")
        assert result.passed is False
        assert "hardcoded_secrets" in result.violation_details

    def test_detects_xss(self) -> None:
        rule = SecurityScanRule()
        code = "element.innerHTML = userInput"
        result = rule.check(code, "code")
        assert result.passed is False
        assert "xss" in result.violation_details

    def test_detects_insecure_deserialization(self) -> None:
        rule = SecurityScanRule()
        # Detects unsafe pickle usage in generated code
        code = "data = pickle.loads(user_data)"
        result = rule.check(code, "code")
        assert result.passed is False
        assert "insecure_deserialization" in result.violation_details

    def test_passes_clean_code(self) -> None:
        rule = SecurityScanRule()
        code = '''
def get_user(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
'''
        result = rule.check(code, "code")
        assert result.passed is True

    def test_detects_eval(self) -> None:
        rule = SecurityScanRule()
        # Verifies that eval() calls are flagged as insecure deserialization
        code = "result = eval(user_expression)"
        result = rule.check(code, "code")
        assert result.passed is False

    def test_multiple_violations(self) -> None:
        rule = SecurityScanRule()
        code = '''
password = "supersecretpass123"
cursor.execute(f"SELECT * FROM users WHERE name = {name}")
'''
        result = rule.check(code, "code")
        assert result.passed is False
        assert len(result.violation_details) >= 2

    def test_rule_attributes(self) -> None:
        rule = SecurityScanRule()
        assert rule.name == "security_scan"
        assert rule.severity == "high"


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
