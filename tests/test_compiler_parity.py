"""Declared-vs-disk parity for the compiler (audit init 3).

spec/etc_sdlc.yaml claims to be the SINGLE SOURCE OF TRUTH, but the compiler
had four contradictory registration semantics:

  - undeclared agents were silently DROPPED;
  - undeclared skills silently SHIPPED (every skills/*/ dir is copytree'd);
  - the standards `categories:` registry was DECORATIVE (copytree wholesale);
  - several `defaults:` knobs were never read.

These tests pin the fix: the on-disk skill/agent surface must match the yaml
registry, the compiler must FAIL LOUDLY (exit 1) on any mismatch, and the
honest registry is the source of truth.

`compile-sdlc.py` is hyphenated, so it loads via importlib (the proven pattern
from tests/test_compiler_runtime_gate.py). Parity is exercised against fake
repo trees in tmp dirs — never the real dist/.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_FILE = REPO_ROOT / "spec" / "etc_sdlc.yaml"

# The 8 core skills the registry lost track of (audit init 3). On disk under
# skills/<name>/SKILL.md but absent from the yaml `skills:` block.
LOST_CORE_SKILLS: tuple[str, ...] = (
    "architect",
    "build",
    "checkpoint",
    "decompose",
    "init-project",
    "postmortem",
    "spec",
    "tasks",
)


def _load_compile_sdlc_module() -> Any:
    """Load compile-sdlc.py as a module (hyphenated filename needs importlib)."""
    module_path = REPO_ROOT / "compile-sdlc.py"
    spec = importlib.util.spec_from_file_location("compile_sdlc", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_real_spec() -> dict[str, Any]:
    """Load the real SDLC spec."""
    return yaml.safe_load(SPEC_FILE.read_text(encoding="utf-8"))


# -- Item 1: the 8 lost core skills are declared -----------------------------


class TestLostCoreSkillsDeclared:
    """The 8 core skills must be declared in the yaml `skills:` block."""

    @pytest.mark.parametrize("skill_name", LOST_CORE_SKILLS)
    def test_should_declare_core_skill_when_it_exists_on_disk(
        self, skill_name: str
    ) -> None:
        # Arrange
        spec = _load_real_spec()
        skills = spec["skills"]

        # Act / Assert — the lost skill is now in the registry.
        assert skill_name in skills, (
            f"core skill '{skill_name}' exists at skills/{skill_name}/SKILL.md "
            f"but is undeclared in spec/etc_sdlc.yaml skills: block"
        )

    @pytest.mark.parametrize("skill_name", LOST_CORE_SKILLS)
    def test_should_point_declared_skill_at_its_source_when_declared(
        self, skill_name: str
    ) -> None:
        # Arrange
        spec = _load_real_spec()
        skill_def = spec["skills"][skill_name]

        # Assert — the declaration follows the existing schema (source pointer).
        assert skill_def.get("source") == f"skills/{skill_name}/SKILL.md"


# -- Item 2: declared-vs-disk parity enforcement -----------------------------


def _make_skill_dir(repo_root: Path, name: str) -> None:
    """Create a fake skills/<name>/SKILL.md under a fake repo root."""
    skill_dir = repo_root / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# /{name}\n", encoding="utf-8")


def _make_agent_md(repo_root: Path, name: str) -> None:
    """Create a fake agents/<name>.md under a fake repo root."""
    agents_dir = repo_root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")


class TestSkillParityEnforcement:
    """An on-disk skill dir that is undeclared makes the compiler fail loud."""

    def test_should_report_violation_when_skill_dir_is_undeclared(
        self, tmp_path: Path
    ) -> None:
        # Arrange — a fake repo with a declared skill and an undeclared one.
        compile_sdlc = _load_compile_sdlc_module()
        _make_skill_dir(tmp_path, "declared-skill")
        _make_skill_dir(tmp_path, "stowaway-skill")
        spec = {
            "skills": {"declared-skill": {"source": "skills/declared-skill/SKILL.md"}},
            "agents": {},
        }

        # Act
        violations = compile_sdlc.check_disk_parity(spec, tmp_path)

        # Assert — the undeclared dir is named in a violation.
        assert any("stowaway-skill" in v for v in violations)
        assert not any("declared-skill" in v for v in violations)

    def test_should_report_no_skill_violation_when_all_dirs_declared(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        compile_sdlc = _load_compile_sdlc_module()
        _make_skill_dir(tmp_path, "declared-skill")
        spec = {
            "skills": {"declared-skill": {"source": "skills/declared-skill/SKILL.md"}},
            "agents": {},
        }

        # Act
        violations = compile_sdlc.check_disk_parity(spec, tmp_path)

        # Assert
        assert not any("declared-skill" in v for v in violations)

    def test_should_report_violation_when_declared_skill_is_absent(
        self, tmp_path: Path
    ) -> None:
        # Arrange — declared but no dir on disk.
        compile_sdlc = _load_compile_sdlc_module()
        (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
        spec = {
            "skills": {"ghost-skill": {"source": "skills/ghost-skill/SKILL.md"}},
            "agents": {},
        }

        # Act
        violations = compile_sdlc.check_disk_parity(spec, tmp_path)

        # Assert
        assert any("ghost-skill" in v for v in violations)


class TestAgentParityEnforcement:
    """Undeclared agents fail loud unless explicitly allowlisted."""

    def test_should_report_violation_when_agent_md_is_undeclared(
        self, tmp_path: Path
    ) -> None:
        # Arrange — an agent on disk neither declared nor allowlisted.
        compile_sdlc = _load_compile_sdlc_module()
        _make_agent_md(tmp_path, "rogue-agent")
        spec: dict[str, Any] = {"skills": {}, "agents": {}}

        # Act
        violations = compile_sdlc.check_disk_parity(spec, tmp_path)

        # Assert
        assert any("rogue-agent" in v for v in violations)

    def test_should_report_no_violation_when_agent_is_allowlisted(
        self, tmp_path: Path
    ) -> None:
        # Arrange — undeclared on disk but listed in unregistered_agents.
        compile_sdlc = _load_compile_sdlc_module()
        _make_agent_md(tmp_path, "pending-agent")
        spec: dict[str, Any] = {
            "skills": {},
            "agents": {},
            "unregistered_agents": {
                "pending-agent": "pending operator in-or-out decision",
            },
        }

        # Act
        violations = compile_sdlc.check_disk_parity(spec, tmp_path)

        # Assert
        assert not any("pending-agent" in v for v in violations)

    def test_should_report_no_violation_when_agent_is_declared(
        self, tmp_path: Path
    ) -> None:
        # Arrange
        compile_sdlc = _load_compile_sdlc_module()
        _make_agent_md(tmp_path, "real-agent")
        spec: dict[str, Any] = {
            "skills": {},
            "agents": {"real-agent": {"source": "agents/real-agent.md"}},
        }

        # Act
        violations = compile_sdlc.check_disk_parity(spec, tmp_path)

        # Assert
        assert not any("real-agent" in v for v in violations)

    def test_should_report_violation_when_declared_agent_is_absent(
        self, tmp_path: Path
    ) -> None:
        # Arrange — declared source points at a file that does not exist.
        compile_sdlc = _load_compile_sdlc_module()
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
        spec: dict[str, Any] = {
            "skills": {},
            "agents": {"phantom-agent": {"source": "agents/phantom-agent.md"}},
        }

        # Act
        violations = compile_sdlc.check_disk_parity(spec, tmp_path)

        # Assert
        assert any("phantom-agent" in v for v in violations)


class TestParityGateRaisesOnViolation:
    """The compile-time gate exits non-zero, naming the offenders."""

    def test_should_exit_when_parity_violations_exist(
        self, tmp_path: Path
    ) -> None:
        # Arrange — one undeclared skill dir is enough to fail the gate.
        compile_sdlc = _load_compile_sdlc_module()
        _make_skill_dir(tmp_path, "stowaway-skill")
        spec: dict[str, Any] = {"skills": {}, "agents": {}}

        # Act / Assert
        with pytest.raises(SystemExit) as exc_info:
            compile_sdlc.enforce_disk_parity(spec, tmp_path)
        assert exc_info.value.code == 1

    def test_should_not_exit_when_parity_holds(self, tmp_path: Path) -> None:
        # Arrange — empty repo, empty registry: nothing to violate.
        compile_sdlc = _load_compile_sdlc_module()
        (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
        spec: dict[str, Any] = {"skills": {}, "agents": {}}

        # Act — must not raise.
        compile_sdlc.enforce_disk_parity(spec, tmp_path)


class TestRealSpecPassesParity:
    """The real spec, post-item-1, must pass the parity gate."""

    def test_should_report_no_violations_for_the_real_spec(self) -> None:
        # Arrange
        compile_sdlc = _load_compile_sdlc_module()
        spec = _load_real_spec()

        # Act
        violations = compile_sdlc.check_disk_parity(spec, REPO_ROOT)

        # Assert — the registry is honest after item 1 + the allowlist.
        assert violations == []

    def test_should_allowlist_the_two_undeclared_agents(self) -> None:
        # Arrange — gemini-analyzer + multi-tenant-auditor exist on disk,
        # undeclared, and must be parked in the allowlist with a reason.
        spec = _load_real_spec()
        allowlist = spec.get("unregistered_agents", {})

        # Assert
        assert "gemini-analyzer" in allowlist
        assert "multi-tenant-auditor" in allowlist
        assert allowlist["gemini-analyzer"].strip() != ""
        assert allowlist["multi-tenant-auditor"].strip() != ""


def test_undeclared_skill_fails_the_real_cli(tmp_path: Path) -> None:
    """End-to-end: the parity gate must fire through the actual CLI, not just
    the function — a gate wired at the function level but not the entry point
    is exactly the built-but-never-wired failure this audit chased."""
    import shutil
    import subprocess
    import sys as _sys

    repo = tmp_path / "repo"
    (repo / "spec").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "compile-sdlc.py", repo / "compile-sdlc.py")
    shutil.copy2(REPO_ROOT / "spec" / "etc_sdlc.yaml", repo / "spec" / "etc_sdlc.yaml")
    for surface in ("hooks", "agents", "skills", "standards"):
        shutil.copytree(REPO_ROOT / surface, repo / surface)
    rogue = repo / "skills" / "rogue-undeclared"
    rogue.mkdir()
    (rogue / "SKILL.md").write_text("# rogue\n", encoding="utf-8")

    completed = subprocess.run(
        [_sys.executable, "compile-sdlc.py", "spec/etc_sdlc.yaml",
         "--output", str(tmp_path / "out")],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode != 0, (
        "an undeclared on-disk skill must fail the REAL compile CLI"
    )
    assert "rogue-undeclared" in completed.stderr
