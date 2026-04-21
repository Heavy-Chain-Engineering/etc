"""Tests for /init-project template deployment, contracts, and mechanical E2E.

Covers PRD acceptance criteria:
- AC1 (partial): mechanical phases produce the expected artifact set
- AC2: idempotent re-run is a no-op
- AC3: tier-0-preflight hook blocks before tier-0 exists and allows after
- AC4: partial tier-0 recovery preserves existing files
- AC5: --phase=<name> isolation (skeleton does not touch tier-0 files)
- AC6: phase dependency enforcement (domain without tech scaffold records the gap)
- AC7: template deployment (SKILL.md + 14 templates land in dist/)
- AC9: role manifest soft-POLA (default_consumes + discovery.allowed_requests, no forbids)
- AC11: README stubs are discoverable (≤15 lines, reference DOMAIN.md / PROJECT.md)
- BR-003: DOMAIN.md.template contains 9 section headers in canonical order

The STATIC tests verify compiled template structure. The MECHANICAL E2E tests
simulate Phase 3 (docs skeleton) and Phase 4 (role manifests) by performing
the file operations the SKILL.md prompt instructs an agent to perform —
reading from the compiled templates and copying to a scratch temp dir. This
gives runtime coverage of the deterministic parts of the skill.

Phase 1 (project-bootstrapper spawn via Task tool) and Phase 2 (interactive
6-question DOMAIN.md flow) require an agent runtime / human input and are
not covered by these automated tests. Those ACs (AC8, AC10, AC12) must be
verified by a manual walkthrough before merge.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "init-project"

# The full template set deployed by compile-sdlc.py: SKILL.md + 14 templates.
EXPECTED_FILES: tuple[str, ...] = (
    "SKILL.md",
    "templates/DOMAIN.md.template",
    "templates/PROJECT.md.template",
    "templates/CLAUDE.md.template",
    "templates/tier-1/prds.README.md",
    "templates/tier-1/plans.README.md",
    "templates/tier-1/sources.README.md",
    "templates/tier-1/standards.README.md",
    "templates/tier-1/guides.README.md",
    "templates/roles-README.md",
    "templates/roles/sem.yaml",
    "templates/roles/architect.yaml",
    "templates/roles/backend-dev.yaml",
    "templates/roles/frontend-dev.yaml",
    "templates/roles/code-reviewer.yaml",
)

TIER_1_READMES: tuple[str, ...] = (
    "prds.README.md",
    "plans.README.md",
    "sources.README.md",
    "standards.README.md",
    "guides.README.md",
)

ROLE_MANIFESTS: tuple[str, ...] = (
    "sem.yaml",
    "architect.yaml",
    "backend-dev.yaml",
    "frontend-dev.yaml",
    "code-reviewer.yaml",
)

# Canonical 9-section DOMAIN.md order from BR-003. Each entry is a regex
# that matches either the canonical heading or the parameterized form
# (e.g. "## How {{PROJECT_NAME}} Makes Money").
DOMAIN_SECTION_PATTERNS: tuple[str, ...] = (
    r"^##\s+Domain\s*$",
    r"^##\s+Core Problem\s*$",
    r"^##\s+(?:Revenue Model|How .+ Makes Money)\s*$",
    r"^##\s+(?:What It Does|What .+ Does)\s*$",
    r"^##\s+Operational & Regulatory Constraints\s*$",
    r"^##\s+Product Core\s*$",
    r"^##\s+(?:What It Is Not|What .+ Is Not)\s*$",
    r"^##\s+Risk Posture\s*$",
    r"^##\s+Design Implications\s*$",
)


# -- Module loader (compile-sdlc.py has a hyphen, blocks direct import) -------


def _load_compile_sdlc_module() -> Any:
    """Load compile-sdlc.py as a module via importlib."""
    module_path = REPO_ROOT / "compile-sdlc.py"
    spec = importlib.util.spec_from_file_location("compile_sdlc", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- Fixtures -----------------------------------------------------------------


@pytest.fixture(scope="module")
def compiled_skill_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run compile_skills once against a tmp dist and return dist/skills/init-project.

    Module-scoped so the compile runs once for the whole test file; each test
    only reads from the result, so there is no cross-test mutation risk.
    """
    dist_dir = tmp_path_factory.mktemp("dist")
    compile_sdlc = _load_compile_sdlc_module()
    compile_sdlc.compile_skills(dist_dir, REPO_ROOT)
    return dist_dir / "skills" / SKILL_NAME


