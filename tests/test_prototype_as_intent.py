"""Contract tests for Prototype-as-Intent in /design (Gap C).

Feature F-2026-05-30-prototype-as-intent-design. Grep-based skill-contract
tests plus a source->dist parity round-trip, mirroring
tests/test_contract_completeness.py (the Gap B grep-contract precedent this
feature reuses).

The implementation under test is on disk (committed source artifacts):

- standards/process/prototype-as-intent.md   (new standing standard)
- skills/design/SKILL.md                      (Phase-1 prototype declaration at
                                               Step 3.5, Phase-5 post-processing
                                               rules at Step 4.4, the
                                               state.yaml.design_phase.prototype
                                               block, cites the standard by path)
- spec/etc_sdlc.yaml                          (the standard registered under
                                               standards.categories.process)

Assertions grep STABLE LITERAL STEMS (e.g. `REQUIRED`, `ILLUSTRATIVE`,
`component_lib_path`, `Data fidelity`) rather than full prose, because a
brittle exact-text test that fails on a wording tweak is worse than a
stem-based test (the Gap B rationale, BR-010).

Per AGA-005 (no new Python module), the parity round-trip compiles the spec
into a tmp dist via compile-sdlc.py and asserts the standard mirrors through
(the #18 named-set-equality precedent: a new standard must have a parity test).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source artifacts (asserted directly against committed files — the
# implementation-on-disk this verification task covers).
PROTOTYPE_STANDARD = REPO_ROOT / "standards" / "process" / "prototype-as-intent.md"
DESIGN_SKILL = REPO_ROOT / "skills" / "design" / "SKILL.md"
COMPILE_SCRIPT = REPO_ROOT / "compile-sdlc.py"
SPEC_FILE = REPO_ROOT / "spec" / "etc_sdlc.yaml"


# -- Module-scoped text fixtures ---------------------------------------------


@pytest.fixture(scope="module")
def prototype_standard_text() -> str:
    assert PROTOTYPE_STANDARD.exists(), f"missing standard: {PROTOTYPE_STANDARD}"
    return PROTOTYPE_STANDARD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def design_skill_text() -> str:
    assert DESIGN_SKILL.exists(), f"missing skill source: {DESIGN_SKILL}"
    return DESIGN_SKILL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def spec_doc() -> dict:
    assert SPEC_FILE.exists(), f"missing spec: {SPEC_FILE}"
    return yaml.safe_load(SPEC_FILE.read_text(encoding="utf-8"))


# -- AC-1..AC-6: the standard states the four disciplines --------------------


class TestStandardStatesFourDisciplines:
    """prototype-as-intent.md is MANDATORY and states all four disciplines."""

    def test_standard_is_mandatory_and_applies_to_design(
        self, prototype_standard_text: str
    ) -> None:
        assert "## Status: MANDATORY" in prototype_standard_text
        assert "## Applies to: /design" in prototype_standard_text

    def test_discipline_intent_only(self, prototype_standard_text: str) -> None:
        # Discipline 1: prototype is intent, its implementation is illustrative.
        assert "Intent-only" in prototype_standard_text
        assert "ILLUSTRATIVE, never canonical" in prototype_standard_text

    def test_discipline_required_vs_illustrative(
        self, prototype_standard_text: str
    ) -> None:
        # Discipline 2: every affordance is REQUIRED or ILLUSTRATIVE.
        assert "REQUIRED vs ILLUSTRATIVE" in prototype_standard_text
        assert "defaults to REQUIRED and is" in prototype_standard_text

    def test_discipline_component_lib_first_real_tokens(
        self, prototype_standard_text: str
    ) -> None:
        # Discipline 3: real component library + real tokens, never the mock's.
        assert "Component-lib-first" in prototype_standard_text
        assert "component_lib_path" in prototype_standard_text
        assert "Provenance over coincidence" in prototype_standard_text

    def test_discipline_data_fidelity_clean_template(
        self, prototype_standard_text: str
    ) -> None:
        # Discipline 4: data fidelity + clean ingestible template.
        assert "Data fidelity" in prototype_standard_text
        assert "clean template" in prototype_standard_text.lower()
        assert "no scaffolding rows" in prototype_standard_text

    def test_declaration_is_explicit_never_inferred(
        self, prototype_standard_text: str
    ) -> None:
        # AGA-001 / ADR-001: explicit declaration, never heuristic detection.
        assert "recorded, never silently inferred" in prototype_standard_text
        assert "standing and MANDATORY" in prototype_standard_text


# -- AC-7/AC-8: /design SKILL.md cites + declares + state block --------------


class TestDesignSkillContract:
    """/design SKILL.md cites the standard, declares the prototype, and writes
    the state.yaml.design_phase.prototype block (AC-7, AC-8)."""

    def test_skill_cites_standard_by_path(self, design_skill_text: str) -> None:
        # F002 citation pattern: reference by path, do not duplicate the rules.
        assert "standards/process/prototype-as-intent.md" in design_skill_text

    def test_skill_has_phase_1_prototype_declaration(
        self, design_skill_text: str
    ) -> None:
        # Phase-1 Step 3.5 prototype declaration + the invocation flags.
        assert "Prototype declaration" in design_skill_text
        assert "--prototype" in design_skill_text
        assert "--component-lib" in design_skill_text

    def test_skill_has_design_phase_prototype_block(
        self, design_skill_text: str
    ) -> None:
        # The state.yaml.design_phase.prototype sub-block (AGA-002).
        assert "prototype:" in design_skill_text
        assert "declared" in design_skill_text
        assert "component_lib_path" in design_skill_text

    def test_skill_has_post_processing_annotation_rules(
        self, design_skill_text: str
    ) -> None:
        # Phase-5 post-processing: REQUIRED/ILLUSTRATIVE annotation + tokens.
        assert "REQUIRED" in design_skill_text
        assert "ILLUSTRATIVE" in design_skill_text

    def test_skill_does_not_re_litigate_the_discipline(
        self, design_skill_text: str
    ) -> None:
        # Forward-only: a declared:false (or absent) prototype is a no-op.
        assert "declared: false" in design_skill_text
        assert "forward-only" in design_skill_text.lower()


# -- AC-7: the standard is registered in the compile manifest ----------------


class TestStandardRegisteredInSpec:
    """prototype-as-intent.md is registered under standards.categories.process."""

    def test_registered_under_process_category(self, spec_doc: dict) -> None:
        process = spec_doc["standards"]["categories"]["process"]
        assert "prototype-as-intent.md" in process


# -- AC: source -> dist parity (the #18 named-set-equality precedent) ---------


class TestSourceToDistParity:
    """The standard mirrors source -> dist on a clean compile (parity test)."""

    def test_standard_mirrors_into_dist(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "dist"
        result = subprocess.run(
            [sys.executable, str(COMPILE_SCRIPT), str(SPEC_FILE), "--output", str(out_dir)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
        )
        assert result.returncode == 0, (
            f"compile-sdlc.py failed: {result.stderr or result.stdout}"
        )
        mirrored = out_dir / "standards" / "process" / "prototype-as-intent.md"
        assert mirrored.exists(), "prototype-as-intent.md did not mirror into dist/"
        # Byte-for-byte parity: dist content equals the source standard.
        assert (
            mirrored.read_text(encoding="utf-8")
            == PROTOTYPE_STANDARD.read_text(encoding="utf-8")
        )
