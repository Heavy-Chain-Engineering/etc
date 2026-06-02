"""Tests for scripts/manifest_body_conformance.py (F-2026-06-01 profile-driven bodies).

Body-conformance deny-list scan — a sibling of scripts/layer_review.py. A
profile-aware manifest (one carrying the `${profiles}` marker, ADR-003) must
not name a language-specific operative tool/path in its body outside a fenced
code block, a clearly-illustrative mention, or a bindings-referenced line.

Coverage:
  - AC-5: non-conformant manifest → exit 2 + `<manifest>:<line>: <token>`;
    a conformed profile-aware manifest → exit 0.
  - Edge case 3 (no over-fire — the #54/#46 foil): a fenced mention, an
    illustrative mention, and a bindings-referenced mention all PASS.
  - AC-8 (forward-only): a legacy manifest WITHOUT the `${profiles}` marker is
    skipped (passes untouched).
  - Exit 1 on usage/IO error; argv-list interface.

The module exposes pure functions under a CLI (mirrors layer_review.py):
    - DENY_TOKENS (tuple[str, ...]) — the tunable deny-list
    - PROFILE_AWARE_MARKER (str)
    - scannable_lines(body) -> list[tuple[int, str]]
    - find_violations(manifest_text) -> list[Violation]
    - check_manifest(path) -> ConformanceResult
    - main(argv) -> int

Coverage of scripts/manifest_body_conformance.py == 100% (AC-4).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "manifest_body_conformance.py"


def _load_module() -> ModuleType:
    """Import scripts/manifest_body_conformance.py directly (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("manifest_body_conformance", MODULE_PATH)
    if spec is None or spec.loader is None:
        msg = f"Cannot load module at {MODULE_PATH}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["manifest_body_conformance"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scanner() -> ModuleType:
    """Module under test, imported once per test module."""
    return _load_module()


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the script as a subprocess (exercises the exit-code contract)."""
    return subprocess.run(
        ["python3", str(MODULE_PATH), *args],
        capture_output=True,
        text=True,
        timeout=15,
    )


# ── Fixture manifest bodies (crafted, NOT the real agents/*.md) ──────────

_PROFILE_AWARE_HEADER = """---
name: example-agent
language: ${profiles}
required_reading:
  - standards/code/clean-code.md
  - ${profile_bindings_template}
---
"""

_LEGACY_HEADER = """---
name: legacy-agent
language: python
required_reading:
  - standards/code/clean-code.md
---
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ── AC-5: deny-list detection + clean pass ───────────────────────────────


def test_should_exit_2_and_report_token_when_profile_aware_body_names_pytest(
    tmp_path: Path,
) -> None:
    body = _PROFILE_AWARE_HEADER + "\n## Cycle\n\nRun pytest to validate the change.\n"
    path = _write(tmp_path, "nonconformant.md", body)

    result = _run_cli("check", str(path))

    assert result.returncode == 2
    assert f"{path}:" in result.stdout
    assert "pytest" in result.stdout


def test_should_exit_0_when_profile_aware_body_is_clean(tmp_path: Path) -> None:
    body = (
        _PROFILE_AWARE_HEADER
        + "\n## Cycle\n\nRun the active profile's configured test command.\n"
    )
    path = _write(tmp_path, "conformant.md", body)

    result = _run_cli("check", str(path))

    assert result.returncode == 0


def test_should_report_line_number_of_the_offending_token(
    scanner: ModuleType, tmp_path: Path
) -> None:
    body = _PROFILE_AWARE_HEADER + "\nclean line\nrun mypy here\n"
    path = _write(tmp_path, "lined.md", body)

    result = scanner.check_manifest(path)

    assert result.complete is False
    assert result.violations[0].token == "mypy"
    assert result.violations[0].line == 10


# ── Edge case 3: the over-fire foil (no false positives) ─────────────────


def test_should_not_flag_token_inside_fenced_code_block(tmp_path: Path) -> None:
    body = (
        _PROFILE_AWARE_HEADER
        + "\n## Example\n\n```bash\nuv run pytest -x\n```\n"
    )
    path = _write(tmp_path, "fenced.md", body)

    result = _run_cli("check", str(path))

    assert result.returncode == 0


def test_should_not_flag_token_in_illustrative_prose(tmp_path: Path) -> None:
    body = (
        _PROFILE_AWARE_HEADER
        + "\nUse the configured test command (e.g. pytest on a Python stack).\n"
    )
    path = _write(tmp_path, "illustrative.md", body)

    result = _run_cli("check", str(path))

    assert result.returncode == 0


def test_should_not_flag_token_on_a_bindings_referenced_line(tmp_path: Path) -> None:
    body = (
        _PROFILE_AWARE_HEADER
        + "\nSee the profile bindings for the ruff invocation and pyproject layout.\n"
    )
    path = _write(tmp_path, "bindings_ref.md", body)

    result = _run_cli("check", str(path))

    assert result.returncode == 0


# ── AC-8: forward-only (no marker → skipped) ─────────────────────────────


def test_should_skip_legacy_manifest_without_profile_aware_marker(
    tmp_path: Path,
) -> None:
    body = _LEGACY_HEADER + "\n## Cycle\n\nRun pytest with uv run pytest in src/.\n"
    path = _write(tmp_path, "legacy.md", body)

    result = _run_cli("check", str(path))

    assert result.returncode == 0


# ── AC-4: usage / IO error path; argv interface ──────────────────────────


def test_should_exit_1_when_no_manifest_paths_given() -> None:
    result = _run_cli("check")

    assert result.returncode == 1


def test_should_exit_1_when_manifest_path_does_not_exist(tmp_path: Path) -> None:
    missing = tmp_path / "nope.md"

    result = _run_cli("check", str(missing))

    assert result.returncode == 1


def test_should_exit_1_when_no_subcommand_given() -> None:
    result = _run_cli()

    assert result.returncode == 1


# ── Multi-manifest argv + token-set breadth ──────────────────────────────


def test_should_exit_2_when_any_of_several_manifests_is_nonconformant(
    tmp_path: Path,
) -> None:
    clean = _write(
        tmp_path,
        "clean.md",
        _PROFILE_AWARE_HEADER + "\nRun the configured test command.\n",
    )
    dirty = _write(
        tmp_path,
        "dirty.md",
        _PROFILE_AWARE_HEADER + "\nEdit files under src/ then run pip audit.\n",
    )

    result = _run_cli("check", str(clean), str(dirty))

    assert result.returncode == 2
    assert str(dirty) in result.stdout
    assert str(clean) not in result.stdout


@pytest.mark.parametrize(
    "token_line",
    [
        "use ruff to lint",
        "decorate with @router.get",
        "run pip audit on deps",
        "edit pyproject directly",
        "place modules in src/",
        "invoke uv run pytest",
    ],
)
def test_should_flag_each_operative_language_token(
    scanner: ModuleType, tmp_path: Path, token_line: str
) -> None:
    body = _PROFILE_AWARE_HEADER + f"\n{token_line}\n"
    path = _write(tmp_path, "token.md", body)

    result = scanner.check_manifest(path)

    assert result.complete is False


def test_should_expose_deny_tokens_as_module_constant(scanner: ModuleType) -> None:
    assert isinstance(scanner.DENY_TOKENS, tuple)
    assert "pytest" in scanner.DENY_TOKENS


# ── Pure-function units (scannable_lines / find_violations) ──────────────


def test_should_drop_fenced_lines_from_scannable_lines(scanner: ModuleType) -> None:
    text = "keep one\n```bash\nuv run pytest\n```\nkeep two\n"

    kept = scanner.scannable_lines(text)

    assert [text for _, text in kept] == ["keep one", "keep two"]


def test_should_drop_illustrative_lines_from_scannable_lines(
    scanner: ModuleType,
) -> None:
    text = "operative line\nthe test command (e.g. pytest)\n"

    kept = scanner.scannable_lines(text)

    assert [text for _, text in kept] == ["operative line"]


def test_should_drop_bindings_referenced_lines_from_scannable_lines(
    scanner: ModuleType,
) -> None:
    text = "operative line\nsee the bindings for ruff\n"

    kept = scanner.scannable_lines(text)

    assert [text for _, text in kept] == ["operative line"]


def test_should_return_empty_violations_for_legacy_manifest_text(
    scanner: ModuleType, tmp_path: Path
) -> None:
    text = _LEGACY_HEADER + "\nRun pytest here.\n"

    violations = scanner.find_violations(tmp_path / "legacy.md", text)

    assert violations == []


# ── In-process main() dispatch (coverage of the CLI surface) ─────────────


def test_should_return_zero_when_main_check_clean(
    scanner: ModuleType, tmp_path: Path
) -> None:
    body = _PROFILE_AWARE_HEADER + "\nRun the configured test command.\n"
    path = _write(tmp_path, "clean.md", body)

    assert scanner.main(["check", str(path)]) == 0


def test_should_return_two_and_list_violation_when_main_check_dirty(
    scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = _PROFILE_AWARE_HEADER + "\nRun pytest now.\n"
    path = _write(tmp_path, "dirty.md", body)

    code = scanner.main(["check", str(path)])
    out = capsys.readouterr().out

    assert code == 2
    assert f"{path}:" in out
    assert "pytest" in out


def test_should_return_one_when_main_check_has_no_paths(
    scanner: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    code = scanner.main(["check"])
    err = capsys.readouterr().err

    assert code == 1
    assert "no manifest" in err.lower()


def test_should_return_one_when_main_check_path_missing(
    scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = scanner.main(["check", str(tmp_path / "missing.md")])
    err = capsys.readouterr().err

    assert code == 1
    assert "not found" in err.lower()


def test_should_return_one_when_main_check_path_is_directory(
    scanner: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a_dir = tmp_path / "a_dir"
    a_dir.mkdir()

    code = scanner.main(["check", str(a_dir)])
    err = capsys.readouterr().err

    assert code == 1
    assert "not found" in err.lower()


def test_should_raise_usage_exit_one_when_main_has_no_subcommand(
    scanner: ModuleType,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        scanner.main([])

    assert exc_info.value.code == 1


def test_should_raise_manifest_read_error_when_file_unreadable(
    scanner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, "unreadable.md", _PROFILE_AWARE_HEADER + "\nclean\n")

    def _raise(*_args: object, **_kwargs: object) -> str:
        raise OSError("boom")

    monkeypatch.setattr(Path, "read_text", _raise)

    with pytest.raises(scanner.ManifestReadError, match="cannot read"):
        scanner.check_manifest(path)


def test_should_run_as_script_module_entrypoint() -> None:
    result = subprocess.run(
        ["python3", str(MODULE_PATH)],
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 1
