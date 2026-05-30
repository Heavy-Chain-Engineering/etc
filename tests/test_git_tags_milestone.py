"""Tests for milestone tag grammar in scripts/git_tags.py (ADR-002 / AGA-002).

Milestone release tags use the grammar ``etc/feature/<id>/milestone/<NNN>``
(zero-padded sequence, append-only) — a directory sibling of the existing
``release`` LEAF tag. A *bare* ``etc/feature/<id>/milestone`` write is a
programming-contract violation: it would occupy ``milestone`` as a ref leaf
and prevent ``milestone/`` from being usable as a directory for the
``<NNN>`` children. Such a write must be rejected loudly (ValueError), as
distinct from the graceful-degrade git failure modes (return False).
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "git_tags.py"


def _load_git_tags() -> ModuleType:
    """Load scripts/git_tags.py as a module without requiring a package."""
    spec = importlib.util.spec_from_file_location("git_tags", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in cwd, capturing output."""
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
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
    """Return tag names in repo."""
    result = subprocess.run(
        ["git", "tag", "--list"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


class TestMilestoneTagGrammar:
    def test_should_create_tag_when_milestone_has_sequence_leaf(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        result = git_tags.write_tag("etc/feature/F001/milestone/001")

        assert result is True
        assert "etc/feature/F001/milestone/001" in _list_tags(repo)

    def test_should_create_annotated_tag_when_milestone_written(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        assert git_tags.write_tag("etc/feature/F001/milestone/002") is True

        result = subprocess.run(
            ["git", "cat-file", "-t", "etc/feature/F001/milestone/002"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "tag"


class TestBareMilestoneGuard:
    def test_should_raise_value_error_when_milestone_is_bare(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        with pytest.raises(ValueError, match="milestone"):
            git_tags.write_tag("etc/feature/F001/milestone")

    def test_should_not_create_any_tag_when_milestone_is_bare(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        with pytest.raises(ValueError):
            git_tags.write_tag("etc/feature/F001/milestone")

        assert _list_tags(repo) == []

    def test_should_allow_tag_named_milestone_only_as_path_segment(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # The guard targets a trailing bare ``/milestone`` leaf, not the
        # substring. A non-feature tag merely containing the word must not
        # be rejected.
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        assert git_tags.write_tag("etc/feature/F001/milestone/010") is True
