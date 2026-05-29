"""Regression tests for /janitor registration in the SDLC spec (Task 006).

Tasks 001-005 shipped the janitor skill (skills/janitor/SKILL.md), the
janitor fix-subagent (agents/janitor.md), and its supporting scripts and
standards. Task 006 registers the agent in spec/etc_sdlc.yaml's `agents:`
section and the skill in its `skills:` section so the compiler emits both
into dist/ and the installer ships them.

These tests compile the real spec into a hermetic tmp dist/ directory and
assert both artifacts land. They do NOT inspect the repo's committed dist/
(which may be stale) — they run the compiler fresh.

Note on the skill mechanism: compile_skills() auto-discovers every
repo_root/skills/<name>/ directory containing a SKILL.md and copies it to
dist/skills/<name>/. The DSL `skills:` declaration is metadata only; the
janitor entry was added for consistency with the other hand-authored skills,
but the SKILL.md ships regardless. test_should_ship_janitor_skill_to_dist
asserts the shipped file; test_should_declare_janitor_in_skills_block
asserts the (consistency) DSL declaration.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "spec" / "etc_sdlc.yaml"


def _load_compile_sdlc_module() -> Any:
    """Load compile-sdlc.py as a module (hyphenated filename needs importlib)."""
    module_path = REPO_ROOT / "compile-sdlc.py"
    spec = importlib.util.spec_from_file_location("compile_sdlc", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_spec() -> dict[str, Any]:
    """Parse the committed spec/etc_sdlc.yaml."""
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def test_should_register_janitor_agent_in_spec() -> None:
    """spec/etc_sdlc.yaml must register the janitor agent with the standard
    `source: agents/janitor.md` shape used by every other agent entry."""
    spec = _load_spec()
    agents = spec.get("agents", {})

    assert "janitor" in agents, (
        "janitor agent missing from spec/etc_sdlc.yaml `agents:` section"
    )
    assert agents["janitor"].get("source") == "agents/janitor.md", (
        "janitor agent entry must point at agents/janitor.md via `source:`, "
        f"matching the existing agent shape. Got: {agents['janitor'].get('source')!r}"
    )


def test_should_declare_janitor_in_skills_block() -> None:
    """spec/etc_sdlc.yaml `skills:` block declares janitor for consistency with
    the other hand-authored skills (source: skills/janitor/SKILL.md)."""
    spec = _load_spec()
    skills = spec.get("skills", {})

    assert "janitor" in skills, (
        "janitor skill missing from spec/etc_sdlc.yaml `skills:` section"
    )
    assert skills["janitor"].get("source") == "skills/janitor/SKILL.md", (
        "janitor skill entry must point at skills/janitor/SKILL.md via "
        f"`source:`. Got: {skills['janitor'].get('source')!r}"
    )


def test_should_ship_janitor_agent_to_dist(tmp_path: Path) -> None:
    """Compiling the real spec must emit dist/agents/janitor.md.

    Hermetic: compiles into a tmp dist dir (not the repo's committed dist/).
    """
    compile_sdlc = _load_compile_sdlc_module()
    spec = _load_spec()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    compile_sdlc.compile_agents(spec, dist_dir, REPO_ROOT)

    janitor_agent = dist_dir / "agents" / "janitor.md"
    assert janitor_agent.exists(), (
        f"janitor agent not compiled to {janitor_agent}. The compiler copies "
        "agents[*].source files into dist/agents/ — check the `agents:` entry."
    )
    assert janitor_agent.stat().st_size > 0, "janitor.md compiled but is empty"


def test_should_ship_janitor_skill_to_dist(tmp_path: Path) -> None:
    """Compiling the real spec must emit dist/skills/janitor/SKILL.md.

    The skill is auto-discovered from repo_root/skills/ by compile_skills()
    regardless of the DSL declaration; this asserts the shipped artifact.
    Hermetic: compiles into a tmp dist dir.
    """
    compile_sdlc = _load_compile_sdlc_module()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    compile_sdlc.compile_skills(dist_dir, REPO_ROOT)

    janitor_skill = dist_dir / "skills" / "janitor" / "SKILL.md"
    assert janitor_skill.exists(), (
        f"janitor skill not compiled to {janitor_skill}. compile_skills() "
        "auto-copies every skills/<name>/ dir containing a SKILL.md."
    )
    assert janitor_skill.stat().st_size > 0, "janitor SKILL.md compiled but is empty"


def test_should_ship_both_janitor_artifacts_together(tmp_path: Path) -> None:
    """End-to-end: a single compile pass emits BOTH the janitor agent and the
    janitor skill into dist/ (Task 006 acceptance criterion 2)."""
    compile_sdlc = _load_compile_sdlc_module()
    spec = _load_spec()
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    compile_sdlc.compile_agents(spec, dist_dir, REPO_ROOT)
    compile_sdlc.compile_skills(dist_dir, REPO_ROOT)

    assert (dist_dir / "agents" / "janitor.md").exists(), "agents/janitor.md missing"
    assert (dist_dir / "skills" / "janitor" / "SKILL.md").exists(), (
        "skills/janitor/SKILL.md missing"
    )
