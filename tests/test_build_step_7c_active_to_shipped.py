"""Contract tests for /build Step 7 sub-step c (active->shipped rename).

Covers the bug reported on 2026-05-21: when ``.etc_sdlc/`` is gitignored
(the default in client projects and in etc itself, gated on the incidents/
and 4.7-audit/ whitelist), ``git mv`` fails with::

    fatal: source directory is empty,
    source=.etc_sdlc/features/active/F<NNN>-<slug>,
    destination=.etc_sdlc/features/shipped/F<NNN>-<slug>

The bug fired on F021's build (2026-05-20) and again on F022's build
(2026-05-21). Both times the conductor fell back to plain ``mv`` manually.
This contract pins the three-branch failure shape:

    (a) git-tracked source -> ``git mv`` succeeds; git ls-files reports
        the new path; rename is canonical in the index.
    (b) gitignored source (no tracked files in source dir) -> ``shutil.move``
        fallback fires; destination exists; the helper's stderr line
        announces the filesystem-only nature of the move so the audit
        trail observation is honest.
    (c) destination already exists -> non-zero exit + git stderr surfaced
        verbatim (preserves the existing edge-case-6 behavior).
    (d) source missing -> non-zero exit (preserves edge-case-6 behavior).

Test isolation: every test uses pytest ``tmp_path``; no test reads or
writes real ``.etc_sdlc/`` content. Subprocess + git operations run with
``cwd=tmp_path`` so the spawned git process is scoped to the synthetic
tree and never touches the operator's working repo.

Precedent: tests/test_directory_lifecycle.py (F009 contract).
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
SKILL_SRC = REPO_ROOT / "skills" / "build" / "SKILL.md"

# Make scripts/ importable so the in-process tests can drive the helper
# directly. Mirrors tests/test_directory_lifecycle.py.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import active_to_shipped_mv  # pyright: ignore[reportMissingImports]  # noqa: E402

# ── Helpers ──────────────────────────────────────────────────────────────


def _git_init(tmp_path: Path) -> None:
    """Initialize ``tmp_path`` as a git repo with a test identity.

    Identity is set ``--local`` so the test never touches the operator's
    global ``~/.gitconfig``. Mirrors test_directory_lifecycle.py.
    """
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "--local", "user.email", "test@example.invalid"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "--local", "user.name", "Test Runner"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "--local", "commit.gpgsign", "false"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )


def _git_add_commit(tmp_path: Path, message: str = "seed") -> None:
    """Stage all tracked paths under ``tmp_path`` and commit."""
    subprocess.run(
        ["git", "add", "-A"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "--quiet", "-m", message],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )


def _write_gitignore_excluding_etc_sdlc(tmp_path: Path) -> None:
    """Write a ``.gitignore`` matching etc's own pattern: exclude
    ``.etc_sdlc/`` so feature dirs created under it are untracked.

    Mirrors the real-world condition that triggered the bug.
    """
    (tmp_path / ".gitignore").write_text(
        ".etc_sdlc/\n",
        encoding="utf-8",
    )


def _make_feature_dir(parent: Path, name: str) -> Path:
    """Create ``<parent>/<name>/`` with a marker file and return its path."""
    feature_dir = parent / name
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "spec.md").write_text(f"# {name}\n", encoding="utf-8")
    (feature_dir / "release-notes.md").write_text(
        f"# Release Notes {name}\n", encoding="utf-8"
    )
    return feature_dir


def _ls_files(tmp_path: Path, path: str) -> str:
    """Return ``git ls-files <path>`` stdout for assertion."""
    result = subprocess.run(
        ["git", "ls-files", path],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


# ── (a) git-tracked source -> git mv succeeds ────────────────────────────


def test_should_invoke_git_mv_when_source_is_git_tracked(
    tmp_path: Path,
) -> None:
    """Branch (a): when the feature dir IS tracked (e.g. etc itself with
    its whitelist allowing ``incidents/`` to be tracked under
    ``.etc_sdlc/``), ``git mv`` must succeed and the rename must land in
    the index so ``git log --follow`` traces the directory history."""
    _git_init(tmp_path)
    src = _make_feature_dir(
        tmp_path / ".etc_sdlc" / "features" / "active",
        "F100-tracked-feature",
    )
    _git_add_commit(tmp_path, "seed tracked F100")

    dst = tmp_path / ".etc_sdlc" / "features" / "shipped" / "F100-tracked-feature"
    dst.parent.mkdir(parents=True, exist_ok=True)

    stderr = io.StringIO()
    exit_code = active_to_shipped_mv.move_active_to_shipped(
        src=src,
        dst=dst,
        cwd=tmp_path,
        stderr=stderr,
    )

    assert exit_code == 0, (
        f"helper returned non-zero on tracked-source happy path; "
        f"stderr={stderr.getvalue()!r}"
    )
    assert not src.exists(), (
        f"source path {src} still exists after rename; expected removal"
    )
    assert dst.is_dir(), f"target {dst} not a directory after rename"
    assert (dst / "spec.md").is_file()
    assert (dst / "release-notes.md").is_file()

    # The rename must be canonical in the index: ls-files reports the new
    # path AND does NOT report the old path.
    new_listing = _ls_files(
        tmp_path,
        ".etc_sdlc/features/shipped/F100-tracked-feature",
    )
    assert ".etc_sdlc/features/shipped/F100-tracked-feature/spec.md" in new_listing, (
        f"git ls-files does not show the renamed path; got {new_listing!r}"
    )
    old_listing = _ls_files(
        tmp_path,
        ".etc_sdlc/features/active/F100-tracked-feature",
    )
    assert old_listing == "", (
        f"git ls-files still shows the old path after rename; got {old_listing!r}"
    )


# ── (b) gitignored source -> shutil.move fallback ────────────────────────


def test_should_fallback_to_shutil_when_source_is_gitignored(
    tmp_path: Path,
) -> None:
    """Branch (b): the real-world bug condition. ``.etc_sdlc/`` is
    gitignored in client projects, so the feature dir under
    ``features/active/`` has zero tracked files. ``git mv`` reports
    ``source directory is empty`` and exits non-zero. The helper must
    catch that exact stderr substring and fall back to ``shutil.move``."""
    _git_init(tmp_path)
    _write_gitignore_excluding_etc_sdlc(tmp_path)
    _git_add_commit(tmp_path, "seed gitignore only")

    src = _make_feature_dir(
        tmp_path / ".etc_sdlc" / "features" / "active",
        "F101-gitignored-feature",
    )

    dst = (
        tmp_path / ".etc_sdlc" / "features" / "shipped" / "F101-gitignored-feature"
    )
    dst.parent.mkdir(parents=True, exist_ok=True)

    stderr = io.StringIO()
    exit_code = active_to_shipped_mv.move_active_to_shipped(
        src=src,
        dst=dst,
        cwd=tmp_path,
        stderr=stderr,
    )

    assert exit_code == 0, (
        f"helper returned non-zero on gitignored fallback path; "
        f"stderr={stderr.getvalue()!r}"
    )
    assert not src.exists(), (
        f"source path {src} still exists after fallback; expected removal"
    )
    assert dst.is_dir(), f"target {dst} not a directory after fallback"
    assert (dst / "spec.md").is_file(), (
        "spec.md missing at target after shutil.move fallback"
    )
    assert (dst / "release-notes.md").is_file(), (
        "release-notes.md missing at target after shutil.move fallback"
    )

    # The audit-trail honesty contract: stderr line must mention the
    # filesystem-only nature of the move so operators / log readers
    # know the rename is NOT in git's index.
    stderr_text = stderr.getvalue()
    assert "filesystem-only" in stderr_text, (
        f"helper stderr must note 'filesystem-only' on shutil.move fallback "
        f"so the audit trail is honest about the missing git-index entry; "
        f"got stderr={stderr_text!r}"
    )
    assert ".etc_sdlc/" in stderr_text or "gitignored" in stderr_text, (
        f"helper stderr must mention .etc_sdlc/ or gitignored so the "
        f"reader knows WHY the fallback fired; got stderr={stderr_text!r}"
    )


# ── (c) destination exists -> non-zero exit + git stderr surfaced ────────


def test_should_fail_with_nonzero_exit_when_destination_exists(
    tmp_path: Path,
) -> None:
    """Branch (c): preserves the existing edge-case-6 behavior. The
    destination directory under ``features/shipped/`` already exists (e.g.
    operator pre-staged a manual ``F100-…`` dir there). ``git mv``'s
    ``destination already exists`` failure path must NOT be silently
    rewritten as a fallback — the helper must exit non-zero and surface
    git's stderr verbatim."""
    _git_init(tmp_path)
    src = _make_feature_dir(
        tmp_path / ".etc_sdlc" / "features" / "active",
        "F102-collision",
    )
    _git_add_commit(tmp_path, "seed tracked F102 active")

    # Pre-existing collision at the destination: a NESTED dir mirroring
    # what git mv expands ``shipped/F102-collision`` to when shipped/F102-collision
    # is already a directory. This is the realistic operator-collision
    # case from test_directory_lifecycle.py's AC9 #7 precedent.
    nested_collision = (
        tmp_path
        / ".etc_sdlc"
        / "features"
        / "shipped"
        / "F102-collision"
        / "F102-collision"
    )
    nested_collision.mkdir(parents=True, exist_ok=False)
    (nested_collision / "marker.txt").write_text(
        "pre-existing from prior run\n", encoding="utf-8"
    )
    _git_add_commit(tmp_path, "seed colliding shipped target")

    dst = tmp_path / ".etc_sdlc" / "features" / "shipped" / "F102-collision"

    stderr = io.StringIO()
    exit_code = active_to_shipped_mv.move_active_to_shipped(
        src=src,
        dst=dst,
        cwd=tmp_path,
        stderr=stderr,
    )

    assert exit_code != 0, (
        "helper unexpectedly succeeded despite destination collision; "
        "edge-case-6 requires non-zero exit"
    )
    # Source survives (git mv is atomic on failure; shutil.move was NOT
    # invoked because the branch is the destination-exists branch).
    assert src.exists(), (
        f"source {src} removed despite collision failure; the helper must "
        "be atomic on the destination-exists branch (no partial fallback)"
    )
    stderr_text = stderr.getvalue()
    assert stderr_text.strip() != "", (
        "helper stderr was empty on collision; git's stderr must be "
        "surfaced verbatim per Security item 4 (no silent swallow)"
    )
    assert "destination already exists" in stderr_text.lower(), (
        f"helper stderr missing 'destination already exists' substring; "
        f"got stderr={stderr_text!r}"
    )


