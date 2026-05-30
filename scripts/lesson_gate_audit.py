#!/usr/bin/env python3
"""Lessons-terminate-in-gates audit engine (F-2026-05-30, meta-fix #53).

Read-only reporter that scans the operator-local memory directory, classifies
each lesson-class memory by whether it terminates in a gate, and (via the
sibling CLI built in task 001.002) emits a structured report. It makes etc's
feedback-loop leak visible: lessons flow incident → retro → memory, but the
audit measures how many actually terminate in an enforced gate.

This file is the established etc helper-script tier (peer to ``git_tags.py``,
``value_hypothesis.py``, ``layer_review.py``): a frozen-dataclass core plus an
``argparse`` CLI. It is **read-only over memory** — it never writes or mutates
a memory file, and a ``terminates_in`` gate-ref is ``Path.exists()``-tested
under ``repo_root`` but **never opened, executed, or interpolated**
(path-claim validation, not path-fetch).

Public surface (task 001.001 — this file):
    CLASSIFICATIONS         (tuple[str, ...]) — the closed literal vocabulary
    LessonRecord            (frozen dataclass) — one audited lesson-class memory
    AuditReport             (frozen dataclass) — the whole-corpus result
    resolve_memory_dir(override=None) -> Path
    parse_frontmatter(text) -> dict[str, Any] | None
    classify_lesson(frontmatter, filename, repo_root) -> tuple[str, str]

Task 001.002 adds ``audit_memory_dir(memory_dir, repo_root) -> AuditReport``
and the ``audit`` argparse subcommand on top of these functions. The CLI is
**advisory by construction** (ADR-002): it always exits 0 on a completed scan,
including an absent/unreadable memory dir (a clean "no memory dir" report);
only an argparse usage error exits 2. It never participates in a hard-block.

Classification literals (the loop's possible terminations):
    gated | none-yet | note-only | missing | dangling
plus the caller-skip sentinel ``exempt`` for a non-lesson-class memory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT: Path = Path(__file__).resolve().parent.parent

# The closed classification vocabulary. ``exempt`` is the caller-skip sentinel
# for a non-lesson-class memory (it is not a loop-termination state and is
# excluded from gated_pct by the auditor in 001.002).
CLASSIFICATIONS: tuple[str, ...] = (
    "gated",
    "none-yet",
    "note-only",
    "missing",
    "dangling",
)

# Filename prefixes that mark a memory as lesson-class regardless of its
# declared type (ADR-001 union classifier).
_LESSON_FILENAME_PREFIXES: tuple[str, ...] = ("feedback-", "lessons-")

# Type values (read from nested ``metadata.type`` OR flat top-level ``type``)
# that mark a memory as lesson-class regardless of its filename (ADR-001).
_LESSON_TYPE_VALUES: frozenset[str] = frozenset({"feedback", "lessons"})

# A frontmatter block delimited by leading/closing ``---`` fences.
_FRONTMATTER_PATTERN = re.compile(
    r"\A---\s*\n(?P<body>.*?)\n---\s*(?:\n|\Z)",
    re.DOTALL,
)

# A ``#<tracker>`` token inside a ``none-yet`` declaration (e.g. ``#42``,
# ``#DEV-001``). The tracker must be non-empty after the hash.
_TRACKER_TOKEN_PATTERN = re.compile(r"#\S+")


@dataclass(frozen=True)
class LessonRecord:
    """One audited lesson-class memory and its loop-termination verdict."""

    name: str
    path: Path
    classification: str
    terminates_in: list[str]
    detail: str


@dataclass(frozen=True)
class AuditReport:
    """The whole-corpus audit result. ``gated_pct = gated / lesson-class``."""

    records: list[LessonRecord]
    counts: dict[str, int]
    gated_pct: float
    memory_dir: str


def resolve_memory_dir(override: Path | None = None) -> Path:
    """Resolve the memory directory to audit.

    Defaults to ``~/.claude/projects/<cwd-as-slug>/memory`` where
    ``<cwd-as-slug> = str(Path.cwd()).replace("/", "-")`` (the verified live
    convention). An explicit ``override`` short-circuits the default so a
    caller (or ``--memory-dir``) can point at any directory.
    """
    if override is not None:
        return override
    slug = str(Path.cwd()).replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug / "memory"


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse a leading ``---``-fenced YAML frontmatter block.

    Returns the parsed mapping, or ``None`` when the frontmatter is absent,
    not a fenced block, malformed YAML, or does not parse to a mapping. Never
    raises — a malformed memory degrades to ``None`` so the caller treats it
    as unparseable rather than crashing the whole scan.
    """
    match = _FRONTMATTER_PATTERN.match(text)
    if match is None:
        return None
    try:
        parsed = yaml.safe_load(match.group("body"))
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def classify_lesson(
    frontmatter: dict[str, Any] | None,
    filename: str,
    repo_root: Path,
) -> tuple[str, str]:
    """Classify a memory by whether it terminates in a gate.

    Returns ``(classification, detail)`` where ``classification`` is one of
    ``CLASSIFICATIONS`` for a lesson-class memory, or ``"exempt"`` for a
    non-lesson memory the caller should skip.

    Lesson-class is the ADR-001 union: the filename starts ``feedback-`` /
    ``lessons-`` **OR** the declared type (nested ``metadata.type`` or flat
    top-level ``type``) is ``feedback`` / ``lessons``. A lesson-class memory
    with unparseable/absent frontmatter (``frontmatter is None``) degrades to
    ``missing`` (detail ``"frontmatter unparseable"``) rather than crashing.
    """
    is_lesson = _is_lesson_class(frontmatter, filename)
    if not is_lesson:
        return "exempt", ""

    if frontmatter is None:
        return "missing", "frontmatter unparseable"

    if "terminates_in" not in frontmatter:
        return "missing", ""

    return _classify_terminates_in(frontmatter["terminates_in"], repo_root)


