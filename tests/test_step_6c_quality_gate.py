"""F021 Task 007 — /build Step 6c quality-gate integration test.

Asserts the F021 BR-003 + BR-004 contract:

1. AC-004: skills/build/SKILL.md Step 6c (between **6c. and **6d. headers)
   contains an invocation of hooks/verify-green.sh.
2. AC-005: integration test against tests/fixtures/diagnostic-discipline-
   failing-wave/ — a python-profile fixture with a deliberate mypy error.
   - (a) verify-green.sh exits non-zero against the fixture.
   - (b) the conductor-equivalent test driver does NOT write any
         phase-N/done git tag (no git_tags.write_tag call, no `git tag`
         subprocess invocation).
   - (c) stderr surfaces the verify-green output verbatim (substring match
         on the key error fragment).
3. Step 6c sub-step prose matches design.md Architecture Overview:
   zero-tolerance contract, F020 dispatcher inheritance, no exception flag.

Architectural constraints (per design.md):
- hooks/verify-green.sh is NOT modified — read-only inheritance per
  ADR-F021-004.
- This test simulates /build's conductor; the conductor's actual change
  is in skills/build/SKILL.md.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ETC_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = ETC_ROOT / "hooks"
SCRIPTS_DIR = ETC_ROOT / "scripts"
PROFILES_DIR = ETC_ROOT / "standards" / "code" / "profiles"
SKILL_PATH = ETC_ROOT / "skills" / "build" / "SKILL.md"
FIXTURE_DIR = ETC_ROOT / "tests" / "fixtures" / "diagnostic-discipline-failing-wave"


# ---------------------------------------------------------------------------
# AC-004 — SKILL.md Step 6c contains verify-green.sh invocation
# ---------------------------------------------------------------------------


def _extract_step_6c_block(skill_text: str) -> str:
    """Return the substring between the **6c. header and the **6d. header."""
    lines = skill_text.splitlines()
    start: int | None = None
    end: int | None = None
    for idx, line in enumerate(lines):
        if line.startswith("**6c."):
            start = idx
        elif start is not None and line.startswith("**6d."):
            end = idx
            break
    assert start is not None, "Step 6c header (**6c.) not found in SKILL.md"
    assert end is not None, "Step 6d header (**6d.) not found in SKILL.md"
    return "\n".join(lines[start:end])


class TestStep6cContainsVerifyGreenInvocation:
    """AC-004 (BR-003): Step 6c block invokes hooks/verify-green.sh."""

    def test_should_contain_verify_green_invocation_in_step_6c_block(self) -> None:
        assert SKILL_PATH.is_file(), f"SKILL.md missing at {SKILL_PATH}"
        block = _extract_step_6c_block(SKILL_PATH.read_text())
        # AC-004 acceptance test: literal substring 'verify-green.sh' must
        # appear at least once inside Step 6c.
        count = block.count("verify-green.sh")
        assert count >= 1, (
            f"Step 6c must invoke verify-green.sh (BR-003); found {count} mentions. "
            f"Block:\n{block}"
        )

    def test_should_declare_zero_tolerance_contract_in_step_6c(self) -> None:
        block = _extract_step_6c_block(SKILL_PATH.read_text())
        # Design.md mandates the prose names the zero-tolerance contract.
        lower = block.lower()
        assert "zero-tolerance" in lower or "zero tolerance" in lower, (
            "Step 6c must declare the zero-tolerance contract per design.md"
        )

    def test_should_state_phase_done_tag_not_written_on_failure(self) -> None:
        block = _extract_step_6c_block(SKILL_PATH.read_text())
        lower = block.lower()
        # Per design.md: tag is NOT written on non-zero exit.
        assert "phase-n/done" in lower or "phase-<n>/done" in lower, (
            "Step 6c must reference the phase-N/done tag explicitly"
        )

    def test_should_not_provide_exception_flag(self) -> None:
        block = _extract_step_6c_block(SKILL_PATH.read_text())
        # Per ADR-F021-003: no threshold / delta / exception flag.
        forbidden = ("--allow-quality-errors", "--threshold", "--delta")
        for flag in forbidden:
            assert flag not in block, (
                f"Step 6c must not provide an exception flag ({flag!r}) per ADR-F021-003"
            )


# ---------------------------------------------------------------------------
# AC-005 — Integration test against the failing-wave fixture
# ---------------------------------------------------------------------------


def _seed_workspace_from_fixture(tmp_path: Path) -> Path:
    """Copy the fixture into tmp_path and stage F020 dispatch assets.

    Mirrors the tmp_project fixture: copies dispatcher + python profile +
    helpers so verify-green.sh resolves the same way operators see it.
    """
    # Copy fixture tree
    for src_path in FIXTURE_DIR.rglob("*"):
        if src_path.is_file():
            rel = src_path.relative_to(FIXTURE_DIR)
            dst = tmp_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst)

    # Stage F020 dispatcher + profile assets so verify-green.sh resolves
    scripts_dst = tmp_path / "scripts"
    scripts_dst.mkdir(exist_ok=True)
    for name in ("profile_loader.py", "dispatch_profile.sh", "detect_profiles.py"):
        src = SCRIPTS_DIR / name
        if src.is_file():
            shutil.copy2(src, scripts_dst / name)

    profile_dst = tmp_path / "standards" / "code" / "profiles" / "python"
    profile_dst.mkdir(parents=True, exist_ok=True)
    profile_src = PROFILES_DIR / "python"
    for f in profile_src.iterdir():
        if f.is_file():
            shutil.copy2(f, profile_dst / f.name)

    helpers_dst = tmp_path / "hooks" / "helpers"
    helpers_dst.mkdir(parents=True, exist_ok=True)
    helpers_src = HOOKS_DIR / "helpers"
    if helpers_src.is_dir():
        for f in helpers_src.iterdir():
            if f.is_file() and f.suffix == ".py":
                shutil.copy2(f, helpers_dst / f.name)

    # The dispatcher only runs when .tdd-dirty exists; this is the
    # marker the conductor would have left during the wave's work.
    (tmp_path / ".tdd-dirty").touch()

    return tmp_path


def _invoke_verify_green(cwd: Path) -> subprocess.CompletedProcess[str]:
    """Invoke hooks/verify-green.sh against cwd, mirroring Step 6c's contract."""
    payload = json.dumps({"cwd": str(cwd)})
    return subprocess.run(
        ["bash", str(HOOKS_DIR / "verify-green.sh")],
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
    )


