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
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml


def _find_bash() -> str:
    """Prefer Git Bash on Windows; ``shutil.which("bash")`` elsewhere."""
    if platform.system() == "Windows":
        git_bash = Path(r"C:\Program Files\Git\usr\bin\bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    found = shutil.which("bash")
    if found:
        return found
    raise FileNotFoundError("No bash executable found on PATH")


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "init-project"

# Ftmp-5afddbce task 005 ships ``etc_installer/install_steps.py`` as the
# Python rewrite of install.sh's 11 step functions, including the
# recursive skill-deploy step. Per task 006 AC-006-5, the install-script
# recursive-copy assertion migrates from grep-on-install.sh to
# grep-on-install_steps.py once task 005 ships. Pre-task-005, the
# migrated test SKIPS via skipif(not INSTALL_STEPS_PATH.exists(), ...).
INSTALL_STEPS_PATH = REPO_ROOT / "etc_installer" / "install_steps.py"
INSTALL_STEPS_PENDING_REASON = (
    "etc_installer/install_steps.py not yet shipped (pending Ftmp-5afddbce "
    "task 005 install_steps.py)"
)

# The full template set deployed by compile-sdlc.py: SKILL.md + 15 templates.
# ARCHITECTURE.md.template is the human-twin render skeleton for the
# architecture-baseline phase (Phase 1.5); it lands alongside the three
# placeholder templates as a Category-1 (substituted-on-render) artifact.
EXPECTED_FILES: tuple[str, ...] = (
    "SKILL.md",
    "templates/DOMAIN.md.template",
    "templates/PROJECT.md.template",
    "templates/CLAUDE.md.template",
    "templates/ARCHITECTURE.md.template",
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


def test_should_deploy_exactly_the_expected_file_set_when_compile_runs(
    compiled_skill_dir: Path,
) -> None:
    """The init-project skill ships exactly 1 SKILL.md + 15 templates.

    Covers AC7 completeness: guards against silent drift where a new template
    is added to skills/ but no one updates EXPECTED_FILES or the PRD. The set
    is data-driven from EXPECTED_FILES, so adding a template means updating one
    tuple — the guard then re-locks the count.
    """
    # Arrange & Act
    deployed = sorted(
        # Normalize Windows backslashes — `relative_to` returns paths with
        # the platform separator, but the expected-files list uses forward
        # slashes. Without this the fifteen-files assertion fails on Windows.
        str(p.relative_to(compiled_skill_dir)).replace("\\", "/")
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
    raw = manifest_path.read_text(encoding="utf-8")

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
    content = readme_path.read_text(encoding="utf-8")
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
    content = template_path.read_text(encoding="utf-8")

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
        [_find_bash(), str(hook_path)],
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
            content = readme.read_text(encoding="utf-8")
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
            parsed = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
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
        preserved = (roles_dir / "backend-dev.yaml").read_text(encoding="utf-8")
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
        return (compiled_skill_dir / "SKILL.md").read_text(encoding="utf-8")

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
        # Placeholder instructions must appear BEFORE the actual Task tool
        # invocation. Use rfind() to locate the last occurrence (the real
        # Phase 1 Step 2 invocation); earlier occurrences may appear in
        # policy sections (e.g., Subagent Dispatch) that describe dispatch
        # rules without executing them. The invariant we care about is
        # "actual invocation comes after placeholder creation," not "every
        # mention of the type comes after."
        idx_placeholder = skill_md_text.find("placeholder")
        idx_task_tool = skill_md_text.rfind('subagent_type: "project-bootstrapper"')
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

    def test_should_slot_baseline_phase_between_phase_1_and_phase_2(
        self, skill_md_text: str
    ) -> None:
        """AC1: the architecture-baseline phase heading must appear, named
        'Phase 1.5: Architecture Baseline', positioned in the body AFTER the
        Phase 1 heading and BEFORE the Phase 2 heading.

        Numbering the phase 1.5 keeps the existing Phase 2-4 headings stable
        (the slot-between framing). A wave-3 sibling fills RATIFY/ENFORCE;
        this task only proves the slot is present and ordered.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        idx_phase_1 = skill_md_text.find("## Phase 1 -- Technical Scaffold")
        idx_phase_2 = skill_md_text.find("## Phase 2 -- Domain Scaffold")
        assert idx_baseline != -1, (
            "SKILL.md missing the 'Phase 1.5 -- Architecture Baseline' heading "
            "(AC1) — the baseline phase slot was not added."
        )
        assert idx_phase_1 != -1 and idx_phase_2 != -1
        assert idx_phase_1 < idx_baseline < idx_phase_2, (
            "Phase 1.5 -- Architecture Baseline must slot BETWEEN Phase 1 and "
            "Phase 2 in the SKILL body (AC1)."
        )

    def test_should_document_phase_baseline_flag(
        self, skill_md_text: str
    ) -> None:
        """AC1: --phase=baseline runs the architecture-baseline phase standalone.

        The flag must appear in the Usage block AND the Flag Parsing section so
        an agent both advertises and honors the standalone backfill path.
        """
        assert "--phase=baseline" in skill_md_text, (
            "SKILL.md does not document the --phase=baseline flag (AC1) — the "
            "standalone backfill path is unreachable."
        )
        # Must be wired in Flag Parsing, not only the Usage banner.
        idx_flag_parsing = skill_md_text.find("## Flag Parsing")
        assert idx_flag_parsing != -1
        flag_parsing_section = skill_md_text[idx_flag_parsing : idx_flag_parsing + 1500]
        assert "--phase=baseline" in flag_parsing_section, (
            "Flag Parsing section does not handle --phase=baseline (AC1)."
        )

    def test_should_block_baseline_phase_when_phase_1_artifacts_absent(
        self, skill_md_text: str
    ) -> None:
        """AC1: standalone --phase=baseline must carry a precondition block.

        When Phase 1 artifacts (the .meta/ tree) are absent, the baseline phase
        must surface a clear precondition message rather than silently running
        a discovery pass against an un-surveyed repo. The message text is the
        contract a regression would drop.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        assert idx_baseline != -1
        baseline_section = skill_md_text[idx_baseline:]
        # Cut the section at the next top-level phase heading so we grep only
        # the baseline phase body.
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]
        lowered = baseline_section.lower()
        assert "precondition" in lowered, (
            "Phase 1.5 does not document a precondition block for standalone "
            "--phase=baseline (AC1)."
        )
        # The precondition must name the missing Phase 1 artifact (.meta/) so
        # the agent knows exactly what to check.
        assert ".meta" in baseline_section, (
            "Phase 1.5 precondition does not name the .meta/ tree as the "
            "Phase 1 artifact it depends on (AC1)."
        )

    def test_should_dispatch_baseline_surveyor_in_parallel_batches(
        self, skill_md_text: str
    ) -> None:
        """AC2: DISCOVER/VERIFY dispatches baseline-surveyor agents in parallel
        batches capped at 5 (project-bootstrapper precedent).

        The phase must name the Agent tool, the baseline-surveyor subagent_type,
        and the ≤5-per-batch ceiling so the fan-out is unambiguous.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        assert idx_baseline != -1
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]

        assert 'subagent_type: "baseline-surveyor"' in baseline_section, (
            "Phase 1.5 does not name the baseline-surveyor subagent_type "
            "(AC2) — the fan-out is unroutable."
        )
        # The four assignment types must all be named.
        for assignment in ("inventory", "claims", "patterns", "seams"):
            assert assignment in baseline_section, (
                f"Phase 1.5 does not name the '{assignment}' surveyor "
                f"assignment (AC2)."
            )
        # The ≤5-per-batch ceiling (project-bootstrapper precedent).
        has_batch_cap = (
            "5 per batch" in baseline_section
            or "≤5" in baseline_section
            or "<=5" in baseline_section
            or "at most 5" in baseline_section
        )
        assert has_batch_cap, (
            "Phase 1.5 does not document the ≤5-per-batch dispatch ceiling "
            "(AC2, project-bootstrapper precedent)."
        )

    def test_should_call_baseline_py_init_with_merged_findings(
        self, skill_md_text: str
    ) -> None:
        """AC2: the conductor merges surveyor findings and calls baseline.py init.

        The exact CLI invocation prefix must appear so the Codex path-rewrite
        works and the agent does not parse YAML itself.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        assert idx_baseline != -1
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]

        assert "~/.claude/scripts/baseline.py init" in baseline_section, (
            "Phase 1.5 does not call `baseline.py init` with the "
            "~/.claude/scripts/ prefix (AC2) — the merge step is unwired and "
            "Codex path-rewrite breaks."
        )
        assert "--from" in baseline_section, (
            "Phase 1.5 baseline.py init call does not pass --from <merged-json> "
            "(AC2)."
        )

    def test_should_treat_empty_inventory_as_valid_baseline(
        self, skill_md_text: str
    ) -> None:
        """AC2: an empty inventory proceeds as a valid baseline (no-docs repo)."""
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        assert idx_baseline != -1
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]
        lowered = baseline_section.lower()
        assert "empty inventory" in lowered, (
            "Phase 1.5 does not state that an empty inventory is a valid "
            "baseline (AC2, the no-docs fixture)."
        )

    def test_should_seed_trivial_ratified_baseline_in_greenfield_mode(
        self, skill_md_text: str
    ) -> None:
        """AC2: greenfield mode seeds a trivial ratified baseline from the
        scaffold with NO verification pass.

        A freshly scaffolded greenfield repo has no pre-existing claims to
        verify — the scaffold IS the architecture — so the fan-out is skipped
        and a trivial baseline is seeded directly.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        assert idx_baseline != -1
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]
        lowered = baseline_section.lower()
        assert "greenfield" in lowered, (
            "Phase 1.5 does not document the greenfield branch (AC2)."
        )
        # Greenfield must explicitly skip the verification/discovery pass.
        skips_verification = (
            "no verification pass" in lowered
            or "without a verification pass" in lowered
            or "skip the verification" in lowered
            or "skips the verification" in lowered
        )
        assert skips_verification, (
            "Phase 1.5 greenfield branch does not state that it skips the "
            "verification pass (AC2)."
        )

    def test_should_verify_existing_tier_0_artifacts_through_claim_ledger(
        self, skill_md_text: str
    ) -> None:
        """AC3: self-check — on re-init, existing DOMAIN.md/PROJECT.md/.meta
        artifacts' load-bearing claims enter the claim ledger through the SAME
        verification pass as third-party docs (never silently retained).

        This is the ADR-003 self-application: etc's own prior tier-0 output is
        not trusted on faith just because etc generated it.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        assert idx_baseline != -1
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]
        lowered = baseline_section.lower()

        # Must name the self-check / re-init path.
        has_self_check = "self-check" in lowered or "re-init" in lowered
        assert has_self_check, (
            "Phase 1.5 does not document the re-init self-check (AC3)."
        )
        # Must name etc's own tier-0 artifacts as subject to verification.
        assert "DOMAIN.md" in baseline_section, (
            "Phase 1.5 self-check does not name DOMAIN.md as a claim source "
            "(AC3) — etc's own docs must be verified, not retained on faith."
        )
        # Must state the never-silently-retained contract.
        retains_nothing_silently = (
            "never silently retained" in lowered
            or "not silently retained" in lowered
            or "same verification pass" in lowered
        )
        assert retains_nothing_silently, (
            "Phase 1.5 self-check does not state that existing tier-0 claims "
            "go through the same verification pass and are never silently "
            "retained (AC3)."
        )

    def test_should_stub_ratify_and_enforce_for_next_wave(
        self, skill_md_text: str
    ) -> None:
        """Phase 1.5 carries RATIFY and ENFORCE sub-headings as one-line
        forward-pointer stubs that the wave-3 sibling replaces in place.

        Structuring the stubs now (rather than leaving the headings absent)
        gives the wave-3 task a stable insertion point and signals to readers
        that the phase is intentionally incomplete, not broken.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        assert idx_baseline != -1
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]

        assert "### DISCOVER" in baseline_section, (
            "Phase 1.5 missing the DISCOVER sub-step heading."
        )
        assert "### VERIFY" in baseline_section, (
            "Phase 1.5 missing the VERIFY sub-step heading."
        )
        assert "### RATIFY" in baseline_section, (
            "Phase 1.5 missing the RATIFY stub heading (wave-3 insertion point)."
        )
        assert "### ENFORCE" in baseline_section, (
            "Phase 1.5 missing the ENFORCE stub heading (wave-3 insertion point)."
        )
        # The forward-pointer must be present so the stubs read as deliberate.
        lowered = baseline_section.lower()
        assert "next wave" in lowered, (
            "Phase 1.5 RATIFY/ENFORCE stubs missing the 'next wave' forward "
            "pointer — wave-3 has no marked insertion point."
        )

    def test_should_ratify_via_interactive_matrix_walk(
        self, skill_md_text: str
    ) -> None:
        """Task-008 AC1: RATIFY is an interactive matrix walk (Pattern A/B) over
        every non-VERIFIED claim, every competing-patterns concern, exemplar
        blessing, do-not-copy marker, and seam resolution.

        The matrix-walk forcing function (layer-rubrics precedent) means the
        engine NEVER fabricates a decision — each non-VERIFIED cell is surfaced
        to the human and a decision is recorded. The section must name the cell
        classes it walks and bind to the interactive-input patterns.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        assert idx_baseline != -1
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]

        idx_ratify = baseline_section.find("### RATIFY")
        assert idx_ratify != -1
        idx_enforce = baseline_section.find("### ENFORCE")
        assert idx_enforce != -1, "ENFORCE must follow RATIFY in Phase 1.5"
        ratify_section = baseline_section[idx_ratify:idx_enforce]
        lowered = ratify_section.lower()

        assert "matrix walk" in lowered or "matrix-walk" in lowered, (
            "RATIFY must be framed as the interactive matrix walk (AC1)."
        )
        # Every cell class the walk must cover.
        for cell in (
            "non-VERIFIED",
            "competing",
            "exemplar",
            "do-not-copy",
            "seam",
        ):
            assert cell.lower() in lowered, (
                f"RATIFY matrix walk does not cover the '{cell}' cell class (AC1)."
            )
        # Seam resolution alternatives (the closed enum).
        assert "sibling" in lowered and "boundary-unknown" in lowered, (
            "RATIFY must surface both seam resolutions: sibling path and "
            "boundary-unknown (AC1)."
        )
        # Must bind to the interactive-input patterns (A for enumerable cells,
        # B for free-form rationale).
        assert "AskUserQuestion" in ratify_section, (
            "RATIFY must use AskUserQuestion (Pattern A) for enumerable cell "
            "decisions (AC1)."
        )
        assert "▶ Your answer needed" in ratify_section, (
            "RATIFY must use the Pattern B visual marker for free-form rationale "
            "capture (AC1)."
        )
        # The engine-never-fabricates contract.
        assert "never fabricat" in lowered or "engine never" in lowered, (
            "RATIFY must state that the engine never fabricates a decision (AC1)."
        )

    def test_should_persist_partial_ratify_decisions_and_resume(
        self, skill_md_text: str
    ) -> None:
        """Task-008 AC1: abort persists partial decisions with status
        ``unratified`` and a re-run resumes from the recorded decisions.

        The single-writer rule binds: the skill records each decision THROUGH
        baseline.py (re-running ``init --from`` with the updated merged JSON,
        since baseline.py exposes no per-claim resolution subcommand) and NEVER
        hand-edits the YAML. The baseline stays ``unratified`` until ratify.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]
        idx_ratify = baseline_section.find("### RATIFY")
        idx_enforce = baseline_section.find("### ENFORCE")
        ratify_section = baseline_section[idx_ratify:idx_enforce]
        lowered = ratify_section.lower()

        # Abort/resume contract.
        assert "abort" in lowered, "RATIFY must document the abort path (AC1)."
        assert "resume" in lowered or "resumes" in lowered, (
            "RATIFY must document resuming from recorded decisions (AC1)."
        )
        assert "unratified" in lowered, (
            "RATIFY abort must leave the baseline status unratified (AC1)."
        )
        # Single-writer: never hand-edit the YAML; record through baseline.py.
        assert "never" in lowered and (
            "edit the yaml" in lowered or "hand-edit" in lowered
        ), (
            "RATIFY must state the skill never hand-edits the baseline YAML "
            "(single-writer rule, AC1)."
        )
        # The honest persistence path: re-run init --from with updated JSON.
        assert "init --from" in ratify_section or "init`" in ratify_section, (
            "RATIFY partial-decision persistence must route through "
            "baseline.py init --from (the only resolution writer, AC1)."
        )

    def test_should_ratify_via_baseline_py_ratify_rendering_doc(
        self, skill_md_text: str
    ) -> None:
        """Task-008 AC1: ratification calls ``baseline.py ratify --by`` which
        performs the one-way transition and renders ARCHITECTURE.md.

        The substrate fact: ratify exits 2 listing ``CL-NNN: <reason>`` lines
        when non-VERIFIED claims lack resolution, and renders the human twin on
        success. The skill must invoke ratify with the ~/.claude/scripts/ prefix
        (Codex path-rewrite) and not separately hand-render the doc.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]
        idx_ratify = baseline_section.find("### RATIFY")
        idx_enforce = baseline_section.find("### ENFORCE")
        ratify_section = baseline_section[idx_ratify:idx_enforce]

        assert "~/.claude/scripts/baseline.py ratify" in ratify_section, (
            "RATIFY must call baseline.py ratify with the ~/.claude/scripts/ "
            "prefix (AC1, Codex path-rewrite)."
        )
        assert "--by" in ratify_section, (
            "baseline.py ratify call must pass --by <name> (AC1)."
        )
        # The render is a consequence of ratify, named so the agent does not
        # double-render.
        assert "ARCHITECTURE.md" in ratify_section, (
            "RATIFY must name ARCHITECTURE.md as ratify's rendered output (AC1)."
        )
        # The exit-2 blocking contract must be documented so the agent knows
        # what an unresolved claim looks like.
        assert "CL-" in ratify_section and "exit" in ratify_section.lower(), (
            "RATIFY must document ratify's exit-2 CL-NNN blocking behavior "
            "(AC1)."
        )

    def test_should_route_enforce_rules_native_first_then_generated(
        self, skill_md_text: str
    ) -> None:
        """Task-008 AC2: ENFORCE generates rules into the project's native
        fitness-function tool where one covers the rule class, else records
        ``enforced_by: generated`` for the profile checker.

        Native-tool-first (ADR-004). The per-rule routing split is the
        bookkeeping the completion report must name. The mechanizable v1 grammar
        (python profile) is the routing input for the generated fallback.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]
        idx_enforce = baseline_section.find("### ENFORCE")
        assert idx_enforce != -1
        enforce_section = baseline_section[idx_enforce:]
        lowered = enforce_section.lower()

        assert "native" in lowered and "fitness" in lowered, (
            "ENFORCE must document native fitness-function-first routing (AC2)."
        )
        # The enforced_by closed enum must be named for both routes.
        assert "enforced_by: native" in enforce_section, (
            "ENFORCE must name enforced_by: native for native-tool rules (AC2)."
        )
        assert "enforced_by: generated" in enforce_section, (
            "ENFORCE must name enforced_by: generated for the profile-checker "
            "fallback (AC2)."
        )
        assert "human-judgment" in lowered, (
            "ENFORCE must route un-mechanizable rules to human-judgment (AC2)."
        )
        # The generated fallback routes through append-rule --mechanizable
        # (baseline.py is the single writer; there is no enforce subcommand).
        assert "append-rule" in enforce_section, (
            "ENFORCE generated rules must be recorded via baseline.py "
            "append-rule (AC2, single-writer)."
        )
        assert "--mechanizable" in enforce_section, (
            "ENFORCE must pass --mechanizable when recording a generated-"
            "checker rule (AC2)."
        )

    def test_should_recommend_never_perform_host_ci_wiring(
        self, skill_md_text: str
    ) -> None:
        """Task-008 AC2: the completion report names per-rule routing and
        RECOMMENDS (never performs) host-CI wiring.

        etc writes the native-tool config and records generated rules, but it
        must not silently mutate the host CI pipeline — it recommends the wiring
        and leaves the decision to the operator.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]
        idx_enforce = baseline_section.find("### ENFORCE")
        enforce_section = baseline_section[idx_enforce:]
        lowered = enforce_section.lower()

        assert "per-rule routing" in lowered or "per-rule" in lowered, (
            "ENFORCE completion report must name per-rule routing (AC2)."
        )
        # Recommend, never perform, host-CI wiring.
        assert "ci" in lowered, "ENFORCE must address host-CI wiring (AC2)."
        assert "recommend" in lowered, (
            "ENFORCE must RECOMMEND host-CI wiring (AC2)."
        )
        assert "never perform" in lowered or "not perform" in lowered or (
            "never wire" in lowered
        ), (
            "ENFORCE must state it never PERFORMS host-CI wiring — only "
            "recommends it (AC2)."
        )

    def test_should_review_mode_zero_drift_zero_writes_drift_surfaced(
        self, skill_md_text: str
    ) -> None:
        """Task-008 AC3: re-init review mode — zero drift -> zero writes +
        'already present' report; drift -> surfaced for amendment, never
        auto-mutated.

        The idempotency contract at the top of the skill is preserved: a re-run
        on a ratified baseline with no drift writes nothing; detected drift is
        surfaced to the human for amendment, never silently rewritten.
        """
        idx_baseline = skill_md_text.find("## Phase 1.5 -- Architecture Baseline")
        baseline_section = skill_md_text[idx_baseline:]
        next_heading = baseline_section.find("## Phase 2 -- Domain Scaffold")
        if next_heading != -1:
            baseline_section = baseline_section[:next_heading]
        lowered = baseline_section.lower()

        assert "review mode" in lowered, (
            "Phase 1.5 must document re-init review mode (AC3)."
        )
        assert "already present" in lowered, (
            "Review mode must emit an 'already present' report on zero drift "
            "(AC3)."
        )
        assert "zero writes" in lowered or "no writes" in lowered or (
            "writes zero" in lowered
        ), (
            "Review mode zero-drift path must write nothing (AC3)."
        )
        assert "drift" in lowered, "Review mode must detect drift (AC3)."
        # Drift is surfaced, never auto-mutated.
        assert "never auto-mutat" in lowered or "not auto-mutat" in lowered or (
            "never silently" in lowered
        ), (
            "Review mode drift must never be auto-mutated — surfaced for "
            "amendment only (AC3)."
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


# -- Task-009 workspace-mode prompt-contract tests (AC1, AC2) ----------------
#
# Workspace mode initializes a directory of N git repos: each repo gets a full
# single-repo init+baseline, and the workspace gets ONE canonical seam map. As
# with the rest of TestSkillMdContract, these greps cannot prove agent-runtime
# behavior — but they turn "someone rewrites the workspace section and drops a
# safety rail or the sync-seams call" from a silent regression into a caught
# one. The covr failure (a two-repo system whose cross-repo contracts lived in
# nobody's context) is exactly what the seam map exists to prevent.


class TestWorkspaceModeContract:
    """SKILL.md must encode the workspace-mode detection trichotomy, the
    per-repo run loop, the canonical seam-map artifact, and the workspace
    safety rails (Task-009 AC1 + AC2)."""

    @pytest.fixture(scope="class")
    def skill_md_text(self, compiled_skill_dir: Path) -> str:
        return (compiled_skill_dir / "SKILL.md").read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def workspace_section(self, skill_md_text: str) -> str:
        """The top-level Workspace Mode section body (heading → next top-level
        heading or EOF). All workspace-specific contract greps scope to here so
        a stray mention elsewhere cannot satisfy the assertion."""
        idx = skill_md_text.find("## Workspace Mode")
        assert idx != -1, (
            "SKILL.md is missing the top-level '## Workspace Mode' section "
            "(Task-009) — multi-repo initialization is unreachable."
        )
        rest = skill_md_text[idx + len("## Workspace Mode") :]
        next_heading = rest.find("\n## ")
        if next_heading != -1:
            rest = rest[:next_heading]
        return rest

    def test_should_carry_top_level_workspace_mode_section(
        self, skill_md_text: str
    ) -> None:
        """AC1/AC2: a top-level '## Workspace Mode' section exists and is named
        for multi-repo initialization so the capability is discoverable."""
        idx = skill_md_text.find("## Workspace Mode")
        assert idx != -1, (
            "SKILL.md missing the '## Workspace Mode' top-level section "
            "(Task-009)."
        )
        # The heading must signal multi-repo initialization, not be a bare
        # 'Workspace Mode' that a reader could mistake for a flag.
        heading_line = skill_md_text[idx : skill_md_text.find("\n", idx)].lower()
        assert "multi-repo" in heading_line or "multi repo" in heading_line, (
            "The Workspace Mode heading must name multi-repo initialization "
            "(Task-009)."
        )

    def test_should_detect_workspace_shape_before_phase_1(
        self, skill_md_text: str
    ) -> None:
        """AC1: a detection step at skill entry must run BEFORE Phase 1 so a
        directory-of-repos is routed to workspace mode rather than being
        treated as a single (non-)repo by Phase 1."""
        idx_detect = skill_md_text.find("## Workspace Mode")
        idx_phase_1 = skill_md_text.find("## Phase 1 -- Technical Scaffold")
        assert idx_detect != -1 and idx_phase_1 != -1
        assert idx_detect < idx_phase_1, (
            "The Workspace Mode detection section must appear BEFORE Phase 1 in "
            "the SKILL body so the invocation-directory shape is resolved at "
            "entry, not after the single-repo flow has started (AC1)."
        )

    def test_should_detect_trichotomy_repo_vs_workspace_vs_greenfield(
        self, workspace_section: str
    ) -> None:
        """AC1: the detection trichotomy must be fully spelled out — a git repo
        runs the normal flow; a non-repo dir with ≥2 child repos offers
        workspace mode; exactly 1 child repo degrades to single-repo with a
        note; 0 repos is greenfield. All four arms are the contract."""
        lowered = workspace_section.lower()

        # Arm 1: the invocation dir is itself a git repo → normal single-repo flow.
        assert "git repo" in lowered or "is a git repository" in lowered, (
            "Detection must name the 'invocation dir IS a git repo → normal "
            "flow' arm (AC1)."
        )
        # Arm 2: non-repo dir containing ≥2 child repos → offer workspace mode.
        has_two_or_more = (
            "≥2" in workspace_section
            or ">=2" in workspace_section
            or "two or more" in lowered
            or "2 or more" in lowered
            or "at least 2" in lowered
            or "at least two" in lowered
        )
        assert has_two_or_more, (
            "Detection must name the '≥2 immediate-child git repos → offer "
            "workspace mode' arm (AC1)."
        )
        # Arm 3: exactly 1 child repo → degrade to single-repo with a note.
        has_single_degrade = (
            "exactly 1" in lowered
            or "exactly one" in lowered
            or "one repo" in lowered
            or "one-repo" in lowered
            or "single child" in lowered
        )
        assert has_single_degrade, (
            "Detection must name the 'exactly 1 child repo → degrade to "
            "single-repo with a note' arm (AC1)."
        )
        # The single-repo degrade must mention a NOTE (not silent).
        assert "note" in lowered, (
            "The one-repo degrade must be accompanied by a note, not a silent "
            "fallthrough (AC1)."
        )
        # Arm 4: 0 repos → greenfield handling.
        has_zero = (
            "0 repos" in lowered
            or "zero repos" in lowered
            or "no repos" in lowered
            or "0 child" in lowered
        )
        assert has_zero and "greenfield" in lowered, (
            "Detection must name the '0 repos → greenfield' arm (AC1)."
        )

    def test_should_treat_monorepo_as_single_repo_not_workspace(
        self, workspace_section: str
    ) -> None:
        """AC1: a multi-package single repo (monorepo) is NOT a workspace. The
        discriminator is git-repo-boundary count, not package count — a
        monorepo has one .git and must run the normal single-repo flow."""
        lowered = workspace_section.lower()
        assert "monorepo" in lowered, (
            "Detection must explicitly distinguish a monorepo (multi-package "
            "single repo) from a workspace (AC1)."
        )
        # The monorepo line must say it is NOT a workspace.
        assert "not a workspace" in lowered or "not workspace" in lowered, (
            "Detection must state a monorepo is NOT a workspace (AC1) — "
            "otherwise a multi-package single repo wrongly fans out."
        )

    def test_should_offer_workspace_mode_via_pattern_a(
        self, workspace_section: str
    ) -> None:
        """AC1: when ≥2 child repos are detected, workspace mode is OFFERED via
        Pattern A (AskUserQuestion) — never auto-entered. The operator decides
        whether to fan out across the whole directory."""
        assert "AskUserQuestion" in workspace_section, (
            "Workspace mode must be offered via Pattern A (AskUserQuestion), "
            "not auto-entered (AC1)."
        )

    def test_should_enforce_workspace_safety_rails(
        self, workspace_section: str
    ) -> None:
        """AC1: the three safety rails are verbatim contract — never crawl
        upward, never follow symlinks out of the workspace, immediate children
        only. A regression that drops any rail re-opens the directory-traversal
        / symlink-escape surface the ADR-005 security note closed."""
        lowered = workspace_section.lower()
        assert "never crawl upward" in lowered, (
            "Workspace mode must state it never crawls upward (AC1 safety rail)."
        )
        assert "never follow" in lowered and "symlink" in lowered, (
            "Workspace mode must state it never follows symlinks out of the "
            "workspace (AC1 safety rail)."
        )
        assert "immediate child" in lowered or "immediate-child" in lowered, (
            "Workspace mode must enumerate immediate children only (AC1 safety "
            "rail) — no recursive descent into nested repos."
        )

    def test_should_run_per_repo_init_and_baseline_loop_sequentially(
        self, workspace_section: str
    ) -> None:
        """AC2: the run loop processes each child repo through the full
        single-repo flow (Phases 1, 1.5, 2-4), and repos are processed
        SEQUENTIALLY — one ratification session at a time, because human
        attention (the matrix walk) is the bottleneck."""
        lowered = workspace_section.lower()
        # Each repo runs the full single-repo flow including the baseline phase.
        assert "phase 1.5" in lowered or "baseline" in lowered, (
            "The per-repo loop must run the architecture-baseline phase per "
            "repo (AC2) — each repo's baseline must be complete standalone."
        )
        # Sequential processing (not parallel) — human attention is the
        # bottleneck, one ratification session at a time.
        assert "sequential" in lowered, (
            "The per-repo loop must process repos sequentially (AC2) — one "
            "ratification session at a time."
        )
        assert "one ratification session at a time" in lowered or (
            "human attention" in lowered
        ), (
            "The sequential constraint must be justified by the "
            "one-ratification-session-at-a-time / human-attention bottleneck "
            "(AC2)."
        )

    def test_should_keep_each_repo_baseline_complete_standalone(
        self, workspace_section: str
    ) -> None:
        """AC2: each repo's own baseline must remain complete standalone — a
        solo-cloned repo keeps full context (the covr solo-clone blindness is
        the failure this closes). The per-repo seam block is a regenerated
        read-only mirror, not the canonical source."""
        lowered = workspace_section.lower()
        assert "standalone" in lowered or "self-contained" in lowered, (
            "The workspace run must state each repo's baseline remains complete "
            "standalone (AC2)."
        )
        assert "mirror" in lowered, (
            "Per-repo seam blocks must be described as read-only mirrors of the "
            "canonical workspace seam map (AC2)."
        )

    def test_should_write_one_canonical_seam_map_at_workspace_path(
        self, workspace_section: str
    ) -> None:
        """AC2: exactly ONE canonical seam map lives at
        <workspace>/.etc_workspace/seam-map.yaml — the single editable source
        the per-repo mirrors derive from."""
        assert ".etc_workspace/seam-map.yaml" in workspace_section, (
            "The workspace run must name the canonical "
            "<workspace>/.etc_workspace/seam-map.yaml path (AC2)."
        )
        lowered = workspace_section.lower()
        assert "canonical" in lowered, (
            "The seam map must be described as the single canonical artifact "
            "(AC2) — there is exactly one per workspace."
        )

    def test_should_name_the_four_seam_kinds_and_owner_consumer_confidence(
        self, workspace_section: str
    ) -> None:
        """AC2: the seam map records the four seam kinds (url-routing,
        auth-session, data-schema, embed-loader), owner/consumer repos per seam,
        and a workspace-level confidence score (ADR-005 schema)."""
        for kind in (
            "url-routing",
            "auth-session",
            "data-schema",
            "embed-loader",
        ):
            assert kind in workspace_section, (
                f"The seam map must record the '{kind}' seam kind (AC2)."
            )
        lowered = workspace_section.lower()
        assert "owner" in lowered and "consumer" in lowered, (
            "Each seam must carry owner/consumer repo assignment (AC2)."
        )
        assert "confidence" in lowered, (
            "The seam map must carry a workspace-level confidence score (AC2)."
        )

    def test_should_reconcile_seams_via_pattern_a_b_owner_consumer(
        self, workspace_section: str
    ) -> None:
        """AC2: after the per-repo loop, the per-repo seam findings are MERGED
        into the canonical seam map via Pattern A/B reconciliation — owner /
        consumer assignment per seam and a workspace confidence score."""
        lowered = workspace_section.lower()
        assert "merge" in lowered or "reconcil" in lowered, (
            "The workspace run must merge/reconcile per-repo seam findings into "
            "the canonical seam map (AC2)."
        )
        # The reconciliation is human-mediated via the interactive patterns.
        assert "pattern a" in lowered or "pattern b" in lowered, (
            "Seam reconciliation (owner/consumer assignment) must route through "
            "Pattern A/B interactive input (AC2)."
        )

    def test_should_state_skill_writes_seam_map_via_write_tool_no_writer_subcommand(
        self, workspace_section: str
    ) -> None:
        """AC2: baseline.py has NO seam-map writer subcommand (wave-2 added
        sync-seams, which READS the map). So the skill writes the seam-map YAML
        via the Write tool. The skill must state this boundary explicitly: the
        seam map lives OUTSIDE any repo's .etc_sdlc, so the single-writer rule
        (which covers architecture-baseline.yaml) does NOT cover this file."""
        lowered = workspace_section.lower()
        # The skill must name the Write-tool path for the seam map.
        assert "write tool" in lowered or "write the seam-map" in lowered or (
            "writes the seam-map" in lowered
        ), (
            "The workspace run must state the skill writes the seam-map YAML via "
            "the Write tool, since baseline.py has no seam-map writer "
            "subcommand (AC2)."
        )
        # The single-writer boundary must be stated explicitly.
        assert "single-writer" in lowered or "single writer" in lowered, (
            "The workspace run must explicitly state the single-writer-rule "
            "boundary for the seam map (AC2)."
        )
        # The boundary: seam map lives OUTSIDE any repo's .etc_sdlc.
        assert "outside" in lowered and ".etc_sdlc" in workspace_section, (
            "The workspace run must state the seam map lives OUTSIDE any repo's "
            ".etc_sdlc, so the single-writer rule does not cover it (AC2)."
        )

    def test_should_regenerate_mirrors_via_baseline_py_sync_seams(
        self, workspace_section: str
    ) -> None:
        """AC2: after writing the canonical seam map, the skill runs
        `baseline.py sync-seams <workspace_root>` to regenerate every repo's
        read-only mirror. The ~/.claude/scripts/ prefix is required (Codex
        path-rewrite depends on it verbatim)."""
        assert "~/.claude/scripts/baseline.py sync-seams" in workspace_section, (
            "The workspace run must call `baseline.py sync-seams "
            "<workspace_root>` with the ~/.claude/scripts/ prefix to regenerate "
            "per-repo mirrors (AC2, Codex path-rewrite)."
        )
        lowered = workspace_section.lower()
        assert "mirror" in lowered, (
            "sync-seams must be described as regenerating the per-repo "
            "read-only mirrors (AC2)."
        )

    def test_should_order_write_then_sync_seams(
        self, workspace_section: str
    ) -> None:
        """AC2: the seam map is WRITTEN (Write tool) BEFORE sync-seams runs —
        sync-seams reads the map and regenerates mirrors, so a sync before the
        write would mirror a stale or absent map."""
        idx_write = -1
        for needle in (".etc_workspace/seam-map.yaml",):
            idx_write = workspace_section.find(needle)
            if idx_write != -1:
                break
        idx_sync = workspace_section.find("sync-seams")
        assert idx_write != -1 and idx_sync != -1
        # The canonical-path first mention should precede the sync-seams call,
        # establishing write-then-sync ordering in the prose.
        assert idx_write < idx_sync, (
            "The canonical seam-map write must be described BEFORE the "
            "sync-seams call (AC2) — sync-seams reads the map to build mirrors."
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

    @pytest.mark.skipif(
        not INSTALL_STEPS_PATH.exists(),
        reason=INSTALL_STEPS_PENDING_REASON,
    )
    def test_install_steps_py_uses_recursive_copy(self) -> None:
        """Install-steps module must not use non-recursive cp for skill
        directories.

        Ftmp-5afddbce task 006 migration: this source-level guard now
        targets ``etc_installer/install_steps.py`` (task 005) instead of
        ``install.sh``. The bug being guarded against was install.sh
        line 79's ``cp "$skill_dir"/*`` glob, which silently dropped
        subdirectories like ``templates/``. The Python rewrite invokes
        ``subprocess.run`` with rsync or ``cp -R`` (argv-list, never a
        shell string per design.md Technical Constraints).
        """
        install_steps_text = INSTALL_STEPS_PATH.read_text(encoding="utf-8")

        # The broken bash glob pattern must NOT be present in the
        # rewrite (it cannot be — the rewrite is Python — but the guard
        # is symmetric to the original install.sh contract).
        assert 'cp "$skill_dir"/*' not in install_steps_text, (
            "etc_installer/install_steps.py still references the non-"
            "recursive glob copy pattern; the rewrite must use rsync or "
            "cp -R via subprocess.run argv list."
        )
        # Some form of recursive copy must be present somewhere in the
        # module. The rewrite calls subprocess.run with either rsync or
        # cp -R / cp -r as the argv[0].
        uses_rsync = "rsync" in install_steps_text
        uses_cp_r = (
            '"cp", "-R"' in install_steps_text
            or '"cp", "-r"' in install_steps_text
            or "'cp', '-R'" in install_steps_text
            or "'cp', '-r'" in install_steps_text
        )
        assert uses_rsync or uses_cp_r, (
            "etc_installer/install_steps.py must invoke rsync or cp -R / "
            "cp -r (via subprocess.run argv list) to install skill subdirs."
        )
