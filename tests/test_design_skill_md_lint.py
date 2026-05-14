"""Tests for skills/design/SKILL.md content extensions in F018.

Verify SKILL.md documents the F018 compose step, the lint invocation,
and the operator convenience modes (--lint, --export, --refresh, --spec).
"""

from __future__ import annotations

from pathlib import Path

SKILL_PATH = Path(__file__).parent.parent / "skills" / "design" / "SKILL.md"


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


class TestComposeStepDocumented:
    def test_compose_script_invocation_documented(self) -> None:
        text = _skill_text()
        assert "design_md_compose.py" in text

    def test_compose_step_references_phase_5(self) -> None:
        text = _skill_text()
        # New step should sit inside Phase 5 (between component-specs and state.yaml)
        assert "4.5" in text or "Compose" in text

    def test_compose_documents_lint_invocation(self) -> None:
        text = _skill_text()
        assert "@google/design.md" in text
        assert "lint" in text

    def test_compose_documents_impeccable_preservation(self) -> None:
        text = _skill_text()
        assert "DESIGN-impeccable.md" in text


class TestOperatorModes:
    def test_lint_mode_documented(self) -> None:
        text = _skill_text()
        assert "/design --lint" in text

    def test_refresh_mode_documented(self) -> None:
        text = _skill_text()
        assert "/design --refresh" in text

    def test_export_mode_documented_with_formats(self) -> None:
        text = _skill_text()
        assert "/design --export" in text
        # At least Tailwind + DTCG references
        assert "tailwind" in text.lower()
        assert "dtcg" in text.lower()

    def test_spec_mode_documented(self) -> None:
        text = _skill_text()
        assert "/design --spec" in text


class TestStateYamlSchemaExtended:
    def test_state_yaml_includes_google_designmd_version_pin(self) -> None:
        text = _skill_text()
        assert "google_designmd_version_pinned" in text


class TestGoogleSpecCited:
    def test_skill_links_to_google_design_md_repo(self) -> None:
        text = _skill_text()
        assert "google-labs-code/design.md" in text or "@google/design.md" in text
