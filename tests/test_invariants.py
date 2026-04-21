"""Tests for hooks/check-invariants.sh using conftest fixtures.

Validates that the invariant enforcement hook:
- Allows operations when no INVARIANTS.md exists
- Allows operations when all invariants pass (verify commands produce empty output)
- Blocks operations when invariants are violated (verify commands produce non-empty output)
- Reports the violating INV-NNN identifier in stderr
"""

from __future__ import annotations

from typing import Any

HOOK_NAME = "check-invariants.sh"
BLOCKED = 2
ALLOWED = 0


def _make_input(file_path: str, cwd: str) -> dict[str, Any]:
    """Build the JSON input dict expected by the hook."""
    return {
        "tool_input": {"file_path": file_path},
        "cwd": cwd,
    }


# -- Allow tests (no violations) -----------------------------------------------


def test_should_allow_when_no_invariants_file(
    run_hook: Any, tmp_project: Any
) -> None:
    """Hook exits 0 when no INVARIANTS.md exists in cwd."""
    # Arrange
    hook_input = _make_input(
        file_path=str(tmp_project / "src" / "app.py"),
        cwd=str(tmp_project),
    )

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == ALLOWED


def test_should_allow_when_invariants_pass(
    run_hook: Any, tmp_project: Any, invariants_file: Any
) -> None:
    """Hook exits 0 when all verify commands produce empty output."""
    # Arrange
    invariants_file([
        {
            "id": "INV-001",
            "description": "Always-passing invariant",
            "verify": "true",
        },
    ])
    hook_input = _make_input(
        file_path=str(tmp_project / "src" / "app.py"),
        cwd=str(tmp_project),
    )

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == ALLOWED


# -- Block tests (violations found) --------------------------------------------


def test_should_block_when_invariant_violated(
    run_hook: Any, tmp_project: Any, invariants_file: Any
) -> None:
    """Hook exits 2 when a verify command produces non-empty output."""
    # Arrange
    invariants_file([
        {
            "id": "INV-001",
            "description": "Invariant that always fails",
            "verify": 'echo "violation found"',
        },
    ])
    hook_input = _make_input(
        file_path=str(tmp_project / "src" / "app.py"),
        cwd=str(tmp_project),
    )

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == BLOCKED


def test_should_report_violation_id_when_blocked(
    run_hook: Any, tmp_project: Any, invariants_file: Any
) -> None:
    """When blocked, stderr contains the INV-NNN identifier of the violated invariant."""
    # Arrange
    invariants_file([
        {
            "id": "INV-042",
            "description": "Invariant that always fails",
            "verify": 'echo "found a problem"',
        },
    ])
    hook_input = _make_input(
        file_path=str(tmp_project / "src" / "app.py"),
        cwd=str(tmp_project),
    )

    # Act
    result = run_hook(HOOK_NAME, hook_input)

    # Assert
    assert result.exit_code == BLOCKED
    assert "INV-042" in result.stderr
