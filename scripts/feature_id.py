"""feature_id.py — Atomic F<NNN> + Ftmp-<hex> feature-ID allocator and slug helper.

<!-- forward-only: temp-ID allocation enforced from F023 release tag onward -->

Allocates per-project feature IDs of the form ``F<NNN>`` (3-digit zero-padded)
using POSIX-atomic ``os.mkdir`` with EEXIST retry. This is the canonical
race-free allocation pattern (see ``.etc_sdlc/features/metrics-and-release-
notes/gray-areas.md`` GA-006: POSIX.1 mkdir(2) atomicity).

F023 extends this module with a branch-local temp-ID form
``Ftmp-<8-char-hex>`` derived from ``secrets.token_hex(4)``. ``/spec``
allocates a temp ID; ``/build`` Step 7c renames the dir + ADRs to the
sequential ``F<NNN>`` form via ``resolve-final-id``.

Public API:

- ``allocate_next(features_dir, slug) -> (feature_id, feature_path)``
- ``allocate_temp(slug, etc_sdlc_root) -> (temp_id, feature_path)``
- ``resolve_final_id(temp_dir_name, etc_sdlc_root, *, repo_root) -> str``
- ``resolve_feature_path(feature_id, etc_sdlc_root) -> Path | None``
- ``slugify(title) -> str``
- ``FeatureIdExhaustedError`` — raised when the project hits the v1 F999 ceiling.
- ``TempIdCollisionError`` — raised when 3 token_hex retries fail to find a
  free Ftmp-<hex> slot (operationally astronomical; documented in EC-001).
- ``AdrRenameError`` — raised when ``git mv`` of a matching ADR fails during
  ``resolve_final_id``. Surface partial state via stderr; do NOT roll back.

Behavior is forward-only: existing slug-only directories (grandfathered per
GA-002) are ignored when computing the maximum F-ID. ID gaps are acceptable;
ID reuse is not (BR-002).

F009 layout (forward-only):
    .etc_sdlc/
        features/
            F001-…/                   # legacy flat (F001-F008 + F006)
            active/F<NNN>-…/          # in-flight work (new allocations)
            active/Ftmp-<hex>-…/      # F023 in-flight temp form
            shipped/F<NNN>-…/         # done audit-frozen work
        rejections/F<NNN>-…/          # /spec three-state classifier rejects
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ── Module constants ────────────────────────────────────────────────────

#: Regex matching a final-form feature directory name. Group 1 captures the integer ID.
_FEATURE_DIR_PATTERN = re.compile(r"^F(\d{3})(?:-.*)?$")

#: Regex matching a temp-form feature ID (no slug). Group 1 captures the hex value.
#: LEGACY: superseded by date-based form (see _DATED_ID_PATTERN). Kept for
#: backward-compat reads of any in-flight Ftmp-<hex> dirs from pre-revision
#: builds (F021-F026 era). See ADR superseding F023-001 for the rationale.
_TEMP_ID_PATTERN = re.compile(r"^Ftmp-([0-9a-f]{8})$")

#: Regex matching a temp-form feature directory name (with optional slug suffix).
#: LEGACY — see _TEMP_ID_PATTERN note.
_TEMP_DIR_PATTERN = re.compile(r"^Ftmp-([0-9a-f]{8})(?:-(.*))?$")

#: Regex matching an ADR filename written under the temp form.
#: Captures: 1) hex, 2) the trailing portion after the hex (e.g. "001-foo.md").
#: LEGACY — see _TEMP_ID_PATTERN note.
_ADR_TEMP_PATTERN = re.compile(r"^Ftmp-([0-9a-f]{8})-(.+\.md)$")

#: Regex matching a date-based feature ID / directory name.
#: Captures: 1) the date YYYY-MM-DD, 2) the slug-and-optional-collision-suffix.
#: Examples:
#:   F-2026-05-22-installer-rewrite     -> ("2026-05-22", "installer-rewrite")
#:   F-2026-05-22-fix-bug-2             -> ("2026-05-22", "fix-bug-2")
#:
#: Replaces the F023 Ftmp-<hex> form. The dir name IS the feature_id (no
#: separate -<slug> suffix segment); same-day same-slug collisions auto-suffix
#: with -2, -3, ... per the revision ADR.
_DATED_ID_PATTERN = re.compile(r"^F-(\d{4}-\d{2}-\d{2})-(.+)$")

#: Maximum feature ID supported by the v1 schema (3-digit zero-padded).
#: Hitting this ceiling raises FeatureIdExhaustedError rather than overflowing
#: silently. Upgrade to 4-digit IDs is deferred to a future PRD.
_MAX_FEATURE_ID = 999

#: Length cap for slugs. Mirrors scripts/tasks.py::_slugify_title (80 chars).
_SLUG_MAX_LEN = 80

#: Length cap for the temp-ID slug input (F023 security boundary 1). The
#: 80-char general slug cap stands for ``slugify``; ``allocate_temp`` further
#: restricts to 64 chars per design.md's slug-input boundary.
_TEMP_SLUG_MAX_LEN = 64

#: Fallback slug when the input title contains no alphanumeric characters.
_SLUG_FALLBACK = "task"

#: Subdirectory under ``features/`` for in-flight feature work (F009 BR-002).
_ACTIVE_SUBDIR = "active"

#: Subdirectory under ``features/`` for done audit-frozen feature work.
_SHIPPED_SUBDIR = "shipped"

#: Sibling directory of ``features/`` under ``.etc_sdlc/`` for rejection
#: trails written by /spec's three-state classifier.
_REJECTIONS_DIR = "rejections"

# NOTE: F023 introduced ``Ftmp-<hex>`` temp IDs and the associated
# ``_TEMP_ID_MAX_ATTEMPTS`` / ``_TEMP_ID_BYTES`` constants for the
# collision-retry loop driven by ``secrets.token_hex``. The revision ADR
# (supersedes F023-001) replaces that scheme with a date-based form
# (``F-YYYY-MM-DD-<slug>``) that needs no retry budget — same-day
# same-slug collisions auto-suffix deterministically. The constants and
# their import are removed; the legacy regex patterns above are kept
# for backward-compat reads of any Ftmp-<hex> dirs from F021-F026 era.


# ── Errors ──────────────────────────────────────────────────────────────


class FeatureIdExhaustedError(RuntimeError):
    """Raised when the project has consumed every available F<NNN> slot."""


class TempIdCollisionError(RuntimeError):
    """Raised when 3 consecutive temp-ID generations collide with existing dirs.

    Operationally astronomical at 4 bytes of entropy (birthday-problem 50%
    threshold ≈ 65k allocations). Documented in EC-001.
    """


class AdrRenameError(RuntimeError):
    """Raised when ``git mv`` fails on a matching ADR during resolve-final-id.

    EC-005: surface git's stderr verbatim; do NOT roll back the dir rename.
    Partial state surfaced; operator remediates manually.
    """


# ── Public API ──────────────────────────────────────────────────────────


def slugify(title: str) -> str:
    """Convert a free-form title into a kebab-case feature-directory slug.

    Mirrors ``scripts/tasks.py::_slugify_title`` for cross-tool parity:

    1. Lowercase.
    2. Replace runs of non-alphanumeric characters with a single hyphen.
    3. Strip leading/trailing hyphens.
    4. Truncate to ``_SLUG_MAX_LEN`` characters; re-strip trailing hyphens
       so a truncation never leaves a dangling separator.
    5. Fall back to ``_SLUG_FALLBACK`` if the result would be empty.
    """
    lowered = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not slug:
        return _SLUG_FALLBACK
    if len(slug) > _SLUG_MAX_LEN:
        slug = slug[:_SLUG_MAX_LEN].rstrip("-") or _SLUG_FALLBACK
    return slug


def allocate_next(features_dir: Path, slug: str) -> tuple[str, Path]:
    """Allocate the next available F<NNN> feature directory atomically.

    Args:
        features_dir: Project-scoped features root (e.g. ``.etc_sdlc/features``).
            The ``active/`` subdirectory under this root is created if absent
            (F009 BR-002); new feature dirs land at
            ``<features_dir>/active/F<NNN>-<slug>/``.
        slug: Already-slugified suffix appended to the F-ID directory name.

    Returns:
        ``(feature_id, feature_path)`` where ``feature_id`` is ``"F<NNN>"`` and
        ``feature_path`` is the freshly-created directory under ``active/``.

    Raises:
        FeatureIdExhaustedError: When all F001–F999 slots are consumed.

    Concurrency:
        Uses ``os.mkdir`` which is POSIX-atomic for the F<NNN>-<slug> child.
        On ``FileExistsError`` the function re-reads the maximum existing
        F-ID and retries at +1, so two racing callers receive distinct IDs
        (BR-003 / AC-002).

    Layout (F009 BR-002):
        Max-ID scan rglobs across ``features_dir``'s parent (``.etc_sdlc/``)
        so legacy flat F001-F008 plus ``active/``, ``shipped/``, and
        ``rejections/`` all contribute. New dirs land under ``active/`` only.
    """
    active_dir = features_dir / _ACTIVE_SUBDIR
    active_dir.mkdir(parents=True, exist_ok=True)

    while True:
        next_id = _scan_max_feature_id(features_dir) + 1
        if next_id > _MAX_FEATURE_ID:
            raise FeatureIdExhaustedError(
                f"Project has reached the v1 feature ID ceiling "
                f"({_MAX_FEATURE_ID})"
            )

        feature_id_str = f"F{next_id:03d}"
        candidate = active_dir / f"{feature_id_str}-{slug}"

        try:
            os.mkdir(candidate)
        except FileExistsError:
            # Lost the race — another writer won this slot. Re-scan and retry.
            continue

        return feature_id_str, candidate


def allocate_temp(slug: str, etc_sdlc_root: Path) -> tuple[str, Path]:
    """Allocate a date-based feature ID and create the active feature dir.

    REVISION (supersedes F023 BR-001): returns ``F-YYYY-MM-DD-<slug>`` form
    using the current UTC date. The dir name IS the feature_id (no separate
    ``-<slug>`` suffix). On same-day same-slug collision, auto-suffixes
    with ``-2``, ``-3``, ... until a free slot is found.

    Side effect: creates ``<etc_sdlc_root>/features/active/<feature_id>/``
    with an initial ``state.yaml`` carrying ``feature_id: <id>``.

    Why the date-based form (vs the original ``Ftmp-<hex>``): the hex
    form was opaque ("Ftmp-5afddbce-installer-rewrite" carries no
    semantic content), required a temp→final rename at /build Step 7c
    (extra plumbing), and was hard to scan in ``ls`` output. The date
    form sorts chronologically by lexicographic order, is cross-machine
    collision-safe (date + slug combo is near-unique), and never needs
    a rename step.

    Backward compatibility: this function is still called
    ``allocate_temp`` and the CLI subcommand is still ``allocate-temp``
    so existing skill bodies (SKILL.md) keep working unchanged. The
    only observable change is the FORMAT of the returned feature_id.

    Args:
        slug: Caller-provided kebab-case slug. Rejected (``ValueError``)
            if it contains ``..``, is an absolute path, or exceeds 64
            chars (security boundary 1 in design.md).
        etc_sdlc_root: Path to the project's ``.etc_sdlc/`` directory.
            The ``features/active/`` subtree is created if absent.

    Returns:
        ``(feature_id, feature_path)``. ``feature_id`` matches
        ``^F-\\d{4}-\\d{2}-\\d{2}-.+$``; ``feature_path`` is the freshly-
        created directory at ``.etc_sdlc/features/active/<feature_id>/``.

    Raises:
        ValueError: When ``slug`` fails the security checks.
        RuntimeError: When same-day same-slug collisions exhaust the
            99-attempt safety bound (operationally impossible — would
            require 99 features with the same slug shipped on the
            same UTC day).
    """
    _validate_temp_slug(slug)
    active_dir = etc_sdlc_root / "features" / _ACTIVE_SUBDIR
    active_dir.mkdir(parents=True, exist_ok=True)

    today = _utc_now_iso8601()[:10]  # YYYY-MM-DD slice from ISO-8601
    base_id = f"F-{today}-{slug}"

    # Auto-suffix on collision: F-DATE-slug, then F-DATE-slug-2, -3, ...
    candidate_id = base_id
    suffix = 1
    while True:
        candidate = active_dir / candidate_id
        try:
            os.mkdir(candidate)
            break
        except FileExistsError:
            suffix += 1
            if suffix > 99:
                raise RuntimeError(
                    f"same-day same-slug collision exhausted after 99 "
                    f"attempts at {base_id!r}; operationally impossible — "
                    f"investigate systemic state."
                )
            candidate_id = f"{base_id}-{suffix}"

    _write_initial_state_yaml(candidate, candidate_id)
    return candidate_id, candidate


def resolve_final_id(
    temp_dir_name: str,
    etc_sdlc_root: Path,
    *,
    repo_root: Path,
) -> str:
    """Allocate the final F-ID and rename the feature dir + ADRs.

    F023 BR-002 / BR-008. Steps (semantically atomic from operator perspective):

    1. Validate input matches ``Ftmp-<hex>-<slug>`` shape; on ``F<NNN>``
       input, return short-circuit (EC-003 — already final).
    2. Call ``allocate_next`` to get the next sequential ``F<NNN>``.
    3. Rename ``.etc_sdlc/features/active/Ftmp-<hex>-<slug>/`` to
       ``.etc_sdlc/features/active/F<NNN>-<slug>/`` via ``shutil.move``
       (``.etc_sdlc/`` is gitignored; mirrors F022's pattern).
    4. Rename ``docs/adrs/Ftmp-<hex>-NN-*.md`` to ``docs/adrs/F<NNN>-NN-*.md``
       via ``git mv`` argv-style (``docs/adrs/`` IS tracked).
    5. Append ``id_history[final]`` entry to the renamed feature's
       ``state.yaml``.

    On any sub-step failure, surface partial state via raised exception with
    descriptive ``args`` (operator remediates manually). The dir rename is
    NOT rolled back on ADR-rename failure (EC-005).

    Args:
        temp_dir_name: The feature dir basename. Either ``Ftmp-<hex>-<slug>``
            (active, rename required) or ``F<NNN>-<slug>`` (EC-003 short
            circuit — already final).
        etc_sdlc_root: Path to the project's ``.etc_sdlc/`` directory.
        repo_root: Repo root used for ``git mv`` ``cwd``. ``docs/adrs/`` is
            resolved relative to this path.

    Returns:
        The final ``F<NNN>`` identifier.

    Raises:
        ValueError: When ``temp_dir_name`` shape is unrecognized.
        FileNotFoundError: When the feature dir does not exist under
            ``<etc_sdlc_root>/features/active/``.
        AdrRenameError: When ``git mv`` fails on a matching ADR (EC-005).
        FeatureIdExhaustedError: Propagated from ``allocate_next``.
    """
    final_match = _FEATURE_DIR_PATTERN.match(temp_dir_name)
    if final_match is not None:
        # EC-003: already in final F<NNN> form (legacy F001-F026 path).
        # No rename needed.
        return f"F{int(final_match.group(1)):03d}"

    dated_match = _DATED_ID_PATTERN.match(temp_dir_name)
    if dated_match is not None:
        # Date-based form is the final form by construction. No rename;
        # /build Step 7c.0 treats this as a no-op. The dir name itself
        # IS the feature_id.
        return temp_dir_name

    temp_match = _TEMP_DIR_PATTERN.match(temp_dir_name)
    if temp_match is None:
        raise ValueError(
            f"unrecognized feature directory name {temp_dir_name!r}; "
            f"expected F-YYYY-MM-DD-<slug> (date-based) or "
            f"F<NNN>-<slug> (legacy sequential) or "
            f"Ftmp-<hex>-<slug> (legacy temp form)"
        )

    temp_hex = temp_match.group(1)
    slug = temp_match.group(2) or ""
    temp_id = f"Ftmp-{temp_hex}"

    active_dir = etc_sdlc_root / "features" / _ACTIVE_SUBDIR
    source_dir = active_dir / temp_dir_name
    if not source_dir.is_dir():
        raise FileNotFoundError(
            f"temp feature directory not found: {source_dir}"
        )

    # Step 2: allocate the final F<NNN>. The os.mkdir inside allocate_next
    # claims the slot atomically; we then move it aside to overlay the
    # contents of source_dir onto the final path.
    final_id, claimed_path = allocate_next(active_dir.parent, slug)
    # claimed_path is now an EMPTY directory under active/. Remove it so
    # shutil.move can land the temp dir at exactly that location.
    claimed_path.rmdir()
    shutil.move(str(source_dir), str(claimed_path))

    # Step 4: rename ADRs under docs/adrs/ via `git mv` (argv-style).
    _rename_temp_adrs_via_git_mv(
        temp_hex=temp_hex,
        final_id=final_id,
        repo_root=repo_root,
    )

    # Step 5: append id_history[final] to state.yaml.
    _append_final_id_history(claimed_path, temp_id=temp_id, final_id=final_id)

    return final_id


def resolve_feature_path(feature_id: str, etc_sdlc_root: Path) -> Path | None:
    """Return the directory for ``feature_id`` under ``etc_sdlc_root``, or None.

    Accepts both pre-F023 ``F<NNN>`` and F023 ``Ftmp-<hex>`` forms (BR-004).
    Checks four locations in F009 lifecycle priority order:

    1. ``<etc_sdlc_root>/features/<id>-*/``         (legacy flat — F001-F008)
    2. ``<etc_sdlc_root>/features/active/<id>-*/``  (in-flight work)
    3. ``<etc_sdlc_root>/features/shipped/<id>-*/`` (done audit-frozen work)
    4. ``<etc_sdlc_root>/rejections/<id>-*/``       (rejection trails)

    Args:
        feature_id: Either ``F<NNN>`` (no slug) or ``Ftmp-<8-hex>``. MUST
            match one of the two regexes; otherwise this function returns
            ``None`` without touching the filesystem (path-traversal guard
            per F009 Security Considerations item 1).
        etc_sdlc_root: Path to the project's ``.etc_sdlc/`` directory.

    Returns:
        The first matching directory as a resolved ``Path``, or ``None`` if
        no directory exists at any of the four locations.

    Read-only contract:
        Does not open, read contents of, or modify any file.
    """
    if not _is_resolvable_feature_id(feature_id):
        return None

    features_root = etc_sdlc_root / "features"
    search_locations = (
        features_root,
        features_root / _ACTIVE_SUBDIR,
        features_root / _SHIPPED_SUBDIR,
        etc_sdlc_root / _REJECTIONS_DIR,
    )

    # For date-based IDs, the dir name IS the feature_id (no separate
    # ``-<slug>`` suffix). Check exact-match first; the legacy glob form
    # below catches the F<NNN>/Ftmp-<hex> cases where the slug lives in
    # a suffix segment.
    is_dated = bool(_DATED_ID_PATTERN.match(feature_id))
    glob_pattern = f"{feature_id}-*"

    for location in search_locations:
        if not location.is_dir():
            continue
        if is_dated:
            exact = location / feature_id
            if exact.is_dir():
                return exact.resolve()
        for match in location.glob(glob_pattern):
            if match.is_dir():
                return match.resolve()

    return None


# ── Internals ───────────────────────────────────────────────────────────


def _is_resolvable_feature_id(feature_id: str) -> bool:
    """True iff ``feature_id`` matches any of the three ID form regexes.

    Recognized forms:
      1. ``F<NNN>``                 (legacy sequential, F001-F026 era)
      2. ``Ftmp-<8-hex>``           (legacy temp form, F023 era; superseded)
      3. ``F-YYYY-MM-DD-<slug>``    (current — date-based)
    """
    if _FEATURE_DIR_PATTERN.match(feature_id):
        return True
    if _TEMP_ID_PATTERN.match(feature_id):
        return True
    if _DATED_ID_PATTERN.match(feature_id):
        return True
    return False


def _validate_temp_slug(slug: str) -> None:
    """Reject slugs that contain path-traversal markers or exceed the cap.

    Security boundary 1 in design.md: caps length, forbids ``..`` and
    absolute paths.
    """
    if not slug:
        raise ValueError("temp-ID slug must not be empty")
    if len(slug) > _TEMP_SLUG_MAX_LEN:
        raise ValueError(
            f"temp-ID slug exceeds {_TEMP_SLUG_MAX_LEN}-char cap: "
            f"{len(slug)} chars"
        )
    if ".." in slug:
        raise ValueError(
            f"temp-ID slug contains path-traversal marker '..': {slug!r}"
        )
    if slug.startswith("/") or slug.startswith("\\"):
        raise ValueError(
            f"temp-ID slug must not be an absolute path: {slug!r}"
        )
    if "/" in slug or "\\" in slug:
        raise ValueError(
            f"temp-ID slug must not contain path separators: {slug!r}"
        )


def _write_initial_state_yaml(feature_dir: Path, temp_id: str) -> None:
    """Write the initial state.yaml with id_history[0] = {form: temp, ...}."""
    state = {
        "id_history": [
            {
                "form": "temp",
                "value": temp_id,
                "written_at": _utc_now_iso8601(),
            }
        ]
    }
    (feature_dir / "state.yaml").write_text(yaml.safe_dump(state, sort_keys=False))


def _append_final_id_history(
    feature_dir: Path, *, temp_id: str, final_id: str
) -> None:
    """Append the final-form id_history entry to the renamed dir's state.yaml.

    Creates the file if absent (EC-006: pre-F023 features without
    id_history get the field bootstrapped). Reads existing entries via
    ``yaml.safe_load`` and re-emits via ``yaml.safe_dump``.
    """
    state_path = feature_dir / "state.yaml"
    state: dict[str, Any]
    if state_path.is_file():
        loaded = yaml.safe_load(state_path.read_text())
        state = loaded if isinstance(loaded, dict) else {}
    else:
        state = {}

    history = state.get("id_history")
    if not isinstance(history, list):
        history = [
            {
                "form": "temp",
                "value": temp_id,
                "written_at": _utc_now_iso8601(),
            }
        ]
    history.append(
        {
            "form": "final",
            "value": final_id,
            "written_at": _utc_now_iso8601(),
        }
    )
    state["id_history"] = history
    state_path.write_text(yaml.safe_dump(state, sort_keys=False))


def _rename_temp_adrs_via_git_mv(
    *,
    temp_hex: str,
    final_id: str,
    repo_root: Path,
) -> None:
    """Rename docs/adrs/Ftmp-<hex>-*.md to docs/adrs/F<NNN>-*.md via git mv.

    Iterates ``docs/adrs/`` for any filename starting ``Ftmp-<hex>-`` and
    invokes ``git mv <old> <new>`` (argv-style, never shell string) for each
    match. On the first ``git mv`` non-zero exit, raises ``AdrRenameError``
    with git's stderr in ``args`` so the operator sees the failure verbatim
    (EC-005). The dir rename is NOT rolled back.

    Silently no-ops when ``docs/adrs/`` is absent (EC-004).
    """
    adr_dir = repo_root / "docs" / "adrs"
    if not adr_dir.is_dir():
        return

    prefix = f"Ftmp-{temp_hex}-"
    for entry in sorted(adr_dir.iterdir()):
        if not entry.is_file():
            continue
        if not entry.name.startswith(prefix):
            continue
        match = _ADR_TEMP_PATTERN.match(entry.name)
        if match is None:
            # Defensive: name starts with the prefix but doesn't match the
            # full pattern (e.g., wrong extension). Skip rather than guess.
            continue
        suffix = match.group(2)  # e.g. "001-foo.md"
        new_name = f"{final_id}-{suffix}"
        new_path = adr_dir / new_name
        result = subprocess.run(
            ["git", "mv", str(entry), str(new_path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AdrRenameError(
                f"git mv failed for {entry.name} -> {new_name}: "
                f"{result.stderr.strip()}"
            )


def _scan_max_feature_id(features_dir: Path) -> int:
    """Return the highest F<NNN> id present under ``.etc_sdlc/``, or 0.

    F009 BR-001 update: scan rglobs across the ``.etc_sdlc/`` root (derived
    from ``features_dir.parent`` when ``features_dir.name == "features"``)
    so the legacy flat path, ``features/active/``, ``features/shipped/``,
    and ``rejections/`` all contribute to the max-id calculation.

    Non-feature directories (legacy slug-only entries grandfathered per
    GA-002, plus any unrelated content) are ignored.

    Args:
        features_dir: Project-scoped features root passed by ``allocate_next``.
            Backward-compat: when this path's basename is ``features``, the
            ``.etc_sdlc/`` root is derived as ``features_dir.parent``;
            otherwise the path itself is treated as the scan root. If the
            scan root does not exist on disk, the function returns ``0``.
    """
    scan_root = (
        features_dir.parent if features_dir.name == "features" else features_dir
    )
    if not scan_root.is_dir():
        return 0

    highest = 0
    for entry in scan_root.rglob("F*"):
        if not entry.is_dir():
            continue
        match = _FEATURE_DIR_PATTERN.match(entry.name)
        if match is None:
            continue
        value = int(match.group(1))
        if value > highest:
            highest = value
    return highest


def _utc_now_iso8601() -> str:
    """Return the current UTC instant as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── CLI ─────────────────────────────────────────────────────────────────


def _cmd_allocate_next(features_dir: str, slug: str) -> int:
    """Allocate the next F<NNN> directory and print ``<id> <path>`` to stdout.

    Returns a process exit code: 0 on success, non-zero with a stderr
    message on failure. Skills invoke this as
    ``python3 scripts/feature_id.py allocate-next <features_dir> <slug>``
    so the contract is intentionally narrow: one line, space-separated,
    newline-terminated.
    """
    try:
        feature_id_str, feature_path = allocate_next(Path(features_dir), slug)
    except FeatureIdExhaustedError as exc:
        print(f"feature-id exhausted: {exc}", file=sys.stderr)
        return 2
    except (OSError, FileNotFoundError, NotADirectoryError) as exc:
        print(f"failed to allocate feature dir under {features_dir!r}: {exc}",
              file=sys.stderr)
        return 1

    print(f"{feature_id_str} {feature_path}")
    return 0


def _cmd_allocate_temp(etc_sdlc_root: str, slug: str) -> int:
    """Allocate a temp F-ID and print ``<temp_id> <path>`` to stdout.

    F023 contract: same shape as ``allocate-next`` so ``/spec``'s parsing
    logic stays unchanged. One newline-terminated line, space-separated.
    """
    try:
        temp_id, feature_path = allocate_temp(slug, Path(etc_sdlc_root))
    except ValueError as exc:
        print(f"invalid slug for allocate-temp: {exc}", file=sys.stderr)
        return 1
    except TempIdCollisionError as exc:
        print(f"temp-id collision: {exc}", file=sys.stderr)
        return 2
    except AttributeError as exc:
        # EC-009: FIPS-restricted Python lacking secrets.token_hex.
        print(
            f"secrets.token_hex unavailable on this Python build: {exc}",
            file=sys.stderr,
        )
        return 3
    except (OSError, FileNotFoundError, NotADirectoryError) as exc:
        print(
            f"failed to allocate temp feature dir under "
            f"{etc_sdlc_root!r}: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"{temp_id} {feature_path}")
    return 0


def _cmd_resolve_final_id(etc_sdlc_root: str, temp_dir_name: str) -> int:
    """Resolve a temp feature dir to its final F<NNN> form.

    EC-003 short-circuit: on already-final input, prints the F<NNN> portion
    to stdout, writes a note to stderr, exits 0.
    """
    repo_root = Path(etc_sdlc_root).resolve().parent
    if _FEATURE_DIR_PATTERN.match(temp_dir_name):
        # EC-003: short-circuit on already-final input.
        try:
            final_id = resolve_final_id(
                temp_dir_name, Path(etc_sdlc_root), repo_root=repo_root
            )
        except ValueError as exc:
            print(f"resolve-final-id error: {exc}", file=sys.stderr)
            return 1
        print(
            "feature already has final ID; no rename needed.",
            file=sys.stderr,
        )
        print(final_id)
        return 0

    try:
        final_id = resolve_final_id(
            temp_dir_name, Path(etc_sdlc_root), repo_root=repo_root
        )
    except FileNotFoundError as exc:
        print(f"resolve-final-id error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"resolve-final-id error: {exc}", file=sys.stderr)
        return 1
    except AdrRenameError as exc:
        # EC-005: surface git's stderr verbatim; do NOT roll back.
        print(f"resolve-final-id ADR rename failure: {exc}", file=sys.stderr)
        return 2
    except FeatureIdExhaustedError as exc:
        print(f"feature-id exhausted: {exc}", file=sys.stderr)
        return 3

    print(final_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the feature_id CLI.

    Subcommands:
        allocate-next <features_dir> <slug>
            Allocate the next available F<NNN> directory under
            ``<features_dir>`` and print ``<feature_id> <feature_path>``
            to stdout.
        allocate-temp <etc_sdlc_root> <slug>
            Allocate a branch-local Ftmp-<hex> feature dir under
            ``<etc_sdlc_root>/features/active/`` and print
            ``<temp_id> <feature_path>`` to stdout (F023 BR-001).
        resolve-final-id <etc_sdlc_root> <feature_dir_name>
            Rename a temp feature dir to its final F<NNN> form,
            renaming matching ADRs via ``git mv`` (F023 BR-002).
    """
    parser = argparse.ArgumentParser(
        prog="feature_id.py",
        description=(
            "Atomic F<NNN> feature-ID allocator + F023 Ftmp-<hex> "
            "temp-ID lifecycle."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    alloc = sub.add_parser(
        "allocate-next",
        help="Allocate the next F<NNN> feature directory.",
    )
    alloc.add_argument(
        "features_dir",
        help="Path to the project-scoped features root "
             "(e.g. .etc_sdlc/features).",
    )
    alloc.add_argument(
        "slug",
        help="Already-slugified suffix appended to the F-ID directory name.",
    )

    alloc_temp = sub.add_parser(
        "allocate-temp",
        help="Allocate a branch-local Ftmp-<hex> feature directory (F023).",
    )
    alloc_temp.add_argument(
        "etc_sdlc_root",
        help="Path to the project's .etc_sdlc/ root directory.",
    )
    alloc_temp.add_argument(
        "slug",
        help="Caller-provided kebab-case slug "
             "(rejected on '..', '/', or >64 chars).",
    )

    resolve = sub.add_parser(
        "resolve-final-id",
        help="Rename a temp feature dir to its final F<NNN> form (F023).",
    )
    resolve.add_argument(
        "etc_sdlc_root",
        help="Path to the project's .etc_sdlc/ root directory.",
    )
    resolve.add_argument(
        "feature_dir_name",
        help="Feature dir basename (Ftmp-<hex>-<slug> or F<NNN>-<slug>).",
    )

    args = parser.parse_args(argv)

    if args.command == "allocate-next":
        return _cmd_allocate_next(args.features_dir, args.slug)
    if args.command == "allocate-temp":
        return _cmd_allocate_temp(args.etc_sdlc_root, args.slug)
    if args.command == "resolve-final-id":
        return _cmd_resolve_final_id(args.etc_sdlc_root, args.feature_dir_name)

    # argparse with required=True should never let us reach here.
    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
