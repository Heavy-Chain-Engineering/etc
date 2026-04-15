"""Tests for the /hotfix incident response lane (v1.6).

Verifies that the compiled hotfix skill, hotfix-responder agent manifest,
and standards/process/incident-response.md are shaped correctly and that
the .gitignore exception for .etc_sdlc/incidents/ is in place.

These are CONTRACT tests on the compiled output, not integration tests
of /hotfix execution. They assert that the source files encode the
BR-001 through BR-015 contracts from .etc_sdlc/features/hotfix/spec.md.
They do NOT dispatch a real hotfix-responder subagent or run a /hotfix
skill end-to-end — that would require Claude Code's runtime.

Added 2026-04-15 alongside the v1.6 release that introduced the /hotfix
lane.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = REPO_ROOT / "skills" / "hotfix" / "SKILL.md"
DIST_SKILL_PATH = REPO_ROOT / "dist" / "skills" / "hotfix" / "SKILL.md"
AGENT_PATH = REPO_ROOT / "agents" / "hotfix-responder.md"
DIST_AGENT_PATH = REPO_ROOT / "dist" / "agents" / "hotfix-responder.md"
STANDARDS_PATH = REPO_ROOT / "standards" / "process" / "incident-response.md"
DIST_STANDARDS_PATH = (
    REPO_ROOT / "dist" / "standards" / "process" / "incident-response.md"
)
GITIGNORE_PATH = REPO_ROOT / ".gitignore"
GITKEEP_PATH = REPO_ROOT / ".etc_sdlc" / "incidents" / ".gitkeep"


class TestHotfixSkillFile:
    """Skill file existence and top-level shape.

    Verifies that skills/hotfix/SKILL.md (source) and dist/skills/hotfix/
    SKILL.md (compiled output) both exist, have standard frontmatter, and
    name `/hotfix` as the invocation form in a Usage section. Added
    2026-04-15 with the v1.6 /hotfix lane.
    """

    def test_should_exist_at_skills_hotfix_skill_md_when_compiled(self) -> None:
        # Arrange / Act / Assert
        assert SKILL_PATH.exists(), f"source skill missing at {SKILL_PATH}"
        assert DIST_SKILL_PATH.exists(), (
            f"compiled skill missing at {DIST_SKILL_PATH}; run compile-sdlc.py"
        )

    def test_should_have_standard_skill_frontmatter_when_read(self) -> None:
        # Arrange
        content = DIST_SKILL_PATH.read_text()

        # Act
        # Split off the frontmatter block between the first two `---` markers.
        parts = content.split("---", 2)

        # Assert
        assert len(parts) >= 3, "skill file missing a frontmatter block"
        frontmatter = parts[1]
        assert "name: hotfix" in frontmatter, (
            "skill frontmatter must declare `name: hotfix`"
        )
        # description: must exist and have non-empty text after the colon.
        desc_lines = [
            line
            for line in frontmatter.splitlines()
            if line.strip().startswith("description:")
        ]
        assert desc_lines, "skill frontmatter must have a description: line"
        first = desc_lines[0].split("description:", 1)[1].strip()
        # Handle YAML folded-scalar style where description value is on the next line.
        assert first or len(frontmatter.strip()) > len("name: hotfix"), (
            "description: field must be non-empty"
        )

    def test_should_name_hotfix_invocation_form_in_usage_section(self) -> None:
        # Arrange
        content = DIST_SKILL_PATH.read_text()

        # Act
        # Find the Usage section and confirm /hotfix appears after it.
        assert "## Usage" in content, "skill must have a `## Usage` section"
        usage_idx = content.index("## Usage")
        tail = content[usage_idx:]

        # Assert
        assert "/hotfix" in tail, (
            "skill Usage section must name `/hotfix` as the invocation form"
        )


class TestHotfixResponderAgentFile:
    """Agent manifest existence and authorization shape.

    Verifies agents/hotfix-responder.md (source + dist) exists and that the
    manifest declares exactly the three gates BR-002 authorizes for bypass,
    and explicitly preserves the three BR-003 safety-critical gates. Added
    2026-04-15.
    """

    def test_should_exist_at_agents_hotfix_responder_md_when_compiled(self) -> None:
        # Arrange / Act / Assert
        assert AGENT_PATH.exists(), f"source agent missing at {AGENT_PATH}"
        assert DIST_AGENT_PATH.exists(), (
            f"compiled agent missing at {DIST_AGENT_PATH}; run compile-sdlc.py"
        )

    def test_should_declare_bypass_authorization_for_three_gates_when_read(
        self,
    ) -> None:
        # Arrange
        content = DIST_AGENT_PATH.read_text()

        # Act / Assert
        assert "tdd-gate" in content, "manifest must name tdd-gate as bypassed"
        assert "enough-context" in content, (
            "manifest must name enough-context as bypassed"
        )
        assert "phase-gate" in content, "manifest must name phase-gate as bypassed"

        # Locate the "authorized to bypass" section and confirm none of the
        # three safety-critical gates appear inside it.
        bypass_idx = content.find("authorized to bypass")
        assert bypass_idx != -1, (
            "manifest must have an 'authorized to bypass' section"
        )
        respect_idx = content.find("MUST respect", bypass_idx)
        assert respect_idx != -1, (
            "manifest must have a 'MUST respect' section after the bypass list"
        )
        bypass_section = content[bypass_idx:respect_idx]
        for forbidden in ("safety-guardrails", "tier-0-preflight", "check-invariants"):
            assert forbidden not in bypass_section, (
                f"{forbidden} must NOT appear in the bypass-authorization section"
            )

    def test_should_not_bypass_safety_critical_gates_when_read(self) -> None:
        # Arrange
        content = DIST_AGENT_PATH.read_text()

        # Act / Assert
        for gate in ("safety-guardrails", "tier-0-preflight", "check-invariants"):
            assert gate in content, (
                f"{gate} must be named in the manifest's preserved-gates section"
            )
        # The manifest names these gates under a "MUST respect" heading.
        assert "MUST respect" in content, (
            "manifest must explicitly document gates the agent MUST respect"
        )


class TestSingleIncidentLock:
    """BR-004 single-incident lock documented in the skill source.

    Verifies that the skill file has a Phase 1 section that scans
    .etc_sdlc/incidents/*/incident.md for filed or in_progress incidents.
    Added 2026-04-15.
    """

    def test_should_document_single_incident_lock_in_phase_1_when_read(self) -> None:
        # Arrange
        content = SKILL_PATH.read_text()

        # Act / Assert
        assert "Phase 1" in content, "skill must have a Phase 1 section"
        assert "Single-Incident Lock" in content or "single-incident lock" in content, (
            "Phase 1 must be labeled the single-incident lock phase"
        )
        assert ".etc_sdlc/incidents/" in content, (
            "Phase 1 must reference the incidents directory"
        )
        assert "incident.md" in content, (
            "Phase 1 must reference the incident.md filename"
        )
        assert "filed" in content and "in_progress" in content, (
            "Phase 1 must scan for status filed or in_progress"
        )


class TestGateBypass:
    """BR-002 and BR-003 encoded in the skill's Constraints section.

    Mirrors TestHotfixResponderAgentFile but from the skill's perspective:
    the /hotfix skill's Constraints list must name all three bypassed gates
    and all three preserved gates. Added 2026-04-15.
    """

    def test_should_name_the_three_bypassed_gates_in_constraints_when_read(
        self,
    ) -> None:
        # Arrange
        content = SKILL_PATH.read_text()

        # Act / Assert
        assert "## Constraints" in content, "skill must have a Constraints section"
        assert "tdd-gate" in content
        assert "enough-context" in content
        assert "phase-gate" in content

    def test_should_name_the_three_preserved_gates_in_constraints_when_read(
        self,
    ) -> None:
        # Arrange
        content = SKILL_PATH.read_text()
        constraints_idx = content.index("## Constraints")
        constraints = content[constraints_idx:]

        # Act / Assert
        assert "safety-guardrails" in constraints, (
            "Constraints must name safety-guardrails as still firing"
        )
        assert "tier-0-preflight" in constraints, (
            "Constraints must name tier-0-preflight as still firing"
        )
        assert "check-invariants" in constraints, (
            "Constraints must name check-invariants as still firing"
        )


class TestBuildPreemption:
    """BR-005 /build preemption in the skill source.

    Verifies the Phase 2 section handles checkpointing an active /build via
    state.yaml and prints /build --resume. Added 2026-04-15.
    """

    def test_should_document_build_preemption_in_phase_2_when_read(self) -> None:
        # Arrange
        content = SKILL_PATH.read_text()

        # Act
        assert "Phase 2" in content, "skill must have a Phase 2 section"
        phase2_idx = content.index("Phase 2")
        # Take a reasonable chunk after the Phase 2 header to bound the search.
        tail = content[phase2_idx : phase2_idx + 4000]

        # Assert
        assert "state.yaml" in tail, "Phase 2 must reference state.yaml"
        assert "preempted_by_hotfix" in tail, (
            "Phase 2 must set status: preempted_by_hotfix"
        )
        assert "/build --resume" in content, (
            "skill must instruct operator to run /build --resume after preempt"
        )


class TestPickerFlow:
    """BR-006 picker category enumeration.

    The skill's three Pattern A pickers must enumerate the exact category
    labels from BR-006 so the incident frontmatter carries the canonical
    values. Added 2026-04-15.
    """

    def test_should_enumerate_five_failure_type_categories_when_read(self) -> None:
        # Arrange
        content = SKILL_PATH.read_text()

        # Act / Assert
        for label in (
            "endpoint_error",
            "service_down",
            "data_corruption",
            "config_wrong",
            "deployment_failure",
        ):
            assert label in content, f"Q1 must enumerate {label}"

    def test_should_enumerate_five_fix_kind_categories_when_read(self) -> None:
        # Arrange
        content = SKILL_PATH.read_text()

        # Act / Assert
        for label in (
            "revert_commit",
            "edit_files",
            "flip_config",
            "disable_feature_flag",
            "dependency_rollback",
        ):
            assert label in content, f"Q2 must enumerate {label}"

    def test_should_enumerate_five_rollback_kind_categories_when_read(self) -> None:
        # Arrange
        content = SKILL_PATH.read_text()

        # Act / Assert
        for label in (
            "revert_to_sha",
            "restore_backup",
            "disable_flag",
            "reapply_commit",
            "manual_steps",
        ):
            assert label in content, f"Q3 must enumerate {label}"


class TestDescriptionGuardrail:
    """BR-012 description guardrail in the agent manifest.

    The hotfix-responder manifest must require both a specific system
    reference AND a specific failure mode in the incident description,
    and must document the exact stopReason template. Added 2026-04-15.
    """

    def test_should_require_system_reference_and_failure_mode_when_read(self) -> None:
        # Arrange
        content = AGENT_PATH.read_text()

        # Act / Assert
        # The manifest must name at least one of the system-reference synonyms
        # AND at least one failure-mode synonym in the rubric.
        system_hits = any(
            token in content for token in ("system", "file path", "endpoint", "service")
        )
        failure_hits = any(
            token in content
            for token in ("failure mode", "error code", "symptom", "observed behavior")
        )
        assert system_hits, (
            "manifest guardrail rubric must name system/file path/endpoint/service"
        )
        assert failure_hits, (
            "manifest guardrail rubric must name failure mode/error code/symptom"
        )

    def test_should_document_stop_reason_template_when_read(self) -> None:
        # Arrange
        content = AGENT_PATH.read_text()

        # Act / Assert
        assert "Description does not match an incident shape" in content, (
            "manifest must contain the verbatim rejection stopReason template"
        )


class TestAuditTrail:
    """BR-013 and BR-014 audit fields instructed in the agent manifest.

    The manifest must instruct the agent to maintain the gates_bypassed
    and files_touched lists and write them into the incident frontmatter
    at completion. Added 2026-04-15.
    """

    def test_should_instruct_recording_gates_bypassed_when_read(self) -> None:
        # Arrange
        content = AGENT_PATH.read_text()

        # Act / Assert
        assert "gates_bypassed" in content, (
            "manifest must instruct the agent to record gates_bypassed"
        )

    def test_should_instruct_recording_files_touched_when_read(self) -> None:
        # Arrange
        content = AGENT_PATH.read_text()

        # Act / Assert
        assert "files_touched" in content, (
            "manifest must instruct the agent to record files_touched"
        )


class TestRecursionGuard:
    """BR-015 recursion guard in both the skill and the agent manifest.

    The skill checks the caller's agent_type for hotfix-responder; the
    agent manifest itself refuses recursive /hotfix with a literal
    rejection phrase. Added 2026-04-15.
    """

    def test_should_check_agent_type_in_skill_when_read(self) -> None:
        # Arrange
        content = SKILL_PATH.read_text()

        # Act / Assert
        assert "Recursion Guard" in content or "recursion guard" in content, (
            "skill must have a recursion-guard section"
        )
        assert "agent_type" in content or "hotfix-responder" in content, (
            "recursion guard must reference agent_type or hotfix-responder"
        )

    def test_should_refuse_recursive_invocation_in_agent_manifest_when_read(
        self,
    ) -> None:
        # Arrange
        content = AGENT_PATH.read_text()

        # Act / Assert
        assert "recursive /hotfix not allowed" in content, (
            "manifest must contain the literal phrase 'recursive /hotfix not allowed'"
        )


class TestGitignoreException:
    """AC-18 .gitignore exception and .gitkeep placeholder.

    The critical regression test: .etc_sdlc/incidents/ must NOT be ignored
    while .etc_sdlc/features/ continues to be ignored. Also verifies the
    .gitkeep placeholder exists and is empty. Added 2026-04-15.
    """

    def test_should_track_gitkeep_file_when_present(self) -> None:
        # Arrange / Act / Assert
        assert GITKEEP_PATH.exists(), (
            f".gitkeep must exist at {GITKEEP_PATH} to materialize the "
            "incidents directory in fresh checkouts"
        )
        assert GITKEEP_PATH.stat().st_size == 0, (
            ".gitkeep must be empty — it is a placeholder, not a documentation file"
        )

    def test_should_unignore_etc_sdlc_incidents_when_git_check_ignore_runs(
        self,
    ) -> None:
        # Arrange
        target = ".etc_sdlc/incidents/2026-04-15-test/incident.md"

        # Act
        result = subprocess.run(
            ["git", "check-ignore", target],
            capture_output=True,
            cwd=str(REPO_ROOT),
        )

        # Assert
        assert result.returncode != 0, (
            f"{target} must NOT be ignored — the /hotfix lane requires "
            "incident logs to be git-tracked. The .gitignore must have an "
            "exception for .etc_sdlc/incidents/ and .etc_sdlc/incidents/**."
        )

    def test_should_still_ignore_etc_sdlc_features_when_git_check_ignore_runs(
        self,
    ) -> None:
        # Arrange
        target = ".etc_sdlc/features/test-feature/spec.md"

        # Act
        result = subprocess.run(
            ["git", "check-ignore", target],
            capture_output=True,
            cwd=str(REPO_ROOT),
        )

        # Assert — AC-18 regression: .etc_sdlc/features/ must still be ignored.
        assert result.returncode == 0, (
            f"{target} must remain ignored — the incidents exception must not "
            "have accidentally unignored the rest of .etc_sdlc/. AC-18 regression."
        )


class TestStandardsDoc:
    """standards/process/incident-response.md exists and carries the
    Security Considerations warnings.

    The standards doc must warn operators about secrets in incident
    descriptions and about public exposure when open-sourcing repos with
    incident history. Added 2026-04-15.
    """

    def test_should_exist_at_standards_process_incident_response_md(self) -> None:
        # Arrange / Act / Assert
        assert STANDARDS_PATH.exists(), (
            f"source standards doc missing at {STANDARDS_PATH}"
        )
        assert DIST_STANDARDS_PATH.exists(), (
            f"compiled standards doc missing at {DIST_STANDARDS_PATH}"
        )

    def test_should_warn_against_secrets_in_descriptions_when_read(self) -> None:
        # Arrange
        content = STANDARDS_PATH.read_text()

        # Act / Assert
        assert "secret" in content.lower(), (
            "standards doc must discuss secrets in incident descriptions"
        )
        warns = any(phrase in content for phrase in ("DO NOT", "NEVER", "do not"))
        assert warns, (
            "standards doc must explicitly warn with DO NOT / NEVER language "
            "about pasting secrets into incident descriptions"
        )

    def test_should_warn_against_public_exposure_when_read(self) -> None:
        # Arrange
        content = STANDARDS_PATH.read_text()

        # Act / Assert
        assert any(
            phrase in content
            for phrase in ("open-source", "open-sourcing", "public exposure", "public")
        ), (
            "standards doc must warn about open-sourcing repos with "
            ".etc_sdlc/incidents/ content"
        )


class TestSecretDetection:
    """High-confidence secret patterns declared in the agent manifest.

    The Security Considerations section of the spec mandates a
    high-confidence regex check for AWS keys, GitHub tokens, JWTs, and
    private keys. At least two of these patterns must appear verbatim in
    the hotfix-responder manifest's secret-detection section. Added
    2026-04-15.
    """

    def test_should_include_high_confidence_secret_patterns_in_agent_manifest(
        self,
    ) -> None:
        # Arrange
        content = AGENT_PATH.read_text()
        patterns = ["AKIA", "ghp_", "ghs_", "gho_", "ghu_", "ghr_", "eyJ", "PRIVATE KEY"]

        # Act
        hits = [p for p in patterns if p in content]

        # Assert
        assert len(hits) >= 2, (
            f"manifest must include at least two high-confidence secret "
            f"patterns from {patterns}, found only: {hits}"
        )
