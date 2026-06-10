"""Tests for scripts/reject_feature_mv.py + the no-legacy-ID-snippet contract.

Audit init 7: the /spec rejection flow carried an inline snippet that built
the rejection target as ``f"F{nnn:03d}-{slug}"`` — ``nnn`` undefined since
the 2026-05-22 date-form ID revision — so a faithful agent NameError'd
mid-rejection. The helper replaces the snippet; the grep contract here pins
that the dead ``F{nnn:03d}`` format never returns to any skill body.

Mirrors the synthetic-git conventions of the active→shipped helper tests.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "reject_feature_mv.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("reject_feature_mv", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["reject_feature_mv"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def helper() -> ModuleType:
    return _load_module()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def test_git_tracked_source_moves_via_git_mv(helper: ModuleType, repo: Path) -> None:
    src = repo / ".etc_sdlc" / "features" / "active" / "F-2026-06-09-rejected-idea"
    src.mkdir(parents=True)
    (src / "rejected.md").write_text("# why\n")
    _git(repo, "add", str(src / "rejected.md"))
    _git(repo, "commit", "-m", "seed")

    rc = helper.move_to_rejections(src, repo / ".etc_sdlc" / "rejections", repo)

    assert rc == 0
    assert not src.exists()
    assert (repo / ".etc_sdlc" / "rejections" / "F-2026-06-09-rejected-idea" / "rejected.md").exists()


def test_gitignored_source_moves_via_filesystem_fallback(
    helper: ModuleType, repo: Path
) -> None:
    (repo / ".gitignore").write_text(".etc_sdlc/\n")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "ignore")
    src = repo / ".etc_sdlc" / "features" / "active" / "F-2026-06-09-ignored"
    src.mkdir(parents=True)
    (src / "rejected.md").write_text("# why\n")

    import io

    err = io.StringIO()
    rc = helper.move_to_rejections(
        src, repo / ".etc_sdlc" / "rejections", repo, stderr=err
    )

    assert rc == 0
    assert (repo / ".etc_sdlc" / "rejections" / "F-2026-06-09-ignored" / "rejected.md").exists()
    assert "fallback" in err.getvalue()


def test_existing_target_refuses_and_names_both_paths(
    helper: ModuleType, repo: Path
) -> None:
    src = repo / ".etc_sdlc" / "features" / "active" / "F-2026-06-09-dup"
    src.mkdir(parents=True)
    (src / "rejected.md").write_text("x\n")
    target = repo / ".etc_sdlc" / "rejections" / "F-2026-06-09-dup"
    target.mkdir(parents=True)

    import io

    err = io.StringIO()
    rc = helper.move_to_rejections(
        src, repo / ".etc_sdlc" / "rejections", repo, stderr=err
    )

    assert rc == 1
    assert src.exists(), "source must be untouched on refusal"
    assert str(target) in err.getvalue() and str(src) in err.getvalue()


def test_missing_source_is_nonzero(helper: ModuleType, repo: Path) -> None:
    rc = helper.move_to_rejections(
        repo / "nope", repo / ".etc_sdlc" / "rejections", repo
    )
    assert rc == 1


def test_legacy_dir_name_also_moves(helper: ModuleType, repo: Path) -> None:
    """Both ID grammars work — the target is just the source dir name."""
    src = repo / ".etc_sdlc" / "features" / "active" / "F015-old-style"
    src.mkdir(parents=True)
    (src / "rejected.md").write_text("x\n")
    _git(repo, "add", str(src / "rejected.md"))
    _git(repo, "commit", "-m", "seed")

    rc = helper.move_to_rejections(src, repo / ".etc_sdlc" / "rejections", repo)

    assert rc == 0
    assert (repo / ".etc_sdlc" / "rejections" / "F015-old-style").is_dir()


# ── Contract: the dead legacy-ID format string never returns ────────────


def test_no_skill_body_contains_legacy_nnn_format_string() -> None:
    """No skills/*/SKILL.md may contain the ``F{nnn:03d}`` format literal.

    The allocator has issued date-form IDs since 2026-05-22; ``nnn`` is
    undefined in every flow that carried this snippet, so following the
    prose crashes (audit init 7 — independently confirmed by four
    reviewers). The rejection flow now invokes reject_feature_mv.py; ADR
    paths are built from the feature_id directly.
    """
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in (REPO_ROOT / "skills").glob("*/SKILL.md")
        if "F{nnn:03d}" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"legacy F{{nnn:03d}} format string found in: {offenders}. The ID "
        "scheme is date-form; build paths from the feature_id / dir name."
    )


def test_spec_rejection_flow_cites_helper_and_post_move_path() -> None:
    """The /spec rejection flow must invoke the helper and point the
    operator at the POST-move rejected.md location."""
    text = (REPO_ROOT / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8")
    assert "reject_feature_mv.py" in text, (
        "/spec rejection flow must invoke scripts/reject_feature_mv.py"
    )
    assert ".etc_sdlc/features/{slug}/rejected.md" not in text, (
        "operator message still points at the PRE-move rejected.md path; "
        "after step 4 the directory lives under .etc_sdlc/rejections/"
    )
