#!/usr/bin/env python3
"""completion_report.py — Per-phase completion-report writer for /build Step 6d.5.

The /build skill (Step 6d, after the phase-done git tag) calls this helper
to emit a properly-formatted ``completion-report.md`` under
``<feature_dir>/build/phase-<N>/``. The output format is fixed by the
reader contract in ``scripts/release_notes.py`` (see its module docstring
and the ``_parse_report`` / ``_split_sections`` helpers): a top-level
``# Phase <N> — <title>`` heading followed by four sections —
``## PRD``, ``## Acceptance Criteria``, ``## Deferred Items``,
``## Known Limitations``.

Per F005 spec:
- BR-001: ``write`` CLI subcommand with ``--feature-dir``, ``--phase``,
  ``--prd-title``, ``--prd-id``, plus four ``--*-file`` flags pointing at
  newline-delimited text files (one bullet per line) for the AC pass/fail,
  deferred, and limitations sections.
- BR-002: emit the markdown shape verbatim; empty sections render as the
  single literal ``- (none)`` line.
- Security: validate that ``--feature-dir`` resolves under
  ``.etc_sdlc/features/`` (path-traversal guard); strip control characters
  and cap each bullet at 1024 chars (markdown/log injection guard); no
  subprocess, no network, no shell.
- Convention: every ``open``/``read_text``/``write_text`` passes
  ``encoding="utf-8"`` per F004's PEP 686 future-proofing.

The helper is pure local-filesystem; it never spawns subprocesses or
touches the network. Failure paths log to stderr and return exit code 1;
success returns 0.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── Module constants ────────────────────────────────────────────────────

#: Filename written under ``<feature_dir>/build/phase-<N>/``. Matches
#: ``scripts/release_notes.py::REPORT_FILENAME`` exactly so the writer
#: and reader agree on disk layout.
REPORT_FILENAME = "completion-report.md"

#: Required prefix (relative to the cwd / repo root) under which the
#: resolved ``--feature-dir`` must live. Anything outside this prefix is
#: refused with a stderr message + exit 1 (path-traversal guard, F005
#: Security Considerations).
ALLOWED_FEATURE_DIR_PREFIX = Path(".etc_sdlc/features")

#: Per-bullet length cap. Lines from the four input files are truncated
#: to this many characters before being emitted into the report. Bullets
#: longer than this are truncated silently (per F005 Security
#: Considerations: "truncate excess; do not error").
MAX_BULLET_LENGTH = 1024

#: Control-character stripping regex. Matches C0 controls (``\x00``-
#: ``\x1f``) plus DEL (``\x7f``). Applied to every bullet line read from
#: an input file before that bullet is emitted into the report.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")

#: Literal placeholder emitted when a section's input list is empty (or
#: every line in the input file became empty after sanitization).
EMPTY_SECTION_PLACEHOLDER = "- (none)"


# ── Public API ──────────────────────────────────────────────────────────


def render_report(
    *,
    phase: int,
    prd_title: str,
    prd_id: str,
    ac_passed: list[str],
    ac_failed: list[str],
    deferred: list[str],
    limitations: list[str],
) -> str:
    """Render a completion-report.md body as a single markdown string.

    Pure: takes already-sanitized inputs and returns the markdown the
    caller will write to disk. Empty sections produce the literal
    ``- (none)`` line. AC entries are emitted as ``- [x]``/``- [ ]``
    checkbox bullets so ``release_notes.py`` can split them into
    pass/fail.

    The function is intentionally side-effect-free so unit tests can
    exercise it without touching the filesystem.
    """
    lines: list[str] = []
    lines.append(f"# Phase {phase} — {prd_title}")
    lines.append("")
    lines.append("## PRD")
    lines.append(f"- Title: {prd_title}")
    lines.append(f"- ID: {prd_id}")
    lines.append("")
    lines.append("## Acceptance Criteria")
    lines.extend(_render_ac_section(ac_passed, ac_failed))
    lines.append("")
    lines.append("## Deferred Items")
    lines.extend(_render_bullet_section(deferred))
    lines.append("")
    lines.append("## Known Limitations")
    lines.extend(_render_bullet_section(limitations))
    # Trailing newline so the file ends cleanly when written.
    return "\n".join(lines) + "\n"


def sanitize_bullet(line: str) -> str:
    """Strip control characters and cap length for one bullet line.

    Returns the cleaned text. The caller decides whether the result is
    empty (in which case the line should be skipped per F005 Security
    Considerations: "Skip lines that become empty after sanitization").
    """
    cleaned = _CONTROL_CHAR_RE.sub("", line)
    cleaned = cleaned.rstrip("\r\n").strip()
    if len(cleaned) > MAX_BULLET_LENGTH:
        cleaned = cleaned[:MAX_BULLET_LENGTH]
    return cleaned


def read_bullet_file(path: Path | None) -> list[str]:
    """Read a newline-delimited bullet file and return sanitized entries.

    Each non-empty line becomes one bullet. Lines are stripped of control
    characters and capped at ``MAX_BULLET_LENGTH``. Lines that become
    empty after sanitization are dropped. ``None`` or a non-existent path
    yields an empty list (treated as "no items" by the renderer).
    """
    if path is None:
        return []
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    bullets: list[str] = []
    for line in raw.splitlines():
        cleaned = sanitize_bullet(line)
        if not cleaned:
            continue
        bullets.append(cleaned)
    return bullets


# ── Internals ───────────────────────────────────────────────────────────


def _render_ac_section(passed: list[str], failed: list[str]) -> list[str]:
    """Emit ``- [x]`` and ``- [ ]`` bullets, or the empty placeholder."""
    if not passed and not failed:
        return [EMPTY_SECTION_PLACEHOLDER]
    lines: list[str] = []
    for item in passed:
        lines.append(f"- [x] {item}")
    for item in failed:
        lines.append(f"- [ ] {item}")
    return lines


def _render_bullet_section(items: list[str]) -> list[str]:
    """Emit one ``- <text>`` line per item, or the empty placeholder."""
    if not items:
        return [EMPTY_SECTION_PLACEHOLDER]
    return [f"- {item}" for item in items]


def _resolve_under_features_root(feature_dir: Path) -> Path | None:
    """Resolve ``feature_dir`` and confirm it lives under the allowed prefix.

    The repo root is the cwd at script invocation. We resolve both the
    cwd and the feature dir to absolute paths, then check that the
    feature dir is a descendant of ``<cwd>/.etc_sdlc/features``. Returns
    the resolved path on success, ``None`` on path-traversal violation.

    ``Path.resolve(strict=False)`` is used so we can validate paths that
    do not yet exist on disk (the ``build/phase-<N>/`` directory is
    created by the writer); the prefix check still works because we
    compare resolved absolute paths.
    """
    cwd = Path.cwd().resolve()
    allowed_root = (cwd / ALLOWED_FEATURE_DIR_PREFIX).resolve()
    resolved = feature_dir.resolve()
    try:
        resolved.relative_to(allowed_root)
    except ValueError:
        return None
    return resolved


# ── CLI ─────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser. Single ``write`` subcommand for now.

    The CLI shape (subcommand + flags) leaves room for future verbs
    without breaking callers. Mirrors the convention established by
    ``git_tags.py write-tag``, ``release_notes.py build``, and
    ``feature_id.py allocate-next``.
    """
    parser = argparse.ArgumentParser(
        prog="completion_report.py",
        description=(
            "Per-phase completion-report writer for /build Step 6d.5. "
            "Emits a release_notes.py-compatible markdown report under "
            "<feature_dir>/build/phase-<N>/completion-report.md."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    write_p = sub.add_parser(
        "write",
        help="Write a completion-report.md for one phase.",
    )
    write_p.add_argument(
        "--feature-dir",
        required=True,
        type=Path,
        help=(
            "Path to a feature directory (must resolve under "
            ".etc_sdlc/features/ relative to the cwd)."
        ),
    )
    write_p.add_argument(
        "--phase",
        required=True,
        type=int,
        help="Phase number (non-negative integer; 0 is the flat-fallback phase).",
    )
    write_p.add_argument(
        "--prd-title",
        required=True,
        help="PRD title from <feature_dir>/spec.md's first heading.",
    )
    write_p.add_argument(
        "--prd-id",
        required=True,
        help="Feature ID from <feature_dir>/state.yaml's feature_id field.",
    )
    write_p.add_argument(
        "--ac-passed-file",
        type=Path,
        default=None,
        help="Path to a newline-delimited file of passed AC bullets.",
    )
    write_p.add_argument(
        "--ac-failed-file",
        type=Path,
        default=None,
        help="Path to a newline-delimited file of failed AC bullets.",
    )
    write_p.add_argument(
        "--deferred-file",
        type=Path,
        default=None,
        help="Path to a newline-delimited file of deferred-item bullets.",
    )
    write_p.add_argument(
        "--limitations-file",
        type=Path,
        default=None,
        help="Path to a newline-delimited file of known-limitation bullets.",
    )
    return parser


def _cmd_write(args: argparse.Namespace) -> int:
    """Handle ``write``: validate, render, and write the report file.

    Returns a process exit code: 0 on success, 1 on a validation or I/O
    error (with stderr message). Never raises on the documented failure
    modes; unexpected exceptions propagate.
    """
    # 1. Path-traversal guard. Refuse feature_dirs that escape the
    #    allowed ``.etc_sdlc/features/`` prefix (resolved against the
    #    cwd at invocation time).
    resolved_feature_dir = _resolve_under_features_root(args.feature_dir)
    if resolved_feature_dir is None:
        print(
            f"error: --feature-dir must resolve under "
            f"{ALLOWED_FEATURE_DIR_PREFIX.as_posix()}/ "
            f"(got {args.feature_dir})",
            file=sys.stderr,
        )
        return 1

    # 2. Phase number must be a non-negative integer. argparse already
    #    enforces ``int``; we additionally reject negatives. Phase 0 is the
    #    flat-fallback phase introduced by the phase→wave decoupling (#35),
    #    so it MUST be accepted (#43).
    if args.phase < 0:
        print(
            f"error: --phase must be a non-negative integer (got {args.phase})",
            file=sys.stderr,
        )
        return 1

    # 3. Read + sanitize each input list. Missing/None paths yield empty
    #    lists, which the renderer turns into the ``- (none)`` literal.
    try:
        ac_passed = read_bullet_file(args.ac_passed_file)
        ac_failed = read_bullet_file(args.ac_failed_file)
        deferred = read_bullet_file(args.deferred_file)
        limitations = read_bullet_file(args.limitations_file)
    except OSError as exc:
        print(
            f"error: failed to read bullet input file: {exc}",
            file=sys.stderr,
        )
        return 1

    # 4. Render the markdown body from sanitized inputs.
    body = render_report(
        phase=args.phase,
        prd_title=args.prd_title,
        prd_id=args.prd_id,
        ac_passed=ac_passed,
        ac_failed=ac_failed,
        deferred=deferred,
        limitations=limitations,
    )

    # 5. Create the phase directory if absent and write the report.
    phase_dir = resolved_feature_dir / "build" / f"phase-{args.phase}"
    try:
        phase_dir.mkdir(parents=True, exist_ok=True)
        report_path = phase_dir / REPORT_FILENAME
        report_path.write_text(body, encoding="utf-8")
    except OSError as exc:
        print(
            f"error: failed to write completion report: {exc}",
            file=sys.stderr,
        )
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the exit code; does not call sys.exit.

    Kept thin so tests can drive it directly without subprocess. The
    ``__main__`` block below propagates the return value to the OS.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "write":
        return _cmd_write(args)
    # argparse with required=True should make this unreachable.
    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
