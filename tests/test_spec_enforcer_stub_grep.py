"""Contract tests for spec-enforcer Stub-Marker Grep (F007 / BR-009).

Covers PRD .etc_sdlc/features/F007-spec-enforcer-stub-grep/spec.md AC1-AC15
via grep-based assertions over four artifacts:

- agents/spec-enforcer.md (compiled at dist/agents/spec-enforcer.md)
- standards/process/stub-marker-grep.md
- hooks/inject-standards.sh
- standards/process/user-flow-completeness.md (See-also pointer only)

Precedent: tests/test_spec_enforcer_reachability.py (the F002 contract test).
Same autouse session-scoped compile fixture pattern; same
`Path(...).read_text(encoding="utf-8")` reading idiom; same grep-based
assertions over committed source plus compiled dist/ outputs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source artifacts (assert directly against committed files).
STANDARDS_DOC = REPO_ROOT / "standards" / "process" / "stub-marker-grep.md"
HOOK_SCRIPT = REPO_ROOT / "hooks" / "inject-standards.sh"
USERFLOW_DOC = REPO_ROOT / "standards" / "process" / "user-flow-completeness.md"

# Compiled artifact is read from the shared session-scoped ``compiled_dist``
# fixture (conftest.py), which compiles into a tmp dir — the operator's real
# dist/ is never read or mutated by this suite.
AGENT_REL = Path("agents") / "spec-enforcer.md"


# -- Module-scoped text fixtures ---------------------------------------------


@pytest.fixture(scope="module")
def agent_dist_text(compiled_dist: Path) -> str:
    path = compiled_dist / AGENT_REL
    assert path.exists(), (
        f"missing compiled agent: {path}; "
        "the shared compiled_dist fixture should have created it"
    )
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def standards_text() -> str:
    assert STANDARDS_DOC.exists(), f"missing standards doc: {STANDARDS_DOC}"
    return STANDARDS_DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def hook_text() -> str:
    assert HOOK_SCRIPT.exists(), f"missing hook script: {HOOK_SCRIPT}"
    return HOOK_SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def userflow_text() -> str:
    assert USERFLOW_DOC.exists(), f"missing user-flow doc: {USERFLOW_DOC}"
    return USERFLOW_DOC.read_text(encoding="utf-8")


# -- Agent-body tests (AC9: Step 2d + citation + budget=20) ------------------


def test_agent_dist_has_step_2d_and_citation_and_budget_20(
    agent_dist_text: str,
) -> None:
    """AC9: dist/agents/spec-enforcer.md contains the Step 2d header, the
    standards-doc citation by path, and the bumped tool-budget total.

    Three load-bearing literals must coexist in the compiled agent body:

    1. The Step 2d header anchor ("Step 2d") — F007's verify-time stub-grep
       step inserted between Step 2c and Step 3.
    2. The standards-doc path reference 'standards/process/stub-marker-grep.md'
       — Step 2d MUST cite the standards doc rather than duplicate contracts
       inline (matches F002's citation pattern).
    3. The budget total '20 across all tools' — F007's BR-007 bumped the
       budget from 16 → 20 (Grep 8 → 12). The stale '16 across all tools'
       literal must NOT survive anywhere in the file.
    """
    assert "Step 2d" in agent_dist_text, (
        "compiled agent missing Step 2d header anchor: 'Step 2d'"
    )
    assert "standards/process/stub-marker-grep.md" in agent_dist_text, (
        "compiled agent missing standards-doc citation by path: "
        "'standards/process/stub-marker-grep.md'"
    )
    assert "20 across all tools" in agent_dist_text, (
        "compiled agent missing bumped budget token: '20 across all tools'"
    )
    assert "16 across all tools" not in agent_dist_text, (
        "compiled agent still contains stale budget token: "
        "'16 across all tools' (F007 should have replaced all occurrences "
        "with '20 across all tools')"
    )


# -- Standards-doc tests (AC10: section headers + security + patterns) ------


def test_standards_doc_has_five_contract_sections_and_security(
    standards_text: str,
) -> None:
    """AC10: standards/process/stub-marker-grep.md contains all five contract
    section headers verbatim — `## Universal Hard-Fail Patterns`,
    `## Universal Warning Patterns`, `## Per-Project Token List`,
    `## Tests-Path Skip`, `## Verdict Mapping` — plus the
    `## Security Constraints` section.
    """
    required_headers = (
        "## Universal Hard-Fail Patterns",
        "## Universal Warning Patterns",
        "## Per-Project Token List",
        "## Tests-Path Skip",
        "## Verdict Mapping",
        "## Security Constraints",
    )
    for header in required_headers:
        assert header in standards_text, (
            f"standards doc missing section header verbatim: {header!r}"
        )


def test_standards_doc_has_hard_fail_patterns(standards_text: str) -> None:
    """AC10: standards/process/stub-marker-grep.md contains the literal
    universal hard-fail regex patterns from BR-002 — the feature-id-prefixed
    TODO form (`TODO\\(F[0-9]+`), `FIXME`, and `XXX`.

    Region-restricted: slice on the `## Universal Hard-Fail Patterns` header
    and the next `## ` boundary so the assertion is scoped to the hard-fail
    section's body (defends against drift where the patterns appear elsewhere
    in the doc but the canonical section is missing them).

    The raw-string literal `r"TODO\\(F[0-9]+"` preserves the backslash-paren
    so the substring assertion checks for the exact bytes
    `T`, `O`, `D`, `O`, `\\`, `(`, `F`, `[`, `0`, `-`, `9`, `]`, `+`.
    """
    section_header = "## Universal Hard-Fail Patterns"
    section_idx = standards_text.find(section_header)
    assert section_idx != -1, (
        f"standards doc missing section header: {section_header!r}"
    )
    next_section_idx = standards_text.find("\n## ", section_idx + 1)
    if next_section_idx == -1:
        next_section_idx = len(standards_text)
    section_body = standards_text[section_idx:next_section_idx]

    # Feature-id-prefixed TODO form. Use a raw-string literal so the
    # backslash-paren is preserved verbatim in the substring assertion.
    feature_todo_pattern = r"TODO\(F[0-9]+"
    assert feature_todo_pattern in section_body, (
        "Universal Hard-Fail Patterns section missing feature-id-prefixed "
        f"TODO regex literal: {feature_todo_pattern!r}"
    )

    # Conventional code-comment markers.
    assert "FIXME" in section_body, (
        "Universal Hard-Fail Patterns section missing 'FIXME' marker"
    )
    assert "XXX" in section_body, (
        "Universal Hard-Fail Patterns section missing 'XXX' marker"
    )


def test_standards_doc_security_constraints(standards_text: str) -> None:
    """AC10 (security clause): the `## Security Constraints` section names
    (a) the 1024-character cap on token-list entries, (b) the C0 control-set
    sanitization regex, and (c) the no-automatic-Read rule (Grep-only).

    Region-restricted to the Security Constraints section body so the
    assertions are scoped to the right paragraph.
    """
    section_header = "## Security Constraints"
    section_idx = standards_text.find(section_header)
    assert section_idx != -1, (
        f"standards doc missing section header: {section_header!r}"
    )
    next_section_idx = standards_text.find("\n## ", section_idx + 1)
    if next_section_idx == -1:
        next_section_idx = len(standards_text)
    section_body = standards_text[section_idx:next_section_idx]

    # 1024-character cap.
    assert "1024" in section_body, (
        "Security Constraints section missing length cap: '1024'"
    )

    # C0 control-set sanitization regex literal. The raw-string preserves
    # the backslashes so the substring assertion checks for the exact bytes
    # of `\x00-\x1f\x7f`.
    control_set_pattern = r"\x00-\x1f\x7f"
    assert control_set_pattern in section_body, (
        "Security Constraints section missing C0 control-set regex literal: "
        f"{control_set_pattern!r}"
    )

    # No-automatic-Read rule. Accept either the verbatim "no automatic Read"
    # phrasing or the close variant "Grep only" / "never `Read`" used in the
    # standards doc body.
    has_no_read_phrase = "No automatic Read" in section_body
    has_grep_only_phrase = "Grep" in section_body and "never" in section_body
    assert has_no_read_phrase or has_grep_only_phrase, (
        "Security Constraints section missing no-automatic-Read rule: "
        "expected 'No automatic Read' or 'Grep' + 'never' phrasing"
    )


# -- Hook injection test (AC11) ----------------------------------------------


def test_hook_has_stub_grep_section_and_doc_pointer(hook_text: str) -> None:
    """AC11: hooks/inject-standards.sh contains the
    `### Stub-Marker Grep Contract for spec-enforcer` section header AND a
    path reference to the standards doc.
    """
    section_header = "### Stub-Marker Grep Contract for spec-enforcer"
    assert section_header in hook_text, (
        f"hook script missing section header: {section_header!r}"
    )
    assert "standards/process/stub-marker-grep.md" in hook_text, (
        "hook script missing standards-doc path pointer: "
        "'standards/process/stub-marker-grep.md'"
    )


# -- Cross-reference test (AC12) ---------------------------------------------


def test_userflow_has_see_also_pointer(userflow_text: str) -> None:
    """AC12: standards/process/user-flow-completeness.md contains the literal
    substring 'standards/process/stub-marker-grep.md' in its Cross-References
    section.

    Region-restricted: slice on the `## Cross-References` header and the
    next `## ` boundary so the assertion is scoped to the Cross-References
    section's body (defends against drift where the pointer appears
    elsewhere but the canonical Cross-References section is missing it).
    """
    section_header = "## Cross-References"
    section_idx = userflow_text.find(section_header)
    assert section_idx != -1, (
        f"user-flow doc missing section header: {section_header!r}"
    )
    next_section_idx = userflow_text.find("\n## ", section_idx + 1)
    if next_section_idx == -1:
        next_section_idx = len(userflow_text)
    section_body = userflow_text[section_idx:next_section_idx]

    assert "standards/process/stub-marker-grep.md" in section_body, (
        "user-flow doc Cross-References section missing F007 standards-doc "
        "pointer: 'standards/process/stub-marker-grep.md'"
    )
