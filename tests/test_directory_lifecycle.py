"""Contract tests for two-state features lifecycle (F009 / BR-009).

Covers PRD .etc_sdlc/features/F009-directory-lifecycle/spec.md acceptance
criteria AC9-AC13 via:

- In-process unit tests that drive ``feature_id._scan_max_feature_id``,
  ``feature_id.allocate_next``, and ``feature_id.resolve_feature_path``
  against synthetic ``.etc_sdlc/`` trees rooted at ``tmp_path``.
- Subprocess-based end-to-end tests that exercise the ``git mv`` semantics
  used by /spec's rejection-write flow and /build's terminal-close flow.
  Each subprocess test ``git init``s the ``tmp_path`` so ``git mv`` operates
  against a real (but isolated) git index, preserving the rename-history
  invariant the skill bodies rely on.

Test isolation contract (AC10):
    Every test uses pytest ``tmp_path``. NO test reads or writes real
    ``.etc_sdlc/features/`` or ``.etc_sdlc/rejections/`` directories. Tests
    construct synthetic ``.etc_sdlc/`` trees in ``tmp_path``. Subprocess
    tests pass ``cwd=str(tmp_path)`` so the spawned ``git`` process is
    scoped to the synthetic tree.

Precedent:
- tests/test_completion_report.py (F005 contract test) — tmp_path subprocess
  pattern + path-traversal-guard workaround.
- tests/test_wave_planner_implicit_deps.py (F008 contract test) — sys.path
  manipulation for runtime helper imports + in-memory + subprocess hybrid.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Make scripts/ importable so the in-process unit tests can drive the
# resolver and allocator helpers directly. Mirrors F005/F008 precedent.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import feature_id as feature_id_module  # pyright: ignore[reportMissingImports]  # noqa: E402

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_etc_sdlc_root(tmp_path: Path) -> Path:
    """Create ``<tmp_path>/.etc_sdlc/`` and return its path."""
    root = tmp_path / ".etc_sdlc"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _make_feature_dir(parent: Path, name: str) -> Path:
    """Create ``<parent>/<name>/`` with a marker file and return its path.

    The marker file ensures ``git mv`` (which refuses to move empty trees
    in some configurations) has at least one tracked file to rename.
    """
    feature_dir = parent / name
    feature_dir.mkdir(parents=True, exist_ok=True)
    marker = feature_dir / "spec.md"
    marker.write_text(f"# {name}\n", encoding="utf-8")
    return feature_dir


def _git_init(tmp_path: Path) -> None:
    """Initialize ``tmp_path`` as a git repo and configure a test identity.

    The identity is set inside the repo (``--local``) so the test never
    touches the operator's global ``~/.gitconfig``. Without an identity
    ``git commit`` would fail; we commit at least once so ``git mv``
    operates against a non-empty index (matches /spec's and /build's
    real-world flow where the feature dir is already tracked).
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
    """Stage all paths under ``tmp_path`` and create a commit."""
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


