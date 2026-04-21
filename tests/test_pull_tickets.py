"""Tests for pull-tickets skill compilation and installation pipeline.

Validates that the pull-tickets skill is correctly defined in the SDLC spec,
compiled to the expected dist/ location, and contains all required content
for closed-loop ticket processing.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
SPEC_PATH = REPO_ROOT / "spec" / "etc_sdlc.yaml"
SKILL_SOURCE = REPO_ROOT / "skills" / "pull-tickets" / "SKILL.md"
COMPILED_SKILL = DIST_DIR / "skills" / "pull-tickets" / "SKILL.md"


def _load_spec() -> dict:
    """Load and parse the SDLC spec."""
    return yaml.safe_load(SPEC_PATH.read_text())


def _load_skill_content() -> str:
    """Load the skill source file content."""
    return SKILL_SOURCE.read_text()


# -- Test 1: YAML spec contains pull-tickets ----------------------------------


def test_yaml_spec_contains_pull_tickets() -> None:
    """spec/etc_sdlc.yaml must have a pull-tickets entry under skills with required fields."""
    # Arrange
    spec = _load_spec()

    # Act
    skills = spec.get("skills", {})
    pull_tickets = skills.get("pull-tickets")

    # Assert
    assert pull_tickets is not None, "pull-tickets entry missing from skills section"
    assert "name" in pull_tickets, "pull-tickets missing 'name' field"
    assert "description" in pull_tickets, "pull-tickets missing 'description' field"
    assert "usage" in pull_tickets, "pull-tickets missing 'usage' field"
    assert "flow" in pull_tickets, "pull-tickets missing 'flow' field"


# -- Test 2: source_file field and file existence ------------------------------


def test_pull_tickets_skill_source_exists() -> None:
    """Hand-authored skill source must exist at skills/pull-tickets/SKILL.md."""
    # Assert
    assert SKILL_SOURCE.exists(), (
        f"Skill source not found: {SKILL_SOURCE}. "
        f"Expected hand-authored SKILL.md at skills/pull-tickets/SKILL.md"
    )
    assert SKILL_SOURCE.stat().st_size > 0, "SKILL.md exists but is empty"


# -- Test 3: compiler produces pull-tickets skill ------------------------------


def test_compiler_produces_pull_tickets_skill() -> None:
    """dist/skills/pull-tickets/SKILL.md must exist after compilation."""
    # Arrange & Act — check compiled artifact

    # Assert
    assert COMPILED_SKILL.exists(), (
        f"Compiled skill not found: {COMPILED_SKILL}. "
        f"Run 'python3 compile-sdlc.py spec/etc_sdlc.yaml' first."
    )
    assert COMPILED_SKILL.stat().st_size > 0, "SKILL.md exists but is empty"


# -- Test 4: compiled skill matches source -------------------------------------


def test_compiled_skill_matches_source() -> None:
    """dist/skills/pull-tickets/SKILL.md must be identical to skills/pull-tickets.md."""
    # Arrange
    assert COMPILED_SKILL.exists(), (
        f"Compiled skill not found: {COMPILED_SKILL}. "
        f"Run 'python3 compile-sdlc.py spec/etc_sdlc.yaml' first."
    )

    # Act
    source_content = SKILL_SOURCE.read_text()
    compiled_content = COMPILED_SKILL.read_text()

    # Assert
    assert compiled_content == source_content, (
        "Compiled SKILL.md does not match source skills/pull-tickets.md. "
        "The compiler should copy source_file skills verbatim."
    )


# -- Test 5: skill has valid frontmatter ---------------------------------------


def test_skill_has_valid_frontmatter() -> None:
    """Skill source file must have YAML frontmatter with name and description."""
    # Arrange
    content = _load_skill_content()

    # Act — extract frontmatter between --- delimiters
    assert content.startswith("---"), "Skill file must start with --- frontmatter delimiter"
    end_index = content.index("---", 3)
    frontmatter_text = content[3:end_index].strip()
    frontmatter = yaml.safe_load(frontmatter_text)

    # Assert
    assert "name" in frontmatter, "Frontmatter missing 'name' field"
    assert frontmatter["name"] == "pull-tickets", (
        f"Expected frontmatter name 'pull-tickets', got {frontmatter['name']!r}"
    )
    assert "description" in frontmatter, "Frontmatter missing 'description' field"
    assert len(frontmatter["description"]) > 0, "Frontmatter description must not be empty"


# -- Test 6: skill contains MCP verification -----------------------------------


def test_skill_contains_mcp_verification() -> None:
    """Skill must contain Phase 0 MCP verification with get_status_map and connection check."""
    # Arrange
    content = _load_skill_content()

    # Assert
    assert "get_status_map" in content, (
        "Skill must reference get_status_map for status UUID resolution"
    )
    assert "MCP" in content, "Skill must reference MCP connection verification"
    assert "unreachable" in content.lower() or "STOP IMMEDIATELY" in content, (
        "Skill must contain abort logic when MCP is unreachable"
    )


# -- Test 7: skill contains rejection routing ----------------------------------


def test_skill_contains_rejection_routing() -> None:
    """Skill must contain rejection routing with create_comment, update_issue, Needs Clarification."""
    # Arrange
    content = _load_skill_content()

    # Assert
    assert "create_comment" in content, (
        "Skill must reference create_comment for rejection feedback"
    )
    assert "update_issue" in content, (
        "Skill must reference update_issue for status transitions"
    )
    assert "Needs Clarification" in content, (
        "Skill must reference 'Needs Clarification' status for rejections"
    )


# -- Test 8: skill contains success closure ------------------------------------


def test_skill_contains_success_closure() -> None:
    """Skill must contain success loop closure: PR creation, In Review status, build summary."""
    # Arrange
    content = _load_skill_content()

    # Assert
    assert "gh pr create" in content, (
        "Skill must reference 'gh pr create' for PR creation on success"
    )
    assert "In Review" in content, (
        "Skill must reference 'In Review' status for successful builds"
    )
    assert "What was done" in content or "summary" in content.lower(), (
        "Skill must contain build summary template for SME-facing comments"
    )


# -- Test 9: skill contains PRD generation with all 8 sections ----------------


def test_skill_contains_prd_generation() -> None:
    """Skill must reference all 8 PRD sections for ticket-to-PRD translation."""
    # Arrange
    content = _load_skill_content()
    required_sections = [
        "Summary",
        "Scope",
        "Requirements",
        "Acceptance Criteria",
        "Edge Cases",
        "Technical Constraints",
        "Security Considerations",
        "Module Structure",
    ]

    # Act
    missing = [section for section in required_sections if section not in content]

    # Assert
    assert not missing, (
        f"Skill missing PRD sections: {missing}. "
        f"All 8 sections must be referenced in the skill."
    )


# -- Test 10: skill has no hardcoded UUIDs -------------------------------------


def test_skill_no_hardcoded_uuids() -> None:
    """Skill must NOT contain any UUID patterns (8-4-4-4-12 hex), confirming no hardcoded Linear status IDs."""
    # Arrange
    content = _load_skill_content()
    uuid_pattern = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        re.IGNORECASE,
    )

    # Act
    matches = uuid_pattern.findall(content)

    # Assert
    assert not matches, (
        f"Skill contains hardcoded UUIDs: {matches}. "
        f"Status IDs must be resolved via get_status_map at runtime."
    )


# -- Test 11: skill contains triage-only mode -----------------------------------


def test_skill_contains_triage_mode() -> None:
    """Skill must contain triage-only mode with complexity scoring, dependency mapping, and epic decomposition."""
    # Arrange
    content = _load_skill_content()

    # Assert
    assert "--triage-only" in content, (
        "Skill must reference --triage-only flag"
    )
    assert "Triage" in content, (
        "Skill must contain triage mode documentation"
    )
    assert "S/M/L/XL" in content or ("size" in content.lower() and "complexity" in content.lower()), (
        "Skill must contain size/complexity scoring (S/M/L/XL)"
    )
    assert "sub-issue" in content.lower() or "create_issue" in content, (
        "Skill must reference creating sub-issues for epic decomposition"
    )


# -- Test 12: skill contains scope gate -----------------------------------------


def test_skill_contains_scope_gate() -> None:
    """Skill must contain scope gate (BR-010) that prevents building oversized tickets."""
    # Arrange
    content = _load_skill_content()

    # Assert
    assert "Scope Gate" in content or "scope gate" in content or "BR-010" in content, (
        "Skill must contain scope gate for oversized tickets"
    )
    assert "15" in content, (
        "Skill must reference the 15 leaf-task threshold for scope gate"
    )
    assert "sub-ticket" in content.lower() or "sub-issue" in content.lower(), (
        "Skill must describe creating sub-tickets/sub-issues for oversized tickets"
    )


# -- Test 13: YAML spec includes triage and scope gate flow steps ---------------


def test_yaml_spec_includes_triage_and_scope_gate_flows() -> None:
    """YAML spec must include scope_gate and triage_only in the pull-tickets flow."""
    # Arrange
    spec = _load_spec()
    flow = spec["skills"]["pull-tickets"]["flow"]

    # Assert
    assert "scope_gate" in flow, "flow must include scope_gate step"
    assert "triage_only" in flow, "flow must include triage_only step"
