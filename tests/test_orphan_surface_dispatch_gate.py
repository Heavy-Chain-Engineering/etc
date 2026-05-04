"""Contract tests for Orphan-Surface Dispatch Gate (F003 / BR-009).

Covers PRD .etc_sdlc/features/F003-orphan-surface-dispatch-gate/spec.md via
grep-based assertions over:

- the appended `## Dispatch-time Wiring Contract` section of
  standards/process/user-flow-completeness.md
- the compiled /build skill at dist/skills/build/SKILL.md (sibling 003.002
  owns the build-skill assertions; this module owns the standards-doc half)

Precedent: tests/test_user_flow_completeness.py (the F001 contract test)
and tests/test_spec_enforcer_reachability.py (the F002 contract test).
Same autouse session-scoped compile fixture pattern; same
`Path(...).read_text(encoding="utf-8")` reading idiom; same grep-based
assertions over committed source plus compiled dist/ outputs.

This module owns the 4 standards-doc tests. Sibling subtask 003.002 adds
the 4 build-skill tests + the 1 dispatch-shape preservation test for 8
total. All tests share the module-level fixture and constants below.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source artifact (assert directly against the committed file).
STANDARDS_DOC_PATH = Path(REPO_ROOT) / "standards/process/user-flow-completeness.md"

# Compiled artifact (the session-scoped fixture guarantees it is fresh).
# Sibling subtask 003.002 owns the build-skill assertions; the path constant
# is declared here so both this module and the sibling share the canonical
# location and the module-scoped text fixture below loads it once.
BUILD_SKILL_DIST_PATH = Path(REPO_ROOT) / "dist/skills/build/SKILL.md"


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
def standard_doc_text() -> str:
    assert STANDARDS_DOC_PATH.exists(), (
        f"missing standards doc: {STANDARDS_DOC_PATH}"
    )
    return STANDARDS_DOC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def build_skill_dist_text() -> str:
    assert BUILD_SKILL_DIST_PATH.exists(), (
        f"missing compiled build skill: {BUILD_SKILL_DIST_PATH}; "
        "the session-scoped compile fixture should have created it"
    )
    return BUILD_SKILL_DIST_PATH.read_text(encoding="utf-8")


# -- Standards-doc tests (BR-009) --------------------------------------------


def _dispatch_section_body(standard_doc_text: str) -> str:
    """Return the body of the `## Dispatch-time Wiring Contract` section.

    Slice from the section heading to the next top-level `## ` heading or
    end-of-file, whichever comes first. Used to scope assertions to the
    F003 section so coincidental matches elsewhere in the doc (e.g., from
    F001 / F002 sections) don't satisfy a Dispatch-time check.
    """
    section_header = "## Dispatch-time Wiring Contract"
    start_idx = standard_doc_text.find(section_header)
    assert start_idx != -1, (
        f"standards doc missing section header: {section_header!r}"
    )
    # Search for the next top-of-line `## ` heading after the section start.
    next_section_idx = standard_doc_text.find("\n## ", start_idx + len(section_header))
    if next_section_idx == -1:
        return standard_doc_text[start_idx:]
    return standard_doc_text[start_idx:next_section_idx]


def test_standard_doc_has_dispatch_wiring_section(standard_doc_text: str) -> None:
    """AC1: standards/process/user-flow-completeness.md contains a
    `## Dispatch-time Wiring Contract` section, AND that section references
    the canonical User-flow sentence prefix `As {role}, navigate from`
    verbatim.
    """
    section_header = "## Dispatch-time Wiring Contract"
    assert section_header in standard_doc_text, (
        f"standards doc missing section header: {section_header!r}"
    )

    # Scope the prefix check to the Dispatch-time Wiring Contract section so
    # the assertion isn't satisfied by F001's earlier mentions of the prefix.
    section_body = _dispatch_section_body(standard_doc_text)
    canonical_prefix = "As {role}, navigate from"
    assert canonical_prefix in section_body, (
        "Dispatch-time Wiring Contract section must reference the canonical "
        f"User-flow sentence prefix verbatim: {canonical_prefix!r}"
    )


def test_standard_doc_documents_heuristic_signal_list(
    standard_doc_text: str,
) -> None:
    """AC3 / BR-001: the Dispatch-time Wiring Contract section enumerates
    the four-tier auto-add heuristic preference order with the tier names
    appearing verbatim:

      1. Sidebar-nav config files
      2. Parent-route files matching the new component's route prefix
      3. Barrel exports
      4. Settings-rail / tab-array config files
    """
    section_body = _dispatch_section_body(standard_doc_text)

    tier_1 = "Sidebar-nav config files"
    tier_2 = "Parent-route files matching the new component's route prefix"
    tier_3 = "Barrel exports"
    tier_4 = "Settings-rail / tab-array config files"

    assert tier_1 in section_body, (
        f"Dispatch-time Wiring Contract section missing Tier 1 name: "
        f"{tier_1!r}"
    )
    assert tier_2 in section_body, (
        f"Dispatch-time Wiring Contract section missing Tier 2 name: "
        f"{tier_2!r}"
    )
    assert tier_3 in section_body, (
        f"Dispatch-time Wiring Contract section missing Tier 3 name: "
        f"{tier_3!r}"
    )
    assert tier_4 in section_body, (
        f"Dispatch-time Wiring Contract section missing Tier 4 name: "
        f"{tier_4!r}"
    )

    # Order check: tiers must appear in the prescribed preference order so
    # the auto-add heuristic resolves matches predictably.
    pos_1 = section_body.index(tier_1)
    pos_2 = section_body.index(tier_2)
    pos_3 = section_body.index(tier_3)
    pos_4 = section_body.index(tier_4)
    assert pos_1 < pos_2 < pos_3 < pos_4, (
        "Dispatch-time Wiring Contract section must list tiers in the "
        f"prescribed preference order: Tier 1 (pos {pos_1}) → Tier 2 "
        f"(pos {pos_2}) → Tier 3 (pos {pos_3}) → Tier 4 (pos {pos_4})"
    )


def test_standard_doc_documents_operator_prompt_fallback(
    standard_doc_text: str,
) -> None:
    """AC4 / BR-004: the Dispatch-time Wiring Contract section documents the
    operator-prompt fallback contract — the Pattern A `AskUserQuestion`
    citation, the `surface_status: deferred` deferral marker, and the
    `intentionally orphaned` deferral-option language.
    """
    section_body = _dispatch_section_body(standard_doc_text)

    askuser_literal = "AskUserQuestion"
    deferred_marker = "surface_status: deferred"
    intentional_orphan_phrase = "intentionally orphaned"

    assert askuser_literal in section_body, (
        f"Dispatch-time Wiring Contract section missing Pattern A citation: "
        f"{askuser_literal!r}"
    )
    assert deferred_marker in section_body, (
        f"Dispatch-time Wiring Contract section missing deferral marker: "
        f"{deferred_marker!r}"
    )
    assert intentional_orphan_phrase in section_body, (
        f"Dispatch-time Wiring Contract section missing deferral-option "
        f"language: {intentional_orphan_phrase!r}"
    )


def test_standard_doc_documents_security_constraints(
    standard_doc_text: str,
) -> None:
    """BR-001 + Security: the Dispatch-time Wiring Contract section
    documents the operator-supplied path sanitization rule (control-char
    strip regex `[\\x00-\\x1f\\x7f]` + 256-char cap) and the no-automatic-
    Read constraint (`MUST NOT` near `Read`).
    """
    section_body = _dispatch_section_body(standard_doc_text)

    control_char_regex = "[\\x00-\\x1f\\x7f]"
    char_cap = "256"
    must_not_literal = "MUST NOT"
    read_literal = "Read"

    assert control_char_regex in section_body, (
        f"Dispatch-time Wiring Contract section missing control-char strip "
        f"regex: {control_char_regex!r}"
    )
    assert char_cap in section_body, (
        f"Dispatch-time Wiring Contract section missing 256-char cap "
        f"literal: {char_cap!r}"
    )
    assert must_not_literal in section_body, (
        f"Dispatch-time Wiring Contract section missing no-automatic-Read "
        f"assertion literal: {must_not_literal!r}"
    )
    assert read_literal in section_body, (
        f"Dispatch-time Wiring Contract section missing Read tool name "
        f"literal: {read_literal!r}"
    )

    # Proximity check: `MUST NOT` and `Read` must co-occur in a reasonable
    # window so the assertion is scoped to the no-automatic-Read constraint
    # rather than coincidental occurrences elsewhere in the section.
    must_not_idx = section_body.find(must_not_literal)
    proximity_window = section_body[must_not_idx : must_not_idx + 400]
    assert read_literal in proximity_window, (
        f"Dispatch-time Wiring Contract section: {must_not_literal!r} and "
        f"{read_literal!r} must co-occur within ~400 chars to constitute the "
        "no-automatic-Read constraint; found them too far apart"
    )


# -- Build-skill tests (BR-009) ----------------------------------------------


def _step_6_section(text: str) -> str:
    """Return the body of `### Step 6:` in the build skill text.

    Slice from the `### Step 6:` heading to the next `### Step ` heading or
    end-of-file, whichever comes first. Used to scope assertions to /build's
    Step 6 region so coincidental matches elsewhere (e.g., the Subagent
    Dispatch section earlier in the skill or Step 7's verify block later)
    don't satisfy a Step-6 check.
    """
    section_header = "### Step 6:"
    start_idx = text.find(section_header)
    assert start_idx != -1, (
        f"build skill missing section header: {section_header!r}"
    )
    next_section_idx = text.find("\n### Step ", start_idx + len(section_header))
    if next_section_idx == -1:
        return text[start_idx:]
    return text[start_idx:next_section_idx]


def _normalize_whitespace(text: str) -> str:
    """Collapse all runs of whitespace (newlines included) into single spaces.

    The skill body is prose and wraps mid-sentence, so canonical literals like
    `, navigate from` and `Dispatch hooks will enforce TDD, invariants,
    required reading, and phase gate` may straddle line breaks. The contract
    cares about the canonical string the dispatcher recognizes, not the
    wrapping. Normalize before substring matching.
    """
    return " ".join(text.split())


def test_build_skill_documents_dispatch_detection(
    build_skill_dist_text: str,
) -> None:
    """AC5 / BR-002: dist/skills/build/SKILL.md Step 6 documents the
    User-flow sentence detection step — recognizing the canonical prefix
    `As ` + `, navigate from` in each task's AC list. Detected tasks
    trigger the wiring check; non-detected tasks dispatch unchanged.
    """
    section = _step_6_section(build_skill_dist_text)
    # The canonical `, navigate from` literal wraps across a line break in
    # the prose, so substring matching requires whitespace-normalized text.
    normalized = _normalize_whitespace(section)

    as_literal = "As "
    navigate_from_literal = ", navigate from"
    detection_keyword = "User-flow sentence"

    assert as_literal in section, (
        f"Step 6 missing User-flow sentence prefix literal: {as_literal!r}"
    )
    assert navigate_from_literal in normalized, (
        f"Step 6 missing User-flow sentence connector literal: "
        f"{navigate_from_literal!r}"
    )
    assert detection_keyword in section, (
        f"Step 6 missing detection-step keyword: {detection_keyword!r}"
    )

    # Both branches MUST be documented: detected tasks fire the wiring check
    # AND non-detected tasks pass through unchanged. The brief allows close
    # variants for the pass-through phrase ("passes through" / "unchanged").
    detected_phrase = "Detected tasks"
    assert detected_phrase in section, (
        f"Step 6 missing detected-branch documentation phrase: "
        f"{detected_phrase!r}"
    )
    assert "unchanged" in section, (
        "Step 6 missing pass-through documentation phrase: 'unchanged'"
    )


def test_build_skill_documents_heuristic_invocation(
    build_skill_dist_text: str,
) -> None:
    """AC6 / BR-003: dist/skills/build/SKILL.md Step 6 documents the
    auto-add heuristic invocation — the heuristic name, the four tier
    names verbatim from the standards doc, and the three resolution
    outcomes (exactly one → auto-add; zero → operator prompt; multiple →
    operator prompt).
    """
    section = _step_6_section(build_skill_dist_text)

    # Heuristic name: skill body uses "auto-add heuristic" (close variant of
    # the brief's "Auto-Add Heuristic" — substring match remains case-aware).
    heuristic_keyword = "auto-add heuristic"
    assert heuristic_keyword in section, (
        f"Step 6 missing heuristic-invocation keyword: {heuristic_keyword!r}"
    )

    # Tier names verbatim from the standards doc; require at least 3 of 4
    # but in practice we expect all 4 to appear in the documented heuristic.
    tier_names = [
        "Sidebar-nav",
        "Parent-route",
        "Barrel exports",
        "Settings-rail",
    ]
    found_tiers = [tier for tier in tier_names if tier in section]
    assert len(found_tiers) >= 3, (
        f"Step 6 missing at least 3 of 4 tier names verbatim; found "
        f"{found_tiers!r} from required set {tier_names!r}"
    )

    # Resolution outcomes: exactly-one (auto-add path) and the
    # zero/multiple operator-prompt fallback path.
    auto_add_outcome = "Exactly one"
    zero_outcome = "Zero candidates"
    multiple_outcome = "Multiple"
    assert auto_add_outcome in section, (
        f"Step 6 missing auto-add resolution outcome literal: "
        f"{auto_add_outcome!r}"
    )
    assert zero_outcome in section, (
        f"Step 6 missing zero-candidates resolution outcome literal: "
        f"{zero_outcome!r}"
    )
    assert multiple_outcome in section, (
        f"Step 6 missing multiple-candidates resolution outcome literal: "
        f"{multiple_outcome!r}"
    )


def test_build_skill_documents_wiring_contract_clause(
    build_skill_dist_text: str,
) -> None:
    """AC7 / BR-005: dist/skills/build/SKILL.md Step 6 contains the
    verbatim wiring-contract clause that the dispatcher appends to the
    prompt of every dispatched agent on a User-flow-sentenced task.
    """
    section = _step_6_section(build_skill_dist_text)

    clause_opening = "Your task creates a user-facing surface"
    same_commit_phrase = "wired into the parent navigation graph in the SAME commit"
    grep_instruction = "Before reporting success, run `grep -rn"
    no_success_clause = (
        "If the parent file does not contain a working reference after your "
        "edits, do not report success"
    )

    assert clause_opening in section, (
        f"Step 6 missing wiring-contract clause opening: {clause_opening!r}"
    )
    assert same_commit_phrase in section, (
        f"Step 6 missing wiring-contract same-commit phrase: "
        f"{same_commit_phrase!r}"
    )
    assert grep_instruction in section, (
        f"Step 6 missing wiring-contract grep instruction: "
        f"{grep_instruction!r}"
    )
    assert no_success_clause in section, (
        f"Step 6 missing wiring-contract no-success clause: "
        f"{no_success_clause!r}"
    )


def test_build_skill_cites_standards_doc(
    build_skill_dist_text: str,
) -> None:
    """AC8 / AC10 / BR-006: dist/skills/build/SKILL.md Step 6 cites
    `standards/process/user-flow-completeness.md` by path at least twice
    (once in the detection/heuristic sub-step and once in the wiring-
    contract clause), and names the `Dispatch-time Wiring Contract`
    section being cited.
    """
    section = _step_6_section(build_skill_dist_text)

    standards_path = "standards/process/user-flow-completeness.md"
    section_name = "Dispatch-time Wiring Contract"

    occurrences = section.count(standards_path)
    assert occurrences >= 2, (
        f"Step 6 must cite {standards_path!r} at least twice "
        f"(detection/heuristic sub-step + wiring-contract clause); "
        f"found {occurrences} occurrence(s)"
    )
    assert section_name in section, (
        f"Step 6 missing canonical section-name citation: {section_name!r}"
    )


def test_build_skill_preserves_existing_dispatch_shape(
    build_skill_dist_text: str,
) -> None:
    """AC9 / BR-008: dist/skills/build/SKILL.md Step 6 preserves the
    pre-edit dispatch shape verbatim — the Agent-tool call header, the
    `subagent_type` argument bound to the task's `assigned_agent` field,
    the prompt-content list (`requires_reading`, `files_in_scope`), the
    standard "Dispatch hooks will enforce..." instruction, the Step 6b
    "Wait for wave completion" header, and the parallel fan-out language.

    Adversarial: a refactor that drops or rewrites any of these literals
    (even while adding the new wiring-contract logic) would silently
    break the existing dispatch contract. This test is the regression
    canary.
    """
    section = _step_6_section(build_skill_dist_text)
    # The dispatch-hook instruction wraps across a line break in the prose
    # ("...required reading, and\nphase gate..."), so the whole-sentence
    # canonical literal needs the whitespace-normalized text to match.
    normalized = _normalize_whitespace(section)

    agent_tool_header = "Invoke the Agent tool ONCE with"
    subagent_type_arg = "subagent_type"
    assigned_agent_field = "assigned_agent"
    requires_reading_field = "requires_reading"
    files_in_scope_field = "files_in_scope"
    dispatch_hook_instruction = (
        "Dispatch hooks will enforce TDD, invariants, required reading, and "
        "phase gate"
    )
    wait_header = "Wait for wave completion"
    parallel_fanout_phrase = "parallel fan-out"
    single_turn_phrase = "single turn"

    assert agent_tool_header in section, (
        f"Step 6 missing existing per-task dispatch header: "
        f"{agent_tool_header!r}"
    )
    assert subagent_type_arg in section, (
        f"Step 6 missing existing dispatch argument literal: "
        f"{subagent_type_arg!r}"
    )
    assert assigned_agent_field in section, (
        f"Step 6 missing existing task-field reference: "
        f"{assigned_agent_field!r}"
    )
    assert requires_reading_field in section, (
        f"Step 6 missing existing prompt-content field: "
        f"{requires_reading_field!r}"
    )
    assert files_in_scope_field in section, (
        f"Step 6 missing existing prompt-content field: "
        f"{files_in_scope_field!r}"
    )
    assert dispatch_hook_instruction in normalized, (
        f"Step 6 missing existing standard dispatch-hook instruction: "
        f"{dispatch_hook_instruction!r}"
    )
    assert wait_header in section, (
        f"Step 6 missing existing 6b header: {wait_header!r}"
    )
    assert parallel_fanout_phrase in section, (
        f"Step 6 missing existing parallel-dispatch phrase: "
        f"{parallel_fanout_phrase!r}"
    )
    assert single_turn_phrase in section, (
        f"Step 6 missing existing parallel-dispatch phrase: "
        f"{single_turn_phrase!r}"
    )
