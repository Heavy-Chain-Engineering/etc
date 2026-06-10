#!/usr/bin/env python3
"""Spec→ADR coupling gate (F015 / /build Step 7.5).

Scans <feature_dir>/spec.md (and design.md if present) for scope-change
markers anchored to AC/BR/ADR references. For each finding, checks for
coverage by a decision memo or ADR appendix. Blocks the release tag
(via exit code 2) if any finding is uncovered.

Exit codes:
  0 = all findings covered (or no findings)
  1 = usage error or IO error
  2 = uncovered findings (BLOCK release tag)

Usage:
  spec_coupling_check.py <feature_dir>

Where <feature_dir> is the path to .etc_sdlc/features/F<NNN>-<slug>/
(or its shipped/ counterpart).
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# AC-02 markers (case-insensitive)
MARKERS: tuple[str, ...] = (
    "deferred",
    "scope-narrowed",
    "scope narrowed",
    "removed",
    "out-of-scope",
    "out of scope",
    "not in scope",
    "explicitly excluded",
    "no longer in scope",
)
MARKER_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(m) for m in MARKERS) + r")\b",
    re.IGNORECASE,
)

# AC-NN / BR-NN / ADR-NN reference patterns
REFERENCE_PATTERN = re.compile(r"\b(AC|BR|ADR)-\d+(?:-\d+)*\b", re.IGNORECASE)

# Any backticked phrase counts as a "quoted spec phrase" anchor
BACKTICK_PATTERN = re.compile(r"`[^`\n]+`")

# Out of Scope / Not in Scope literal headers (AC-05 exclusion for header lines)
OUT_OF_SCOPE_HEADER_PATTERN = re.compile(
    r"^#{1,6}\s+(out of scope|not in scope)\s*$",
    re.IGNORECASE,
)

# ADR coverage requires one of these phrases near the AC/BR
ADR_COVERAGE_PHRASES: tuple[str, ...] = (
    "scope clarification",
    "scope-narrowed",
    "appendix",
)


@dataclass
class Finding:
    source_file: str  # "spec.md" or "design.md"
    line_number: int  # 1-indexed
    paragraph: str
    references: list[str]  # e.g., ["AC-12", "BR-007"]


@dataclass
class CoverageResult:
    covered: bool
    evidence: str  # path to memo/ADR that covers it, or "" if uncovered


# Legacy sequential form: the feature id is the F<NNN> PREFIX (slug stripped).
_LEGACY_ID_PATTERN = re.compile(r"^(F\d+)-")
# Date-based form (current scheme): the directory NAME *is* the feature id;
# there is no separate -<slug> suffix to strip. Mirror scripts/feature_id.py.
_DATED_ID_PATTERN = re.compile(r"^F-\d{4}-\d{2}-\d{2}-.+$")


def parse_feature_id(feature_dir: Path) -> str | None:
    """Extract the feature id from a directory name, accepting both grammars.

    - Legacy sequential ``F015-foo-bar`` → ``"F015"`` (the prefix; slug stripped).
    - Date-based ``F-2026-06-02-build-review-agent-gate`` → the FULL directory
      name (the name itself is the id). The baseline tag this gate looks up,
      ``etc/feature/<id>/spec``, is built on this exact id — so the date-form
      name must be returned verbatim, not truncated.

    Returns ``None`` when the name matches neither grammar.
    """
    name = feature_dir.name
    if _DATED_ID_PATTERN.match(name):
        return name
    legacy = _LEGACY_ID_PATTERN.match(name)
    return legacy.group(1) if legacy else None


def repo_root_from(feature_dir: Path) -> Path:
    """Walk up from feature_dir until we find a .git directory."""
    cur = feature_dir.resolve()
    while cur != cur.parent:
        if (cur / ".git").exists():
            return cur
        cur = cur.parent
    return feature_dir.parent  # best-effort


def display_path(path: Path, root: Path) -> str:
    """Render `path` relative to `root` for display, robust to mixed
    absolute/relative operands.

    `repo_root_from()` always returns a resolved (absolute) path, but a
    memo discovered under a caller-supplied *relative* feature_dir stays
    relative. `path.relative_to(root)` would then raise ValueError (#38),
    crashing the gate with an uncaught traceback. Resolve both sides
    before computing the relative path, and fall back to the raw path
    string when `path` genuinely lies outside `root`."""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def get_spec_at_tag(
    repo: Path, tag: str, relative_path: str
) -> tuple[str | None, str | None]:
    """Return (content_at_tag, error_message). Either content_at_tag or
    error_message is non-None; never both."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{tag}:{relative_path}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return None, f"git show failed: {e}"
    if result.returncode != 0:
        return None, result.stderr.strip() or "git show non-zero exit"
    return result.stdout, None


def added_line_indices(current: str, baseline: str) -> set[int]:
    """Return 0-indexed line numbers from `current` that are NOT in `baseline`.

    Uses simple set semantics — not a true diff, but adequate for finding
    "lines added since spec/done tag". Lines added or modified count as added.
    """
    baseline_lines = set(baseline.splitlines())
    return {
        i for i, line in enumerate(current.splitlines()) if line not in baseline_lines
    }


def strip_code_block_lines(text: str) -> set[int]:
    """Return 0-indexed lines that are inside fenced code blocks."""
    in_code = False
    excluded: set[int] = set()
    for i, line in enumerate(text.splitlines()):
        if line.strip().startswith("```"):
            excluded.add(i)
            in_code = not in_code
            continue
        if in_code:
            excluded.add(i)
    return excluded


def header_lines(text: str) -> set[int]:
    """0-indexed line numbers that are markdown headers."""
    return {
        i
        for i, line in enumerate(text.splitlines())
        if re.match(r"^#{1,6}\s+", line)
    }


def find_findings_in_text(
    text: str, scan_lines: set[int], source_file: str
) -> list[Finding]:
    """Find markers in `text` restricted to `scan_lines`. Group into
    paragraphs (blank-line-separated). A paragraph is a finding if:
      - At least one line is in scan_lines
      - It contains a marker
      - It contains an AC/BR/ADR reference OR a backtick-quoted phrase
      - The marker is NOT in a code block
      - The marker line is NOT a literal "Out of Scope" header
    """
    lines = text.splitlines()
    code_lines = strip_code_block_lines(text)
    hdr_lines = header_lines(text)

    # Group into paragraphs separated by blank lines.
    # Each entry: (start_line_0idx, line_indices, joined_text)
    paragraphs: list[tuple[int, list[int], str]] = []
    current_start = 0
    current_indices: list[int] = []
    current_text: list[str] = []
    for i, line in enumerate(lines):
        if not line.strip():
            if current_indices:
                paragraphs.append((current_start, current_indices, "\n".join(current_text)))
                current_indices = []
                current_text = []
            current_start = i + 1
            continue
        if not current_indices:
            current_start = i
        current_indices.append(i)
        current_text.append(line)
    if current_indices:
        paragraphs.append((current_start, current_indices, "\n".join(current_text)))

    findings: list[Finding] = []
    for start, indices, para in paragraphs:
        # Must intersect scan_lines
        if not any(i in scan_lines for i in indices):
            continue
        # Strip code-block lines from consideration
        non_code_indices = [i for i in indices if i not in code_lines]
        if not non_code_indices:
            continue
        non_code_text = "\n".join(lines[i] for i in non_code_indices)
        # AC-05: exclude paragraphs whose entire content is just an "Out of Scope" header
        if all(
            (i in hdr_lines) and OUT_OF_SCOPE_HEADER_PATTERN.match(lines[i])
            for i in non_code_indices
        ):
            continue
        # Marker present?
        if not MARKER_PATTERN.search(non_code_text):
            continue
        # Anchor present? Collect full reference tokens (not just groups).
        ref_tokens = [m.group(0) for m in REFERENCE_PATTERN.finditer(non_code_text)]
        has_backtick = bool(BACKTICK_PATTERN.search(non_code_text))
        if not ref_tokens and not has_backtick:
            continue
        # Record finding
        findings.append(
            Finding(
                source_file=source_file,
                line_number=start + 1,  # 1-indexed
                paragraph=para.strip(),
                references=ref_tokens,
            )
        )
    return findings


def check_coverage(
    finding: Finding, feature_dir: Path, repo_root: Path
) -> CoverageResult:
    """Check coverage: a decision memo or ADR appendix references at least
    one of the finding's references."""
    if not finding.references:
        # Anchored by backtick only — fall back to checking ANY decision memo
        # or ADR appendix exists in the feature's decisions/ directory.
        decisions_dir = feature_dir / "decisions"
        if decisions_dir.is_dir():
            memos = list(decisions_dir.glob("*.md"))
            if memos:
                return CoverageResult(True, str(memos[0]))
        return CoverageResult(False, "")

    # Check decision memos (AC-07)
    decisions_dir = feature_dir / "decisions"
    if decisions_dir.is_dir():
        for memo in decisions_dir.glob("*.md"):
            try:
                content = memo.read_text(encoding="utf-8")
            except OSError:
                continue
            for ref in finding.references:
                if re.search(rf"\b{re.escape(ref)}\b", content, re.IGNORECASE):
                    return CoverageResult(True, display_path(memo, repo_root))

    # Check ADRs (AC-08)
    adrs_dir = repo_root / "docs" / "adrs"
    if adrs_dir.is_dir():
        for adr in adrs_dir.glob("*.md"):
            try:
                content = adr.read_text(encoding="utf-8")
            except OSError:
                continue
            content_lower = content.lower()
            has_phrase = any(p in content_lower for p in ADR_COVERAGE_PHRASES)
            if not has_phrase:
                continue
            for ref in finding.references:
                if re.search(rf"\b{re.escape(ref)}\b", content, re.IGNORECASE):
                    return CoverageResult(True, display_path(adr, repo_root))

    return CoverageResult(False, "")


def scan_feature(feature_dir: Path) -> tuple[list[Finding], list[CoverageResult]]:
    """Returns (findings, coverage_results). Same length, parallel indexing."""
    feature_id = parse_feature_id(feature_dir)
    repo_root = repo_root_from(feature_dir)

    findings: list[Finding] = []
    for source_name in ["spec.md", "design.md"]:
        source_path = feature_dir / source_name
        if not source_path.exists():
            continue
        text = source_path.read_text(encoding="utf-8")

        # Scan only the lines ADDED since the prior tracked spec baseline.
        #
        # The baseline is the spec content committed and tagged at the LEAF
        # tag `/spec` actually writes — `etc/feature/<id>/spec` (NOT
        # `…/spec/done`; a git ref cannot be both a leaf and a directory, so
        # `…/spec/done` could never exist — #46).
        #
        # When there is NO usable baseline, PASS CLEAN (scan nothing). A
        # fresh spec has no prior version to detect a scope CHANGE against —
        # there is nothing to "couple". This is the normal state for every
        # first-time build: the harness gitignores feature dirs, so spec.md is
        # untracked and `git show <tag>:<rel>` fails even when the tag exists.
        # Whole-spec-scanning in that case over-fired on every fresh build
        # (#46, 6th occurrence). "No baseline" is not an error condition.
        scan_lines: set[int]
        if feature_id is None:
            # No parseable feature id → no tag to look up → no baseline.
            scan_lines = set()
        else:
            # Determine the relative path from repo_root for git show
            try:
                rel = str(source_path.resolve().relative_to(repo_root.resolve()))
            except ValueError:
                rel = str(source_path)
            tag = f"etc/feature/{feature_id}/spec"
            baseline, _ = get_spec_at_tag(repo_root, tag, rel)
            if baseline is None:
                # No tracked baseline at the tag (tag absent, or the spec is
                # untracked/gitignored at that tag): nothing to couple against.
                scan_lines = set()
            else:
                scan_lines = added_line_indices(text, baseline)

        if not scan_lines:
            continue

        findings.extend(find_findings_in_text(text, scan_lines, source_name))

    coverage = [check_coverage(f, feature_dir, repo_root) for f in findings]
    return findings, coverage


def print_block_report(
    findings: list[Finding], coverage: list[CoverageResult], feature_dir: Path
) -> None:
    """AC-09: emit a structured stdout report listing each uncovered finding
    with file:line + remediation hint."""
    print("SPEC→ADR COUPLING GATE FAILED")
    print()
    print("The following scope-change markers have no decision memo or ADR appendix:")
    print()
    for f, c in zip(findings, coverage):
        if c.covered:
            continue
        first_line = f.paragraph.splitlines()[0] if f.paragraph else ""
        truncated = (first_line[:100] + "...") if len(first_line) > 100 else first_line
        refs = ", ".join(f.references) if f.references else "(backtick-quoted only)"
        print(f"  {f.source_file}:{f.line_number} [{refs}] — {truncated}")
    print()
    print("For each finding above, provide ONE of:")
    print(
        f"  A) Decision memo at {feature_dir}/decisions/<name>.md"
        " referencing the AC/BR/ADR token."
    )
    print(
        "  B) ADR appendix at docs/adrs/<existing>.md modified to add a"
        ' "Scope clarification" / "scope-narrowed" / "appendix" section'
        " citing the AC/BR/ADR token."
    )
    print()
    print(
        "Override (requires non-empty reason, logged to verification.md +"
        " release-notes.md):"
    )
    print('  /build --skip-spec-coupling-check="<reason>" --resume')


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(__doc__ or "")
        return 1

    feature_dir = Path(argv[1])
    if not feature_dir.is_dir():
        sys.stderr.write(f"ERROR: feature_dir not found: {feature_dir}\n")
        return 1

    findings, coverage = scan_feature(feature_dir)
    if not findings:
        return 0

    uncovered = [(f, c) for f, c in zip(findings, coverage) if not c.covered]
    if not uncovered:
        # All covered — emit a brief stdout summary for the operator
        for f, c in zip(findings, coverage):
            print(f"  ✓ {f.source_file}:{f.line_number} covered by {c.evidence}")
        return 0

    print_block_report(findings, coverage, feature_dir)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
