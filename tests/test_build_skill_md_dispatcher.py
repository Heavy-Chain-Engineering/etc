"""Contract tests for skills/build/SKILL.md test-invocation discipline.

The /build skill must drive wave verification and the Definition of Done
through the F020 profile-aware dispatcher (hooks/verify-green.sh), NOT a
hardcoded ``python3 -m pytest`` invocation. On a non-Python project pytest
exits 5 (no tests collected) = non-zero, which Step 6c reads as a failing
wave and halts /build before the language profile ever runs.

Grep-based, consistent with the other *_md_* contract tests in the suite.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_SKILL_PATH = REPO_ROOT / "skills" / "build" / "SKILL.md"


def _read_build_skill() -> str:
    assert BUILD_SKILL_PATH.exists(), f"Build skill not found: {BUILD_SKILL_PATH}"
    return BUILD_SKILL_PATH.read_text(encoding="utf-8")


def test_should_have_zero_hardcoded_pytest_invocations() -> None:
    """No literal ``python3 -m pytest`` may remain in the build skill.

    Regression: legacy prose predating the F020 dispatcher broke /build on
    every non-Python language profile (pytest exit 5 read as a failed wave).
    """
    # Arrange
    content = _read_build_skill()

    # Act
    occurrences = content.count("python3 -m pytest")

    # Assert
    assert occurrences == 0, (
        f"skills/build/SKILL.md still has {occurrences} hardcoded "
        f"'python3 -m pytest' invocation(s); use the F020 dispatcher "
        f"(printf ... | bash hooks/verify-green.sh) instead."
    )


def test_should_invoke_dispatcher_at_wave_verify_and_dod() -> None:
    """The profile-aware dispatcher must appear at >= 2 locations.

    One at the original ~1265 quality-gate sub-block (untouched), plus the
    wave-verify (~1251) and DoD (~2047) sites that replaced the pytest
    literals — so at least three invocations total.
    """
    # Arrange
    content = _read_build_skill()

    # Act
    dispatcher_count = content.count("bash hooks/verify-green.sh")

    # Assert
    assert dispatcher_count >= 3, (
        f"Expected the F020 dispatcher (bash hooks/verify-green.sh) at the "
        f"wave-verify, DoD, and quality-gate locations; found "
        f"{dispatcher_count} invocation(s)."
    )
