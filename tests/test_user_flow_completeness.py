"""Contract tests for the User-Flow Completeness rule (F001 / BR-008).

Covers PRD .etc_sdlc/features/F001-user-flow-completeness/spec.md AC12,
AC14, and AC15 via grep-based assertions over:

- the new standards doc at standards/process/user-flow-completeness.md
- the compiled /spec skill at dist/skills/spec/SKILL.md (Phase 3 detection,
  Phase 4 gate, augmented DoR checklist item, interactive-input patterns)
- the source hook at hooks/inject-standards.sh (new HEREDOC section and
  the standards pointer)

Precedent: tests/test_spec_three_state.py and tests/test_init_project.py
(class TestSkillMdContract) — grep-based contract tests over committed
source plus compiled dist/ outputs.

The dist/ outputs are compiled by a session-scoped autouse fixture that
invokes `python3 compile-sdlc.py spec/etc_sdlc.yaml` once at session start.
The compiler is idempotent; running it twice is safe. The fixture does NOT
mock the compile step — assertions run against real dist/ files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source artifacts (assert directly against committed files).
STANDARD_DOC = REPO_ROOT / "standards" / "process" / "user-flow-completeness.md"
SKILL_SRC = REPO_ROOT / "skills" / "spec" / "SKILL.md"
INJECT_HOOK = REPO_ROOT / "hooks" / "inject-standards.sh"

# Compiled artifacts (the session-scoped fixture guarantees these are fresh).
SKILL_DIST = REPO_ROOT / "dist" / "skills" / "spec" / "SKILL.md"

# The canonical User-flow sentence form (BR-001, AC1). Asserted verbatim.
CANONICAL_SENTENCE = (
    "As {role}, navigate from {parent route} via {affordance label}, "
    "complete {happy path}, observe {outcome}."
)

# Strong user-facing UI nouns from BR-002 / AC2.
UI_NOUNS: tuple[str, ...] = (
    "modal",
    "page",
    "wizard step",
    "tab",
    "button",
    "drawer",
    "menu",
    "dialog",
    "form",
    "screen",
    "panel",
    "sidebar",
    "link",
    "card",
)

# Strong user-facing user verbs from BR-002 / AC2.
USER_VERBS: tuple[str, ...] = (
    "navigate",
    "click",
    "submit",
    "see",
    "view",
    "open",
    "select",
    "enter",
)


# -- Session-scoped compile fixture ------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _compile_sdlc() -> None:
    """Run compile-sdlc.py once at session start so dist/ is fresh.

    The compiler is idempotent — running twice is fine. We do NOT mock the
    compile step; assertions in this module read real files written by
    compile-sdlc.py from the committed source artifacts.
    """
    subprocess.run(
        ["python3", "compile-sdlc.py", "spec/etc_sdlc.yaml"],
        check=True,
        cwd=str(REPO_ROOT),
        capture_output=True,
    )


# Module-level reference so Pyright sees the autouse fixture as accessed.
# The fixture is invoked by pytest at session start regardless of this line;
# the line exists only to silence Pyright's "is not accessed" hint, which is
# independent of `# pyright: ignore` directives and can only be silenced by
# an actual reference to the symbol.
_ = _compile_sdlc


# -- Module-scoped text fixtures ---------------------------------------------


@pytest.fixture(scope="module")
def standard_text() -> str:
    assert STANDARD_DOC.exists(), f"missing standards doc: {STANDARD_DOC}"
    return STANDARD_DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_dist_text() -> str:
    assert SKILL_DIST.exists(), (
        f"missing compiled skill: {SKILL_DIST}; "
        "the session-scoped compile fixture should have created it"
    )
    return SKILL_DIST.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_src_text() -> str:
    assert SKILL_SRC.exists(), f"missing skill source: {SKILL_SRC}"
    return SKILL_SRC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def inject_hook_text() -> str:
    assert INJECT_HOOK.exists(), f"missing hook script: {INJECT_HOOK}"
    return INJECT_HOOK.read_text(encoding="utf-8")


# -- The seven contract tests (BR-008 / AC12) --------------------------------


def test_standard_doc_exists(standard_text: str) -> None:
    """AC1: standards/process/user-flow-completeness.md exists and contains
    the canonical User-flow sentence form verbatim.
    """
    assert STANDARD_DOC.exists(), (
        f"standards doc must exist at {STANDARD_DOC.relative_to(REPO_ROOT)}"
    )
    assert CANONICAL_SENTENCE in standard_text, (
        "standards/process/user-flow-completeness.md must contain the "
        f"canonical User-flow sentence form verbatim: {CANONICAL_SENTENCE!r}"
    )


def test_standard_documents_signal_list(standard_text: str) -> None:
    """AC2: the standards doc enumerates the strong-user-facing signal list
    (UI nouns + user verbs) and the strong-backend-only signal language
    (status codes, DB rows, background jobs, no UI noun, no user verb).
    """
    # UI nouns — every entry must appear in the signal list.
    for noun in UI_NOUNS:
        assert noun in standard_text, (
            f"standards doc missing UI noun signal: {noun!r}"
        )

    # User verbs — every entry must appear in the signal list.
    for verb in USER_VERBS:
        assert verb in standard_text, (
            f"standards doc missing user verb signal: {verb!r}"
        )

    # Strong-backend-only signal language. The doc enumerates these as the
    # gating conditions for backend-only classification.
    backend_only_markers = (
        "HTTP status codes",
        "database row",
        "background-job",
        "migration",
        "no UI noun",
        "no user verb",
    )
    for marker in backend_only_markers:
        assert marker in standard_text, (
            f"standards doc missing backend-only signal language: {marker!r}"
        )


def test_skill_documents_phase_3_detection(skill_dist_text: str) -> None:
    """AC5, AC6: the compiled skill's Phase 3 documents the auto-detection
    step, references the standards doc by path, and renders the per-AC
    AskUserQuestion options (accept / refine / not-user-facing).
    """
    # The Phase 3 section must exist in the compiled skill so the option
    # labels below are scoped to it.
    phase_3_idx = skill_dist_text.find("### Phase 3:")
    phase_4_idx = skill_dist_text.find("### Phase 4:")
    assert phase_3_idx != -1, "compiled skill missing '### Phase 3:' header"
    assert phase_4_idx != -1, "compiled skill missing '### Phase 4:' header"
    assert phase_4_idx > phase_3_idx, (
        "Phase 4 header must come after Phase 3 header in the compiled skill"
    )
    phase_3_body = skill_dist_text[phase_3_idx:phase_4_idx]

    # Reference to the standards doc by path (BR-002: by name, not duplicated
    # inline).
    assert "standards/process/user-flow-completeness.md" in phase_3_body, (
        "Phase 3 of the compiled skill must reference "
        "standards/process/user-flow-completeness.md by path"
    )

    # Per-AC accept / refine / not-user-facing option labels (AC6).
    accept_label = "Accept the draft User-flow sentence (Recommended)"
    refine_label = "Refine — I have changes"
    backend_label = "Mark this AC not-user-facing"
    assert accept_label in phase_3_body, (
        f"Phase 3 missing AskUserQuestion option label: {accept_label!r}"
    )
    assert refine_label in phase_3_body, (
        f"Phase 3 missing AskUserQuestion option label: {refine_label!r}"
    )
    assert backend_label in phase_3_body, (
        f"Phase 3 missing AskUserQuestion option label: {backend_label!r}"
    )


def test_skill_documents_phase_4_gate(skill_dist_text: str) -> None:
    """AC7, AC8: the compiled skill's Phase 4 documents the WARN-with-YES/NO
    gate text, both gate options, and the surface_status: deferred marker.
    """
    phase_4_idx = skill_dist_text.find("### Phase 4:")
    phase_5_idx = skill_dist_text.find("### Phase 5:")
    assert phase_4_idx != -1, "compiled skill missing '### Phase 4:' header"
    # Phase 5 may or may not exist depending on skill structure; if absent,
    # scope from Phase 4 to end-of-file.
    phase_4_body = (
        skill_dist_text[phase_4_idx:phase_5_idx]
        if phase_5_idx != -1
        else skill_dist_text[phase_4_idx:]
    )

    gate_question = (
        "User-facing ACs are missing User-flow sentences. Continue without them?"
    )
    no_option = "No, fix the missing sentences first (Recommended)"
    yes_option = "Yes, ship without — these surfaces are intentionally deferred"
    deferral_marker = "surface_status: deferred"

    assert gate_question in phase_4_body, (
        f"Phase 4 missing gate question text: {gate_question!r}"
    )
    assert no_option in phase_4_body, (
        f"Phase 4 missing gate option label: {no_option!r}"
    )
    assert yes_option in phase_4_body, (
        f"Phase 4 missing gate option label: {yes_option!r}"
    )
    assert deferral_marker in phase_4_body, (
        f"Phase 4 missing deferral marker: {deferral_marker!r}"
    )


def test_skill_cites_standard_in_dor_item(
    skill_dist_text: str, skill_src_text: str
) -> None:
    """AC9: the augmented DoR checklist item that cites the new standard
    appears verbatim. The compiled skill is the authoritative artifact;
    the source skill is checked as a co-located guard so source/dist drift
    is also caught at this layer.
    """
    augmented_item = (
        "Has measurable acceptance criteria. Every user-facing AC also "
        "includes a User-flow sentence per "
        "`standards/process/user-flow-completeness.md`."
    )
    assert augmented_item in skill_dist_text, (
        "compiled dist/skills/spec/SKILL.md must contain the augmented DoR "
        f"checklist item verbatim: {augmented_item!r}"
    )
    assert augmented_item in skill_src_text, (
        "source skills/spec/SKILL.md must contain the augmented DoR "
        f"checklist item verbatim: {augmented_item!r}"
    )


def test_inject_standards_cites_new_doc(inject_hook_text: str) -> None:
    """AC10 / BR-006: hooks/inject-standards.sh contains the new HEREDOC
    section title and the literal pointer to the standards doc.
    """
    section_title = "### User-Flow Completeness for User-Facing ACs"
    pointer = "See standards/process/user-flow-completeness.md for the full rule."
    assert section_title in inject_hook_text, (
        f"hooks/inject-standards.sh must contain section title: {section_title!r}"
    )
    assert pointer in inject_hook_text, (
        f"hooks/inject-standards.sh must contain standards pointer: {pointer!r}"
    )


def test_skill_uses_interactive_input_patterns(skill_dist_text: str) -> None:
    """AC14 / BR-010: the new Phase 3 and Phase 4 sections of the compiled
    skill use Pattern A (`AskUserQuestion(`) and Pattern B
    (`**▶ Your answer needed:**`) markers. Both literals MUST appear
    somewhere within the Phase 3 — end-of-Phase-4 span so the new prompts
    are demonstrably attributable to the documented patterns.
    """
    phase_3_idx = skill_dist_text.find("### Phase 3:")
    phase_5_idx = skill_dist_text.find("### Phase 5:")
    assert phase_3_idx != -1, "compiled skill missing '### Phase 3:' header"
    new_prompt_span = (
        skill_dist_text[phase_3_idx:phase_5_idx]
        if phase_5_idx != -1
        else skill_dist_text[phase_3_idx:]
    )

    pattern_a_literal = "AskUserQuestion("
    pattern_b_literal = "**▶ Your answer needed:**"

    assert pattern_a_literal in new_prompt_span, (
        "Phase 3 / Phase 4 of the compiled skill must use Pattern A "
        f"({pattern_a_literal!r}) for multi-choice prompts"
    )
    assert pattern_b_literal in new_prompt_span, (
        "Phase 3 / Phase 4 of the compiled skill must use Pattern B "
        f"({pattern_b_literal!r}) for free-form refinement prompts"
    )
