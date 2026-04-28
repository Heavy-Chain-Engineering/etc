#!/usr/bin/env python3
"""release_notes.py — pure roll-up builder for /build's terminal close.

The /build skill (Step 7/8) calls `build(feature_dir)` and writes the
returned markdown to `<feature_dir>/release-notes.md`. This module never
touches disk for output; it only reads phase completion reports.

Per PRD .etc_sdlc/features/metrics-and-release-notes/spec.md:
- AC-011: release-notes.md cites PRD title+ID, phases closed, per-phase
  AC pass/fail summary citing each completion-report path, deferred
  items, and known limitations.
- BR-009: every successful terminal-phase close writes release-notes.md.

Module structure: a small set of focused helpers, each with a single
responsibility:
  - `build`              top-level orchestrator (pure function)
  - `_collect_phases`    walks build/phase-* and returns phase records
  - `_parse_report`      extracts the structured fields from one report
  - `_render_*`          shape each section of the output markdown
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ── Module constants ────────────────────────────────────────────────────

REPORT_FILENAME = "completion-report.md"
PHASE_DIR_GLOB = "build/phase-*"
PHASE_DIR_PATTERN = re.compile(r"^phase-(\d+)$")

# Recognised section headers in a completion report. Matching is
# case-insensitive on the heading text. Each heading marks the start
# of a section; the section ends at the next heading of equal or
# shallower depth.
SECTION_AC = "acceptance criteria"
SECTION_DEFERRED = "deferred items"
SECTION_LIMITATIONS = "known limitations"
SECTION_PRD = "prd"

# Markdown checkbox patterns for AC pass/fail.
AC_PASS_PATTERN = re.compile(r"^\s*-\s*\[[xX]\]\s*(.+?)\s*$")
AC_FAIL_PATTERN = re.compile(r"^\s*-\s*\[\s\]\s*(.+?)\s*$")

# PRD title/id key-value patterns inside a "## PRD" section.
PRD_TITLE_PATTERN = re.compile(r"^\s*-\s*Title\s*:\s*(.+?)\s*$", re.IGNORECASE)
PRD_ID_PATTERN = re.compile(r"^\s*-\s*ID\s*:\s*(.+?)\s*$", re.IGNORECASE)


# ── Data records ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _AcSummary:
    """Pass/fail rollup for one phase's acceptance criteria."""

    passed: tuple[str, ...]
    failed: tuple[str, ...]


@dataclass(slots=True)
class _PhaseRecord:
    """Parsed contents of one phase, or a marker for a missing report."""

    number: int
    report_path: Path  # path RELATIVE to the feature_dir
    report_exists: bool
    prd_title: str | None = None
    prd_id: str | None = None
    ac: _AcSummary = field(default_factory=lambda: _AcSummary((), ()))
    deferred: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


# ── Public API ──────────────────────────────────────────────────────────


def build(feature_dir: Path) -> str:
    """Roll up per-phase completion reports into a single markdown doc.

    The function is pure: it reads from `feature_dir/build/phase-*`
    and returns a string. It does NOT write to disk — the caller
    (skills/build/SKILL.md Step 7/8) is responsible for writing the
    result to `feature_dir/release-notes.md`.

    Args:
        feature_dir: Path to a feature directory (e.g.,
            `.etc_sdlc/features/F042-metrics-and-release-notes`).

    Returns:
        A markdown document with sections: heading, Phases, Deferred
        Items, Known Limitations. If no phase data is present, returns
        a minimal "No build phases found" note rather than raising.

    Raises:
        FileNotFoundError: if `feature_dir` does not exist.
    """
    if not feature_dir.exists():
        msg = f"feature_dir does not exist: {feature_dir}"
        raise FileNotFoundError(msg)

    phases = _collect_phases(feature_dir)

    sections: list[str] = [_render_header(feature_dir)]
    if not phases:
        sections.append("\n_No build phases found._\n")
        return "\n".join(sections)

    sections.append(_render_phases_section(phases))
    sections.append(_render_deferred_section(phases))
    sections.append(_render_limitations_section(phases))
    return "\n".join(sections)


# ── Phase collection ────────────────────────────────────────────────────


def _collect_phases(feature_dir: Path) -> list[_PhaseRecord]:
    """Find phase-* dirs under build/ and parse each report.

    Phase dirs are sorted numerically by the integer that follows
    `phase-` so `phase-2` precedes `phase-10`. Directories that do
    not match `phase-<digits>` are ignored.
    """
    build_dir = feature_dir / "build"
    if not build_dir.is_dir():
        return []

    candidates: list[tuple[int, Path]] = []
    for child in build_dir.iterdir():
        if not child.is_dir():
            continue
        match = PHASE_DIR_PATTERN.match(child.name)
        if not match:
            continue
        candidates.append((int(match.group(1)), child))

    candidates.sort(key=lambda pair: pair[0])

    records: list[_PhaseRecord] = []
    for phase_number, phase_dir in candidates:
        report_path_rel = Path("build") / phase_dir.name / REPORT_FILENAME
        report_abs = phase_dir / REPORT_FILENAME
        if not report_abs.is_file():
            records.append(
                _PhaseRecord(
                    number=phase_number,
                    report_path=report_path_rel,
                    report_exists=False,
                )
            )
            continue
        records.append(
            _parse_report(
                phase_number=phase_number,
                report_path_rel=report_path_rel,
                text=report_abs.read_text(encoding="utf-8"),
            )
        )

    return records


# ── Report parsing ──────────────────────────────────────────────────────