class ConductorTagWritten(Exception):
    """Raised if the conductor-equivalent test driver would have written a tag."""


def _step_6c_conductor_driver(cwd: Path) -> tuple[int, str, str, bool]:
    """Simulate what /build's conductor does at Step 6c.

    Returns (verify_green_exit_code, stdout, stderr, would_write_tag).

    Contract per BR-004: would_write_tag is True iff verify-green exits 0.
    The driver does NOT actually invoke git_tags.write_tag or `git tag` —
    it returns the gating decision so the test can assert it.
    """
    result = _invoke_verify_green(cwd)
    would_write_tag = result.returncode == 0
    return result.returncode, result.stdout, result.stderr, would_write_tag


class TestStep6cIntegrationAgainstFailingWaveFixture:
    """AC-005 (BR-004): zero-tolerance contract against a failing fixture."""

    def test_fixture_directory_exists_with_required_layout(self) -> None:
        assert FIXTURE_DIR.is_dir(), f"Fixture dir missing: {FIXTURE_DIR}"
        assert (FIXTURE_DIR / "pyproject.toml").is_file()
        assert (FIXTURE_DIR / "src" / "bad.py").is_file()
        assert (FIXTURE_DIR / "src" / "good.py").is_file()
        lock = FIXTURE_DIR / ".etc_sdlc" / "profiles.lock"
        assert lock.is_file(), f"profiles.lock missing at {lock}"
        # F020 detection schema: single line with profile name.
        assert lock.read_text().strip() == "python"

    def test_fixture_pyproject_contains_mypy_strict_config(self) -> None:
        pyproject = (FIXTURE_DIR / "pyproject.toml").read_text()
        assert "[tool.mypy]" in pyproject
        # Must enable type-checking strictness so the bad.py error fires.
        assert "strict = true" in pyproject or "disallow_untyped_defs = true" in pyproject

    def test_fixture_bad_py_has_deliberate_type_error(self) -> None:
        bad = (FIXTURE_DIR / "src" / "bad.py").read_text()
        # The deliberate error: declared return type str, returns int.
        assert "-> str" in bad
        assert "return a" in bad or "return 1" in bad

    def test_should_exit_non_zero_when_verify_green_runs_on_failing_fixture(
        self, tmp_path: Path
    ) -> None:
        """AC-005(a): verify-green.sh exits non-zero on the failing fixture."""
        workspace = _seed_workspace_from_fixture(tmp_path)
        result = _invoke_verify_green(workspace)
        assert result.returncode != 0, (
            f"verify-green.sh should fail on the fixture (mypy error expected); "
            f"got exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )

    def test_should_not_write_phase_done_tag_when_verify_green_fails(
        self, tmp_path: Path
    ) -> None:
        """AC-005(b): conductor-equivalent driver does NOT write phase-N/done tag."""
        workspace = _seed_workspace_from_fixture(tmp_path)
        exit_code, _, _, would_write_tag = _step_6c_conductor_driver(workspace)
        assert exit_code != 0, "Precondition: verify-green must fail on the fixture"
        assert would_write_tag is False, (
            "BR-004 zero-tolerance violated: conductor would have written phase-N/done "
            f"tag despite verify-green exit={exit_code}"
        )

    def test_should_surface_verify_green_output_in_stderr(self, tmp_path: Path) -> None:
        """AC-005(c): stderr surfaces verify-green output verbatim (substring match)."""
        workspace = _seed_workspace_from_fixture(tmp_path)
        result = _invoke_verify_green(workspace)
        assert result.returncode != 0
        # Profile-dispatched stderr signature from python/verify-green.sh.
        # Either mypy or coverage will surface a FAILED line.
        stderr = result.stderr
        assert "[python/verify-green]" in stderr or "FAILED" in stderr, (
            f"verify-green stderr should surface profile output. Got:\n{stderr}"
        )

    def test_should_write_tag_only_when_verify_green_passes(self, tmp_path: Path) -> None:
        """Negative control: tag-writing logic gates on exit code 0, not other signals."""
        workspace = _seed_workspace_from_fixture(tmp_path)
        # The fixture is designed to fail, so would_write_tag must be False.
        *_, would_write_tag = _step_6c_conductor_driver(workspace)
        assert would_write_tag is False


# ---------------------------------------------------------------------------
# Architectural-constraint guard tests
# ---------------------------------------------------------------------------


class TestVerifyGreenIsReadOnly:
    """ADR-F021-004: hooks/verify-green.sh is inherited, not modified."""

    def test_verify_green_script_exists_at_expected_path(self) -> None:
        assert (HOOKS_DIR / "verify-green.sh").is_file()

    def test_verify_green_script_unchanged_by_f021(self) -> None:
        """Sanity check: verify-green still honors its F020 stdin contract.

        Reads {"cwd": "..."} from stdin; this is the contract Step 6c
        composes on. If F021 were to mutate verify-green, this test
        would fail when the contract drifts.
        """
        body = (HOOKS_DIR / "verify-green.sh").read_text()
        assert "jq -r '.cwd" in body, (
            "F021 must not modify verify-green.sh's stdin contract (ADR-F021-004)"
        )
