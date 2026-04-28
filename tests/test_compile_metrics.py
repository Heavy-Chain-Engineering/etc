"""Compile-output regression test for the /metrics skill.

Pins AC-019 from the metrics-and-release-notes PRD:

    python3 compile-sdlc.py spec/etc_sdlc.yaml
    must produce dist/skills/metrics/SKILL.md

The skill is hand-authored at skills/metrics/SKILL.md. The DSL must
register it under the `skills:` map (with a `source:` pointer) and the
compiler's compile_skills pass must copy it through byte-for-byte. If
either link breaks, /metrics will not deploy via install.sh — even
though tests/test_metrics.py (the SKILL-content contract) keeps
passing — and the regression is invisible until a user invokes the
slash command in Claude Code.

This test exercises the compile pipeline in-process against a
pytest-managed tmp_path so it neither depends on, nor mutates, the
checked-in dist/ tree. That keeps it independent of the rest of the
test suite (notably tests/test_compiler.py, which loads the real
dist/settings-hooks.json at module scope).

Pattern mirrors tests/test_compiler.py::test_should_copy_skill_subdir_
when_templates_present — load compile-sdlc.py via importlib (the
filename is hyphenated, so a plain import does not work) and call
the relevant pass directly.
"""

from __future__ import annotations

import filecmp
import importlib.util
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPILE_SCRIPT = REPO_ROOT / "compile-sdlc.py"
SPEC_PATH = REPO_ROOT / "spec" / "etc_sdlc.yaml"
METRICS_SOURCE = REPO_ROOT / "skills" / "metrics" / "SKILL.md"


def _load_compile_sdlc_module() -> Any:
    """Load compile-sdlc.py as a module (hyphenated filename requires importlib)."""
    spec = importlib.util.spec_from_file_location("compile_sdlc", COMPILE_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_should_register_metrics_skill_in_spec() -> None:
    """spec/etc_sdlc.yaml must register the metrics skill under skills:.

    First link in the AC-019 chain. Without this entry, compile_skills
    still copies skills/metrics/ through (because it iterates the
    filesystem, not the DSL) — but the spec ceases to be the single
    source of truth for what the harness ships, and DSL-driven tooling
    (install manifests, skill catalogs, future agent prompts that
    enumerate available slash commands) silently loses sight of it.
    """
    spec = yaml.safe_load(SPEC_PATH.read_text())
    skills = spec.get("skills", {})

    assert "metrics" in skills, (
        "spec/etc_sdlc.yaml is missing the `metrics:` entry under `skills:`. "
        "AC-019 requires the /metrics skill to be registered in the DSL."
    )

    metrics_entry = skills["metrics"]
    source = metrics_entry.get("source")
    assert source == "skills/metrics/SKILL.md", (
        f"Expected skills.metrics.source == 'skills/metrics/SKILL.md', "
        f"got {source!r}"
    )


def test_should_emit_metrics_skill_to_dist_when_compile_runs(tmp_path: Path) -> None:
    """compile_skills must copy skills/metrics/SKILL.md into dist/skills/metrics/.

    Exercises the second link in the AC-019 chain: the compile pass must
    produce dist/skills/metrics/SKILL.md when run against the real
    skills/ tree. We invoke compile_skills directly (not the full main()
    entrypoint) to keep the test hermetic — the compiler's main() hard-
    codes dist_dir = repo_root/'dist', which would clobber the checked-in
    artifacts that other tests (test_compiler.py) read at module scope.
    """
    assert METRICS_SOURCE.exists(), (
        f"Test precondition failed: {METRICS_SOURCE} does not exist. "
        "The /metrics skill source is missing from the repository; "
        "AC-019 cannot hold."
    )

    tmp_dist = tmp_path / "dist"
    tmp_dist.mkdir()

    compile_sdlc = _load_compile_sdlc_module()
    compile_sdlc.compile_skills(tmp_dist, REPO_ROOT)

    compiled_metrics = tmp_dist / "skills" / "metrics" / "SKILL.md"
    assert compiled_metrics.exists(), (
        f"compile_skills did not produce {compiled_metrics}. "
        "AC-019 requires `python3 compile-sdlc.py spec/etc_sdlc.yaml` "
        "to emit dist/skills/metrics/SKILL.md."
    )

    # Byte-identical: shallow=False forces a content compare, not a stat compare.
    assert filecmp.cmp(compiled_metrics, METRICS_SOURCE, shallow=False), (
        f"Compiled {compiled_metrics} differs from source {METRICS_SOURCE}. "
        "compile_skills must pass the SKILL.md through byte-for-byte; any "
        "transformation would silently desynchronize the deployed skill from "
        "tests/test_metrics.py's content contract."
    )
