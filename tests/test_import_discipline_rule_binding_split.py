"""Tests for F022 task 003: import-discipline rule-vs-binding split.

Locks in the four ACs for `standards/code/import-discipline.md` and the
adjacent Python binding file:

- AC-001+BR-001: normative sections of `import-discipline.md` contain ZERO
  occurrences of the forbidden Python tool-name list.
- AC-002+BR-001: `standards/code/profiles/python/import-discipline-bindings.md`
  exists and contains Python-tool-specific content.
- AC-003+BR-002: rule semantics preserved (mechanical split — the universal
  rule headings remain).
- AC-011: `import-discipline.md` contains the forward-only HTML comment near
  the file head.

Normative sections are partitioned by H2 heading; the partition mirrors
F021's `test_diagnostic_discipline_vocabulary.py` shape. The H2 headings
this task treats as normative are: ## Rules, ## Contract, ## Required,
## Standards, ## Principles.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
STANDARD = REPO_ROOT / "standards" / "code" / "import-discipline.md"
PYTHON_BINDINGS = (
    REPO_ROOT
    / "standards"
    / "code"
    / "profiles"
    / "python"
    / "import-discipline-bindings.md"
)

NORMATIVE_H2_PREFIXES: tuple[str, ...] = (
    "## Rules",
    "## Contract",
    "## Required",
    "## Standards",
    "## Principles",
)

FORBIDDEN_TOOL_NAMES: tuple[str, ...] = (
    "mypy",
    "pytest",
    "ruff",
    "black",
    "pylint",
    "isort",
    "flake8",
    "bandit",
)

FORWARD_ONLY_COMMENT = (
    "<!-- forward-only: vocabulary purity enforced from F022 release tag onward -->"
)


def _partition_by_h2(text: str) -> dict[str, str]:
    """Return `{h2_heading_line: section_body}` for every H2 in `text`."""
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


def _normative_sections(text: str) -> dict[str, str]:
    """Return only those H2 sections whose heading matches a normative prefix."""
    all_sections = _partition_by_h2(text)
    return {
        heading: body
        for heading, body in all_sections.items()
        if any(heading.startswith(prefix) for prefix in NORMATIVE_H2_PREFIXES)
    }


def test_should_contain_forward_only_comment_when_import_discipline_loaded() -> None:
    text = STANDARD.read_text(encoding="utf-8")
    head = "\n".join(text.splitlines()[:10])
    assert FORWARD_ONLY_COMMENT in head, (
        f"Expected forward-only HTML comment within first 10 lines of "
        f"{STANDARD}; not found. AC-011 requires it near the file head."
    )


def test_should_have_at_least_one_normative_section_when_partitioned() -> None:
    text = STANDARD.read_text(encoding="utf-8")
    normative = _normative_sections(text)
    assert normative, (
        f"Expected at least one normative H2 section in {STANDARD} "
        f"(prefixes: {NORMATIVE_H2_PREFIXES!r}); found none."
    )


@pytest.mark.parametrize("forbidden", FORBIDDEN_TOOL_NAMES)
def test_should_not_contain_forbidden_tool_name_when_section_is_normative(
    forbidden: str,
) -> None:
    text = STANDARD.read_text(encoding="utf-8")
    normative = _normative_sections(text)
    violations = {
        heading: body
        for heading, body in normative.items()
        if forbidden in body
    }
    assert not violations, (
        f"Forbidden Python tool name {forbidden!r} appears in normative "
        f"section(s) {sorted(violations)!r} of {STANDARD}; normative text "
        f"must remain tool-agnostic per BR-001."
    )


def test_should_exist_when_python_bindings_file_requested() -> None:
    assert PYTHON_BINDINGS.is_file(), (
        f"Expected Python binding file at {PYTHON_BINDINGS}; not found. "
        f"AC-002 requires the lifted Python-tool-specific content live here."
    )


def test_should_contain_python_tooling_reference_when_bindings_loaded() -> None:
    body = PYTHON_BINDINGS.read_text(encoding="utf-8")
    assert "ruff" in body, (
        f"Expected Python bindings file {PYTHON_BINDINGS} to reference "
        f"`ruff` (the lifted tool name); not found. AC-002 requires the "
        f"binding to carry the tool-specific content."
    )


def test_should_preserve_rule_semantics_when_split_applied() -> None:
    """AC-003: rule semantics preserved — the universal rule list still
    appears in the top-level standard, just without the tool binding lines.
    """
    text = STANDARD.read_text(encoding="utf-8")
    expected_rule_concepts = (
        "imports",
        "circular",
        "absolute",
    )
    missing = [
        concept
        for concept in expected_rule_concepts
        if concept.lower() not in text.lower()
    ]
    assert not missing, (
        f"Expected {STANDARD} to retain the universal rule concepts "
        f"{expected_rule_concepts!r} after the split; missing: {missing!r}."
    )


def test_should_cross_link_to_bindings_when_top_level_standard_loaded() -> None:
    """Architectural constraint: cross-link from informative section to
    per-profile bindings (mirrors error-handling.md / clean-code.md pattern).
    """
    text = STANDARD.read_text(encoding="utf-8")
    assert "import-discipline-bindings.md" in text, (
        f"Expected {STANDARD} to cross-link to the per-profile bindings "
        f"(`import-discipline-bindings.md`); not found. Mechanical-split "
        f"contract requires the cross-link."
    )