def _is_lesson_class(frontmatter: dict[str, Any] | None, filename: str) -> bool:
    """True iff the memory is lesson-class under the ADR-001 union."""
    if filename.startswith(_LESSON_FILENAME_PREFIXES):
        return True
    declared_type = _read_type(frontmatter)
    return declared_type in _LESSON_TYPE_VALUES


def _read_type(frontmatter: dict[str, Any] | None) -> str | None:
    """Read the declared type from nested ``metadata.type`` or flat ``type``.

    The live corpus carries both shapes; keying on one alone would silently
    skip half the files (dual-shape parse, load-bearing). Returns ``None``
    when neither is a string.
    """
    if frontmatter is None:
        return None
    metadata = frontmatter.get("metadata")
    if isinstance(metadata, dict):
        nested = metadata.get("type")
        if isinstance(nested, str):
            return nested
    flat = frontmatter.get("type")
    if isinstance(flat, str):
        return flat
    return None


def _classify_terminates_in(value: Any, repo_root: Path) -> tuple[str, str]:
    """Classify a present ``terminates_in`` value into a loop-termination."""
    if isinstance(value, str):
        return _classify_scalar(value, repo_root)
    if isinstance(value, list):
        return _classify_path_list([str(entry) for entry in value], repo_root)
    # An unexpected shape (e.g. a mapping) is treated as an open loop.
    return "missing", f"unrecognized terminates_in shape: {type(value).__name__}"


def _classify_scalar(value: str, repo_root: Path) -> tuple[str, str]:
    """Classify a scalar ``terminates_in``: note-only, none-yet, or a path."""
    stripped = value.strip()
    if stripped == "note-only":
        return "note-only", ""
    if stripped.startswith("none-yet"):
        return _classify_none_yet(stripped)
    return _classify_path_list([stripped], repo_root)


def _classify_none_yet(value: str) -> tuple[str, str]:
    """A ``none-yet`` is actionable only with a ``#<tracker>`` token.

    Without a tracker it downgrades to ``missing`` — an open loop with no
    landing place is indistinguishable from an unfiled one (AC-006, GA-003).
    """
    if _TRACKER_TOKEN_PATTERN.search(value):
        return "none-yet", ""
    return "missing", "none-yet without tracker"


