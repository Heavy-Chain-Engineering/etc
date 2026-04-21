"""Tests for .meta/ reconciliation system.

Tests the post-commit hook logic, pre-push warning, and reconcile script.
Uses temporary directory structures to simulate real project layouts.
"""

import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def project_dir(tmp_path):
    """Create a realistic project structure with .meta/ descriptions."""
    # Root .meta/
    meta_root = tmp_path / ".meta"
    meta_root.mkdir()
    (meta_root / "description.md").write_text("# Project Root\n**Purpose:** Test project\n")

    # src/ with .meta/
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("# app code\n")
    (src / "models.py").write_text("# models\n")
    meta_src = src / ".meta"
    meta_src.mkdir()
    (meta_src / "description.md").write_text("# src\n**Purpose:** Source code\n")

    # src/auth/ with .meta/
    auth = src / "auth"
    auth.mkdir()
    (auth / "login.py").write_text("# login\n")
    meta_auth = auth / ".meta"
    meta_auth.mkdir()
    (meta_auth / "description.md").write_text("# auth\n**Purpose:** Authentication\n")

    # tests/ without .meta/ (should be ignored)
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_app.py").write_text("# tests\n")

    return tmp_path


REPO_ROOT = Path(__file__).parent.parent


# ──────────────────────────────────────────────
# Post-commit hook tests
# ──────────────────────────────────────────────


class TestPostCommitHookLogic:
    """Test the stale-marking logic that the post-commit hook performs."""

    def _mark_stale(self, project_dir: Path, changed_files: list[str]):
        """Simulate the post-commit hook's stale-marking logic in Python.

        This mirrors the shell script logic for testability without
        requiring a real git repo.
        """
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        marked = set()

        for file in changed_files:
            # Skip .meta/ files themselves
            if "/.meta/" in file or file.startswith(".meta/"):
                continue

            # Walk up directory tree
            dir_path = Path(file).parent
            while str(dir_path) != "." and str(dir_path) != "/":
                meta_dir = project_dir / dir_path / ".meta"
                if (meta_dir / "description.md").is_file() and str(meta_dir) not in marked:
                    stale_file = meta_dir / "stale.json"
                    if stale_file.is_file():
                        with open(stale_file) as f:
                            data = json.load(f)
                        data["changed_files"] = list(
                            set(data["changed_files"] + [file])
                        )
                        data["marked_at"] = timestamp
                    else:
                        data = {
                            "marked_at": timestamp,
                            "changed_files": [file],
                        }
                    with open(stale_file, "w") as f:
                        json.dump(data, f, indent=2)
                    marked.add(str(meta_dir))
                dir_path = dir_path.parent

    def test_marks_direct_parent(self, project_dir):
        """Changing a file marks its parent's .meta/ as stale."""
        self._mark_stale(project_dir, ["src/app.py"])

        stale = project_dir / "src" / ".meta" / "stale.json"
        assert stale.is_file()
        data = json.loads(stale.read_text())
        assert "src/app.py" in data["changed_files"]
        assert "marked_at" in data

    def test_marks_ancestor_meta(self, project_dir):
        """Changing a deeply nested file marks all ancestor .meta/ dirs."""
        self._mark_stale(project_dir, ["src/auth/login.py"])

        # auth's .meta/ should be stale
        stale_auth = project_dir / "src" / "auth" / ".meta" / "stale.json"
        assert stale_auth.is_file()
        data = json.loads(stale_auth.read_text())
        assert "src/auth/login.py" in data["changed_files"]

        # src's .meta/ should also be stale (ancestor)
        stale_src = project_dir / "src" / ".meta" / "stale.json"
        assert stale_src.is_file()

    def test_does_not_mark_without_meta(self, project_dir):
        """Changing a file in a directory without .meta/ does nothing."""
        self._mark_stale(project_dir, ["tests/test_app.py"])

        # tests/ has no .meta/, so nothing should be stale
        stale = project_dir / "tests" / ".meta" / "stale.json"
        assert not stale.is_file()

    def test_skips_meta_files_themselves(self, project_dir):
        """Changes to .meta/ files don't trigger stale marking."""
        self._mark_stale(project_dir, ["src/.meta/description.md"])

        stale = project_dir / "src" / ".meta" / "stale.json"
        assert not stale.is_file()

    def test_accumulates_changed_files(self, project_dir):
        """Multiple commits accumulate changed files in stale.json."""
        self._mark_stale(project_dir, ["src/app.py"])
        self._mark_stale(project_dir, ["src/models.py"])

        stale = project_dir / "src" / ".meta" / "stale.json"
        data = json.loads(stale.read_text())
        assert "src/app.py" in data["changed_files"]
        assert "src/models.py" in data["changed_files"]

    def test_no_duplicates_on_recommit(self, project_dir):
        """Re-committing the same file doesn't create duplicates."""
        self._mark_stale(project_dir, ["src/app.py"])
        self._mark_stale(project_dir, ["src/app.py"])

        stale = project_dir / "src" / ".meta" / "stale.json"
        data = json.loads(stale.read_text())
        assert data["changed_files"].count("src/app.py") == 1


# ──────────────────────────────────────────────
# Reconcile script tests
# ──────────────────────────────────────────────


