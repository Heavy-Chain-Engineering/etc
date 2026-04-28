"""Contract tests for /build skill phase tags + release tag + release-notes.md.

Covers PRD .etc_sdlc/features/metrics-and-release-notes/spec.md acceptance
criteria AC-008, AC-009, AC-011 and business rules BR-007, BR-009, plus
edge case 4 (mid-build failure -> no release tag, no release notes).

Structural assertions against the source SKILL.md text — no agent loop is
executed. Precedent: tests/test_spec_three_state.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_SRC = REPO_ROOT / "skills" / "build" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    assert SKILL_SRC.exists(), f"missing {SKILL_SRC}"
    return SKILL_SRC.read_text(encoding="utf-8")


def _step6_block(text: str) -> str:
    """Return the slice of SKILL.md covering Step 6 only."""
    start = text.index("### Step 6:")
    end = text.index("### Step 7:", start)
    return text[start:end]


def _step7_block(text: str) -> str:
    """Return the slice of SKILL.md covering Step 7 only."""
    start = text.index("### Step 7:")
    end = text.index("### Step 8:", start)
    return text[start:end]


def _step8_block(text: str) -> str:
    """Return the slice of SKILL.md covering Step 8 only."""
    start = text.index("### Step 8:")
    # Step 8 ends at the next top-level "---" or "## Resume Protocol".
    end_candidates = [
        text.find("## Resume Protocol", start),
        text.find("\n---\n", start),
    ]
    end_candidates = [c for c in end_candidates if c != -1]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end]


class TestStep6PhaseTags:
    """AC-008, BR-007: phase-N start/done tags on wave entry/exit."""

    def test_step6_describes_phase_start_tag_at_wave_entry(
        self, skill_text: str
    ) -> None:
        block = _step6_block(skill_text)
        assert "etc/feature/F<NNN>/build/phase-<N>/start" in block, (
            "Step 6 must describe writing the phase-N/start tag at wave entry"
        )

    def test_step6_describes_phase_done_tag_at_wave_exit(
        self, skill_text: str
    ) -> None:
        block = _step6_block(skill_text)
        assert "etc/feature/F<NNN>/build/phase-<N>/done" in block, (
            "Step 6 must describe writing the phase-N/done tag at successful "
            "wave exit"
        )

    def test_step6_phase_tags_use_git_tags_helper(self, skill_text: str) -> None:
        """The skill must invoke the git_tags helper rather than raw `git tag`."""
        block = _step6_block(skill_text)
        assert "git_tags" in block, (
            "Step 6 must reference the scripts/git_tags helper (write_tag) "
            "for phase tag emission"
        )
        assert "write_tag" in block, (
            "Step 6 must call git_tags.write_tag() for phase start/done tags"
        )

    def test_step6_phase_done_is_gated_on_wave_success(
        self, skill_text: str
    ) -> None:
        """The done tag must be conditioned on successful wave completion,
        not written unconditionally."""
        block = _step6_block(skill_text).lower()
        # The skill must explicitly tie the done tag to a successful wave.
        assert "successful" in block or "success" in block, (
            "Step 6 must gate the phase-N/done tag on successful wave completion"
        )

    def test_step6_failure_does_not_emit_done_tag(self, skill_text: str) -> None:
        """Edge case 4: mid-build failure must not write the done tag for the
        failing wave. The skill text must make this explicit."""
        block = _step6_block(skill_text).lower()
        # Either an explicit "do not write the done tag on failure" or a clear
        # ordering: write done only after tests pass / no escalations.
        has_explicit_negative = (
            "do not write" in block
            and "done" in block
        )
        has_ordering = (
            "after" in block and "done" in block and (
                "tests pass" in block or "pass" in block
            )
        )
        assert has_explicit_negative or has_ordering, (
            "Step 6 must make explicit that phase-N/done is NOT written on "
            "test failure or wave escalation"
        )


class TestStep7ReleaseTagAndNotes:
    """AC-009, AC-011, BR-009: release tag + release-notes.md on terminal close."""

    def test_step7_describes_release_tag(self, skill_text: str) -> None:
        block = _step7_block(skill_text)
        assert "etc/feature/F<NNN>/release" in block, (
            "Step 7 must describe writing the etc/feature/F<NNN>/release tag"
        )

    def test_step7_release_tag_uses_git_tags_helper(
        self, skill_text: str
    ) -> None:
        block = _step7_block(skill_text)
        assert "git_tags" in block and "write_tag" in block, (
            "Step 7 must call git_tags.write_tag() for the release tag"
        )

    def test_step7_calls_release_notes_build(self, skill_text: str) -> None:
        block = _step7_block(skill_text)
        assert "release_notes.build" in block, (
            "Step 7 must call release_notes.build(feature_dir) to assemble "
            "the release notes markdown"
        )

    def test_step7_writes_release_notes_md_to_feature_dir(
        self, skill_text: str
    ) -> None:
        block = _step7_block(skill_text)
        assert "release-notes.md" in block, (
            "Step 7 must write release-notes.md to the feature directory"
        )

    def test_step7_release_artifacts_gated_on_terminal_phase_success(
        self, skill_text: str
    ) -> None:
        """AC-009/AC-011 + edge case 4: release tag and release-notes.md are
        only written on a successful terminal-phase close. The skill text
        must state the gating."""
        block = _step7_block(skill_text).lower()
        # The text must talk about "terminal phase" / "terminal-phase close"
        # AND condition release artifact emission on success.
        assert "terminal" in block, (
            "Step 7 must reference the terminal phase close as the trigger "
            "for release artifacts"
        )
        # Successful close is the gate.
        assert "success" in block or "successful" in block or "passes" in block, (
            "Step 7 must gate release artifacts on a successful terminal close"
        )

    def test_step7_failure_does_not_emit_release_artifacts(
        self, skill_text: str
    ) -> None:
        """Edge case 4: on mid-build failure neither release tag nor
        release-notes.md is written. The skill must say so explicitly."""
        block = _step7_block(skill_text).lower()
        # Look for an explicit negative statement covering both artifacts.
        mentions_negative = (
            "do not write" in block
            or "not write" in block
            or "skip" in block
        )
        mentions_release_artifacts = (
            "release tag" in block or "release-notes" in block
        )
        assert mentions_negative and mentions_release_artifacts, (
            "Step 7 must explicitly state that the release tag and "
            "release-notes.md are NOT written on mid-build failure"
        )


class TestStep8ArtifactSummary:
    """AC-011 reporting side: Step 8 summary names release-notes.md and
    the release tag in its artifact list."""

    def test_step8_summary_lists_release_notes_md(
        self, skill_text: str
    ) -> None:
        block = _step8_block(skill_text)
        assert "release-notes.md" in block, (
            "Step 8 artifact summary must name release-notes.md"
        )

    def test_step8_summary_lists_release_tag(self, skill_text: str) -> None:
        block = _step8_block(skill_text).lower()
        assert "release tag" in block or "etc/feature/" in block, (
            "Step 8 artifact summary must name the release tag (or the "
            "etc/feature/<F-id>/release ref) so the user sees it"
        )


class TestDisciplineMessaging:
    """BR-008 / edge case 4: harness tags written in earlier successful waves
    must remain on mid-build failure; release artifacts must not be written.
    The skill must make this discipline explicit somewhere in Steps 6 or 7."""

    def test_skill_states_earlier_phase_tags_remain_on_failure(
        self, skill_text: str
    ) -> None:
        # Look in the Step 6 + Step 7 region for the explicit guarantee.
        region = _step6_block(skill_text) + _step7_block(skill_text)
        lowered = region.lower()
        # Either "remain", "preserved", or "kept" — the operative word is
        # that earlier successful phase tags are not rolled back.
        assert (
            "remain" in lowered
            or "preserved" in lowered
            or "kept" in lowered
            or "not rolled back" in lowered
        ), (
            "Steps 6/7 must state that phase tags from earlier successful "
            "waves remain after a mid-build failure (no rollback)"
        )
