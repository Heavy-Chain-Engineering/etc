"""Tests for check-phase-gate.sh hook.

Validates that the phase-aware file gating hook blocks edits to files
inappropriate for the current SDLC phase and allows edits to files
that are appropriate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


HOOK_NAME = "check-phase-gate.sh"


def _create_state(tmp_project: Path, phase: str) -> None:
    """Write a .sdlc/state.json with the given phase into tmp_project."""
    sdlc_dir = tmp_project / ".sdlc"
    sdlc_dir.mkdir(exist_ok=True)
    state = {"current_phase": phase}
    (sdlc_dir / "state.json").write_text(json.dumps(state))


def test_should_block_when_spec_phase_and_src_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing src/app.py during spec phase must be blocked."""
    _create_state(tmp_project, "Spec")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 2


def test_should_block_when_build_phase_and_spec_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing spec/prd.md during build phase must be blocked."""
    _create_state(tmp_project, "Build")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "spec" / "prd.md")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 2


def test_should_allow_when_build_phase_and_src_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing src/app.py during build phase must be allowed."""
    _create_state(tmp_project, "Build")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 0


def test_should_allow_when_no_state_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """When .sdlc/state.json does not exist, all edits are allowed."""
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 0


def test_should_block_when_bootstrap_and_src_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing src/ during bootstrap phase must be blocked."""
    _create_state(tmp_project, "Bootstrap")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "main.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 2


def test_should_allow_when_spec_phase_and_spec_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing spec/prd.md during spec phase must be allowed."""
    _create_state(tmp_project, "Spec")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "spec" / "prd.md")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 0


def test_should_allow_when_design_phase_and_docs_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing docs/design.md during design phase must be allowed."""
    _create_state(tmp_project, "Design")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "docs" / "design.md")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 0


def test_should_block_when_evaluate_phase_and_src_file(
    run_hook: Any, tmp_project: Path
) -> None:
    """Editing src/ during evaluate phase must be blocked."""
    _create_state(tmp_project, "Evaluate")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 2


def test_should_include_phase_name_in_error(
    run_hook: Any, tmp_project: Path
) -> None:
    """Error message must include the current phase name."""
    _create_state(tmp_project, "Spec")
    result = run_hook(
        HOOK_NAME,
        {
            "tool_input": {"file_path": str(tmp_project / "src" / "app.py")},
            "cwd": str(tmp_project),
        },
    )
    assert result.exit_code == 2
    assert "Spec" in result.stderr