def _classify_path_list(entries: list[str], repo_root: Path) -> tuple[str, str]:
    """Resolve each gate-ref under ``repo_root``; gated iff all exist.

    Each entry has its ``#anchor`` / trailing `` Step N`` / ``:N`` descriptor
    stripped before resolution. The path is existence-tested only — never
    opened, executed, or interpolated (path-claim validation). Any missing
    entry makes the whole declaration ``dangling``.
    """
    missing = [entry for entry in entries if not _gate_ref_exists(entry, repo_root)]
    if missing:
        return "dangling", f"missing gate-ref(s): {', '.join(missing)}"
    return "gated", ""


def _gate_ref_exists(entry: str, repo_root: Path) -> bool:
    """Existence-test the leading path token of a gate-ref under ``repo_root``.

    Security: the value is only ``Path.exists()``-tested; it is never read.
    Even a ``../../``-style value yields only a boolean — no content
    disclosure (directory-traversal defense).
    """
    token = _strip_descriptor(entry)
    if not token:
        return False
    return (repo_root / token).exists()


def _strip_descriptor(entry: str) -> str:
    """Strip a trailing ``#anchor``, `` Step N``, or ``:N`` descriptor.

    Order matters: drop the ``#anchor`` first (a skill-step ref validates the
    ``SKILL.md`` file, not the prose step), then any trailing `` Step N`` or
    ``:N`` line/step descriptor, leaving the bare leading path token.
    """
    token = entry.strip()
    token = token.split("#", 1)[0]
    token = re.sub(r"\s+Step\s+\d+\s*$", "", token, flags=re.IGNORECASE)
    token = re.sub(r":\d+\s*$", "", token)
    return token.strip()


# The memory index file is never a lesson-class memory; always skipped.
_INDEX_FILENAME: str = "MEMORY.md"


def _terminates_in_for_record(frontmatter: dict[str, Any] | None) -> list[str]:
    """Normalize a memory's ``terminates_in`` to a list for the record.

    Mirrors the classifier's shape handling: a scalar becomes a one-element
    list, a list is stringified element-wise, anything else (absent / mapping)
    becomes an empty list. Purely descriptive — the verdict already lives in
    ``classification``; this is the raw declaration for the report.
    """
    if frontmatter is None:
        return []
    value = frontmatter.get("terminates_in")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(entry) for entry in value]
    return []


def audit_memory_dir(memory_dir: Path, repo_root: Path) -> AuditReport:
    """Scan ``memory_dir`` and classify every lesson-class memory.

    Reads each ``*.md`` (skipping the ``MEMORY.md`` index), parses its
    frontmatter via :func:`parse_frontmatter`, and classifies it via
    :func:`classify_lesson`. A ``LessonRecord`` is collected only for
    lesson-class files; the ``"exempt"`` non-lesson sentinel is dropped.

    Read-only: a memory file is read for its frontmatter only; a gate-ref is
    existence-tested under ``repo_root`` (never opened). An absent or
    unreadable ``memory_dir`` yields a clean empty report rather than raising
    (ADR-002 advisory contract). ``gated_pct = gated / total_lesson_class``,
    and ``0.0`` when no lesson-class memory exists (no ``ZeroDivisionError``).
    """
    records = _scan_records(memory_dir, repo_root)
    counts = _count_by_status(records)
    total = len(records)
    gated_pct = counts.get("gated", 0) / total if total else 0.0
    return AuditReport(
        records=records,
        counts=counts,
        gated_pct=gated_pct,
        memory_dir=str(memory_dir),
    )


def _scan_records(memory_dir: Path, repo_root: Path) -> list[LessonRecord]:
    """Collect a record for each lesson-class ``*.md`` under ``memory_dir``."""
    if not memory_dir.is_dir():
        return []
    records: list[LessonRecord] = []
    for path in sorted(memory_dir.glob("*.md")):
        if path.name == _INDEX_FILENAME:
            continue
        record = _record_for(path, repo_root)
        if record is not None:
            records.append(record)
    return records


