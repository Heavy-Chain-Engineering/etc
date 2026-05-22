"""Tests for F022 BR-008 / AC-009: rule-vs-binding vocabulary purity.

Three top-level standards (`standards/code/clean-code.md`,
`standards/code/error-handling.md`, `standards/code/import-discipline.md`) are
the rule layer; per-language bindings under
`standards/code/profiles/<profile>/<rule>-bindings.md` are the binding layer.
The rule layer MUST stay language- and tool-agnostic — specific Python tool
names (`mypy`, `pytest`, `ruff`, `black`, `pylint`, `isort`, `flake8`,
`bandit`) belong only in the binding layer.

This test partitions each standard by H2 heading and asserts no forbidden
Python tool name appears in any normative section's body. Informative
sections (Examples, Background, Anti-patterns, Forbidden Phrases) are
unconstrained — they may name tools to illustrate.

Per F022 BR-008 / AC-009:
    Normative H2 headings (rule layer — MUST be tool-agnostic):
        ## Rules
        ## Contract
        ## Required
        ## Standards
        ## Principles

    Informative H2 headings (documentation — MAY name tools):
        ## Examples
        ## Background
        ## Anti-patterns
        ## Forbidden Phrases

    Forbidden substrings in normative bodies (case-sensitive grep):
        mypy, pytest, ruff, black, pylint, isort, flake8, bandit

Headings outside both sets default to informative (forgiving) so the test
does not block future renames; the partitioner's "found at least one
normative heading" assertion catches the case where someone renames every
normative heading to something unrecognized and silently disables the check.

Mirrors the partitioning shape of `tests/test_diagnostic_discipline_vocabulary.py`
(F021's BR-006/AC-007 lockdown).
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

STANDARDS_DIR = Path(__file__).resolve().parent.parent / "standards" / "code"

STANDARDS_TO_CHECK: tuple[str, ...] = (
    "clean-code.md",
    "error-handling.md",
    "import-discipline.md",
)

NORMATIVE_HEADINGS: tuple[str, ...] = (
    "## Rules",
    "## Contract",
    "## Required",
    "## Standards",
    "## Principles",
)

INFORMATIVE_HEADINGS: tuple[str, ...] = (
    "## Examples",
    "## Background",
    "## Anti-patterns",
    "## Forbidden Phrases",
)

FORBIDDEN_NAMES: tuple[str, ...] = (
    "mypy",
    "pytest",
    "ruff",
    "black",
    "pylint",
    "isort",
    "flake8",
    "bandit",
)


def _partition_by_h2(text: str) -> dict[str, str]:
    """Return `{h2_heading_line: section_body}` for every H2 in `text`.

    A section's body is every line AFTER the H2 line and BEFORE the next H2
    line (or end-of-file). The H2 line itself is the dict key, verbatim
    (e.g. `"## Rules"`). Lines starting with `### ` (H3) or deeper are
    treated as body, not as section boundaries.

    Mirrors F021's `tests/test_diagnostic_discipline_vocabulary.py` shape.
    """
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_body)
            current_heading = line
            current_body = []
        else:
            current_body.append(line)
    if current_heading is not None:
        sections[current_heading] = "\n".join(current_body)
    return sections


def _classify_heading(heading: str) -> str:
    """Return `"normative"`, `"informative"`, or `"unknown"` for an H2 line.

    Unknown headings default to informative at the call site (forgiving) but
    are surfaced via a warning so future renames do not silently disable the
    purity check.
    """
    if heading in NORMATIVE_HEADINGS:
        return "normative"
    if heading in INFORMATIVE_HEADINGS:
        return "informative"
    return "unknown"


@pytest.mark.parametrize("standard_file", STANDARDS_TO_CHECK)
def test_should_find_at_least_one_normative_section_when_partitioning_standard(
    standard_file: str,
) -> None:
    path = STANDARDS_DIR / standard_file
    sections = _partition_by_h2(path.read_text(encoding="utf-8"))
    normative_present = set(NORMATIVE_HEADINGS) & set(sections.keys())
    assert normative_present, (
        f"{standard_file} has zero recognized normative H2 headings. "
        f"Recognized normative headings: {list(NORMATIVE_HEADINGS)}. "
        f"Headings found in file: {sorted(sections.keys())}. "
        "If a normative heading was renamed, update NORMATIVE_HEADINGS "
        "in this test so the purity check stays active (BR-008)."
    )


@pytest.mark.parametrize("standard_file", STANDARDS_TO_CHECK)
@pytest.mark.parametrize("heading", NORMATIVE_HEADINGS)
def test_should_contain_no_forbidden_tool_names_when_section_is_normative(
    standard_file: str,
    heading: str,
) -> None:
    path = STANDARDS_DIR / standard_file
    sections = _partition_by_h2(path.read_text(encoding="utf-8"))
    body = sections.get(heading)
    if body is None:
        pytest.skip(f"{standard_file} has no {heading!r} section")
    violations = [tool for tool in FORBIDDEN_NAMES if tool in body]
    assert not violations, (
        f"Forbidden Python tool name(s) {violations!r} appear in normative "
        f"section {heading!r} of {standard_file}; normative rule text must "
        "remain tool-agnostic per F022 BR-008. Move tool-specific guidance "
        f"to standards/code/profiles/python/{standard_file.removesuffix('.md')}-bindings.md."
    )


@pytest.mark.parametrize("standard_file", STANDARDS_TO_CHECK)
def test_should_warn_on_unknown_h2_headings_when_partitioning_standard(
    standard_file: str,
) -> None:
    """Surface unknown H2 headings as warnings (informative-by-default).

    Unknown headings do not fail the test — they default to informative so
    forward edits do not break the build — but a warning is emitted so a
    reviewer can decide whether the heading should be added to the
    normative or informative allow-list.
    """
    path = STANDARDS_DIR / standard_file
    sections = _partition_by_h2(path.read_text(encoding="utf-8"))
    unknown = [h for h in sections if _classify_heading(h) == "unknown"]
    if unknown:
        warnings.warn(
            f"{standard_file} contains H2 headings not classified as "
            f"normative or informative (defaulting to informative): {unknown}. "
            "If any of these should be normative (rule-bearing), add them "
            "to NORMATIVE_HEADINGS in this test.",
            stacklevel=2,
        )
