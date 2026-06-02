"""Tests for scripts/resolve_agent_profile.py — the manifest placeholder resolver.

Covers the design API contract:
    resolve_agent_profile.py resolve [--lock PATH] [--format json|text]
    -> {active_profiles: [str], bindings: [path], toolchain_summary: str}
    exit 0 ALWAYS on a completed read.

The resolver is read-only over profiles.lock and reuses
profile_loader.active_profiles() — it returns binding PATHS, never opens or
executes their contents. Tests write a temp profiles.lock via --lock so the
repo's real .etc_sdlc/profiles.lock is never touched.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RESOLVER_SCRIPT = REPO_ROOT / "scripts" / "resolve_agent_profile.py"
PLACEHOLDER = "${profile_bindings_template}"
TS_TOOLCHAIN_TOKENS = ("jest", "vitest", "eslint", "tsc")


def _load_module() -> ModuleType:
    """Import scripts/resolve_agent_profile.py directly (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "resolve_agent_profile", RESOLVER_SCRIPT
    )
    if spec is None or spec.loader is None:
        msg = f"Cannot load module at {RESOLVER_SCRIPT}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["resolve_agent_profile"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def resolver() -> ModuleType:
    """Module under test, imported once per test module."""
    return _load_module()


def _write_lock(tmp_path: Path, profiles: list[str]) -> Path:
    lock = tmp_path / "profiles.lock"
    lock.write_text("\n".join(profiles) + ("\n" if profiles else ""), encoding="utf-8")
    return lock


# ── resolve() public API ─────────────────────────────────────────────────


def test_should_return_typescript_bindings_paths_when_typescript_active(
    resolver: ModuleType,
    tmp_path: Path,
) -> None:
    lock = _write_lock(tmp_path, ["typescript"])

    result = resolver.resolve(lock_path=lock)

    assert result.active_profiles == ["typescript"]
    assert result.bindings, "expected at least one binding path"
    for binding in result.bindings:
        assert binding.startswith("standards/code/profiles/typescript/")
        assert binding.endswith("-bindings.md")


def test_should_not_leak_literal_placeholder_when_typescript_active(
    resolver: ModuleType,
    tmp_path: Path,
) -> None:
    lock = _write_lock(tmp_path, ["typescript"])

    result = resolver.resolve(lock_path=lock)

    assert PLACEHOLDER not in result.toolchain_summary
    assert all(PLACEHOLDER not in b for b in result.bindings)


def test_should_name_ts_toolchain_in_a_bindings_file_when_typescript_active(
    resolver: ModuleType,
    tmp_path: Path,
) -> None:
    """AC-1 / AC-6 mechanism: the active profile's toolchain reaches the agent.

    The resolver returns PATHS only; this test (not the resolver) reads one
    binding file to prove a TS tool (jest/vitest/eslint/tsc) is named there.
    """
    lock = _write_lock(tmp_path, ["typescript"])

    result = resolver.resolve(lock_path=lock)

    corpus = "\n".join(
        Path(binding).read_text(encoding="utf-8").lower()
        for binding in result.bindings
    )
    assert any(token in corpus for token in TS_TOOLCHAIN_TOKENS)


def test_should_summarize_toolchain_from_profile_source_when_typescript_active(
    resolver: ModuleType,
    tmp_path: Path,
) -> None:
    lock = _write_lock(tmp_path, ["typescript"])

    result = resolver.resolve(lock_path=lock)

    assert "typescript" in result.toolchain_summary.lower()


def test_should_return_empty_top_level_form_when_lock_absent(
    resolver: ModuleType,
    tmp_path: Path,
) -> None:
    """AC-2 / edge case 1: absent lock -> empty profiles + note, no crash."""
    missing = tmp_path / "does-not-exist.lock"

    result = resolver.resolve(lock_path=missing)

    assert result.active_profiles == []
    assert result.bindings == []
    assert "no active profile" in result.toolchain_summary.lower()
    assert PLACEHOLDER not in result.toolchain_summary


def test_should_return_empty_top_level_form_when_lock_empty(
    resolver: ModuleType,
    tmp_path: Path,
) -> None:
    """AC-2 / edge case 1: empty lock -> empty profiles + note, no crash."""
    lock = _write_lock(tmp_path, [])

    result = resolver.resolve(lock_path=lock)

    assert result.active_profiles == []
    assert result.bindings == []
    assert "no active profile" in result.toolchain_summary.lower()


def test_should_return_union_of_bindings_when_multiple_profiles_active(
    resolver: ModuleType,
    tmp_path: Path,
) -> None:
    """Edge case 2 (polyglot): union of every active profile's bindings."""
    lock = _write_lock(tmp_path, ["python", "typescript"])

    result = resolver.resolve(lock_path=lock)

    assert result.active_profiles == ["python", "typescript"]
    assert any(b.startswith("standards/code/profiles/python/") for b in result.bindings)
    assert any(
        b.startswith("standards/code/profiles/typescript/") for b in result.bindings
    )


def test_should_omit_bindings_for_profile_without_a_profile_dir(
    resolver: ModuleType,
    tmp_path: Path,
) -> None:
    """A lock naming a profile with no shipped dir contributes no paths."""
    lock = _write_lock(tmp_path, ["nonexistent-stack"])

    result = resolver.resolve(lock_path=lock)

    assert result.active_profiles == ["nonexistent-stack"]
    assert result.bindings == []