# ── (d) source missing -> non-zero exit ──────────────────────────────────


def test_should_fail_with_nonzero_exit_when_source_missing(
    tmp_path: Path,
) -> None:
    """Branch (d): preserves the existing edge-case-6 behavior. The
    source directory does not exist at all (e.g. operator state.yaml
    points to a stale slug). The helper must exit non-zero — neither
    branch (a) nor (b) is reachable from this state."""
    _git_init(tmp_path)
    # Establish at least one commit so HEAD resolves; the source dir
    # itself is intentionally absent.
    (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git_add_commit(tmp_path, "seed only")

    src = (
        tmp_path / ".etc_sdlc" / "features" / "active" / "F103-missing-source"
    )
    dst = (
        tmp_path / ".etc_sdlc" / "features" / "shipped" / "F103-missing-source"
    )
    dst.parent.mkdir(parents=True, exist_ok=True)

    stderr = io.StringIO()
    exit_code = active_to_shipped_mv.move_active_to_shipped(
        src=src,
        dst=dst,
        cwd=tmp_path,
        stderr=stderr,
    )

    assert exit_code != 0, (
        "helper unexpectedly succeeded with missing source; the helper "
        "must exit non-zero — neither branch (a) nor (b) is reachable"
    )
    assert not dst.exists(), (
        f"destination {dst} was created despite missing source; the "
        "helper must NOT fabricate an empty target on failure"
    )
    stderr_text = stderr.getvalue()
    assert stderr_text.strip() != "", (
        "helper stderr was empty on missing-source failure; the caller "
        "needs context to remediate"
    )


# ── SKILL.md prose contract: edge-case-6 reflects the new three branches ─


@pytest.fixture(scope="module")
def skill_text() -> str:
    assert SKILL_SRC.exists(), f"missing {SKILL_SRC}"
    return SKILL_SRC.read_text(encoding="utf-8")


def _step7_substep_c_block(text: str) -> str:
    """Slice SKILL.md from the sub-step-c heading to the next sub-step."""
    start = text.index("Move the feature directory from")
    # Sub-step c ends at the "Discipline (edge case 4)" paragraph or the
    # next top-level Step heading, whichever comes first.
    end_candidates = [
        text.find("**Discipline (edge case 4)**", start),
        text.find("### Step 8:", start),
    ]
    end_candidates = [c for c in end_candidates if c != -1]
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end]