def _git_mv(
    tmp_path: Path, src: Path, dst: Path
) -> subprocess.CompletedProcess[str]:
    """Run ``git mv <src> <dst>`` with ``cwd=tmp_path``.

    Paths are passed as strings relative to ``tmp_path`` so the spawned
    git process resolves them against the synthetic tree (and not against
    the test runner's working directory).
    """
    return subprocess.run(
        [
            "git",
            "mv",
            str(src.relative_to(tmp_path)),
            str(dst.relative_to(tmp_path)),
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )


# ── AC9 #1: allocator rglob across all 4 locations ───────────────────────


def test_should_find_max_id_across_all_four_locations_when_scanning(
    tmp_path: Path,
) -> None:
    """AC9 #1 + BR-001: ``_scan_max_feature_id`` rglobs across all four
    lifecycle locations (legacy flat, active, shipped, rejections) and
    returns the highest captured integer.

    Scenario: place synthetic feature dirs at each of the four locations
    with ascending IDs (F001 legacy, F002 active, F003 shipped, F042
    rejections); assert the function returns 42.
    """
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    features_dir = etc_sdlc / "features"

    # 1. Legacy flat (F001-F008 + F006 grandfathered location).
    _make_feature_dir(features_dir, "F001-legacy-flat")
    # 2. features/active/ (in-flight work).
    _make_feature_dir(features_dir / "active", "F002-active-work")
    # 3. features/shipped/ (done audit-frozen).
    _make_feature_dir(features_dir / "shipped", "F003-shipped-work")
    # 4. rejections/ (top-level under .etc_sdlc/).
    _make_feature_dir(etc_sdlc / "rejections", "F042-rejected-idea")

    # Pass features_dir; the helper derives etc_sdlc as features_dir.parent.
    highest = feature_id_module._scan_max_feature_id(features_dir)

    assert highest == 42, (
        "expected highest F-ID across all four locations to be 42 "
        f"(found at rejections/F042-…); got {highest}"
    )


# ── AC9 #2: resolve_feature_path returns the right path per location ─────


def test_should_return_legacy_flat_path_when_resolving_grandfathered_id(
    tmp_path: Path,
) -> None:
    """AC9 #2 + BR-003 priority 1: legacy flat ``features/F<NNN>-*/`` hit.

    F001-F008 + the F006 placeholder remain at the legacy flat path
    after F009 ships (forward-only). The resolver must find them.
    """
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    features_dir = etc_sdlc / "features"
    expected = _make_feature_dir(features_dir, "F004-legacy-build")

    resolved = feature_id_module.resolve_feature_path("F004", etc_sdlc)

    assert resolved is not None, (
        "resolver returned None for legacy flat F004; expected the "
        "priority-1 location to be found"
    )
    assert resolved == expected.resolve(), (
        f"resolver returned {resolved!r}; expected {expected.resolve()!r}"
    )


def test_should_return_active_path_when_resolving_in_flight_id(
    tmp_path: Path,
) -> None:
    """AC9 #2 + BR-003 priority 2: ``features/active/F<NNN>-*/`` hit."""
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    expected = _make_feature_dir(
        etc_sdlc / "features" / "active", "F042-in-flight"
    )

    resolved = feature_id_module.resolve_feature_path("F042", etc_sdlc)

    assert resolved is not None, "resolver returned None for active F042"
    assert resolved == expected.resolve(), (
        f"resolver returned {resolved!r}; expected {expected.resolve()!r}"
    )


def test_should_return_shipped_path_when_resolving_done_id(
    tmp_path: Path,
) -> None:
    """AC9 #2 + BR-003 priority 3: ``features/shipped/F<NNN>-*/`` hit."""
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    expected = _make_feature_dir(
        etc_sdlc / "features" / "shipped", "F050-done-and-tagged"
    )

    resolved = feature_id_module.resolve_feature_path("F050", etc_sdlc)

    assert resolved is not None, "resolver returned None for shipped F050"
    assert resolved == expected.resolve(), (
        f"resolver returned {resolved!r}; expected {expected.resolve()!r}"
    )


def test_should_return_rejections_path_when_resolving_rejected_id(
    tmp_path: Path,
) -> None:
    """AC9 #2 + BR-003 priority 4: ``rejections/F<NNN>-*/`` hit."""
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    expected = _make_feature_dir(
        etc_sdlc / "rejections", "F099-killed-idea"
    )

    resolved = feature_id_module.resolve_feature_path("F099", etc_sdlc)

    assert resolved is not None, "resolver returned None for rejected F099"
    assert resolved == expected.resolve(), (
        f"resolver returned {resolved!r}; expected {expected.resolve()!r}"
    )


def test_should_return_none_when_resolving_nonexistent_feature_id(
    tmp_path: Path,
) -> None:
    """AC9 #2 + BR-003 None case: feature_id absent at all four locations.

    Construct a populated ``.etc_sdlc/`` tree with several other features
    but NOT the queried ID; assert the resolver returns ``None`` (rather
    than raising or returning a partial path).
    """
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    _make_feature_dir(etc_sdlc / "features", "F001-other")
    _make_feature_dir(etc_sdlc / "features" / "active", "F002-other")
    _make_feature_dir(etc_sdlc / "features" / "shipped", "F003-other")
    _make_feature_dir(etc_sdlc / "rejections", "F004-other")

    resolved = feature_id_module.resolve_feature_path("F500", etc_sdlc)

    assert resolved is None, (
        f"resolver returned {resolved!r}; expected None for missing F500"
    )


# ── AC9 #3: allocator creates new dirs under features/active/ ────────────


def test_should_create_new_dir_under_active_when_allocating_next(
    tmp_path: Path,
) -> None:
    """AC9 #3 + BR-002: ``allocate_next`` lands new feature dirs under
    ``features/active/F<NNN>-<slug>/`` (NOT at the legacy flat path).

    Scenario: empty ``features_dir`` (no prior allocations); call
    ``allocate_next``; assert the returned path is under ``active/`` and
    NOT at the legacy flat sibling.
    """
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    features_dir = etc_sdlc / "features"

    feature_id_str, feature_path = feature_id_module.allocate_next(
        features_dir, "fresh-allocation"
    )

    # First allocation in an empty tree is F001.
    assert feature_id_str == "F001", (
        f"expected F001 on empty tree; got {feature_id_str}"
    )
    # The new dir lives under features/active/, not features/ directly.
    expected = features_dir / "active" / "F001-fresh-allocation"
    assert feature_path.resolve() == expected.resolve(), (
        f"allocator placed new dir at {feature_path}; expected {expected}"
    )
    # Legacy flat sibling MUST NOT exist for the new allocation.
    legacy_sibling = features_dir / "F001-fresh-allocation"
    assert not legacy_sibling.exists(), (
        f"allocator wrongly created legacy flat path {legacy_sibling}; "
        "F009 BR-002 mandates new dirs land under features/active/ only"
    )


# ── AC9 #4: /spec rejection-mv subprocess scenario ───────────────────────


def test_should_move_feature_to_rejections_when_spec_rejects_via_git_mv(
    tmp_path: Path,
) -> None:
    """AC9 #4 + BR-004: /spec writes ``rejected.md`` then ``git mv``s the
    feature dir from ``features/active/`` to ``rejections/``.

    Subprocess scenario: simulate /spec's flow — a feature dir at
    ``features/active/F<NNN>-<slug>/`` containing ``rejected.md`` is
    moved via ``git mv`` to ``rejections/F<NNN>-<slug>/``. After the mv:
    the source no longer exists, the target does, and ``git status``
    shows the rename canonically (we don't grep status here; the
    presence/absence of the dirs is sufficient evidence).
    """
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    _git_init(tmp_path)

    src = _make_feature_dir(
        etc_sdlc / "features" / "active", "F042-killed-idea"
    )
    (src / "rejected.md").write_text(
        "# Rejected\n\nClassifier reasoning here.\n",
        encoding="utf-8",
    )
    _git_add_commit(tmp_path, "seed F042 active")

    # Ensure the rejections parent exists (BR-004 mandates creation).
    rejections_parent = etc_sdlc / "rejections"
    rejections_parent.mkdir(parents=True, exist_ok=True)
    dst = rejections_parent / "F042-killed-idea"

    result = _git_mv(tmp_path, src, dst)

    assert result.returncode == 0, (
        f"git mv to rejections failed unexpectedly: "
        f"stderr={result.stderr!r} stdout={result.stdout!r}"
    )
    assert not src.exists(), (
        f"source path {src} still exists after git mv; expected removal"
    )
    assert dst.is_dir(), (
        f"target path {dst} not a directory after git mv"
    )
    # The rejected.md marker survives the rename.
    assert (dst / "rejected.md").is_file(), (
        f"rejected.md not present at {dst / 'rejected.md'} after mv"
    )


# ── AC9 #5: /build active→shipped mv subprocess scenario ─────────────────


def test_should_move_feature_from_active_to_shipped_when_build_closes(
    tmp_path: Path,
) -> None:
    """AC9 #5 + BR-005: /build's terminal-phase Step 7.5c ``git mv``s the
    feature dir from ``features/active/`` to ``features/shipped/``.

    Subprocess scenario: simulate /build's flow — a feature dir at
    ``features/active/F<NNN>-<slug>/`` containing release artifacts is
    moved via ``git mv`` to ``features/shipped/F<NNN>-<slug>/``. After
    the mv: the source no longer exists, the target does, and the
    release artifacts survive the rename.
    """
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    _git_init(tmp_path)

    src = _make_feature_dir(
        etc_sdlc / "features" / "active", "F050-shipped-soon"
    )
    (src / "release-notes.md").write_text(
        "# Release Notes F050\n",
        encoding="utf-8",
    )
    _git_add_commit(tmp_path, "seed F050 active")

    shipped_parent = etc_sdlc / "features" / "shipped"
    shipped_parent.mkdir(parents=True, exist_ok=True)
    dst = shipped_parent / "F050-shipped-soon"

    result = _git_mv(tmp_path, src, dst)

    assert result.returncode == 0, (
        f"git mv active->shipped failed unexpectedly: "
        f"stderr={result.stderr!r} stdout={result.stdout!r}"
    )
    assert not src.exists(), (
        f"source path {src} still exists after git mv"
    )
    assert dst.is_dir(), (
        f"target path {dst} not a directory after git mv"
    )
    assert (dst / "release-notes.md").is_file(), (
        "release-notes.md not present at target after mv; release "
        "artifacts must survive the rename"
    )


# ── AC9 #6: backward-compat for legacy flat F001-F008 paths ──────────────


def test_should_resolve_legacy_flat_path_for_forward_only_invariant(
    tmp_path: Path,
) -> None:
    """AC9 #6 + AC11 + BR-010: forward-only invariant.

    F001-F008 + the F006 placeholder remain at their existing legacy
    flat path AFTER F009 ships. The resolver's priority-1 location MUST
    find them so existing skills (release_notes, value_hypothesis, etc.)
    keep working without migration.

    Scenario: synthetic legacy flat dir at ``features/F<NNN>-<slug>/``
    representing one of F001-F008; resolver returns its path; assertion
    confirms the priority-1 lookup wins (not the active/ or shipped/
    siblings, which we deliberately leave absent).
    """
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    expected = _make_feature_dir(
        etc_sdlc / "features", "F005-build-completion-reports"
    )

    resolved = feature_id_module.resolve_feature_path("F005", etc_sdlc)

    assert resolved is not None, (
        "resolver returned None for legacy flat F005; the forward-only "
        "invariant requires F001-F008 to remain readable post-F009"
    )
    assert resolved == expected.resolve(), (
        f"resolver returned {resolved!r}; expected legacy flat "
        f"{expected.resolve()!r} (priority-1 location)"
    )
    # Sanity: confirm the priority-2/3/4 siblings genuinely do NOT exist
    # — otherwise this test would not be exercising the legacy fallback.
    assert not (etc_sdlc / "features" / "active").exists()
    assert not (etc_sdlc / "features" / "shipped").exists()
    assert not (etc_sdlc / "rejections").exists()


# ── AC9 #7: git mv failure semantics (target exists → abort) ─────────────


def test_should_abort_with_nonzero_exit_when_git_mv_target_exists(
    tmp_path: Path,
) -> None:
    """AC9 #7 + BR-004 + BR-005 + Edge Cases 6/7: ``git mv`` refuses when
    the resolved destination already exists; the caller (/spec or /build)
    must observe a non-zero exit code AND a stderr message containing
    enough context to remediate.

    Scenario mirrors the realistic operator-collision case: an operator
    has previously moved the feature dir into the rejections tree, so
    ``rejections/F<NNN>-<slug>/`` already exists AND already contains a
    nested ``F<NNN>-<slug>/`` from a prior failed/manual run. When /spec
    invokes ``git mv <src> rejections/F<NNN>-<slug>``, git's "move into
    existing dir" expansion resolves to ``rejections/F<NNN>-<slug>/
    F<NNN>-<slug>/`` — which already exists, so git refuses with
    ``destination already exists`` on stderr and a non-zero exit code.

    Asserting on the resolved-collision case (rather than a regular file
    at ``rejections/F<NNN>-<slug>``) is what /spec and /build actually
    observe in production, where the rejections/shipped parent is a
    directory holding prior moves.
    """
    etc_sdlc = _make_etc_sdlc_root(tmp_path)
    _git_init(tmp_path)

    slug = "F060-collision"
    src = _make_feature_dir(etc_sdlc / "features" / "active", slug)
    # Pre-existing target: rejections/<slug>/<slug>/ from a prior move.
    # This is the path git mv expands to when the operator-supplied
    # target ``rejections/<slug>`` is an existing directory — and the
    # path collision is what triggers the abort.
    nested_collision = etc_sdlc / "rejections" / slug / slug
    nested_collision.mkdir(parents=True, exist_ok=False)
    (nested_collision / "marker.txt").write_text(
        "pre-existing from prior run\n", encoding="utf-8"
    )
    _git_add_commit(tmp_path, "seed F060 active + colliding rejection")

    dst = etc_sdlc / "rejections" / slug

    result = _git_mv(tmp_path, src, dst)

    assert result.returncode != 0, (
        f"git mv unexpectedly succeeded with target pre-existing; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # stderr must be non-empty so the caller (/spec or /build) can
    # surface git's own error message verbatim per Security
    # Considerations item 4 (no silent swallow).
    assert result.stderr.strip() != "", (
        "git mv stderr was empty on collision; F009 contracts require "
        "the caller to surface git's stderr verbatim"
    )
    # Stderr names the collision so the operator can remediate.
    assert "destination already exists" in result.stderr.lower(), (
        f"git mv stderr missing 'destination already exists' substring; "
        f"got stderr={result.stderr!r}"
    )
    # Source must still exist — git mv is atomic on failure.
    assert src.exists(), (
        f"source path {src} was removed despite git mv failure; "
        "git mv should be atomic — source survives a refused move"
    )


# Module-level reference so static analyzers see ``pytest`` as used. The
# import is required by pytest's collection machinery via the tmp_path
# fixture used by the test functions above.
_ = pytest