def _parse_report(
    *,
    phase_number: int,
    report_path_rel: Path,
    text: str,
) -> _PhaseRecord:
    """Extract structured fields from one completion-report.md.

    Tolerant of variation in heading depth and ordering. Anything
    not recognised is ignored rather than raising; missing fields
    surface as empty tuples or ``None``.
    """
    sections = _split_sections(text)
    prd_title, prd_id = _extract_prd_fields(sections.get(SECTION_PRD, []))
    ac = _extract_ac(sections.get(SECTION_AC, []))
    deferred = _extract_bullets(sections.get(SECTION_DEFERRED, []))
    limitations = _extract_bullets(sections.get(SECTION_LIMITATIONS, []))

    return _PhaseRecord(
        number=phase_number,
        report_path=report_path_rel,
        report_exists=True,
        prd_title=prd_title,
        prd_id=prd_id,
        ac=ac,
        deferred=deferred,
        limitations=limitations,
    )


def _split_sections(text: str) -> dict[str, list[str]]:
    """Group lines under each section heading.

    Keys are lowercased heading text (e.g. "acceptance criteria");
    values are the raw lines that follow that heading until the next
    heading of any depth. The very first heading determines the
    document title and is not stored as a section.
    """
    sections: dict[str, list[str]] = {}
    current_key: str | None = None
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    for line in text.splitlines():
        match = heading_pattern.match(line)
        if match:
            # Skip the very top-level "# Phase N" doc title — it is not
            # a section we care to roll up.
            heading_text = match.group(2).strip().lower()
            depth = len(match.group(1))
            if depth == 1:
                current_key = None
                continue
            current_key = heading_text
            sections.setdefault(current_key, [])
            continue

        if current_key is not None:
            sections[current_key].append(line)

    return sections


def _extract_prd_fields(lines: list[str]) -> tuple[str | None, str | None]:
    """Read 'Title:' and 'ID:' bullets from the PRD section."""
    title: str | None = None
    prd_id: str | None = None
    for line in lines:
        if title is None:
            title_match = PRD_TITLE_PATTERN.match(line)
            if title_match:
                title = title_match.group(1)
                continue
        if prd_id is None:
            id_match = PRD_ID_PATTERN.match(line)
            if id_match:
                prd_id = id_match.group(1)
    return title, prd_id


def _extract_ac(lines: list[str]) -> _AcSummary:
    """Split AC bullets into pass/fail by the checkbox state."""
    passed: list[str] = []
    failed: list[str] = []
    for line in lines:
        pass_match = AC_PASS_PATTERN.match(line)
        if pass_match:
            passed.append(pass_match.group(1))
            continue
        fail_match = AC_FAIL_PATTERN.match(line)
        if fail_match:
            failed.append(fail_match.group(1))
    return _AcSummary(tuple(passed), tuple(failed))


def _extract_bullets(lines: list[str]) -> tuple[str, ...]:
    """Collect non-empty bullet items, dropping placeholder 'None' rows."""
    bullet_pattern = re.compile(r"^\s*-\s+(.*?)\s*$")
    items: list[str] = []
    for line in lines:
        match = bullet_pattern.match(line)
        if not match:
            continue
        text = match.group(1)
        if not text:
            continue
        if text.strip().lower() == "none":
            continue
        items.append(text)
    return tuple(items)


# ── Rendering ───────────────────────────────────────────────────────────


def _render_header(feature_dir: Path) -> str:
    return f"# Release Notes — {feature_dir.name}\n"


def _render_phases_section(phases: list[_PhaseRecord]) -> str:
    lines: list[str] = ["## Phases", ""]
    for record in phases:
        lines.append(f"### Phase {record.number}")
        lines.append("")
        lines.append(f"- Source: `{record.report_path.as_posix()}`")
        if not record.report_exists:
            lines.append("- (report missing)")
            lines.append("")
            continue
        if record.prd_title or record.prd_id:
            title = record.prd_title or "(unknown)"
            prd_id = record.prd_id or "(unknown)"
            lines.append(f"- PRD: {title} ({prd_id})")
        lines.extend(_render_ac_block(record))
        lines.append("")
    return "\n".join(lines)


def _render_ac_block(record: _PhaseRecord) -> list[str]:
    """Render the per-phase AC pass/fail summary with citation."""
    pass_count = len(record.ac.passed)
    fail_count = len(record.ac.failed)
    lines: list[str] = [
        f"- Acceptance Criteria: {pass_count} passed, {fail_count} failed "
        f"(see `{record.report_path.as_posix()}`)",
    ]
    for item in record.ac.passed:
        lines.append(f"  - [x] {item}")
    for item in record.ac.failed:
        lines.append(f"  - [ ] {item}")
    return lines


def _render_deferred_section(phases: list[_PhaseRecord]) -> str:
    return _render_rolled_up_list(
        heading="## Deferred Items",
        empty_note="_No deferred items._",
        phases=phases,
        attr="deferred",
    )


def _render_limitations_section(phases: list[_PhaseRecord]) -> str:
    return _render_rolled_up_list(
        heading="## Known Limitations",
        empty_note="_No known limitations._",
        phases=phases,
        attr="limitations",
    )


def _render_rolled_up_list(
    *,
    heading: str,
    empty_note: str,
    phases: list[_PhaseRecord],
    attr: str,
) -> str:
    """Render a section that rolls up bullet items across all phases."""
    lines: list[str] = [heading, ""]
    any_items = False
    for record in phases:
        items: tuple[str, ...] = getattr(record, attr)
        if not items:
            continue
        any_items = True
        lines.append(f"From Phase {record.number} (`{record.report_path.as_posix()}`):")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")
    if not any_items:
        lines.append(empty_note)
        lines.append("")
    return "\n".join(lines)
