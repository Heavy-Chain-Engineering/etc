"""Contract tests for /spec → /spec + /architect phase split (F006 / BR-011).

Covers PRD .etc_sdlc/features/F006-spec-architect-split/spec.md acceptance
criteria AC15-AC18 via:

- Grep-based assertions over the compiled ``dist/`` outputs (skills/architect,
  skills/spec, skills/build, agents/architect). The session-scoped autouse
  ``_compile_sdlc`` fixture guarantees the dist artifacts are fresh.
- In-process unit tests against ``scripts/value_hypothesis.py`` to prove the
  schema validator accepts both the legacy single-``author_role`` shape
  (F001-F009) AND the new ``spec_author_role`` + ``architect_author_role``
  shape (F010+), per BR-007.
- A forward-only invariant test that constructs a synthetic legacy F005-style
  feature directory under ``tmp_path`` (single-file ``gray-areas.md`` +
  legacy single ``author_role`` in ``value-hypothesis.yaml``) and asserts
  the existing helpers continue to read it without raising.

Test isolation contract (AC18):
    Every test uses pytest ``tmp_path``. NO test reads or writes real
    ``.etc_sdlc/features/`` or ``docs/adrs/`` directories. The grep tests
    read compiled ``dist/`` artifacts, which are session-scoped read-only
    inputs by construction.

Precedent:
- tests/test_directory_lifecycle.py (F009) — closest pattern: pytest
  tmp_path + sys.path manipulation for in-process imports +
  ``# pyright: ignore[reportMissingImports]`` directive on the import.
- tests/test_completion_report.py (F005) — autouse session-scoped
  ``_compile_sdlc`` fixture + module-level ``_ = _compile_sdlc`` Pyright
  workaround + grep-based contract assertions over committed dist outputs.
- tests/test_wave_planner_implicit_deps.py (F008) — sys.path manipulation
  for in-process helper imports.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# Compiled artifacts (the session-scoped fixture guarantees these are fresh).
ARCHITECT_SKILL_DIST = REPO_ROOT / "dist" / "skills" / "architect" / "SKILL.md"
SPEC_SKILL_DIST = REPO_ROOT / "dist" / "skills" / "spec" / "SKILL.md"
BUILD_SKILL_DIST = REPO_ROOT / "dist" / "skills" / "build" / "SKILL.md"
ARCHITECT_AGENT_DIST = REPO_ROOT / "dist" / "agents" / "architect.md"

# Make scripts/ importable so the in-process schema-validator tests can drive
# value_hypothesis.validate_schema directly. Mirrors F005/F008/F009 precedent.
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import value_hypothesis as value_hypothesis_module  # pyright: ignore[reportMissingImports]  # noqa: E402

# ── Session-scoped compile fixture ───────────────────────────────────────


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


# ── Module-scoped text fixtures ──────────────────────────────────────────


@pytest.fixture(scope="module")
def architect_skill_dist_text() -> str:
    assert ARCHITECT_SKILL_DIST.exists(), (
        f"missing compiled skill: {ARCHITECT_SKILL_DIST}; "
        "the session-scoped compile fixture should have created it"
    )
    return ARCHITECT_SKILL_DIST.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def spec_skill_dist_text() -> str:
    assert SPEC_SKILL_DIST.exists(), (
        f"missing compiled skill: {SPEC_SKILL_DIST}; "
        "the session-scoped compile fixture should have created it"
    )
    return SPEC_SKILL_DIST.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def build_skill_dist_text() -> str:
    assert BUILD_SKILL_DIST.exists(), (
        f"missing compiled skill: {BUILD_SKILL_DIST}; "
        "the session-scoped compile fixture should have created it"
    )
    return BUILD_SKILL_DIST.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def architect_agent_dist_text() -> str:
    assert ARCHITECT_AGENT_DIST.exists(), (
        f"missing compiled agent: {ARCHITECT_AGENT_DIST}; "
        "the session-scoped compile fixture should have created it"
    )
    return ARCHITECT_AGENT_DIST.read_text(encoding="utf-8")


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_legacy_feature_dir(tmp_path: Path, slug: str = "F005-legacy") -> Path:
    """Create a synthetic F001-F009-style feature directory under ``tmp_path``.

    The legacy layout (per F006 BR-012, the "forward-only" invariant) has:
    - a single-file ``gray-areas.md`` (NOT ``gray-areas-spec.md`` or
      ``gray-areas-architect.md``).
    - a ``value-hypothesis.yaml`` carrying the LEGACY single ``author_role``
      field (NOT ``spec_author_role`` or ``architect_author_role``).
    - a ``spec.md`` (intent) — and NO ``design.md`` (legacy specs predate
      the architect phase).

    Returns the feature directory path.
    """
    feature_dir = tmp_path / ".etc_sdlc" / "features" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "spec.md").write_text(
        "# Legacy Spec\n", encoding="utf-8"
    )
    (feature_dir / "gray-areas.md").write_text(
        "# Gray Areas (legacy single-file)\n", encoding="utf-8"
    )
    (feature_dir / "value-hypothesis.yaml").write_text(
        yaml.safe_dump(
            _make_legacy_hypothesis_dict(slug),
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return feature_dir


def _make_legacy_hypothesis_dict(slug: str = "F005-legacy") -> dict[str, object]:
    """Build a synthetic legacy F001-F009 hypothesis dict (single author_role)."""
    return {
        "schema_version": 1,
        "feature_id": slug.split("-", 1)[0],
        "author_role": "Engineer",
        "who": "Backend developers",
        "current_cost": "Manual report assembly takes hours",
        "predicted": {
            "metric": "report_minutes",
            "direction": "decrease",
            "threshold": 5,
            "window_days": 14,
        },
        "how_we_know": "Compare median report time before/after",
        "status": "pending",
        "validation": {
            "measured_at": None,
            "measured_value": None,
            "evidence": None,
        },
    }


def _make_new_hypothesis_dict(
    slug: str = "F010-new",
) -> dict[str, object]:
    """Build a synthetic F010+ hypothesis dict with the new dual-role schema.

    Per F006 BR-007: the new shape uses ``spec_author_role`` AND
    ``architect_author_role`` instead of the legacy ``author_role``. The
    legacy field MUST be absent on a strictly-new file (it can coexist
    when migrating, but a fresh-authored F010+ file should not include it).
    """
    return {
        "schema_version": 1,
        "feature_id": slug.split("-", 1)[0],
        "spec_author_role": "PM",
        "architect_author_role": "Engineer",
        "who": "PMs and engineers",
        "current_cost": "Single-author /spec forces wrong-role authoring",
        "predicted": {
            "metric": "phase_split_adoption",
            "direction": "increase",
            "threshold": 3,
            "window_days": 30,
        },
        "how_we_know": "Count F010+ features that ship design.md",
        "status": "pending",
        "validation": {
            "measured_at": None,
            "measured_value": None,
            "evidence": None,
        },
    }


# ── AC15 #1: /architect skill body has all 5 phase headers ───────────────


def test_should_contain_all_five_phase_headers_when_architect_skill_compiled(
    architect_skill_dist_text: str,
) -> None:
    """AC15 #1 + BR-003: ``dist/skills/architect/SKILL.md`` declares all 5
    phase headers verbatim.

    The skill mirrors /spec's 5-phase structure (F006 BR-003): Phase 1
    intent capture, Phase 2 research, Phase 2.5 gray-area resolution,
    Phase 2.75 three-state classifier, Phase 3 section drafting, Phase 4
    DoR validation, Phase 5 output. The five "major" phase headers the
    test asserts on are Phase 1, Phase 2, Phase 3, Phase 4, Phase 5
    (the .5/.75 sub-phases live under Phase 2's umbrella).
    """
    expected_headers = [
        "### Phase 1: Intent capture",
        "### Phase 2: Research",
        "### Phase 3: Section drafting",
        "### Phase 4: DoR validation",
        "### Phase 5: Output",
    ]
    for header in expected_headers:
        assert header in architect_skill_dist_text, (
            f"compiled dist/skills/architect/SKILL.md missing phase header "
            f"{header!r}; F006 BR-003 mandates all 5 phase headers verbatim"
        )


# ── AC15 #2: /architect classifier constants present ─────────────────────


def test_should_declare_classifier_constants_when_architect_skill_compiled(
    architect_skill_dist_text: str,
) -> None:
    """AC15 #2 + BR-003 (Phase 2.75) + GA-005: the three FILL_RATIO_*
    classifier constants appear verbatim with their initial parity values
    matching /spec's.

    Per F006 GA-005, /architect's classifier constants start identical to
    /spec's at launch (per-phase divergence is future work). Tuning is a
    one-line edit in the skill body; the test pins the literal values so
    drift is caught.
    """
    expected_literals = [
        "FILL_RATIO_RESEARCH_ASSIST_MAX = 0.20",
        "FILL_RATIO_REJECT_MIN          = 0.50",
        "UNFILLABLE_GAP_REJECT_CAP      = 3",
    ]
    for literal in expected_literals:
        assert literal in architect_skill_dist_text, (
            f"compiled dist/skills/architect/SKILL.md missing classifier "
            f"constant declaration {literal!r}"
        )


# ── AC15 #3: /architect Phase 3 lists the 7 sections in order ────────────


def test_should_list_seven_sections_in_order_when_architect_phase_3(
    architect_skill_dist_text: str,
) -> None:
    """AC15 #3 + BR-003 (Phase 3) + AC5: Phase 3 documents the 7 sections
    in the documented order.

    Slice on the Phase 3 header so the test is scoped to the section
    drafting region (the section names also appear elsewhere — Design
    Output Format skeleton, DoR checklist — and we want the test to fail
    when the Phase 3 ORDER drifts, not when distant sections drift).
    """
    phase_3_marker = "### Phase 3: Section drafting"
    phase_4_marker = "### Phase 4: DoR validation"

    p3_idx = architect_skill_dist_text.find(phase_3_marker)
    assert p3_idx != -1, (
        f"compiled dist/skills/architect/SKILL.md missing Phase 3 marker "
        f"{phase_3_marker!r}"
    )
    p4_idx = architect_skill_dist_text.find(phase_4_marker, p3_idx)
    assert p4_idx != -1, (
        f"compiled dist/skills/architect/SKILL.md missing Phase 4 marker "
        f"{phase_4_marker!r} after Phase 3"
    )
    phase_3_region = architect_skill_dist_text[p3_idx:p4_idx]

    expected_sections = [
        "Architecture Overview",
        "Data Model",
        "API Contracts",
        "Module Structure",
        "Technical Constraints",
        "Security Considerations",
        "Trade-offs",
    ]

    # Each section name must appear within the Phase 3 region.
    for section in expected_sections:
        assert section in phase_3_region, (
            f"Phase 3 region missing section name {section!r}; F006 AC5 "
            f"mandates all 7 section names appear in Phase 3"
        )

    # Order check: the FIRST occurrence of each name within the Phase 3
    # region must be in the documented order. Using the first-match index
    # protects the test from incidental later mentions.
    indices = [phase_3_region.find(name) for name in expected_sections]
    assert indices == sorted(indices), (
        f"Phase 3 sections out of order; got first-occurrence indices "
        f"{dict(zip(expected_sections, indices, strict=True))}; F006 AC5 "
        f"mandates the order: {expected_sections}"
    )


# ── AC15 #4: /architect Phase 5 specifies the 6 output paths/items ───────


def test_should_specify_six_output_paths_when_architect_phase_5(
    architect_skill_dist_text: str,
) -> None:
    """AC15 #4 + BR-004 + Definition of Done items 4-7: Phase 5 names all
    six output paths/items for /architect's well-architected and
    research-assisted classifications.

    The six items per BR-004:
    1. design.md — the 7-section architecture document.
    2. docs/adrs/ — 1-N ADR files at docs/adrs/F<NNN>-<slug>.md.
    3. gray-areas-architect.md — Phase 2.5 resolutions.
    4. research/architect-codebase.md — Phase 2 codebase findings.
    5. state.yaml architect_phase block (BR-008 merge-preserve).
    6. value-hypothesis.yaml architect_author_role field (BR-007).

    Slice on the Phase 5 header so the test is scoped to the output
    region (the Definition of Done section ALSO names these paths but
    serves a different contract — output discipline vs. exit criteria).
    """
    phase_5_marker = "### Phase 5: Output"
    p5_idx = architect_skill_dist_text.find(phase_5_marker)
    assert p5_idx != -1, (
        f"compiled dist/skills/architect/SKILL.md missing Phase 5 marker "
        f"{phase_5_marker!r}"
    )
    # Upper bound: the Design Output Format header (Phase 5 ends before
    # the format skeleton). If the format header is absent, fall through
    # to end-of-file.
    format_idx = architect_skill_dist_text.find(
        "## Design Output Format", p5_idx
    )
    upper = format_idx if format_idx != -1 else len(architect_skill_dist_text)
    phase_5_region = architect_skill_dist_text[p5_idx:upper]

    expected_items = [
        "design.md",
        "docs/adrs/",
        "gray-areas-architect.md",
        "research/architect-codebase.md",
        "architect_phase",
        "architect_author_role",
    ]
    for item in expected_items:
        assert item in phase_5_region, (
            f"Phase 5 region missing reference to {item!r}; F006 BR-004 "
            f"mandates all 6 output paths/items appear in Phase 5"
        )


# ── AC15 #5: agents/architect.md frontmatter has primary_phase field ─────


def test_should_declare_primary_phase_when_architect_agent_frontmatter(
    architect_agent_dist_text: str,
) -> None:
    """AC15 #5 + BR-003 (architect agent metadata): the compiled
    ``dist/agents/architect.md`` carries ``primary_phase: architect`` inside
    its YAML frontmatter delimiters.

    The agent body (description, examples) is unchanged by F006 (per the
    PRD's Out-of-Scope section: "Renaming agents/architect.md (it stays
    at the same path; only metadata changes)"). Only the metadata field
    is added.
    """
    # Frontmatter delimiters: opening "---\n" at file start, closing
    # "\n---\n" or end-of-frontmatter marker.
    assert architect_agent_dist_text.startswith("---\n"), (
        "compiled dist/agents/architect.md does not begin with '---\\n' "
        "frontmatter delimiter; F006 BR-003 mandates a YAML frontmatter "
        "block carrying primary_phase"
    )
    # Find the second "---" line (closing delimiter).
    closing_idx = architect_agent_dist_text.find("\n---", 4)
    assert closing_idx != -1, (
        "compiled dist/agents/architect.md missing closing '---' "
        "frontmatter delimiter"
    )
    frontmatter = architect_agent_dist_text[4:closing_idx]
    assert "primary_phase: architect" in frontmatter, (
        f"compiled dist/agents/architect.md frontmatter missing literal "
        f"'primary_phase: architect'; got frontmatter={frontmatter!r}"
    )


# ── AC15 #6: /build Step 1c warning text appears verbatim in dist ────────


def test_should_contain_step_1c_warning_verbatim_when_build_skill_compiled(
    build_skill_dist_text: str,
) -> None:
    """AC15 #6 + BR-005: the compiled ``dist/skills/build/SKILL.md``
    contains the EXACT verbatim Step 1c warning string.

    Per F006 BR-005, /build emits this stderr warning when engineering
    signals fire and design.md is absent. The test contract greps the
    verbatim string — paraphrasing or reflowing breaks the contract that
    /build's actual emit-time string-write must match.

    The warning text is also load-bearing for the F006 PRD's Edge Case 9
    ("F001-F009 spec.md format with new /build" — warning fires cosmetically
    but build proceeds).
    """
    expected_warning = (
        "WARNING: spec.md implies engineering work but design.md is absent. "
        "Consider running /architect first. Proceeding with build using spec.md alone."
    )
    assert expected_warning in build_skill_dist_text, (
        "compiled dist/skills/build/SKILL.md missing Step 1c warning text "
        f"verbatim. Expected: {expected_warning!r}"
    )


# ── AC15 #7: /spec Phase 5 auto-detect Pattern A appears in dist ─────────


def test_should_contain_phase_5_auto_detect_when_spec_skill_compiled(
    spec_skill_dist_text: str,
) -> None:
    """AC15 #7 + BR-002: the compiled ``dist/skills/spec/SKILL.md`` Phase 5
    region contains the AskUserQuestion picker for "Run /architect?" with
    the four documented options.

    Per F006 BR-002, when /spec's Phase 5 detects engineering-signal tokens,
    it surfaces a Pattern A picker offering: chain-now, chain-later,
    non-engineering, chain-now-design-mandatory. The state.yaml field
    `architect_recommendation` records the answer using the underlying
    enum values (chain_now | chain_later | non_engineering |
    chain_now_design_mandatory | not_applicable).

    Slice on the Phase 5 header so the test is scoped (the Pattern A
    options appear nowhere else in /spec's body).
    """
    phase_5_marker = "### Phase 5: Output"
    p5_idx = spec_skill_dist_text.find(phase_5_marker)
    assert p5_idx != -1, (
        f"compiled dist/skills/spec/SKILL.md missing Phase 5 marker "
        f"{phase_5_marker!r}"
    )
    phase_5_region = spec_skill_dist_text[p5_idx:]

    # Pattern A header chip — short, AskUserQuestion-friendly, chip-label
    # length cap respected.
    assert 'header: "Run /architect?"' in phase_5_region, (
        "compiled dist/skills/spec/SKILL.md Phase 5 region missing the "
        'AskUserQuestion header literal `header: "Run /architect?"`'
    )

    # The four state.yaml enum values that record each option's outcome.
    # These are the load-bearing identifiers — the prose-level option
    # labels are wordsmithing-tunable, but the enum values are the
    # downstream-visible contract that /build Step 1c reads.
    expected_enum_values = [
        "chain_now",
        "chain_later",
        "non_engineering",
        "chain_now_design_mandatory",
    ]
    for value in expected_enum_values:
        assert value in phase_5_region, (
            f"compiled dist/skills/spec/SKILL.md Phase 5 region missing "
            f"architect_recommendation enum value {value!r}; F006 BR-002 "
            f"mandates all four documented options surface in Phase 5"
        )


# ── AC15 #8: value-hypothesis.yaml validator accepts both schemas ────────


def test_should_accept_legacy_author_role_when_validating_hypothesis() -> None:
    """AC15 #8 + BR-007: the schema validator accepts the LEGACY single
    ``author_role`` shape (F001-F009 backward compatibility).

    Construct a synthetic legacy hypothesis dict (with ``author_role`` and
    no ``spec_author_role``/``architect_author_role``) and assert
    validate_schema returns without raising.
    """
    legacy = _make_legacy_hypothesis_dict()
    # Validator is void-returning; "passes" == no exception raised.
    value_hypothesis_module.validate_schema(legacy)


def test_should_accept_new_dual_role_when_validating_hypothesis() -> None:
    """AC15 #8 + BR-007: the schema validator accepts the NEW dual-role
    shape (``spec_author_role`` + ``architect_author_role``).

    Construct a synthetic F010+ hypothesis dict with the new shape and
    assert validate_schema returns without raising. Per BR-007: "at least
    one of {author_role, spec_author_role} must be present;
    architect_author_role is independently optional."
    """
    new_shape = _make_new_hypothesis_dict()
    value_hypothesis_module.validate_schema(new_shape)


def test_should_reject_when_both_author_role_fields_missing() -> None:
    """AC15 #8 + BR-007 (negative case): the validator MUST reject a
    hypothesis missing BOTH ``author_role`` and ``spec_author_role``.

    BR-007's contract is "at least one of {author_role, spec_author_role}
    must be present" — neither-present is the rejection case. Constructed
    by removing ``author_role`` from the legacy dict without adding
    ``spec_author_role``; everything else is valid so the missing-field
    error is the only reason for rejection.
    """
    legacy = _make_legacy_hypothesis_dict()
    del legacy["author_role"]
    # Sanity: neither author_role nor spec_author_role is present now.
    assert "author_role" not in legacy
    assert "spec_author_role" not in legacy

    with pytest.raises(ValueError) as excinfo:
        value_hypothesis_module.validate_schema(legacy)
    # Error message names the missing field so /spec and /architect can
    # surface a remediable message to the operator.
    assert "author_role" in str(excinfo.value), (
        f"validator rejection message must name 'author_role' so the "
        f"caller can remediate; got {excinfo.value!r}"
    )


# ── AC16+AC17+AC18: forward-only invariant + preservation ────────────────


def test_should_keep_legacy_layout_valid_when_forward_only_invariant(
    tmp_path: Path,
) -> None:
    """AC16 + AC17 + AC18 + BR-012: synthetic F001-F009-style feature dir
    under tmp_path remains valid post-F006.

    Forward-only invariant per F006 BR-012: "F001-F009 specs continue to
    work unchanged. /build Step 1a still recognizes legacy single-file
    spec.md. F006 itself is authored using legacy gray-areas.md. New
    features after F006 ships use the new layout. Resolver handles both
    layouts gracefully."

    Construction (the legacy layout):
    - feature dir at ``<tmp_path>/.etc_sdlc/features/F005-legacy/``
    - single-file ``gray-areas.md`` (NOT split into spec/architect).
    - ``value-hypothesis.yaml`` with legacy single ``author_role`` field.
    - ``spec.md`` (intent only — no design.md, no architect phase).

    Assertions:
    1. The legacy ``value-hypothesis.yaml`` round-trips through
       ``value_hypothesis.load`` without raising — the validator's
       BR-007 backward-compat clause (legacy ``author_role`` accepted)
       is exercised end-to-end via the file-load path, not just the
       in-memory schema check.
    2. The legacy ``gray-areas.md`` filename remains the source of truth
       (NOT ``gray-areas-spec.md`` or ``gray-areas-architect.md``).
    3. NO ``design.md`` is required for the legacy feature to be valid.
    """
    feature_dir = _make_legacy_feature_dir(tmp_path, slug="F005-legacy")

    # AC18: no real .etc_sdlc/features/ touched — feature_dir lives under
    # tmp_path. Sanity-check the path prefix to make the test self-attest.
    assert str(feature_dir).startswith(str(tmp_path)), (
        f"forward-only test wrote outside tmp_path: {feature_dir!r}"
    )

    # 1. Legacy value-hypothesis.yaml round-trips through load().
    hypothesis_path = feature_dir / "value-hypothesis.yaml"
    loaded = value_hypothesis_module.load(hypothesis_path)
    assert loaded is not None, (
        f"value_hypothesis.load returned None for legacy F005-style "
        f"hypothesis at {hypothesis_path}; expected a dict (forward-only "
        f"invariant per F006 BR-012)"
    )
    assert loaded["author_role"] == "Engineer", (
        "legacy author_role round-trip failed; loaded value differs from "
        "what was written"
    )
    # The new fields MUST be absent on a legacy file (they were never
    # written; the validator's backward-compat clause must not invent them).
    assert "spec_author_role" not in loaded, (
        "spec_author_role appeared in loaded legacy hypothesis; "
        "validator must not synthesize new fields when reading legacy files"
    )
    assert "architect_author_role" not in loaded, (
        "architect_author_role appeared in loaded legacy hypothesis; "
        "validator must not synthesize new fields when reading legacy files"
    )

    # 2. Legacy single-file gray-areas.md survives.
    gray_areas_path = feature_dir / "gray-areas.md"
    assert gray_areas_path.is_file(), (
        f"legacy gray-areas.md missing at {gray_areas_path}; F006 BR-012 "
        f"forward-only invariant requires legacy single-file naming to "
        f"keep working"
    )
    # The split filenames MUST NOT exist for a legacy feature.
    assert not (feature_dir / "gray-areas-spec.md").exists(), (
        "gray-areas-spec.md exists in a synthetic legacy feature dir; "
        "the helper must not emit the split-naming files"
    )
    assert not (feature_dir / "gray-areas-architect.md").exists(), (
        "gray-areas-architect.md exists in a synthetic legacy feature "
        "dir; the helper must not emit the split-naming files"
    )

    # 3. design.md is NOT required for the legacy feature to be valid.
    assert not (feature_dir / "design.md").exists(), (
        "design.md exists in a synthetic legacy feature dir; legacy "
        "features predate the architect phase and must not require it"
    )


# Module-level reference so static analyzers see ``pytest`` as used. The
# import is required by pytest's collection machinery via the tmp_path
# fixture and the @pytest.fixture decorator above.
_ = pytest
