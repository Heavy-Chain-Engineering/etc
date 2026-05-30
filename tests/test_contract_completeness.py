"""Contract tests for Contract-Completeness in /spec + /architect.

Feature F-2026-05-29-contract-completeness-spec-architect. Grep-based
skill-contract tests plus two stdlib-only behavioral round-trips, mirroring
tests/test_user_flow_completeness.py (the near-exact structural precedent this
feature reuses, BR-010).

The implementation under test is on disk (committed source artifacts):

- standards/process/contract-completeness.md            (new standard)
- standards/process/source-of-truth-conflict-rule.md    (new MANDATORY standard)
- skills/spec/SKILL.md       (Phase 3 Steps 4e/4f/4g, Phase 4 Liveness gate,
                              Phase 5 contract_completeness block)
- skills/architect/SKILL.md  (Phase 3.5 format/DTO elicitation, Phase 4 WARN)
- hooks/inject-standards.sh  (two new ### injection blocks)

Assertions grep STABLE LITERAL STEMS (e.g. `Live at`, `BLOCKER:`, `storage=`,
`API-response guarantee:`, `[SPEC-WINS]`, `schema_version`) rather than full
placeholder text, because the SKILL.md edits use placeholder shorthand that
differs slightly from each standard's full placeholder wording. A brittle
exact-placeholder test that fails is worse than a stem-based test.

Per GA-005 (no new tech / no new production module), the schema and
sanitization round-trips use small test-local validators implemented with the
stdlib only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source artifacts (asserted directly against committed files — the
# implementation-on-disk this verification task covers).
CONTRACT_STANDARD = REPO_ROOT / "standards" / "process" / "contract-completeness.md"
CONFLICT_STANDARD = (
    REPO_ROOT / "standards" / "process" / "source-of-truth-conflict-rule.md"
)
SPEC_SKILL = REPO_ROOT / "skills" / "spec" / "SKILL.md"
ARCHITECT_SKILL = REPO_ROOT / "skills" / "architect" / "SKILL.md"
INJECT_HOOK = REPO_ROOT / "hooks" / "inject-standards.sh"


# -- Module-scoped text fixtures ---------------------------------------------


@pytest.fixture(scope="module")
def contract_standard_text() -> str:
    assert CONTRACT_STANDARD.exists(), f"missing standard: {CONTRACT_STANDARD}"
    return CONTRACT_STANDARD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def conflict_standard_text() -> str:
    assert CONFLICT_STANDARD.exists(), f"missing standard: {CONFLICT_STANDARD}"
    return CONFLICT_STANDARD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def spec_skill_text() -> str:
    assert SPEC_SKILL.exists(), f"missing skill source: {SPEC_SKILL}"
    return SPEC_SKILL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def architect_skill_text() -> str:
    assert ARCHITECT_SKILL.exists(), f"missing skill source: {ARCHITECT_SKILL}"
    return ARCHITECT_SKILL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def inject_hook_text() -> str:
    assert INJECT_HOOK.exists(), f"missing hook script: {INJECT_HOOK}"
    return INJECT_HOOK.read_text(encoding="utf-8")


# -- Test-local helpers (stdlib only, GA-005 — no new production module) ------

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_DEFAULT_CAP = 512


def _sanitize(value: str, *, cap: int = _DEFAULT_CAP) -> str:
    """Strip control chars (`[\\x00-\\x1f\\x7f]`) and cap length (BR-011).

    Mirrors the capture-site contract the SKILL.md prose documents: strip
    `[\\x00-\\x1f\\x7f]`, then truncate to `cap` characters.
    """
    stripped = _CONTROL_CHARS_RE.sub("", value)
    return stripped[:cap]


def _validate_liveness_block(block: dict[str, Any]) -> None:
    """Validate a `contract_completeness` block against the design invariants.

    Raises ValueError on any violation. Implements (stdlib only) the invariants
    named in standards/process/contract-completeness.md and design.md:

    - `schema_version` present and an integer.
    - each `liveness[]` entry guarantees ac_id, outcome, live_at,
      acceptance_statement.
    - `deferred_reason` non-empty iff `live_at == "deferred"`.
    - every `override.reason` and every `blocker.owner` non-empty.
    """
    schema_version = block.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ValueError("schema_version must be present and an integer")

    for entry in block.get("liveness", []):
        for key in ("ac_id", "outcome", "live_at", "acceptance_statement"):
            if not entry.get(key):
                raise ValueError(f"liveness entry missing required key: {key}")
        live_at = entry["live_at"]
        deferred_reason = entry.get("deferred_reason")
        is_deferred = live_at == "deferred"
        has_reason = bool(deferred_reason)
        if is_deferred != has_reason:
            raise ValueError(
                "deferred_reason must be non-empty iff live_at == 'deferred'"
            )

    for override in block.get("overrides", []):
        if not override.get("reason"):
            raise ValueError("override.reason must be non-empty")

    for blocker in block.get("blockers", []):
        if not blocker.get("owner"):
            raise ValueError("blocker.owner must be non-empty")


def _well_formed_block() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "liveness": [
            {
                "ac_id": "AC-3",
                "outcome": "saving a drawer edit persists and survives reload",
                "live_at": "wave-2",
                "acceptance_statement": "on save, a network call persists X; "
                "a reload shows it",
                "deferred_reason": None,
            }
        ],
        "blockers": [],
        "overrides": [],
        "conflict_sources": ["code", "spec", "prototype"],
    }


# -- AC-12 / AC-4: standards exist + hook references both --------------------


class TestStandardsExist:
    """Both new standards exist with their load-bearing content (AC-4, AC-12)."""

    def test_contract_completeness_standard_is_mandatory(
        self, contract_standard_text: str
    ) -> None:
        assert "## Status: MANDATORY" in contract_standard_text
        # The five contract classes table is the spine of the standard.
        assert "liveness + milestone" in contract_standard_text.lower()
        assert "Response-DTO obligation" in contract_standard_text

    def test_conflict_rule_standard_is_mandatory_and_states_the_rule(
        self, conflict_standard_text: str
    ) -> None:
        assert "## Status: MANDATORY" in conflict_standard_text
        assert "Majority wins" in conflict_standard_text
        assert "[SPEC-WINS]" in conflict_standard_text
        # Dissent escalates, never silently overridden (BR-004).
        assert "escalate" in conflict_standard_text.lower()


class TestInjectStandardsHook:
    """hooks/inject-standards.sh surfaces BOTH new standards (AC-4, AC-12)."""

    def test_hook_has_both_section_headings(self, inject_hook_text: str) -> None:
        assert (
            "### Contract-Completeness for /spec and /architect (MANDATORY)"
            in inject_hook_text
        )
        assert (
            "### Source-of-Truth Conflict Rule (MANDATORY, always in force)"
            in inject_hook_text
        )

    def test_hook_points_at_both_standards_files(
        self, inject_hook_text: str
    ) -> None:
        assert (
            "standards/process/contract-completeness.md" in inject_hook_text
        )
        assert (
            "standards/process/source-of-truth-conflict-rule.md"
            in inject_hook_text
        )


# -- AC-12: /spec skill contract gates ---------------------------------------


class TestSpecSkillContractGates:
    """/spec SKILL.md documents the intent-tier contract gates (AC-12).

    Liveness elicitation (class 1), source-of-truth capture (class 2),
    open-question -> BLOCKER (class 3), the Phase 4 Liveness WARN gate, and the
    Phase 5 contract_completeness state block.
    """

    def test_liveness_elicitation_present(self, spec_skill_text: str) -> None:
        # Durable canonical-sentence stems (placeholder shorthand-tolerant).
        assert "Live at" in spec_skill_text
        assert "fully-functional" in spec_skill_text

    def test_source_of_truth_capture_present(self, spec_skill_text: str) -> None:
        assert "Sources in play:" in spec_skill_text
        assert "source-of-truth-conflict-rule" in spec_skill_text

    def test_open_question_blocker_path_present(
        self, spec_skill_text: str
    ) -> None:
        # The canonical BLOCKER sentence stem + owner segment.
        assert "BLOCKER:" in spec_skill_text
        assert "— owner:" in spec_skill_text

    def test_liveness_warn_gate_present(self, spec_skill_text: str) -> None:
        # The Phase 4 gate is a WARN, not a hard-block, and is exempt for
        # infrastructure_only features.
        assert "Liveness gate" in spec_skill_text
        assert "WARN, not a hard-block" in spec_skill_text
        assert "infrastructure_only" in spec_skill_text

    def test_phase_5_contract_completeness_block_present(
        self, spec_skill_text: str
    ) -> None:
        assert "contract_completeness" in spec_skill_text
        assert "schema_version" in spec_skill_text
        # deferred_reason invariant prose co-located with the block.
        assert "deferred_reason" in spec_skill_text


# -- AC-12: /architect skill contract gates ----------------------------------


class TestArchitectSkillContractGates:
    """/architect SKILL.md documents the architecture-tier contract gates.

    Format-contract elicitation (class 4), response-DTO-obligation elicitation
    (class 5), and the Phase 4 WARN DoR items (AC-2, AC-3, AC-12).
    """

    def test_format_contract_elicitation_present(
        self, architect_skill_text: str
    ) -> None:
        # Durable format-sentence facet stems.
        assert "Format of" in architect_skill_text
        assert "storage=" in architect_skill_text
        assert "wire=" in architect_skill_text

    def test_dto_obligation_elicitation_present(
        self, architect_skill_text: str
    ) -> None:
        assert "API-response guarantee:" in architect_skill_text
        assert "federally" in architect_skill_text

    def test_phase_4_warn_items_present(
        self, architect_skill_text: str
    ) -> None:
        # The two DoR checklist items must each be WARN, never hard-block.
        assert "Format contracts are present" in architect_skill_text
        assert "Response-DTO obligations are present" in architect_skill_text
        assert "does not hard-block" in architect_skill_text


# -- AC-9: liveness-block schema round-trip (stdlib only, GA-005) -------------


class TestLivenessBlockSchema:
    """Test-local stdlib validator round-trips the liveness block (AC-9)."""

    def test_well_formed_block_validates(self) -> None:
        _validate_liveness_block(_well_formed_block())

    def test_deferred_requires_non_null_reason(self) -> None:
        block = _well_formed_block()
        block["liveness"][0]["live_at"] = "deferred"
        # deferred_reason still null -> invalid.
        with pytest.raises(ValueError, match="deferred_reason"):
            _validate_liveness_block(block)

    def test_deferred_with_reason_validates(self) -> None:
        block = _well_formed_block()
        block["liveness"][0]["live_at"] = "deferred"
        block["liveness"][0]["deferred_reason"] = "blocked on upstream API"
        _validate_liveness_block(block)

    def test_non_deferred_with_reason_is_rejected(self) -> None:
        # Reason present but live_at is a milestone -> the iff is violated.
        block = _well_formed_block()
        block["liveness"][0]["deferred_reason"] = "should not be here"
        with pytest.raises(ValueError, match="deferred_reason"):
            _validate_liveness_block(block)

    def test_missing_schema_version_is_rejected(self) -> None:
        block = _well_formed_block()
        del block["schema_version"]
        with pytest.raises(ValueError, match="schema_version"):
            _validate_liveness_block(block)

    def test_non_integer_schema_version_is_rejected(self) -> None:
        block = _well_formed_block()
        block["schema_version"] = "1"
        with pytest.raises(ValueError, match="schema_version"):
            _validate_liveness_block(block)

    def test_empty_override_reason_is_rejected(self) -> None:
        block = _well_formed_block()
        block["overrides"] = [
            {"contract_class": "liveness", "ref": "AC-3", "reason": ""}
        ]
        with pytest.raises(ValueError, match="override.reason"):
            _validate_liveness_block(block)

    def test_empty_blocker_owner_is_rejected(self) -> None:
        block = _well_formed_block()
        block["blockers"] = [{"question": "what wire format?", "owner": ""}]
        with pytest.raises(ValueError, match="blocker.owner"):
            _validate_liveness_block(block)


# -- AC-11: sanitization round-trip ------------------------------------------


class TestSanitization:
    """Capture-site sanitization strips control chars + caps length (AC-11)."""

    def test_control_chars_are_stripped(self) -> None:
        hostile = "drawer\x00edit\x1f persists\x7f now"
        cleaned = _sanitize(hostile)
        assert "\x00" not in cleaned
        assert "\x1f" not in cleaned
        assert "\x7f" not in cleaned
        assert cleaned == "draweredit persists now"

    def test_newline_and_tab_are_stripped(self) -> None:
        # \n (0x0a) and \t (0x09) fall inside [\x00-\x1f] — CSV/log-injection.
        cleaned = _sanitize("a\nb\tc")
        assert cleaned == "abc"

    def test_oversize_input_is_truncated(self) -> None:
        cleaned = _sanitize("x" * 5000, cap=512)
        assert len(cleaned) == 512

    def test_benign_input_is_preserved(self) -> None:
        benign = "Live at wave-2; fully-functional means: a reload shows it."
        assert _sanitize(benign) == benign


# -- AC-7: forward-only + infrastructure_only exemption ----------------------


class TestForwardOnlyAndExemption:
    """Legacy / infrastructure_only specs produce no contract WARN (AC-7).

    BR-007 (forward-only): legacy artifacts are never auto-mutated. Edge Case 3
    (infrastructure_only): the liveness gate is exempt for such features.
    """

    def test_spec_skill_documents_forward_only(self, spec_skill_text: str) -> None:
        assert "Forward-only behavior (BR-007)" in spec_skill_text
        # Legacy specs are NOT auto-mutated.
        assert "NOT auto-mutated" in spec_skill_text or (
            "NOT auto-modified" in spec_skill_text
        )

    def test_spec_skill_documents_infrastructure_only_exemption(
        self, spec_skill_text: str
    ) -> None:
        # Exemption prose: infrastructure_only -> liveness gate is exempt.
        assert "infrastructure_only" in spec_skill_text
        assert "exempt" in spec_skill_text

    def test_contract_standard_documents_forward_only(
        self, contract_standard_text: str
    ) -> None:
        assert "Forward-only" in contract_standard_text
        assert "never auto-mutated" in contract_standard_text
        assert "infrastructure_only" in contract_standard_text