# ── toolchain descriptor edge cases (harness-anchored detection read) ──────


def test_should_fall_back_to_bare_profile_name_when_detection_absent(
    resolver: ModuleType,
    tmp_path: Path,
) -> None:
    lock = _write_lock(tmp_path, ["nonexistent-stack"])

    result = resolver.resolve(lock_path=lock)

    assert result.toolchain_summary == "nonexistent-stack"


def test_should_fall_back_to_bare_name_when_detection_markers_malformed(
    resolver: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """detection.yaml present but markers not a list -> bare name, no crash."""
    fake_profiles = tmp_path / "profiles"
    profile_dir = fake_profiles / "weird"
    profile_dir.mkdir(parents=True)
    (profile_dir / "detection.yaml").write_text(
        "profile: weird\nmarkers: not-a-list\n", encoding="utf-8"
    )
    monkeypatch.setattr(resolver, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(resolver, "PROFILES_DIR", Path("profiles"))
    lock = _write_lock(tmp_path, ["weird"])

    result = resolver.resolve(lock_path=lock)

    assert result.toolchain_summary == "weird"


def test_should_fall_back_to_bare_name_when_detection_yaml_malformed(
    resolver: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """detection.yaml is unparseable YAML -> bare name, no crash."""
    fake_profiles = tmp_path / "profiles"
    profile_dir = fake_profiles / "broken"
    profile_dir.mkdir(parents=True)
    (profile_dir / "detection.yaml").write_text(
        "profile: broken\nmarkers: [unterminated\n", encoding="utf-8"
    )
    monkeypatch.setattr(resolver, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(resolver, "PROFILES_DIR", Path("profiles"))
    lock = _write_lock(tmp_path, ["broken"])

    result = resolver.resolve(lock_path=lock)

    assert result.toolchain_summary == "broken"


# ── CLI (json + text) ─────────────────────────────────────────────────────


def test_should_emit_json_with_contract_keys_when_format_json(
    resolver: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lock = _write_lock(tmp_path, ["typescript"])

    exit_code = resolver.main(["resolve", "--lock", str(lock), "--format", "json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"active_profiles", "bindings", "toolchain_summary"}
    assert payload["active_profiles"] == ["typescript"]


def test_should_default_to_json_when_format_omitted(
    resolver: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lock = _write_lock(tmp_path, ["typescript"])

    exit_code = resolver.main(["resolve", "--lock", str(lock)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_profiles"] == ["typescript"]


def test_should_emit_human_readable_text_when_format_text(
    resolver: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lock = _write_lock(tmp_path, ["typescript"])

    exit_code = resolver.main(["resolve", "--lock", str(lock), "--format", "text"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "typescript" in out
    assert "standards/code/profiles/typescript/" in out
    assert PLACEHOLDER not in out


def test_should_render_text_none_marker_when_active_profile_has_no_bindings(
    resolver: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Active profile but no shipped bindings dir -> text shows the none marker."""
    lock = _write_lock(tmp_path, ["nonexistent-stack"])

    exit_code = resolver.main(["resolve", "--lock", str(lock), "--format", "text"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "nonexistent-stack" in out
    assert "(none" in out


def test_should_exit_zero_via_cli_when_lock_absent(
    resolver: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "nope.lock"

    exit_code = resolver.main(["resolve", "--lock", str(missing), "--format", "json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["active_profiles"] == []
    assert payload["bindings"] == []


def test_should_default_to_repo_lock_when_lock_flag_omitted(
    resolver: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No --lock falls back to profile_loader's DEFAULT_LOCK_PATH; exits 0."""
    exit_code = resolver.main(["resolve", "--format", "json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"active_profiles", "bindings", "toolchain_summary"}


def test_should_resolve_when_invoked_as_a_standalone_script(
    tmp_path: Path,
) -> None:
    """Design contract: agents call `python3 .../resolve_agent_profile.py`.

    Run from an unrelated cwd with no PYTHONPATH so the in-file path bootstrap
    (not pytest's pythonpath) is what makes `import scripts.profile_loader`
    resolve. Proves the real agent-invocation path works.
    """
    lock = _write_lock(tmp_path, ["typescript"])

    completed = subprocess.run(
        [sys.executable, str(RESOLVER_SCRIPT), "resolve", "--lock", str(lock)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["active_profiles"] == ["typescript"]
    assert PLACEHOLDER not in completed.stdout
    # Bindings paths are harness-anchored, not cwd-anchored: invoking from an
    # unrelated cwd must still yield the real profile dir paths.
    assert payload["bindings"] == [
        "standards/code/profiles/typescript/clean-code-bindings.md",
        "standards/code/profiles/typescript/error-handling-bindings.md",
        "standards/code/profiles/typescript/import-discipline-bindings.md",
    ]
    # The toolchain summary is also harness-anchored: detection.yaml markers
    # resolve relative to the harness root, not the caller's cwd.
    assert "package.json" in payload["toolchain_summary"]


def test_should_run_as_module_entrypoint() -> None:
    """The __main__ guard is exercised so the module is fully covered."""
    import runpy

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("scripts.resolve_agent_profile", run_name="__main__")
    assert excinfo.value.code == 2  # argparse: missing required subcommand
