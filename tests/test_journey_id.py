"""Tests for scripts/journey_id.py (F017).

POSIX-atomic J-NNN allocator. Mirrors feature_id.py's contract.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "journey_id.py"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestAllocateNext:
    def test_first_allocation_returns_j001(self, tmp_path: Path) -> None:
        result = _run(["allocate-next", str(tmp_path), "contract execution"])
        assert result.returncode == 0
        assert result.stdout.startswith("J-001 ")
        # The path should end with the slug:
        assert "contract-execution" in result.stdout

    def test_second_allocation_increments_to_j002(self, tmp_path: Path) -> None:
        _run(["allocate-next", str(tmp_path), "first"])
        result = _run(["allocate-next", str(tmp_path), "second"])
        assert result.returncode == 0
        assert result.stdout.startswith("J-002 ")

    def test_slug_is_kebab_cased(self, tmp_path: Path) -> None:
        result = _run(["allocate-next", str(tmp_path), "Counsel Executes A Contract!"])
        assert result.returncode == 0
        # Spaces, punctuation collapsed to single hyphens; lowercase:
        assert "counsel-executes-a-contract" in result.stdout

    def test_allocation_creates_directory(self, tmp_path: Path) -> None:
        result = _run(["allocate-next", str(tmp_path), "test"])
        assert result.returncode == 0
        # Output format: "<journey_id> <full_path>"
        path = result.stdout.strip().split(" ", 1)[1]
        assert Path(path).is_dir()

    def test_skips_over_existing_higher_numbered_directories(
        self, tmp_path: Path
    ) -> None:
        """If J-001 + J-005 exist, next allocation should be J-006."""
        (tmp_path / "J-001-foo").mkdir()
        (tmp_path / "J-005-bar").mkdir()
        result = _run(["allocate-next", str(tmp_path), "third"])
        assert result.returncode == 0
        assert result.stdout.startswith("J-006 ")

    def test_missing_args_returns_one(self, tmp_path: Path) -> None:
        result = _run(["allocate-next", str(tmp_path)])
        assert result.returncode == 1

    def test_unknown_command_returns_one(self) -> None:
        result = _run(["bogus-command"])
        assert result.returncode == 1


class TestListCommand:
    def test_list_empty_root_prints_nothing(self, tmp_path: Path) -> None:
        result = _run(["list", str(tmp_path)])
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_list_prints_allocated_journeys_sorted(self, tmp_path: Path) -> None:
        _run(["allocate-next", str(tmp_path), "alpha"])
        _run(["allocate-next", str(tmp_path), "beta"])
        result = _run(["list", str(tmp_path)])
        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        # Sorted by integer journey ID, not lexical
        assert len(lines) == 2
        assert "J-001-alpha" in lines[0]
        assert "J-002-beta" in lines[1]


class TestSlugify:
    """The CLI's slug derivation should match feature_id.py's convention
    closely enough that operators don't trip on it."""

    def test_punctuation_stripped(self, tmp_path: Path) -> None:
        result = _run(["allocate-next", str(tmp_path), "Hello, World!"])
        assert "hello-world" in result.stdout

    def test_empty_slug_defaults_to_untitled(self, tmp_path: Path) -> None:
        result = _run(["allocate-next", str(tmp_path), "!!!"])
        assert result.returncode == 0
        assert "untitled" in result.stdout
