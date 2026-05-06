"""Contract tests for spec-enforcer Reachability Evidence (F002 / BR-008).

Covers PRD .etc_sdlc/features/F002-spec-enforcer-reachability/spec.md AC1-AC11
via grep-based assertions over:

- the appended `## Reachability Evidence` section of
  standards/process/user-flow-completeness.md
- the compiled spec-enforcer agent at dist/agents/spec-enforcer.md
- the compiled /build skill at dist/skills/build/SKILL.md (Step 7
  dispatcher prompt referencing the standards doc)

Precedent: tests/test_user_flow_completeness.py (the F001 contract test).
Same autouse session-scoped compile fixture pattern; same
`Path(...).read_text(encoding="utf-8")` reading idiom; same grep-based
assertions over committed source plus compiled dist/ outputs.

This module owns 3 of the 8 BR-008 tests (the standards-doc and dispatcher
tests). Sibling subtask 004.002.001 adds 3 agent-side tests; sibling
subtask 004.002.002 adds the final 2 agent-side tests. All tests share the
module-level fixture and constants below.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source artifacts (assert directly against committed files).
STANDARD_DOC = REPO_ROOT / "standards" / "process" / "user-flow-completeness.md"

# Compiled artifacts (the session-scoped fixture guarantees these are fresh).
AGENT_DIST = REPO_ROOT / "dist" / "agents" / "spec-enforcer.md"
BUILD_SKILL_DIST = REPO_ROOT / "dist" / "skills" / "build" / "SKILL.md"


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
def agent_dist_text() -> str:
    assert AGENT_DIST.exists(), (
        f"missing compiled agent: {AGENT_DIST}; "
        "the session-scoped compile fixture should have created it"
    )
    return AGENT_DIST.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def build_skill_dist_text() -> str:
    assert BUILD_SKILL_DIST.exists(), (
        f"missing compiled build skill: {BUILD_SKILL_DIST}; "
        "the session-scoped compile fixture should have created it"
    )
    return BUILD_SKILL_DIST.read_text(encoding="utf-8")


# -- Standards-doc tests (BR-008 / AC1-AC5) ----------------------------------


def test_standard_doc_has_reachability_section(standard_text: str) -> None:
    """AC1: standards/process/user-flow-completeness.md contains the
    `## Reachability Evidence` section header and names all three evidence
    forms verbatim (E2E test, static nav-graph reference, manual reachability
    proof). Permissive on case/spacing for the static-reference form per the
    task brief; the E2E and manual-proof phrases are asserted verbatim.
    """
    section_header = "## Reachability Evidence"
    assert section_header in standard_text, (
        f"standards doc missing section header: {section_header!r}"
    )

    # Form 1 — E2E test (verbatim).
    assert "E2E test" in standard_text, (
        "standards doc missing evidence-form name: 'E2E test'"
    )

    # Form 2 — static nav-graph reference. Be permissive on case/spacing per
    # the task brief: accept "static nav-graph reference" or close variants
    # (case-insensitive, optional whitespace between words).
    static_ref_pattern = re.compile(
        r"static\s+nav[\s\-]?graph\s+reference",
        re.IGNORECASE,
    )
    assert static_ref_pattern.search(standard_text) is not None, (
        "standards doc missing evidence-form name: 'static nav-graph reference' "
        "(or close variant)"
    )

    # Form 3 — manual reachability proof. Case-insensitive: the doc's section
    # heading capitalizes the phrase ("Manual reachability proof"), and the
    # task brief lists it as 'manual reachability proof'. Accept either.
    manual_proof_pattern = re.compile(r"manual\s+reachability\s+proof", re.IGNORECASE)
    assert manual_proof_pattern.search(standard_text) is not None, (
        "standards doc missing evidence-form name: 'manual reachability proof' "
        "(or capitalized variant)"
    )


def test_standard_doc_documents_evidence_forms(standard_text: str) -> None:
    """AC2-AC4: the Reachability Evidence section documents the per-form
    contract — placeholder tokens, the loose-substring rule for static
    references (false positives acceptable), the E2E evidence shape, and
    the manual-proof evidence shape — verbatim where the task brief
    specifies verbatim.
    """
    # Per-form placeholder slots that appear in the contract language.
    placeholders = ("{parent route}", "{affordance label}", "{happy path}", "{outcome}")
    for placeholder in placeholders:
        assert placeholder in standard_text, (
            f"standards doc missing User-flow placeholder slot: {placeholder!r}"
        )

    # Loose-substring static-reference rule. The task brief allows either the
    # literal pair "loose" + "substring" OR the phrase "false positives". Both
    # forms communicate the GA-003 acceptable-noise contract; this test
    # accepts whichever the doc author used.
    has_loose_substring = "loose" in standard_text and "substring" in standard_text
    has_false_positives = "false positive" in standard_text
    assert has_loose_substring or has_false_positives, (
        "standards doc missing loose-substring static-reference rule: "
        "expected either 'loose' + 'substring' tokens or 'false positives' "
        "phrase to communicate the GA-003 acceptable-noise contract"
    )

    # E2E / static-reference evidence shape: `<test_file_path>: <quoted line>`.
    e2e_evidence_shape = "<test_file_path>: <quoted line>"
    assert e2e_evidence_shape in standard_text, (
        f"standards doc missing E2E evidence shape: {e2e_evidence_shape!r}"
    )

    # Manual-proof evidence shape: `<artifact_path> @ <ISO8601> by <operator_name>`.
    manual_evidence_shape = "<artifact_path> @ <ISO8601> by <operator_name>"
    assert manual_evidence_shape in standard_text, (
        f"standards doc missing manual-proof evidence shape: "
        f"{manual_evidence_shape!r}"
    )


# -- /build dispatcher test (BR-008 / AC11) ----------------------------------


def test_build_dispatcher_cites_standards_doc(build_skill_dist_text: str) -> None:
    """AC11: dist/skills/build/SKILL.md Step 7 spec-enforcer dispatch prompt
    references the standards doc by path AND declares that User-flow
    sentences require reachability evidence per the standard.

    Region-restricted: the Step 7 / Step 8 markers slice the file so the
    assertion is scoped to Step 7's body only — defends against drift where
    the literals appear elsewhere (e.g., a later step or the Step 8 report
    template) but Step 7's dispatcher prompt is missing them.
    """
    step_7_idx = build_skill_dist_text.find("### Step 7:")
    step_8_idx = build_skill_dist_text.find("### Step 8:")
    assert step_7_idx != -1, "compiled build skill missing '### Step 7:' header"
    assert step_8_idx != -1, "compiled build skill missing '### Step 8:' header"
    assert step_8_idx > step_7_idx, (
        "Step 8 header must come after Step 7 header in the compiled build skill"
    )
    step_7_body = build_skill_dist_text[step_7_idx:step_8_idx]

    standards_doc_path = "standards/process/user-flow-completeness.md"
    assert standards_doc_path in step_7_body, (
        "Step 7 of the compiled build skill must reference the standards doc "
        f"by path: {standards_doc_path!r}"
    )

    # User-flow sentence reference. Be permissive on the close variant per
    # the task brief: accept "User-flow sentence" verbatim or "User-flow"
    # appearing as a noun phrase in the dispatcher prompt body.
    has_full_phrase = "User-flow sentence" in step_7_body
    has_close_variant = "User-flow" in step_7_body
    assert has_full_phrase or has_close_variant, (
        "Step 7 of the compiled build skill must mention 'User-flow sentence' "
        "(or 'User-flow' close variant) in the spec-enforcer dispatcher prompt"
    )


# -- Agent-side tests (BR-008 / AC6, AC8, AC9, AC16) -------------------------


def test_agent_documents_user_flow_sentence_detection(agent_dist_text: str) -> None:
    """AC6 + AC16: dist/agents/spec-enforcer.md documents the canonical
    User-flow sentence detection rule (prefix `As ` + `, navigate from`) AND
    documents the legacy-AC fall-through behavior — ACs that do NOT contain a
    User-flow sentence pass through the existing per-AC evaluation flow
    unchanged (BR-010 / AC16).
    """
    assert "As " in agent_dist_text, (
        "compiled agent missing User-flow sentence detection token: 'As '"
    )
    assert ", navigate from" in agent_dist_text, (
        "compiled agent missing User-flow sentence detection token: "
        "', navigate from'"
    )

    # AC16 fall-through coverage: the Wave 2 edit added a "Legacy-AC
    # fall-through" sub-section whose body states that ACs which do NOT
    # contain a User-flow sentence pass through the existing per-AC
    # evaluation flow unchanged. Assert both indicative phrases appear in
    # the same vicinity (within a 600-char window) so the assertion is
    # scoped to the fall-through paragraph rather than coincidental
    # occurrences elsewhere in the file.
    fallthrough_idx = agent_dist_text.find("do NOT contain a User-flow sentence")
    assert fallthrough_idx != -1, (
        "compiled agent missing legacy-AC fall-through phrase: "
        "'do NOT contain a User-flow sentence'"
    )
    window = agent_dist_text[fallthrough_idx : fallthrough_idx + 600]
    assert "pass through" in window, (
        "compiled agent missing legacy-AC fall-through phrase: 'pass through' "
        "in the vicinity of 'do NOT contain a User-flow sentence'"
    )


def test_agent_budget_is_20(agent_dist_text: str) -> None:
    """AC8 (post-F007): dist/agents/spec-enforcer.md declares a hard tool
    budget total of 20 calls. F007's BR-007 bumped the total from 16 → 20
    (Grep 8 → 12) to accommodate Step 2d's per-cited-file stub-marker grep.
    The literal string '20 across all tools' appears verbatim in the Tool
    Budget section; the prior F002-era '16 across all tools' literal does
    NOT survive anywhere in the file (catches stale post-F007 backsliding);
    the pre-F002 '12 across all tools' literal also does NOT survive
    (preserves the original stale-budget regression check).
    """
    assert "20 across all tools" in agent_dist_text, (
        "compiled agent missing bumped budget token: '20 across all tools'"
    )
    assert "16 across all tools" not in agent_dist_text, (
        "compiled agent still contains stale budget token: "
        "'16 across all tools' (F007 should have replaced all occurrences "
        "with '20 across all tools')"
    )
    assert "12 across all tools" not in agent_dist_text, (
        "compiled agent still contains stale budget token: "
        "'12 across all tools' (pre-F002 budget should never reappear)"
    )


def test_agent_cites_standards_doc(agent_dist_text: str) -> None:
    """AC9: dist/agents/spec-enforcer.md references the standards doc by
    path at least once in the per-AC evaluation step (cited from the
    Process Step 2a/2b/2c additions; the agent body MUST NOT duplicate the
    evidence taxonomy inline).
    """
    standards_doc_path = "standards/process/user-flow-completeness.md"
    assert standards_doc_path in agent_dist_text, (
        "compiled agent missing standards-doc citation by path: "
        f"{standards_doc_path!r}"
    )


def test_agent_documents_three_evidence_forms(agent_dist_text: str) -> None:
    """AC7 / BR-003: dist/agents/spec-enforcer.md documents the three
    evidence-form names verbatim and in BR-003's prescribed order
    (E2E test → static nav-graph reference → manual reachability proof),
    along with stop-at-first-hit semantics.

    Region-restricted: slice the agent body on Step 2b's heading
    ("Three-Tier Reachability Evidence Check") and the next `### `
    boundary so the assertion is scoped to Step 2b's body — defends
    against drift where the form names appear elsewhere (e.g., a later
    sub-section referencing the same taxonomy) but Step 2b's check list
    is missing them or out of order.
    """
    # Locate the Step 2b heading. The agent body uses
    # "### Step 2b: Three-Tier Reachability Evidence Check" — accept either
    # the "Step 2b" anchor or the human-readable subtitle to be tolerant
    # of minor heading edits.
    step_2b_idx = agent_dist_text.find("Three-Tier Reachability Evidence Check")
    if step_2b_idx == -1:
        step_2b_idx = agent_dist_text.find("Step 2b")
    assert step_2b_idx != -1, (
        "compiled agent missing Step 2b heading: "
        "'Three-Tier Reachability Evidence Check' or 'Step 2b'"
    )

    # Slice from Step 2b to the next `### ` (top-of-line) boundary.
    next_section_idx = agent_dist_text.find("\n### ", step_2b_idx + 1)
    if next_section_idx == -1:
        next_section_idx = len(agent_dist_text)
    step_2b_body = agent_dist_text[step_2b_idx:next_section_idx]

    # Three evidence-form headings, verbatim and in order.
    form_1 = "Form 1: E2E test"
    form_2 = "Form 2: Static nav-graph reference"
    form_3 = "Form 3: Manual reachability proof"

    assert form_1 in step_2b_body, (
        f"Step 2b body missing evidence-form heading verbatim: {form_1!r}"
    )
    assert form_2 in step_2b_body, (
        f"Step 2b body missing evidence-form heading verbatim: {form_2!r}"
    )
    assert form_3 in step_2b_body, (
        f"Step 2b body missing evidence-form heading verbatim: {form_3!r}"
    )

    # Order check: positions must ascend (Form 1 before Form 2 before Form 3).
    pos_1 = step_2b_body.index(form_1)
    pos_2 = step_2b_body.index(form_2)
    pos_3 = step_2b_body.index(form_3)
    assert pos_1 < pos_2 < pos_3, (
        "Step 2b body must list evidence forms in BR-003's prescribed order: "
        f"Form 1 (pos {pos_1}) → Form 2 (pos {pos_2}) → Form 3 (pos {pos_3})"
    )

    # Stop-at-first-hit semantics: accept the verbatim BR-003 phrase
    # 'stopping at the first form found' OR the close variant
    # 'first form found'. Either communicates the contract.
    has_full_phrase = "stopping at the first form found" in step_2b_body
    has_close_variant = "first form found" in step_2b_body
    assert has_full_phrase or has_close_variant, (
        "Step 2b body missing stop-at-first-hit semantics: expected "
        "'stopping at the first form found' or 'first form found'"
    )


def test_agent_preserves_existing_json_schema(agent_dist_text: str) -> None:
    """AC10 / BR-007: dist/agents/spec-enforcer.md preserves the JSON output
    schema verbatim from F002's pre-build state. All 12 top-level fields
    appear, and the verdict-state enum line is byte-equivalent. Catches any
    accidental schema mutation by sibling Wave 2 agent edits.
    """
    # All 12 top-level field names from BR-007's preserved-verbatim schema.
    schema_fields = (
        "scope",
        "prd_path",
        "deliverable",
        "totals",
        "violations",
        "satisfied",
        "not_applicable",
        "insufficient_evidence",
        "verdict",
        "blocking_acs",
        "budget_exhausted",
        "notes",
    )
    for field in schema_fields:
        assert field in agent_dist_text, (
            f"compiled agent missing preserved JSON schema field: {field!r}"
        )

    # Verdict-state enum line must appear verbatim per AC10.
    verdict_enum = "COMPLIANT | NON_COMPLIANT | INSUFFICIENT_EVIDENCE | BLOCKED"
    assert verdict_enum in agent_dist_text, (
        "compiled agent missing verdict-state enum line verbatim: "
        f"{verdict_enum!r}"
    )