# -- AC7: template deployment -------------------------------------------------


@pytest.mark.parametrize("relative_path", EXPECTED_FILES)
def test_should_deploy_template_when_compile_runs(
    compiled_skill_dir: Path, relative_path: str
) -> None:
    """Every SKILL.md and template file must land in dist/skills/init-project/.

    Covers AC7: after compile-sdlc.py runs, dist/skills/init-project/ contains
    SKILL.md plus a templates/ tree with all 14 template files intact.
    """
    # Arrange
    target = compiled_skill_dir / relative_path

    # Act & Assert
    assert target.is_file(), (
        f"Template missing: dist/skills/{SKILL_NAME}/{relative_path}"
    )
    assert target.stat().st_size > 0, (
        f"Template is empty: dist/skills/{SKILL_NAME}/{relative_path}"
    )


def test_should_deploy_exactly_fifteen_files_when_compile_runs(
    compiled_skill_dir: Path,
) -> None:
    """The init-project skill ships exactly 1 SKILL.md + 14 templates.

    Covers AC7 completeness: guards against silent drift where a new template
    is added to skills/ but no one updates EXPECTED_FILES or the PRD.
    """
    # Arrange & Act
    deployed = sorted(
        str(p.relative_to(compiled_skill_dir))
        for p in compiled_skill_dir.rglob("*")
        if p.is_file()
    )

    # Assert
    expected = sorted(EXPECTED_FILES)
    assert deployed == expected, (
        f"Deployed file set does not match expected.\n"
        f"Expected: {expected}\n"
        f"Actual:   {deployed}"
    )


# -- AC9: role manifest soft-POLA ---------------------------------------------


@pytest.mark.parametrize("manifest_name", ROLE_MANIFESTS)
def test_should_follow_soft_pola_when_role_manifest_parsed(
    compiled_skill_dir: Path, manifest_name: str
) -> None:
    """Each role manifest must parse as YAML and follow the soft-POLA pattern.

    Covers AC9: contains role, default_consumes, and discovery.allowed_requests;
    does not contain a forbids key anywhere in the document.
    """
    # Arrange
    manifest_path = compiled_skill_dir / "templates" / "roles" / manifest_name
    raw = manifest_path.read_text()

    # Act
    parsed = yaml.safe_load(raw)

    # Assert — structure
    assert isinstance(parsed, dict), (
        f"{manifest_name} did not parse as a YAML mapping"
    )
    assert "role" in parsed, f"{manifest_name} missing 'role' key"
    assert "default_consumes" in parsed, (
        f"{manifest_name} missing 'default_consumes' key"
    )
    assert "discovery" in parsed, f"{manifest_name} missing 'discovery' key"
    assert isinstance(parsed["discovery"], dict), (
        f"{manifest_name} 'discovery' is not a mapping"
    )
    assert "allowed_requests" in parsed["discovery"], (
        f"{manifest_name} missing 'discovery.allowed_requests' key"
    )

    # Assert — no forbids anywhere in the parsed tree
    assert not _contains_key(parsed, "forbids"), (
        f"{manifest_name} contains a 'forbids' key; soft-POLA forbids this"
    )


def _contains_key(node: Any, target: str) -> bool:
    """Recursively check whether a parsed YAML tree contains a given key."""
    if isinstance(node, dict):
        if target in node:
            return True
        return any(_contains_key(v, target) for v in node.values())
    if isinstance(node, list):
        return any(_contains_key(item, target) for item in node)
    return False


# -- AC11 / BR-009: README stubs discoverable --------------------------------


@pytest.mark.parametrize("readme_name", TIER_1_READMES)
def test_should_be_short_and_link_tier_0_when_readme_stub(
    compiled_skill_dir: Path, readme_name: str
) -> None:
    """Each Tier 1 README must be ≤15 lines and link to DOMAIN.md and PROJECT.md.

    Covers BR-009 (≤15 lines, self-documenting) and AC11 (discoverable
    pointer back to Tier 0 via relative links that resolve from docs/<dir>/).
    """
    # Arrange
    readme_path = compiled_skill_dir / "templates" / "tier-1" / readme_name
    content = readme_path.read_text()
    line_count = len(content.splitlines())

    # Assert — length
    assert line_count <= 15, (
        f"{readme_name} is {line_count} lines; BR-009 requires ≤15"
    )

    # Assert — Tier 0 backlinks (relative path from docs/<dir>/ back to repo root)
    assert "../../DOMAIN.md" in content, (
        f"{readme_name} missing relative link to ../../DOMAIN.md"
    )
    assert "../../PROJECT.md" in content, (
        f"{readme_name} missing relative link to ../../PROJECT.md"
    )


