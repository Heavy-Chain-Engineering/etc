"""Contract tests for the brownfield-architecture-baseline UNRATIFIED warning.

Feature F-2026-06-10-brownfield-architecture-baseline, task 011: /spec and
/architect must emit a loud UNRATIFIED warning on a brownfield repo whose
architecture baseline is missing or unratified, and proceeding must require a
recorded override that reuses the existing contract-completeness WARN+override
machinery -- never a parallel mechanism.

These are grep-based contract assertions over the two source SKILL.md files
(the same shape as ``tests/test_spec_three_state.py`` and
``tests/test_baseline_fixtures.py``). They pin the warning text, the status
probe, the backfill command, and the override-recording instruction so a future
edit cannot silently drop any of them.

Per the task placement contract:
- /spec: probe at Phase 2 (research) entry, right after Phase 2 Step 0's
  feature-dir allocation.
- /architect: probe at Phase 2 Step 0 (inheritance confirmation).
Both reuse ``state.yaml.spec_phase.contract_completeness.overrides[]`` with
``contract_class: baseline`` -- no forked list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_SRC = REPO_ROOT / "skills" / "spec" / "SKILL.md"
ARCHITECT_SRC = REPO_ROOT / "skills" / "architect" / "SKILL.md"

# The status-probe invocation must use the ~/.claude/scripts/ prefix verbatim
# (Codex path-rewrite depends on it; design.md Technical Constraints) and the
# `status` subcommand emitting one of {missing|unratified|ratified|malformed}.
PROBE_PREFIX = "python3 ~/.claude/scripts/baseline.py status"

# The backfill command the warning must name so the operator knows how to
# remediate (design.md three-state gate; ADR-002).
BACKFILL_COMMAND = "/init-project --phase=baseline"

# The override audit-trail surface reused verbatim (no parallel mechanism).
OVERRIDE_SURFACE = "state.yaml.spec_phase.contract_completeness.overrides[]"

# The contract_class token that slots baseline into the existing overrides[]
# schema (arbitrary contract_class strings already supported; enum extended in
# skill prose, never forked).
OVERRIDE_CLASS = "contract_class: baseline"


@pytest.fixture(scope="module")
def spec_text() -> str:
    assert SPEC_SRC.exists(), f"missing {SPEC_SRC}"
    return SPEC_SRC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def architect_text() -> str:
    assert ARCHITECT_SRC.exists(), f"missing {ARCHITECT_SRC}"
    return ARCHITECT_SRC.read_text(encoding="utf-8")


class TestSpecBaselineWarn:
    """AC1: /spec emits the UNRATIFIED warning + recorded override."""

    def test_spec_invokes_status_probe(self, spec_text: str) -> None:
        """The status probe runs via the ~/.claude/scripts prefix."""
        assert PROBE_PREFIX in spec_text, (
            "skills/spec/SKILL.md must probe the baseline status via "
            f"'{PROBE_PREFIX} \"$REPO_ROOT\"'"
        )

    def test_spec_warning_carries_unratified_token(self, spec_text: str) -> None:
        """The warning is loud: it carries the UNRATIFIED token or the phrase."""
        assert "UNRATIFIED" in spec_text or "architecture baseline" in spec_text, (
            "skills/spec/SKILL.md must render a loud warning naming UNRATIFIED "
            "or the phrase 'architecture baseline'"
        )

    def test_spec_warning_names_architecture_baseline(self, spec_text: str) -> None:
        """The warning names the architecture baseline by phrase."""
        assert "architecture baseline" in spec_text, (
            "skills/spec/SKILL.md warning must name the 'architecture baseline'"
        )

    def test_spec_warning_names_backfill_command(self, spec_text: str) -> None:
        """The warning offers the backfill remediation command."""
        assert BACKFILL_COMMAND in spec_text, (
            f"skills/spec/SKILL.md must name the backfill command "
            f"'{BACKFILL_COMMAND}'"
        )

    def test_spec_records_override_into_existing_surface(self, spec_text: str) -> None:
        """Proceeding records an override into the EXISTING overrides[] surface."""
        assert OVERRIDE_SURFACE in spec_text, (
            "skills/spec/SKILL.md must record the override into the existing "
            f"'{OVERRIDE_SURFACE}' -- no parallel mechanism"
        )

    def test_spec_override_uses_baseline_contract_class(self, spec_text: str) -> None:
        """The override slots into the existing schema with contract_class: baseline."""
        assert OVERRIDE_CLASS in spec_text, (
            "skills/spec/SKILL.md override must carry "
            f"'{OVERRIDE_CLASS}' (reuse the overrides[] enum, never fork a list)"
        )

    def test_spec_override_requires_nonempty_reason(self, spec_text: str) -> None:
        """The recorded override carries a non-empty reason, surfaced downstream."""
        text = spec_text.lower()
        assert "non-empty reason" in text, (
            "skills/spec/SKILL.md baseline override must require a non-empty reason"
        )
        assert "verification.md" in spec_text, (
            "skills/spec/SKILL.md baseline override must surface downstream "
            "(verification.md / release-notes)"
        )


class TestArchitectBaselineWarn:
    """AC2: /architect emits the same warning + recorded override."""

    def test_architect_invokes_status_probe(self, architect_text: str) -> None:
        """The status probe runs via the ~/.claude/scripts prefix."""
        assert PROBE_PREFIX in architect_text, (
            "skills/architect/SKILL.md must probe the baseline status via "
            f"'{PROBE_PREFIX} \"$REPO_ROOT\"'"
        )

    def test_architect_warning_carries_unratified_token(
        self, architect_text: str
    ) -> None:
        """The warning is loud: it carries the UNRATIFIED token or the phrase."""
        assert (
            "UNRATIFIED" in architect_text
            or "architecture baseline" in architect_text
        ), (
            "skills/architect/SKILL.md must render a loud warning naming "
            "UNRATIFIED or the phrase 'architecture baseline'"
        )

    def test_architect_warning_names_architecture_baseline(
        self, architect_text: str
    ) -> None:
        """The warning names the architecture baseline by phrase."""
        assert "architecture baseline" in architect_text, (
            "skills/architect/SKILL.md warning must name the 'architecture baseline'"
        )

    def test_architect_warning_names_backfill_command(
        self, architect_text: str
    ) -> None:
        """The warning offers the backfill remediation command."""
        assert BACKFILL_COMMAND in architect_text, (
            f"skills/architect/SKILL.md must name the backfill command "
            f"'{BACKFILL_COMMAND}'"
        )

    def test_architect_records_override_into_existing_surface(
        self, architect_text: str
    ) -> None:
        """Proceeding records an override into the EXISTING overrides[] surface."""
        assert OVERRIDE_SURFACE in architect_text, (
            "skills/architect/SKILL.md must record the override into the existing "
            f"'{OVERRIDE_SURFACE}' -- no parallel mechanism"
        )

    def test_architect_override_uses_baseline_contract_class(
        self, architect_text: str
    ) -> None:
        """The override slots into the existing schema with contract_class: baseline."""
        assert OVERRIDE_CLASS in architect_text, (
            "skills/architect/SKILL.md override must carry "
            f"'{OVERRIDE_CLASS}' (reuse the overrides[] enum, never fork a list)"
        )

    def test_architect_override_requires_nonempty_reason(
        self, architect_text: str
    ) -> None:
        """The recorded override carries a non-empty reason, surfaced downstream."""
        text = architect_text.lower()
        assert "non-empty reason" in text, (
            "skills/architect/SKILL.md baseline override must require a "
            "non-empty reason"
        )
        assert "verification.md" in architect_text, (
            "skills/architect/SKILL.md baseline override must surface downstream "
            "(verification.md / release-notes)"
        )


class TestBothSkillsParity:
    """The two skills carry the same warning + override instruction (AC2 parity)."""

    def test_both_name_the_probe_token_set(
        self, spec_text: str, architect_text: str
    ) -> None:
        """Both skills branch on the four-token status set, not the exit code."""
        for name, text in (("spec", spec_text), ("architect", architect_text)):
            for token in ("missing", "unratified", "ratified", "malformed"):
                assert token in text, (
                    f"skills/{name}/SKILL.md must name the '{token}' status token "
                    "(callers branch on the token, never the exit code)"
                )
