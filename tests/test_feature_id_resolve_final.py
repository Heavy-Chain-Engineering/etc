"""Tests for `scripts/feature_id.py resolve-final-id` (F023 BR-002, BR-003, BR-008, BR-009).

Coverage targets:
- AC-002+BR-002+BR-008: `resolve-final-id <Ftmp-<hex>-<slug>>` calls
  `allocate_next` to get F<NNN>, renames the active dir via `shutil.move`,
  renames matching ADRs under `docs/adrs/Ftmp-<hex>-NN-*.md` to
  `F<NNN>-NN-*.md` via `git mv` argv-style, appends `id_history[final]`
  entry to `state.yaml`, prints F<NNN> to stdout, exit 0.
- AC-002+EC-005: On `git mv` failure (dirty tree, conflict, etc.), surface
  git's stderr verbatim, exit non-zero, do NOT roll back the dir rename.
- AC-003+BR-003: `allocate-next` is invoked from inside `resolve-final-id`;
  existing `allocate-next` CLI behavior preserved byte-equivalent.
- EC-003: `resolve-final-id` on a non-`Ftmp-` input (already-final form)
  short-circuits with exit 0 + stderr note.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import feature_id  # pyright: ignore[reportMissingImports]  # noqa: E402, I001  — sys.path inserted above

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "feature_id.py"


# ── helpers ─────────────────────────────────────────────────────────────


def _init_git_repo(repo_root: Path) -> None:
    """Initialize a fresh git repo at `repo_root` with an initial commit."""
    subprocess.run(
        ["git", "init", "-q"], cwd=repo_root, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    # An initial empty commit so `git mv` and tree-clean checks behave.
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "initial"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )


def _stage_temp_feature(
    repo_root: Path,
    temp_hex: str,
    slug: str,
    *,
    write_state: bool = True,
) -> Path:
    """Create `<repo>/.etc_sdlc/features/active/Ftmp-<hex>-<slug>/`."""
    feature_dir = (
        repo_root / ".etc_sdlc" / "features" / "active" / f"Ftmp-{temp_hex}-{slug}"
    )
    feature_dir.mkdir(parents=True)
    if write_state:
        state = {
            "id_history": [
                {
                    "form": "temp",
                    "value": f"Ftmp-{temp_hex}",
                    "written_at": "2026-05-21T00:00:00+00:00",
                }
            ]
        }
        (feature_dir / "state.yaml").write_text(yaml.safe_dump(state))
    return feature_dir


def _stage_adr(repo_root: Path, name: str, content: str = "# adr\n") -> Path:
    """Create + git-add an ADR under `<repo>/docs/adrs/`."""
    adr_dir = repo_root / "docs" / "adrs"
    adr_dir.mkdir(parents=True, exist_ok=True)
    adr_path = adr_dir / name
    adr_path.write_text(content)
    subprocess.run(
        ["git", "add", str(adr_path)],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", f"add {name}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return adr_path


# ── happy path: full rename (AC-002 / BR-002 / BR-008) ──────────────────


class TestResolveFinalIdHappyPath:
    def test_should_rename_dir_and_return_final_id(
        self, tmp_path: Path
    ) -> None:
        _init_git_repo(tmp_path)
        temp_hex = "abcdef12"
        slug = "happy-flow"
        feature_dir = _stage_temp_feature(tmp_path, temp_hex, slug)

        final_id = feature_id.resolve_final_id(
            feature_dir.name, tmp_path / ".etc_sdlc", repo_root=tmp_path
        )

        assert final_id == "F001"
        new_dir = tmp_path / ".etc_sdlc" / "features" / "active" / f"F001-{slug}"
        assert new_dir.is_dir()
        assert not feature_dir.exists()

    def test_should_append_final_id_history_entry_to_state_yaml(
        self, tmp_path: Path
    ) -> None:
        _init_git_repo(tmp_path)
        temp_hex = "11223344"
        slug = "stateful"
        _stage_temp_feature(tmp_path, temp_hex, slug)

        final_id = feature_id.resolve_final_id(
            f"Ftmp-{temp_hex}-{slug}",
            tmp_path / ".etc_sdlc",
            repo_root=tmp_path,
        )

        new_dir = tmp_path / ".etc_sdlc" / "features" / "active" / f"{final_id}-{slug}"
        loaded: dict[str, Any] = yaml.safe_load(
            (new_dir / "state.yaml").read_text()
        )
        history = loaded["id_history"]
        assert len(history) == 2
        assert history[0]["form"] == "temp"
        assert history[0]["value"] == f"Ftmp-{temp_hex}"
        assert history[1]["form"] == "final"
        assert history[1]["value"] == final_id
        written_at = history[1]["written_at"]
        assert "T" in written_at
        assert written_at.endswith("Z") or written_at.endswith("+00:00")

    def test_should_rename_matching_adrs_via_git_mv(
        self, tmp_path: Path
    ) -> None:
        _init_git_repo(tmp_path)
        temp_hex = "0badc0de"
        slug = "with-adrs"
        _stage_temp_feature(tmp_path, temp_hex, slug)
        _stage_adr(tmp_path, f"Ftmp-{temp_hex}-001-rationale.md")
        _stage_adr(tmp_path, f"Ftmp-{temp_hex}-002-trade-offs.md")

        final_id = feature_id.resolve_final_id(
            f"Ftmp-{temp_hex}-{slug}",
            tmp_path / ".etc_sdlc",
            repo_root=tmp_path,
        )

        adr_dir = tmp_path / "docs" / "adrs"
        assert (adr_dir / f"{final_id}-001-rationale.md").is_file()
        assert (adr_dir / f"{final_id}-002-trade-offs.md").is_file()
        assert not (adr_dir / f"Ftmp-{temp_hex}-001-rationale.md").exists()
        assert not (adr_dir / f"Ftmp-{temp_hex}-002-trade-offs.md").exists()
        # git ls-files must see the new names (git mv, not raw rename).
        tracked = subprocess.run(
            ["git", "ls-files", "docs/adrs"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert f"{final_id}-001-rationale.md" in tracked
        assert f"{final_id}-002-trade-offs.md" in tracked
        assert f"Ftmp-{temp_hex}-001-rationale.md" not in tracked

    def test_should_skip_adr_rename_when_docs_adrs_directory_missing(
        self, tmp_path: Path
    ) -> None:
        # EC-004: docs/adrs/ absent — proceed without git mv.
        _init_git_repo(tmp_path)
        temp_hex = "ed1700a1"
        slug = "no-adrs"
        _stage_temp_feature(tmp_path, temp_hex, slug)

        final_id = feature_id.resolve_final_id(
            f"Ftmp-{temp_hex}-{slug}",
            tmp_path / ".etc_sdlc",
            repo_root=tmp_path,
        )

        assert final_id.startswith("F")
        new_dir = tmp_path / ".etc_sdlc" / "features" / "active" / f"{final_id}-{slug}"
        assert new_dir.is_dir()


# ── EC-005: git mv failure surfaces stderr; dir rename not rolled back ──


class TestResolveFinalIdGitMvFailure:
    def test_should_raise_when_git_mv_fails_without_rolling_back_dir_rename(
        self, tmp_path: Path
    ) -> None:
        # EC-005: git mv fails (we cause it via a destination-name collision
        # — an untracked file already occupies the target path), and the dir
        # rename is NOT rolled back. Operator sees partial-state on disk.
        _init_git_repo(tmp_path)
        temp_hex = "deadbeef"
        slug = "git-fails"
        _stage_temp_feature(tmp_path, temp_hex, slug)
        _stage_adr(tmp_path, f"Ftmp-{temp_hex}-001-blocked.md")
        # Pre-create an UNTRACKED file at the destination path that git mv
        # will refuse to overwrite (git mv aborts on dest-exists by default).
        adr_dir = tmp_path / "docs" / "adrs"
        # The destination uses the F<NNN> the allocator will pick (F001 —
        # no other features in this tree).
        (adr_dir / "F001-001-blocked.md").write_text("blocker\n")

        with pytest.raises(feature_id.AdrRenameError):
            feature_id.resolve_final_id(
                f"Ftmp-{temp_hex}-{slug}",
                tmp_path / ".etc_sdlc",
                repo_root=tmp_path,
            )

        # Dir rename MUST NOT have been rolled back (EC-005: partial state).
        # The original Ftmp-<hex>-<slug> dir is GONE (rename happened first),
        # and the F<NNN>-<slug> dir IS present.
        original = (
            tmp_path / ".etc_sdlc" / "features" / "active" / f"Ftmp-{temp_hex}-{slug}"
        )
        renamed = tmp_path / ".etc_sdlc" / "features" / "active"
        assert not original.exists(), (
            "EC-005 violation: dir rename was rolled back on git mv failure"
        )
        # Confirm SOME F<NNN>-<slug> dir exists (the partial-state evidence).
        renamed_dirs = list(renamed.glob(f"F[0-9][0-9][0-9]-{slug}"))
        assert len(renamed_dirs) == 1, (
            f"expected one F<NNN>-{slug} dir; got {renamed_dirs}"
        )


# ── EC-003: short-circuit on already-final ID ───────────────────────────


class TestResolveFinalIdShortCircuit:
    def test_should_short_circuit_when_input_is_already_final_form(
        self, tmp_path: Path
    ) -> None:
        # EC-003: passing an already-final F<NNN>-<slug> returns the id
        # unchanged and does not touch the filesystem.
        _init_git_repo(tmp_path)
        already_final = (
            tmp_path / ".etc_sdlc" / "features" / "active" / "F042-already-final"
        )
        already_final.mkdir(parents=True)

        # No exception; returns the F<NNN> portion of the input dir name.
        result = feature_id.resolve_final_id(
            "F042-already-final",
            tmp_path / ".etc_sdlc",
            repo_root=tmp_path,
        )
        assert result == "F042"
        # The dir is untouched.
        assert already_final.is_dir()


# ── AC-003+BR-003: allocate_next is invoked from inside resolve_final_id ─


class TestResolveFinalIdUsesAllocateNext:
    def test_should_invoke_allocate_next_to_select_final_id(
        self, tmp_path: Path
    ) -> None:
        # Pre-create F001 + F002 so the next sequential ID must be F003.
        _init_git_repo(tmp_path)
        features = tmp_path / ".etc_sdlc" / "features"
        (features / "active").mkdir(parents=True)
        (features / "active" / "F001-old").mkdir()
        (features / "active" / "F002-older").mkdir()
        temp_hex = "feed0001"
        slug = "next-up"
        _stage_temp_feature(tmp_path, temp_hex, slug)

        final_id = feature_id.resolve_final_id(
            f"Ftmp-{temp_hex}-{slug}",
            tmp_path / ".etc_sdlc",
            repo_root=tmp_path,
        )

        assert final_id == "F003"

    def test_should_preserve_legacy_allocate_next_cli_behavior(
        self, tmp_path: Path
    ) -> None:
        # AC-003: pre-F023 callers passing only F<NNN> see no behavior change.
        # The existing test_feature_id.py asserts the byte-equivalent shape;
        # this is a regression-smoke that the CLI subcommand still exists
        # and emits "F001 <path>\n" with no extra prefixes/suffixes.
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "allocate-next",
                str(tmp_path),
                "legacy-shape",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, result.stderr
        line = result.stdout.rstrip("\n")
        assert line.startswith("F001 ")
        assert "\n" not in line


# ── CLI subcommand: resolve-final-id ────────────────────────────────────


class TestResolveFinalIdCLI:
    def test_should_print_final_id_to_stdout_with_exit_zero(
        self, tmp_path: Path
    ) -> None:
        _init_git_repo(tmp_path)
        temp_hex = "1234abcd"
        slug = "cli-resolve"
        _stage_temp_feature(tmp_path, temp_hex, slug)

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "resolve-final-id",
                str(tmp_path / ".etc_sdlc"),
                f"Ftmp-{temp_hex}-{slug}",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, (
            f"CLI exited {result.returncode}; stderr={result.stderr!r}"
        )
        printed = result.stdout.rstrip("\n")
        assert printed.startswith("F")
        assert len(printed) == 4  # "F" + 3-digit
        new_dir = (
            tmp_path / ".etc_sdlc" / "features" / "active" / f"{printed}-{slug}"
        )
        assert new_dir.is_dir()

    def test_should_short_circuit_with_stderr_note_when_already_final(
        self, tmp_path: Path
    ) -> None:
        # EC-003: non-Ftmp- input → exit 0 + stderr note.
        _init_git_repo(tmp_path)
        already = (
            tmp_path / ".etc_sdlc" / "features" / "active" / "F042-already"
        )
        already.mkdir(parents=True)

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "resolve-final-id",
                str(tmp_path / ".etc_sdlc"),
                "F042-already",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "already has final ID" in result.stderr
        assert result.stdout.rstrip("\n") == "F042"

    def test_should_exit_nonzero_when_temp_feature_dir_missing(
        self, tmp_path: Path
    ) -> None:
        _init_git_repo(tmp_path)
        (tmp_path / ".etc_sdlc" / "features" / "active").mkdir(parents=True)

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "resolve-final-id",
                str(tmp_path / ".etc_sdlc"),
                "Ftmp-99999999-missing",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode != 0
        assert result.stderr.strip(), "expected non-empty stderr"