def test_should_document_shutil_fallback_when_source_is_gitignored(
    skill_text: str,
) -> None:
    """SKILL.md must document the shutil.move fallback path so the
    orchestrator agent follows the same three-branch contract the helper
    enforces."""
    block = _step7_substep_c_block(skill_text)
    lowered = block.lower()
    assert "shutil" in lowered, (
        "Step 7 sub-step c must mention shutil (the stdlib fallback "
        "when .etc_sdlc/ is gitignored)"
    )
    assert "source directory is empty" in lowered, (
        "Step 7 sub-step c must name the exact git stderr substring "
        "('source directory is empty') the fallback branches on"
    )
    assert "gitignored" in lowered or ".etc_sdlc/" in block, (
        "Step 7 sub-step c must mention the gitignored .etc_sdlc/ "
        "condition that triggers the fallback"
    )


def test_should_revise_edge_case_6_to_three_branch_failure_shape(
    skill_text: str,
) -> None:
    """The edge-case-6 paragraph's prose must reflect the THREE-branch
    failure shape (source-empty -> fallback, destination exists -> fail,
    other -> fail) rather than the old single-branch ('destination
    exists') framing."""
    block = _step7_substep_c_block(skill_text)
    # The old prose claimed the destination-exists failure was the "most
    # common" failure. That claim is empirically wrong as of F021/F022 —
    # the most common failure is the gitignored-source case. Either the
    # phrase must be gone or it must be rewritten to acknowledge the
    # gitignored-source primacy.
    if "most commonly" in block:
        # If retained, the phrase must NOT modify "destination" alone —
        # it must refer to the gitignored-source / fallback path or
        # acknowledge multiple branches.
        idx = block.index("most commonly")
        local = block[idx : idx + 200].lower()
        assert (
            "gitignored" in local
            or "source directory is empty" in local
            or "fallback" in local
        ), (
            "Edge-case-6 prose retains 'most commonly' phrasing but does "
            "not point at the gitignored-source case — empirically wrong "
            "as of F021/F022"
        )


