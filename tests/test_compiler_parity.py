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
