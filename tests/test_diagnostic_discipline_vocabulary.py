"""Tests for F021 BR-006 / AC-007: standards-doc tool-name purity scan.

The standard `standards/process/diagnostic-discipline.md` is structured into
normative sections (which carry the contract and MUST stay language- and
tool-agnostic) and informative sections (Examples, Background, Anti-patterns,
Forbidden-Phrases seed list, which MAY reference specific tools by name).

This test partitions the document by H2 heading and asserts that no specific
quality-tool names appear in any normative section's body. Informative
sections are unconstrained.

The partitioner is also asserted to recover all 5 normative + 4 informative
H2 headings; this catches the case where the standard ships with a missing
or renamed heading.

Per AC-007:
    Normative H2 headings (contract — MUST be tool-agnostic):
        ## Contract
        ## Required Evidence Block
        ## Audit Log
        ## Investigation Cycle Bound
        ## Forward-Only

    Informative H2 headings (documentation — MAY name tools):
        ## Forbidden Phrases (Illustrative — Not Enforcement)
        ## Examples
        ## Background
        ## Anti-patterns

    Forbidden substrings in normative bodies (case-sensitive grep):
        mypy, ruff, tsc, eslint, clippy, gofmt, golangci-lint,
        prettier, clang-tidy, Pyright
"""

from __future__ import annotations

from pathlib import Path

import pytest

STANDARD = (
    Path(__file__).resolve().parent.parent
    / "standards"
    / "process"
    / "diagnostic-discipline.md"
)

NORMATIVE_H2: tuple[str, ...] = (
    "## Contract",
    "## Required Evidence Block",
    "## Audit Log",
    "## Investigation Cycle Bound",
    "## Forward-Only",
)

INFORMATIVE_H2: tuple[str, ...] = (
    "## Forbidden Phrases (Illustrative — Not Enforcement)",
    "## Examples",
    "## Background",
    "## Anti-patterns",
)

FORBIDDEN_TOOL_NAMES: tuple[str, ...] = (
    "mypy",
    "ruff",
    "tsc",
    "eslint",
    "clippy",
    "gofmt",
    "golangci-lint",
    "prettier",
    "clang-tidy",
    "Pyright",
)


def _partition_by_h2(text: str) -> dict[str, str]:
    """Return `{h2_heading_line: section_body}` for every H2 in `text`.

    A section's body is every line AFTER the H2 line and BEFORE the next H2
    line (or end-of-file). The H2 line itself is the dict key, verbatim (e.g.
    `"## Contract"`). Lines starting with `### ` (H3) or deeper are treated
    as body, not as section boundaries.
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


def test_should_recover_all_normative_h2_headings_when_partitioning_standard() -> None:
    sections = _partition_by_h2(STANDARD.read_text(encoding="utf-8"))
    missing = [h for h in NORMATIVE_H2 if h not in sections]
    assert not missing, f"Normative H2 headings missing from standard: {missing}"


def test_should_recover_all_informative_h2_headings_when_partitioning_standard() -> None:
    sections = _partition_by_h2(STANDARD.read_text(encoding="utf-8"))
    missing = [h for h in INFORMATIVE_H2 if h not in sections]
    assert not missing, f"Informative H2 headings missing from standard: {missing}"


@pytest.mark.parametrize("heading", NORMATIVE_H2)
def test_should_contain_no_forbidden_tool_names_when_section_is_normative(
    heading: str,
) -> None:
    sections = _partition_by_h2(STANDARD.read_text(encoding="utf-8"))
    body = sections.get(heading, "")
    assert body, f"Normative section {heading!r} not found in standard"
    violations = [tool for tool in FORBIDDEN_TOOL_NAMES if tool in body]
    assert not violations, (
        f"Forbidden tool name(s) {violations!r} appear in normative section "
        f"{heading!r}; normative text must remain tool-agnostic (BR-006)."
    )