# -- BR-003: DOMAIN.md.template 9-section order ------------------------------


def test_should_contain_nine_sections_in_order_when_domain_template_read(
    compiled_skill_dir: Path,
) -> None:
    """DOMAIN.md.template must contain all 9 section headers in canonical order.

    Covers BR-003: the 9-section blog-article format is the authoritative
    shape of DOMAIN.md. Section 3 (Revenue Model), 4 (What It Does), and 7
    (What It Is Not) may be parameterized with {{PROJECT_NAME}}.
    """
    # Arrange
    template_path = compiled_skill_dir / "templates" / "DOMAIN.md.template"
    content = template_path.read_text()

    # Act — find each pattern's byte offset in the template
    offsets: list[int] = []
    for pattern in DOMAIN_SECTION_PATTERNS:
        match = re.search(pattern, content, re.MULTILINE)
        assert match is not None, (
            f"DOMAIN.md.template missing section matching pattern: {pattern}"
        )
        offsets.append(match.start())

    # Assert — strictly increasing offsets mean sections appear in order
    assert offsets == sorted(offsets), (
        f"DOMAIN.md.template sections out of order. Offsets: {offsets}\n"
        f"Patterns: {DOMAIN_SECTION_PATTERNS}"
    )


# -- Mechanical E2E helpers ---------------------------------------------------


def _simulate_phase_3(target_repo: Path, skill_dir: Path) -> list[Path]:
    """Simulate SKILL.md Phase 3 Step 1: create Tier 1 dirs + README stubs.

    Mirrors the mechanical file-copy operations the SKILL.md prompt instructs
    an agent to perform. Skips any file that already exists (idempotent).

    Returns the list of files the simulation actually created.
    """
    tier_1_mapping = {
        "prds": "prds.README.md",
        "plans": "plans.README.md",
        "sources": "sources.README.md",
        "standards": "standards.README.md",
        "guides": "guides.README.md",
    }
    created: list[Path] = []
    for dir_name, template_name in tier_1_mapping.items():
        dir_path = target_repo / "docs" / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        readme_dst = dir_path / "README.md"
        if readme_dst.exists():
            continue  # idempotent — never overwrite
        readme_src = skill_dir / "templates" / "tier-1" / template_name
        shutil.copy2(readme_src, readme_dst)
        created.append(readme_dst)
    return created


def _simulate_phase_4(target_repo: Path, skill_dir: Path) -> list[Path]:
    """Simulate SKILL.md Phase 4: create roles/README.md + 5 starter manifests.

    Mirrors the mechanical file-copy operations the SKILL.md prompt instructs
    an agent to perform. Skips any file that already exists (idempotent).

    Returns the list of files the simulation actually created.
    """
    roles_dir = target_repo / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    # roles/README.md
    readme_dst = roles_dir / "README.md"
    if not readme_dst.exists():
        shutil.copy2(skill_dir / "templates" / "roles-README.md", readme_dst)
        created.append(readme_dst)

    # 5 manifests
    for manifest_name in ROLE_MANIFESTS:
        manifest_dst = roles_dir / manifest_name
        if manifest_dst.exists():
            continue
        shutil.copy2(
            skill_dir / "templates" / "roles" / manifest_name, manifest_dst
        )
        created.append(manifest_dst)

    return created