def _record_for(path: Path, repo_root: Path) -> LessonRecord | None:
    """Build a record for one file, or ``None`` if non-lesson / unreadable.

    An unreadable file degrades to a ``None``-frontmatter classification (so a
    lesson-by-filename still surfaces as ``missing`` rather than crashing the
    scan).
    """
    frontmatter = _read_frontmatter(path)
    classification, detail = classify_lesson(frontmatter, path.name, repo_root)
    if classification == "exempt":
        return None
    return LessonRecord(
        name=path.stem,
        path=path,
        classification=classification,
        terminates_in=_terminates_in_for_record(frontmatter),
        detail=detail,
    )


def _read_frontmatter(path: Path) -> dict[str, Any] | None:
    """Read + parse a file's frontmatter; ``None`` on any read/parse failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_frontmatter(text)


def _count_by_status(records: list[LessonRecord]) -> dict[str, int]:
    """Tally records per classification across the full closed vocabulary.

    Every literal in :data:`CLASSIFICATIONS` is present (zero when unseen) so
    the JSON ``counts`` object has a stable, complete key set for consumers.
    """
    counts = dict.fromkeys(CLASSIFICATIONS, 0)
    for record in records:
        counts[record.classification] = counts.get(record.classification, 0) + 1
    return counts


# ── CLI (advisory; always exit 0 on a completed scan — ADR-002) ──────────


def _report_to_dict(report: AuditReport) -> dict[str, Any]:
    """Serialize a report to the JSON contract /metrics consumes.

    Top-level keys: ``memory_dir``, ``gated_pct``, ``counts``, ``records``;
    each record carries ``name``, ``classification``, ``terminates_in``,
    ``detail``. ``json.dumps(..., sort_keys=True)`` fixes the key order.
    """
    return {
        "memory_dir": report.memory_dir,
        "gated_pct": report.gated_pct,
        "counts": report.counts,
        "records": [
            {
                "name": record.name,
                "classification": record.classification,
                "terminates_in": record.terminates_in,
                "detail": record.detail,
            }
            for record in report.records
        ],
    }


def _format_json(report: AuditReport) -> str:
    return json.dumps(_report_to_dict(report), indent=2, sort_keys=True)


def _format_text(report: AuditReport) -> str:
    """Render a human-readable table of the audit result."""
    lines = [
        f"Feedback-loop closure audit — {report.memory_dir}",
        (
            f"  gated {report.gated_pct:.0%} of {len(report.records)} "
            "lesson-class memories terminate in a gate"
        ),
        "",
    ]
    lines.extend(
        f"  {literal:<10} {report.counts.get(literal, 0)}"
        for literal in CLASSIFICATIONS
    )
    if report.records:
        lines.append("")
        for record in report.records:
            suffix = f" — {record.detail}" if record.detail else ""
            lines.append(f"  [{record.classification:<10}] {record.name}{suffix}")
    else:
        lines.append("")
        lines.append("  (no lesson-class memories found)")
    return "\n".join(lines)


def _cli_audit(args: argparse.Namespace) -> int:
    memory_dir = resolve_memory_dir(
        Path(args.memory_dir) if args.memory_dir else None
    )
    repo_root = Path(args.repo_root)
    report = audit_memory_dir(memory_dir, repo_root)
    renderer = _format_text if args.format == "text" else _format_json
    print(renderer(report))
    return 0  # advisory: always 0 on a completed scan (ADR-002).


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lesson_gate_audit.py",
        description=(
            "Advisory feedback-loop closure audit: classify each lesson-class "
            "memory by whether it terminates in a gate. Read-only; always "
            "exits 0 on a completed scan (ADR-002)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser(
        "audit",
        help="Scan the memory dir and report feedback-loop closure.",
    )
    p_audit.add_argument(
        "--memory-dir",
        default=None,
        help="Memory dir to audit (defaults to the resolved operator-local dir).",
    )
    p_audit.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repo root that gate-refs are resolved against.",
    )
    p_audit.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format (default: json).",
    )
    p_audit.set_defaults(func=_cli_audit)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. argparse exits with code 2 on a usage error."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