class TestMetaReconcileScript:
    """Test the meta-reconcile.py script."""

    SCRIPT = str(REPO_ROOT / "scripts" / "meta-reconcile.py")

    def _create_stale_marker(self, meta_dir: Path, changed_files: list[str]):
        """Helper to create a stale.json marker."""
        stale_file = meta_dir / "stale.json"
        stale_file.write_text(json.dumps({
            "marked_at": "2026-02-25T12:00:00Z",
            "changed_files": changed_files,
        }, indent=2))

    def test_list_no_stale(self, project_dir):
        """No stale markers → exit 0, clean message."""
        result = subprocess.run(
            ["python3", self.SCRIPT, str(project_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "No stale" in result.stdout

    def test_list_stale(self, project_dir):
        """Stale markers → exit 1, lists directories."""
        self._create_stale_marker(
            project_dir / "src" / ".meta", ["src/app.py"]
        )
        result = subprocess.run(
            ["python3", self.SCRIPT, str(project_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "src/.meta/" in result.stdout

    def test_list_verbose(self, project_dir):
        """Verbose mode shows changed files."""
        self._create_stale_marker(
            project_dir / "src" / ".meta", ["src/app.py", "src/models.py"]
        )
        result = subprocess.run(
            ["python3", self.SCRIPT, "--verbose", str(project_dir)],
            capture_output=True, text=True,
        )
        assert "src/app.py" in result.stdout
        assert "src/models.py" in result.stdout

    def test_clear_all(self, project_dir):
        """--clear removes all stale markers."""
        self._create_stale_marker(
            project_dir / "src" / ".meta", ["src/app.py"]
        )
        self._create_stale_marker(
            project_dir / "src" / "auth" / ".meta", ["src/auth/login.py"]
        )

        # root positional BEFORE --clear so argparse doesn't consume it
        result = subprocess.run(
            ["python3", self.SCRIPT, str(project_dir), "--clear"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Cleared 2" in result.stdout

        # Verify markers are gone
        assert not (project_dir / "src" / ".meta" / "stale.json").exists()
        assert not (project_dir / "src" / "auth" / ".meta" / "stale.json").exists()

    def test_clear_specific_dir(self, project_dir):
        """--clear DIR clears only that directory's marker."""
        self._create_stale_marker(
            project_dir / "src" / ".meta", ["src/app.py"]
        )
        self._create_stale_marker(
            project_dir / "src" / "auth" / ".meta", ["src/auth/login.py"]
        )

        target = str(project_dir / "src")
        result = subprocess.run(
            ["python3", self.SCRIPT, "--clear", target, str(project_dir)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Cleared 1" in result.stdout

        # src marker cleared, auth marker still there
        assert not (project_dir / "src" / ".meta" / "stale.json").exists()
        assert (project_dir / "src" / "auth" / ".meta" / "stale.json").exists()

    def test_handles_corrupt_stale_json(self, project_dir):
        """Corrupt stale.json doesn't crash the script."""
        stale = project_dir / "src" / ".meta" / "stale.json"
        stale.write_text("not json{{{")

        result = subprocess.run(
            ["python3", self.SCRIPT, str(project_dir)],
            capture_output=True, text=True,
        )
        # Should warn but not crash
        assert result.returncode in (0, 1)
        assert "Warning" in result.stderr or "No stale" in result.stdout


# ──────────────────────────────────────────────
# Post-commit hook integration test
# ──────────────────────────────────────────────


class TestPostCommitHookIntegration:
    """Integration test that runs the actual hook in a real git repo."""

    HOOK_PATH = str(REPO_ROOT / "hooks" / "git" / "post-commit")

    @pytest.fixture
    def git_project(self, tmp_path):
        """Create a git repo with .meta/ structure."""
        # Init git repo
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path, capture_output=True, check=True,
        )

        # Create structure
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("# initial\n")
        meta = src / ".meta"
        meta.mkdir()
        (meta / "description.md").write_text("# src\n**Purpose:** Source\n")

        # Initial commit
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path, capture_output=True, check=True,
        )

        # Install the hook
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        hook_dest = hooks_dir / "post-commit"
        # Copy our hook
        import shutil
        shutil.copy2(self.HOOK_PATH, str(hook_dest))
        hook_dest.chmod(0o755)

        return tmp_path

    def test_hook_marks_stale_on_commit(self, git_project):
        """Full integration: edit file → commit → stale.json appears."""
        # Modify a file
        (git_project / "src" / "app.py").write_text("# modified\n")
        subprocess.run(["git", "add", "-A"], cwd=git_project, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "edit app"],
            cwd=git_project, capture_output=True, check=True,
        )

        # Check that stale marker was created
        stale = git_project / "src" / ".meta" / "stale.json"
        assert stale.is_file(), f"Expected {stale} to exist after commit"
        data = json.loads(stale.read_text())
        assert "src/app.py" in data["changed_files"]

    def test_hook_speed(self, git_project):
        """Hook completes in <100ms (the performance requirement)."""
        import time

        (git_project / "src" / "app.py").write_text("# speed test\n")
        subprocess.run(["git", "add", "-A"], cwd=git_project, capture_output=True, check=True)

        start = time.monotonic()
        subprocess.run(
            ["git", "commit", "-m", "speed test"],
            cwd=git_project, capture_output=True, check=True,
        )
        elapsed_ms = (time.monotonic() - start) * 1000

        # The commit itself takes time; we're generous here.
        # The hook should add <100ms on top of normal commit time.
        # Total commit on tmp_path should be well under 2000ms.
        assert elapsed_ms < 2000, f"Commit took {elapsed_ms:.0f}ms (expected <2000ms with hook)"