def _run_preflight(target_repo: Path, edit_target: str) -> tuple[int, str]:
    """Invoke check-tier-0.sh against a target repo and candidate edit.

    Returns (exit_code, stderr). Exit 0 = allowed, exit 2 = blocked.
    """
    hook_path = REPO_ROOT / "hooks" / "check-tier-0.sh"
    hook_input = {
        "tool_input": {"file_path": str(target_repo / edit_target)},
        "cwd": str(target_repo),
    }
    result = subprocess.run(
        ["bash", str(hook_path)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode, result.stderr


@pytest.fixture()
def fresh_repo(tmp_path: Path) -> Path:
    """A fresh empty git repo for E2E simulation."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


# -- AC1 (partial), AC3, AC5: Phase 3 creates only skeleton ------------------


class TestMechanicalPhase3:
    """Phase 3 (docs skeleton) produces the Tier 1 tree and nothing more.

    Covers AC1 (partial — the skeleton side), AC5 (phase isolation: skeleton
    does not touch tier-0 files), AC11 (READMEs are the deployed stubs).
    """

    def test_should_create_all_tier_1_dirs_and_readmes(
        self, fresh_repo: Path, compiled_skill_dir: Path
    ) -> None:
        # Act
        created = _simulate_phase_3(fresh_repo, compiled_skill_dir)

        # Assert — 5 READMEs created, one per Tier 1 dir
        assert len(created) == 5
        for dir_name in ("prds", "plans", "sources", "standards", "guides"):
            readme = fresh_repo / "docs" / dir_name / "README.md"
            assert readme.is_file(), (
                f"Missing README after Phase 3: docs/{dir_name}/README.md"
            )
            content = readme.read_text()
            assert "../../DOMAIN.md" in content, (
                f"docs/{dir_name}/README.md missing DOMAIN.md backlink"
            )

    def test_should_not_create_tier_0_files_during_phase_3(
        self, fresh_repo: Path, compiled_skill_dir: Path
    ) -> None:
        """AC5: phase isolation — Phase 3 must not touch DOMAIN.md/PROJECT.md."""
        # Act
        _simulate_phase_3(fresh_repo, compiled_skill_dir)

        # Assert
        assert not (fresh_repo / "DOMAIN.md").exists()
        assert not (fresh_repo / "PROJECT.md").exists()
        assert not (fresh_repo / "CLAUDE.md").exists()


# -- AC1 (partial), AC9: Phase 4 creates role manifests ----------------------


class TestMechanicalPhase4:
    """Phase 4 (role manifests) produces roles/README.md + 5 starter manifests."""

    def test_should_create_roles_readme_and_five_manifests(
        self, fresh_repo: Path, compiled_skill_dir: Path
    ) -> None:
        # Act
        created = _simulate_phase_4(fresh_repo, compiled_skill_dir)

        # Assert — 6 files: 1 README + 5 manifests
        assert len(created) == 6
        assert (fresh_repo / "roles" / "README.md").is_file()
        for manifest_name in ROLE_MANIFESTS:
            manifest_path = fresh_repo / "roles" / manifest_name
            assert manifest_path.is_file(), (
                f"Missing role manifest after Phase 4: roles/{manifest_name}"
            )
            parsed = yaml.safe_load(manifest_path.read_text())
            assert isinstance(parsed, dict)
            assert "default_consumes" in parsed
            assert not _contains_key(parsed, "forbids")


# -- AC2: idempotent re-run ---------------------------------------------------


class TestIdempotentRerun:
    """A re-run on an already-bootstrapped repo produces zero new files."""

    def test_phase_3_rerun_is_noop(
        self, fresh_repo: Path, compiled_skill_dir: Path
    ) -> None:
        # Arrange: first run creates 5 READMEs
        first_run = _simulate_phase_3(fresh_repo, compiled_skill_dir)
        assert len(first_run) == 5

        # Act: second run on the same repo
        second_run = _simulate_phase_3(fresh_repo, compiled_skill_dir)

        # Assert: nothing new created
        assert second_run == []

    def test_phase_4_rerun_is_noop(
        self, fresh_repo: Path, compiled_skill_dir: Path
    ) -> None:
        # Arrange
        first_run = _simulate_phase_4(fresh_repo, compiled_skill_dir)
        assert len(first_run) == 6

        # Act
        second_run = _simulate_phase_4(fresh_repo, compiled_skill_dir)

        # Assert
        assert second_run == []


# -- AC4: partial tier-0 recovery --------------------------------------------


class TestPartialTier0Recovery:
    """If one Tier 0 file exists, the skill must preserve it and create the rest."""

    def test_phase_4_preserves_existing_backend_dev_manifest(
        self, fresh_repo: Path, compiled_skill_dir: Path
    ) -> None:
        """AC4-ish (roles variant): pre-existing role manifest is preserved;
        the other four are still created.
        """
        # Arrange — pre-create a custom backend-dev.yaml
        roles_dir = fresh_repo / "roles"
        roles_dir.mkdir()
        custom_content = "# Custom backend-dev manifest from a prior experiment\nrole: backend-dev\n"
        (roles_dir / "backend-dev.yaml").write_text(custom_content)

        # Act
        created = _simulate_phase_4(fresh_repo, compiled_skill_dir)

        # Assert — only 5 new files (README + 4 manifests, not backend-dev)
        created_names = [p.name for p in created]
        assert "backend-dev.yaml" not in created_names
        assert len(created) == 5  # README + sem + architect + frontend + reviewer

        # Assert — the original backend-dev.yaml is untouched
        preserved = (roles_dir / "backend-dev.yaml").read_text()
        assert preserved == custom_content


# -- AC3: tier-0-preflight hook interaction ----------------------------------


class TestPreflightHookInteraction:
    """check-tier-0.sh blocks Edit|Write before Tier 0 and allows after.

    This is a real hook invocation against a real scratch repo, not a mock.
    """

    def test_should_block_edit_when_tier_0_missing(
        self, fresh_repo: Path
    ) -> None:
        # Arrange: repo exists, no DOMAIN.md / PROJECT.md
        # Act
        exit_code, stderr = _run_preflight(fresh_repo, "src/app.py")

        # Assert
        assert exit_code == 2, (
            f"Expected preflight block (exit 2), got {exit_code}. stderr: {stderr}"
        )
        assert "DOMAIN.md" in stderr
        assert "PROJECT.md" in stderr
        assert "/init-project" in stderr

    def test_should_allow_edit_when_tier_0_present(
        self, fresh_repo: Path
    ) -> None:
        # Arrange
        (fresh_repo / "DOMAIN.md").write_text("# Domain\n")
        (fresh_repo / "PROJECT.md").write_text("# Project\n")

        # Act
        exit_code, _ = _run_preflight(fresh_repo, "src/app.py")

        # Assert
        assert exit_code == 0

    def test_should_allow_editing_domain_md_itself_when_missing(
        self, fresh_repo: Path
    ) -> None:
        """The preflight must NOT block /init-project from creating DOMAIN.md."""
        # Act — repo has neither DOMAIN.md nor PROJECT.md, but we're editing DOMAIN.md
        exit_code, stderr = _run_preflight(fresh_repo, "DOMAIN.md")

        # Assert
        assert exit_code == 0, (
            f"Preflight blocked creation of DOMAIN.md itself. stderr: {stderr}"
        )

    def test_should_allow_editing_project_md_itself_when_missing(
        self, fresh_repo: Path
    ) -> None:
        """The preflight must NOT block /init-project from creating PROJECT.md."""
        # Act
        exit_code, _ = _run_preflight(fresh_repo, "PROJECT.md")

        # Assert
        assert exit_code == 0


# -- AC6: Phase 3 without Phase 1 still works (graceful degradation) ---------


class TestPhase3WithoutTechScaffold:
    """Phase 3 runs standalone even if Phase 1 has not produced a .meta/ tree.

    AC6 in the PRD says: running --phase=domain on a repo with no .meta/ tree
    succeeds but notes 'brownfield vocabulary unavailable'. The parallel claim
    for phase=skeleton is stricter: it has no phase dependencies at all and
    must succeed unconditionally.
    """

    def test_phase_3_runs_on_bare_repo_without_meta_tree(
        self, fresh_repo: Path, compiled_skill_dir: Path
    ) -> None:
        # Arrange: repo is completely empty (no .meta/, no tooling, nothing)
        assert not (fresh_repo / ".meta").exists()

        # Act
        created = _simulate_phase_3(fresh_repo, compiled_skill_dir)

        # Assert — all 5 READMEs still created
        assert len(created) == 5


# -- SKILL.md prompt-contract tests (AC8, AC10, AC12) -----------------------
#
# These verify that the SKILL.md prompt text explicitly encodes the agent
# behaviors required by AC8, AC10, and AC12. They do NOT verify agent
# runtime behavior — a prompt check is weaker than an end-to-end run. But
# they turn "someone rewrites SKILL.md and drops the rule" from a silent
# regression into a caught one.


class TestSkillMdContract:
    """SKILL.md must explicitly encode the behavior contracts from AC8, AC10, AC12."""

    @pytest.fixture(scope="class")
    def skill_md_text(self, compiled_skill_dir: Path) -> str:
        return (compiled_skill_dir / "SKILL.md").read_text()

    def test_should_use_task_tool_for_project_bootstrapper_invocation(
        self, skill_md_text: str
    ) -> None:
        """AC12: Phase 1 must delegate to project-bootstrapper via the Task tool.

        The literal invocation syntax must appear in the prompt so an agent
        following the skill cannot misroute the delegation.
        """
        assert 'subagent_type: "project-bootstrapper"' in skill_md_text, (
            "SKILL.md Phase 1 does not name the Task tool subagent_type — "
            "agent could delegate incorrectly (AC12 regression)."
        )
        # Must also forbid the wrong paths:
        lowered = skill_md_text.lower()
        assert "do not shell out" in lowered or "no shell delegation" in lowered, (
            "SKILL.md does not forbid shell delegation of Phase 1 (AC12)."
        )

    def test_should_forbid_silent_claude_md_overwrite(
        self, skill_md_text: str
    ) -> None:
        """AC8: CLAUDE.md must never be silently overwritten.

        The prompt must contain an explicit never-overwrite rule for CLAUDE.md.
        """
        lowered = skill_md_text.lower()
        # Accept a few phrasings of the never-overwrite rule
        phrases = [
            "never silently overwrite",
            "do not overwrite it under any circumstances",
            "never overwrite",
        ]
        assert any(p in lowered for p in phrases), (
            "SKILL.md does not forbid silent CLAUDE.md overwrite (AC8)."
        )
        # The rule must mention CLAUDE.md specifically, not just "files"
        assert "claude.md" in lowered, (
            "SKILL.md never-overwrite rule does not name CLAUDE.md (AC8)."
        )

    def test_should_include_completion_report_template(
        self, skill_md_text: str
    ) -> None:
        """AC10: SKILL.md must include a completion report template.

        The prompt must name the exact output block so an agent's final
        report is predictable and comparable across runs.
        """
        assert "/init-project complete" in skill_md_text, (
            "SKILL.md is missing the completion report header (AC10)."
        )
        # Report must mention the concrete artifacts it lists
        required_fragments = [
            "Phases run:",
            "Files created:",
            "Next step:",
        ]
        for fragment in required_fragments:
            assert fragment in skill_md_text, (
                f"SKILL.md completion report missing required fragment: "
                f"{fragment!r} (AC10)."
            )

    def test_should_drop_placeholder_tier_0_stubs_before_bootstrapper(
        self, skill_md_text: str
    ) -> None:
        """Phase 1 must create placeholder DOMAIN.md and PROJECT.md stubs BEFORE
        invoking project-bootstrapper, otherwise tier-0-preflight blocks every
        write the bootstrapper tries to make.

        This is a subtle chicken-and-egg: the preflight hook exists to prevent
        agents operating without Tier 0 context, but Phase 1 explicitly needs
        to run before Tier 0 is authored. The resolution is temporary stubs
        that Phase 2 overwrites.

        Regression test: if someone removes the placeholder instruction from
        SKILL.md, future runs of /init-project will deadlock on the very
        first file the bootstrapper tries to write.
        """
        lowered = skill_md_text.lower()
        # Must mention placeholder stubs explicitly
        assert "placeholder" in lowered, (
            "SKILL.md Phase 1 does not mention placeholder Tier 0 stubs — "
            "project-bootstrapper will deadlock on tier-0-preflight."
        )
        # Must name the specific hook that would block
        assert "tier-0-preflight" in lowered, (
            "SKILL.md does not name the tier-0-preflight hook as the reason "
            "for placeholder stubs — future maintainers will not understand "
            "why the stubs exist."
        )
        # Placeholder instructions must appear BEFORE the Task tool invocation
        idx_placeholder = skill_md_text.find("placeholder")
        idx_task_tool = skill_md_text.find('subagent_type: "project-bootstrapper"')
        assert idx_placeholder != -1 and idx_task_tool != -1
        assert idx_placeholder < idx_task_tool, (
            "Placeholder instructions must appear BEFORE the Task tool "
            "invocation, otherwise the agent will try to delegate first and "
            "hit the preflight block."
        )

    def test_should_ask_mode_question_before_six_questions(
        self, skill_md_text: str
    ) -> None:
        """BR-005: Phase 2 asks the research-vs-teach-me question upfront.

        Verifies the SKILL.md prompt structure puts the mode question
        explicitly before the 6-question flow.
        """
        idx_mode = skill_md_text.find("do you understand this business deeply")
        idx_q1 = skill_md_text.find("What is the name of the business")
        assert idx_mode != -1, "SKILL.md missing mode-selection question (BR-005)"
        assert idx_q1 != -1, "SKILL.md missing Question 1"
        assert idx_mode < idx_q1, (
            "SKILL.md must present the mode question BEFORE the six "
            "domain questions (BR-005)."
        )

    def test_should_use_ask_user_question_for_multi_choice_prompts(
        self, skill_md_text: str
    ) -> None:
        """Multi-choice prompts must use the AskUserQuestion tool.

        Questions buried in prose output get lost in the text stream. The
        AskUserQuestion tool renders as a dedicated picker UI that the user
        cannot miss. Every multi-choice prompt in SKILL.md (Tier 2 prompt,
        mode selection, CLAUDE.md merge decision, Phase 2 review) must
        invoke this tool.

        This test catches regression if someone rewrites the skill to use
        prose questions again.
        """
        # Must document the convention
        assert "User-Input Conventions" in skill_md_text, (
            "SKILL.md missing the User-Input Conventions section — without "
            "it, agents won't know to use AskUserQuestion"
        )
        assert "AskUserQuestion" in skill_md_text, (
            "SKILL.md does not reference the AskUserQuestion tool — "
            "multi-choice prompts will be buried in prose"
        )

        # Count AskUserQuestion references — each known multi-choice
        # decision point should produce at least one reference. Current
        # count: convention section examples + mode selection + CLAUDE.md
        # merge + Tier 2 prompt + teach-me follow-ups = ≥ 5 references.
        count = skill_md_text.count("AskUserQuestion")
        assert count >= 5, (
            f"SKILL.md has only {count} AskUserQuestion references — "
            f"expected at least 5 (conventions + mode + CLAUDE.md + "
            f"Tier 2 + teach-me follow-ups)"
        )

    def test_should_use_bash_cp_for_verbatim_templates(
        self, skill_md_text: str
    ) -> None:
        """Phase 3 and Phase 4 must use `Bash cp` for verbatim templates,
        never Read + Write.

        Regression test: the first dogfood run revealed the agent was
        using Read + Write to 'copy' role manifests and README stubs,
        which transcribes the file through the LLM instead of doing a
        byte-identical copy. That risks typos in the soft-POLA pattern,
        burns tokens on files the agent already read, and makes template
        drift undetectable.

        The rule: placeholder templates (DOMAIN/PROJECT/CLAUDE.md.template)
        use Read + substitute + Write because they need per-project
        values. Verbatim templates (role manifests, README stubs) use
        `cp` via Bash because they are deterministic copies.
        """
        # Must document the Template Copy Conventions section at the top
        assert "Template Copy Conventions" in skill_md_text, (
            "SKILL.md missing the Template Copy Conventions section — "
            "agents will improvise Read + Write and introduce transcription bugs"
        )
        # Must name both categories
        assert "Placeholder templates" in skill_md_text, (
            "SKILL.md missing the 'Placeholder templates' category — "
            "agents won't know which templates need substitution"
        )
        assert "Verbatim templates" in skill_md_text, (
            "SKILL.md missing the 'Verbatim templates' category — "
            "agents won't know which templates should be byte-identical"
        )
        # Must call out the tool per category
        assert "Bash cp" in skill_md_text, (
            "SKILL.md missing explicit `Bash cp` directive — agents "
            "fall back to Read + Write which transcribes through the LLM"
        )
        assert "cp -n" in skill_md_text, (
            "SKILL.md missing the `cp -n` (no-clobber) directive for "
            "idempotent copies — role manifests could get overwritten"
        )
        # Must explicitly forbid Read + Write for verbatim templates
        # (search for language that makes the prohibition explicit)
        lowered = skill_md_text.lower()
        forbids_transcription = (
            "never use `read` + `write`" in lowered
            or "do not use read + write" in lowered
            or "not use `read` + `write`" in lowered
        )
        assert forbids_transcription, (
            "SKILL.md must explicitly forbid using Read + Write for "
            "verbatim templates. Without the prohibition, agents default "
            "to Read + Write because those tools are more salient."
        )

    def test_should_document_visual_marker_for_open_questions(
        self, skill_md_text: str
    ) -> None:
        """Open-ended elicitation (the 6 Phase 2 questions) must use a
        visual marker convention.

        The 6 domain questions are free-form and cannot use AskUserQuestion
        (answers aren't enumerable). They need a visual break from the
        surrounding agent output so the user notices the question.

        The convention is: blank line + horizontal rule + blank line +
        bold "▶ Your answer needed:" prefix.
        """
        # The convention must be documented
        assert "▶ Your answer needed" in skill_md_text, (
            "SKILL.md does not define the visual marker convention for "
            "open-ended questions. Buried prose questions will return."
        )
        # Must be present in the six-questions section so it actually applies
        idx_convention = skill_md_text.find("▶ Your answer needed")
        idx_six_questions = skill_md_text.find("Step 3: The six questions")
        assert idx_convention != -1 and idx_six_questions != -1
        # The convention should be referenced (not just defined) in the
        # six-questions section
        six_questions_section = skill_md_text[idx_six_questions:idx_six_questions + 2000]
        assert "▶ Your answer needed" in six_questions_section, (
            "Step 3 (the six questions) must reference the visual marker "
            "convention explicitly so agents apply it when rendering"
        )


# -- install.sh integration: skill trees install correctly ------------------
#
# BR-011 requires compile-sdlc.py to copy skill subdirectories. The same
# requirement applies to install.sh — it has to deploy the compiled
# skills/init-project/templates/ tree to the target dir, or the skill
# breaks at runtime when it tries to read templates that were not copied.


class TestInstallSkillSubdirs:
    """install.sh must deploy entire skill directories, not just SKILL.md."""

    def test_install_copies_init_project_templates(
        self, tmp_path: Path, compiled_skill_dir: Path
    ) -> None:
        """After simulating install.sh's skill-copy loop, the target dir
        contains SKILL.md AND every template file.

        Regression test for the bug where `cp "$skill_dir"/*` in install.sh
        silently dropped subdirectories because cp without -R cannot
        recurse.
        """
        # Arrange: a fake $TARGET_DIR/skills/init-project/
        target_skill_dir = tmp_path / "skills" / "init-project"
        target_skill_dir.mkdir(parents=True)

        # Act: mirror the fixed install.sh logic — cp -R on the source
        subprocess.run(
            ["cp", "-R", f"{compiled_skill_dir}/.", f"{target_skill_dir}/"],
            check=True,
        )

        # Assert: every expected file landed in the target
        for relative_path in EXPECTED_FILES:
            target = target_skill_dir / relative_path
            assert target.is_file(), (
                f"install.sh would not deploy: {relative_path}. "
                f"The install script must recursively copy skill subdirs."
            )

    def test_install_script_uses_recursive_copy(self) -> None:
        """install.sh must not use non-recursive cp for skill directories.

        This is a source-level guard: the bug was that line 79 used
        `cp "$skill_dir"/*` which silently drops subdirectories. A
        replacement must use rsync or cp -R.
        """
        install_text = (REPO_ROOT / "install.sh").read_text()
        # Find the install-skills section
        skill_section_start = install_text.find("# ── 3. Install skills")
        skill_section_end = install_text.find("# ── 4.")
        assert skill_section_start != -1 and skill_section_end != -1, (
            "install.sh is missing the skill-install section"
        )
        skill_section = install_text[skill_section_start:skill_section_end]

        # The broken pattern — cp of a glob without -R — must not be present
        assert 'cp "$skill_dir"/*' not in skill_section, (
            "install.sh still uses non-recursive glob copy for skills. "
            "This silently drops subdirectories like templates/."
        )
        # Some form of recursive copy must be present
        uses_rsync = "rsync" in skill_section
        uses_cp_r = "cp -R" in skill_section or "cp -r" in skill_section
        assert uses_rsync or uses_cp_r, (
            "install.sh must use rsync or cp -R to install skill subdirs."
        )
