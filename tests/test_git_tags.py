"""Tests for scripts/git_tags.py — git tag helper.

Covers BR-007 (canonical tag points), BR-008 (append-only), AC-007–AC-010,
and edge cases 1 (non-git directory) and 2 (no-HEAD repo).
"""

from __future__ import annotations

import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "git_tags.py"


def _load_git_tags() -> ModuleType:
    """Load scripts/git_tags.py as a module without requiring scripts to be a package."""
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


def _init_repo_without_commit(repo: Path) -> None:
    """Initialize a git repo with no commits (no HEAD reference)."""
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")


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


class TestWriteTag:
    def test_should_create_tag_when_repo_has_head(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        result = git_tags.write_tag("etc/feature/F001/spec")

        assert result is True
        assert "etc/feature/F001/spec" in _list_tags(repo)

    def test_should_return_false_when_directory_is_not_git_repo(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        non_git = tmp_path / "plain"
        non_git.mkdir()
        monkeypatch.chdir(non_git)
        git_tags = _load_git_tags()

        result = git_tags.write_tag("etc/feature/F001/spec")

        assert result is False
        # No exception was raised; control returned False.

    def test_should_return_false_when_repo_has_no_head_commit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "empty-repo"
        _init_repo_without_commit(repo)
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        result = git_tags.write_tag("etc/feature/F001/spec")

        assert result is False
        assert _list_tags(repo) == []

    def test_should_log_warning_when_repo_has_no_head_commit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        repo = tmp_path / "empty-repo"
        _init_repo_without_commit(repo)
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        with caplog.at_level("WARNING", logger="git_tags"):
            git_tags.write_tag("etc/feature/F001/spec")

        assert any("HEAD" in record.message or "no commit" in record.message.lower()
                   for record in caplog.records)

    def test_should_log_warning_when_directory_is_not_git_repo(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        non_git = tmp_path / "plain"
        non_git.mkdir()
        monkeypatch.chdir(non_git)
        git_tags = _load_git_tags()

        with caplog.at_level("WARNING", logger="git_tags"):
            git_tags.write_tag("etc/feature/F001/spec")

        assert len(caplog.records) >= 1


class TestListEtcTags:
    def test_should_return_etc_tag_triples_when_etc_tags_exist(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)
        _git(repo, "tag", "etc/feature/F001/spec")
        _git(repo, "tag", "etc/feature/F001/release")
        _git(repo, "tag", "v1.0.0")  # non-etc tag, should NOT appear
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        results = git_tags.list_etc_tags()

        names = [name for name, _sha, _date in results]
        assert "etc/feature/F001/spec" in names
        assert "etc/feature/F001/release" in names
        assert "v1.0.0" not in names

    def test_should_include_commit_sha_and_date_in_each_triple(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)
        _git(repo, "tag", "etc/feature/F001/spec")
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        results = git_tags.list_etc_tags()

        assert len(results) == 1
        name, sha, date = results[0]
        assert name == "etc/feature/F001/spec"
        # Full SHA-1 is 40 hex chars
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)
        # ISO-8601 dates start with a 4-digit year
        assert date[:4].isdigit()

    def test_should_return_empty_list_when_no_etc_tags_exist(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)
        _git(repo, "tag", "v1.0.0")
        monkeypatch.chdir(repo)
        git_tags = _load_git_tags()

        results = git_tags.list_etc_tags()

        assert results == []

    def test_should_return_empty_list_when_directory_is_not_git_repo(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        non_git = tmp_path / "plain"
        non_git.mkdir()
        monkeypatch.chdir(non_git)
        git_tags = _load_git_tags()

        results = git_tags.list_etc_tags()

        assert results == []


class TestImmutability:
    """Negative tests verifying no delete/rewrite API exists (BR-008, AC-010)."""

    def test_should_not_expose_any_tag_deletion_helper(self) -> None:
        git_tags = _load_git_tags()
        # Only consider functions defined in git_tags itself (not re-imported helpers).
        own_functions = [
            name
            for name, fn in inspect.getmembers(git_tags, inspect.isfunction)
            if not name.startswith("_") and inspect.getmodule(fn) is git_tags
        ]
        forbidden_substrings = ("delete", "remove", "rewrite", "force", "retag")
        for name in own_functions:
            lowered = name.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lowered, (
                    f"git_tags exposes a function whose name contains '{forbidden}': {name!r}. "
                    "Tags must be append-only (BR-008, AC-010)."
                )

    def test_should_not_invoke_destructive_git_commands_in_source(self) -> None:
        source = SCRIPT_PATH.read_text()
        # Append-only invariant: source must never call these subcommands.
        # We check for the specific verb tokens to avoid false positives in docstrings.
        forbidden_invocations = (
            '"tag", "-d"',
            "'tag', '-d'",
            '"tag", "--delete"',
            "'tag', '--delete'",
            '"push", "--force"',
            "'push', '--force'",
            '"update-ref", "-d"',
            "'update-ref', '-d'",
        )
        for token in forbidden_invocations:
            assert token not in source, (
                f"git_tags.py source must not invoke destructive git command: {token}"
            )


class TestCli:
    """Smoke tests for the argparse CLI added by Remediation F1.2.

    The CLI must work when invoked from any cwd (so /spec, /build, /hotfix
    skills can call ``python3 <abs path>/git_tags.py write-tag ...`` without
    needing to be inside the etc-system-engineering checkout).
    """

    def test_should_write_tag_via_subprocess_from_unrelated_cwd(
        self,
        tmp_path: Path,
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write-tag", "etc/test/abc"],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "etc/test/abc" in _list_tags(repo)

    def test_should_exit_one_when_not_a_git_repo(
        self,
        tmp_path: Path,
    ) -> None:
        non_git = tmp_path / "plain"
        non_git.mkdir()

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "write-tag", "etc/test/xyz"],
            cwd=str(non_git),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert result.stderr.strip() != ""

    def test_should_list_etc_tags_via_subprocess(
        self,
        tmp_path: Path,
    ) -> None:
        repo = tmp_path / "repo"
        _init_repo_with_commit(repo)
        _git(repo, "tag", "etc/feature/F001/spec")
        _git(repo, "tag", "etc/feature/F001/release")
        _git(repo, "tag", "v9.9.9")  # non-etc tag must be filtered out

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "list-etc-tags"],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(lines) == 2
        for line in lines:
            parts = line.split("\t")
            assert len(parts) == 3, f"expected 3 tab-separated fields, got: {line!r}"
            name, sha, _date = parts
            assert name.startswith("etc/feature/F001/")
            assert len(sha) == 40
            assert all(c in "0123456789abcdef" for c in sha)