def test_should_revise_git_mv_required_sentence_to_preferred(
    skill_text: str,
) -> None:
    """The 'git mv is required (NOT mv + git add)' sentence is factually
    wrong now that the shutil.move fallback is sanctioned. It must be
    rewritten to 'preferred' (or equivalent) so the orchestrator agent
    does not interpret the fallback as a violation of the skill body."""
    block = _step7_substep_c_block(skill_text)
    # Hard-fail on the old absolute phrasing.
    assert "is required (NOT" not in block, (
        "Step 7 sub-step c retains the absolutist 'git mv is required "
        "(NOT mv + git add)' phrasing — incompatible with the sanctioned "
        "shutil.move fallback for the gitignored case"
    )


def test_should_preserve_argv_invocation_security_note(
    skill_text: str,
) -> None:
    """The security note ('argv-style invocation is mandatory — never a
    shell string') must survive the rewrite so operator-controlled slugs
    cannot inject shell metacharacters."""
    block = _step7_substep_c_block(skill_text)
    lowered = block.lower()
    assert "argv" in lowered, (
        "Step 7 sub-step c must retain the argv-style invocation note"
    )
    assert (
        "shell string" in lowered
        or "shell metacharacter" in lowered
        or "never a shell" in lowered
    ), (
        "Step 7 sub-step c must retain the 'never a shell string' "
        "security rationale so operator-controlled slugs cannot inject"
    )


# Module-level reference so static analyzers see ``pytest`` as used.
_ = pytest
