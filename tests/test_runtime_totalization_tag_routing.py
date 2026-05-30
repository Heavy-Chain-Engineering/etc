"""Tests for terminal tag routing in scripts/runtime_totalization_check.py.

Task 005.002 wires classification -> exit code + terminal tag onto the
TotalizationResult that 005.001's core produces. The routing contract
(carried for task 006 via state.yaml.build.runtime_verification.terminal_tag):

  - all_verified / exempt / schema_skipped / ungated / empty
        -> exit 0, terminal_tag stays null (Step 7c writes the clean release tag)
  - deferred_present
        -> exit 0, milestone/<NNN> written + terminal_tag set (Step 7c SKIPS the
           clean release; the milestone is already the terminal tag)
  - live_failure
        -> exit 2 (hard block), no tag written

The tests drive each classification by monkeypatching the same single
dispatcher seam (``invoke_dispatcher``) that 005.001's tests use, and verify
real tag writes against a disposable git repo.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

_SCRIPT = Path(__file__).parent.parent / "scripts" / "runtime_totalization_check.py"
_SPEC = importlib.util.spec_from_file_location("runtime_totalization_check", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
rtc = importlib.util.module_from_spec(_SPEC)
sys.modules["runtime_totalization_check"] = rtc
_SPEC.loader.exec_module(rtc)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _init_repo_with_commit(repo: Path) -> None:
    """Initialize a disposable git repo with one commit so HEAD exists."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("test\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "initial")


def _list_tags(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "tag", "--list"], cwd=str(repo), capture_output=True, text=True, check=True
    )
    return [line for line in result.stdout.splitlines() if line]


def _write_state(feature_dir: Path, state: dict[str, Any]) -> None:
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "state.yaml").write_text(
        yaml.safe_dump(state, sort_keys=False), encoding="utf-8"
    )


def _read_state(feature_dir: Path) -> dict[str, Any]:
    with (feature_dir / "state.yaml").open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _liveness_state(live_at: str = "wave-2") -> dict[str, Any]:
    return {
        "spec_phase": {
            "contract_completeness": {
                "schema_version": 1,
                "liveness": [
                    {
                        "ac_id": "AC-3",
                        "outcome": "saving persists and survives reload",
                        "live_at": live_at,
                        "acceptance_statement": "on save a network call persists X",
                        "deferred_reason": None,
                    },
                ],
            },
        },
    }


def _feature_dir_in_repo(repo: Path, feature_id: str) -> Path:
    """A feature dir nested inside the git repo so repo_root_from resolves it."""
    feature_dir = repo / ".etc_sdlc" / "features" / "active" / feature_id
    feature_dir.mkdir(parents=True, exist_ok=True)
    return feature_dir


def test_should_exit_zero_with_null_terminal_tag_when_all_verified(
    tmp_path: Path, monkeypatch: Any
) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_commit(repo)
    feature_dir = _feature_dir_in_repo(repo, "F-2026-05-30-x")
    _write_state(feature_dir, _liveness_state(live_at="wave-2"))
    monkeypatch.setattr(
        rtc,
        "invoke_dispatcher",
        lambda *a, **k: {
            "results": [{"ac_id": "AC-3", "status": "pass", "evidence": "PASSED"}]
        },
    )

    exit_code = rtc.main(["runtime_totalization_check.py", str(feature_dir)])

    assert exit_code == 0
    assert _read_state(feature_dir)["build"]["runtime_verification"]["terminal_tag"] is None
    assert _list_tags(repo) == []


def test_should_write_milestone_001_and_set_terminal_tag_when_deferred_present(
    tmp_path: Path, monkeypatch: Any
) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_commit(repo)
    feature_dir = _feature_dir_in_repo(repo, "F-2026-05-30-x")
    state = _liveness_state(live_at="deferred")
    entry = state["spec_phase"]["contract_completeness"]["liveness"][0]
    entry["deferred_reason"] = "auth provider not yet provisioned"
    _write_state(feature_dir, state)
    monkeypatch.setattr(rtc, "invoke_dispatcher", lambda *a, **k: {"results": []})

    exit_code = rtc.main(["runtime_totalization_check.py", str(feature_dir)])

    assert exit_code == 0
    expected_tag = "etc/feature/F-2026-05-30-x/milestone/001"
    assert expected_tag in _list_tags(repo)
    block = _read_state(feature_dir)["build"]["runtime_verification"]
    assert block["terminal_tag"] == expected_tag


def test_should_increment_milestone_sequence_on_second_deferred_run(
    tmp_path: Path, monkeypatch: Any
) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_commit(repo)
    feature_dir = _feature_dir_in_repo(repo, "F-2026-05-30-x")
    state = _liveness_state(live_at="deferred")
    entry = state["spec_phase"]["contract_completeness"]["liveness"][0]
    entry["deferred_reason"] = "auth provider not yet provisioned"
    _write_state(feature_dir, state)
    monkeypatch.setattr(rtc, "invoke_dispatcher", lambda *a, **k: {"results": []})

    rtc.main(["runtime_totalization_check.py", str(feature_dir)])
    exit_code = rtc.main(["runtime_totalization_check.py", str(feature_dir)])

    assert exit_code == 0
    tags = _list_tags(repo)
    assert "etc/feature/F-2026-05-30-x/milestone/001" in tags
    assert "etc/feature/F-2026-05-30-x/milestone/002" in tags
    block = _read_state(feature_dir)["build"]["runtime_verification"]
    assert block["terminal_tag"] == "etc/feature/F-2026-05-30-x/milestone/002"


def test_should_exit_two_and_write_no_tag_when_live_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_commit(repo)
    feature_dir = _feature_dir_in_repo(repo, "F-2026-05-30-x")
    _write_state(feature_dir, _liveness_state(live_at="wave-2"))
    monkeypatch.setattr(
        rtc,
        "invoke_dispatcher",
        lambda *a, **k: {
            "results": [{"ac_id": "AC-3", "status": "fail", "evidence": "0 network calls"}]
        },
    )

    exit_code = rtc.main(["runtime_totalization_check.py", str(feature_dir)])

    assert exit_code == 2
    assert _list_tags(repo) == []


def test_should_exit_two_when_declared_live_ac_has_no_test(
    tmp_path: Path, monkeypatch: Any
) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_commit(repo)
    feature_dir = _feature_dir_in_repo(repo, "F-2026-05-30-x")
    _write_state(feature_dir, _liveness_state(live_at="wave-2"))
    monkeypatch.setattr(rtc, "invoke_dispatcher", lambda *a, **k: {"results": []})

    exit_code = rtc.main(["runtime_totalization_check.py", str(feature_dir)])

    assert exit_code == 2
    assert _list_tags(repo) == []


def test_should_exit_zero_with_null_terminal_tag_when_ungated(
    tmp_path: Path, monkeypatch: Any
) -> None:
    repo = tmp_path / "repo"
    _init_repo_with_commit(repo)
    feature_dir = _feature_dir_in_repo(repo, "F-2026-05-30-x")
    _write_state(feature_dir, {"spec_phase": {"completed_at": "2026-01-01"}})
    monkeypatch.setattr(rtc, "invoke_dispatcher", lambda *a, **k: {"results": []})

    exit_code = rtc.main(["runtime_totalization_check.py", str(feature_dir)])

    assert exit_code == 0
    assert _list_tags(repo) == []


def test_should_exit_one_when_feature_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope"

    exit_code = rtc.main(["runtime_totalization_check.py", str(missing)])

    assert exit_code == 1
