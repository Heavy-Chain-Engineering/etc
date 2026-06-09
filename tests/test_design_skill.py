"""Contract tests for F011: /design phase wrapping impeccable.

Covers PRD .etc_sdlc/features/F011-design-phase-wrapping-impeccable/spec.md
BR-010 test contract items (a)-(j) via grep-based assertions over the
source artifacts that Wave 1 will create:

- ``skills/design/SKILL.md`` (the /design skill body)
- ``agents/design.md`` (the unified design agent)
- ``agents/ux-designer.md`` + ``agents/ui-designer.md`` (deprecation frontmatter)
- ``hooks/tier-0-design-preflight.sh`` (conditional tier-0 hook)
- ``install.sh`` (non-blocking impeccable preflight INFO)

These tests are written FIRST per TDD red-green-refactor. They WILL FAIL
initially because the source artifacts above do not yet exist or have not
yet been edited; Wave 1 tasks turn them green. The initial fail pattern
is the expected outcome of the red phase.

Test isolation contract (per task AC2):
    Every test uses pytest ``tmp_path`` when constructing synthetic
    artifacts. NO test reads or writes real ``.etc_sdlc/features/``
    directories. Grep tests read the SOURCE artifacts directly (NOT
    the compiled ``dist/`` outputs) so they run pre-compile — Wave 1
    can iterate without re-compiling the whole SDLC manifest on every
    edit. When testing the hook, construct synthetic feature directories
    under ``tmp_path`` and synthetic git repos via
    ``subprocess.run(["git", "init", str(tmp_path)])`` per F005 / F008 /
    F010 precedent.

Precedent:

- ``tests/test_architect_skill.py`` (F006): grep-based skill-body
  assertions; the most direct prior art for /design tests. F006 reads
  ``dist/`` artifacts; F011 reads SOURCE artifacts because Wave 1's
  source-of-truth edits land in source files (compile-sdlc.py turns
  them into dist/ outputs as a downstream concern).
- ``tests/test_build_stacked_prs.py`` (F010): grep-based assertions for
  skill body + preflights.py + synthetic git repo construction. Both
  files were post-migrated by Ftmp-5afddbce task 006 — the install.sh
  fixture became ``PREFLIGHTS_PATH`` + skip-conditional grepping of
  ``etc_installer/preflights.py``.
- ``tests/test_completion_report.py`` (F005): pytest ``tmp_path`` +
  ``subprocess.run`` invocation of helpers with ``cwd=tmp_path``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source artifacts Wave 1 will create / modify. These are SOURCE files
# (NOT dist/ outputs) so the tests can grep them pre-compile.
SKILL_DESIGN = REPO_ROOT / "skills" / "design" / "SKILL.md"
AGENT_DESIGN = REPO_ROOT / "agents" / "design.md"
AGENT_UX = REPO_ROOT / "agents" / "ux-designer.md"
AGENT_UI = REPO_ROOT / "agents" / "ui-designer.md"
HOOK_TIER_0 = REPO_ROOT / "hooks" / "tier-0-design-preflight.sh"

# Verbatim strings from spec.md and design.md the source artifacts must contain.
# Per F011 spec.md BR-009 + AC15, the install.sh INFO line prefix is exact.
INSTALL_INFO_PREFIX = "INFO: impeccable not detected"
# Per F011 spec.md BR-009 / AC15: the F011-specific phrase distinguishes the
# message from F010's gh-stack preflight. F010's full line ends with
# "Single-wave builds work without it" (different feature, different contract).
INSTALL_F011_PHRASE = "/design phase requires impeccable"

# Per F011 spec.md AC3: the five "major" phase headers (Phase 1, 2, 2.5,
# 2.75, 3, 4, 5) appear verbatim in the skill body. The task AC enumerates
# all 7 because the .5 / .75 sub-phases are first-class headers in the
# /design skill body (mirroring /architect's structure per BR-002).
EXPECTED_PHASE_HEADERS = (
    "### Phase 1: Intent Capture",
    "### Phase 2: Research",
    "### Phase 2.5: Gray Area Resolution",
    "### Phase 2.75: Threshold Check and Classification",
    "### Phase 3: Iterative Spec Writing",
    "### Phase 4: Validation",
    "### Phase 5: Output",
)

# Per F011 spec.md AC4: classifier constants identical to /spec and /architect.
EXPECTED_CLASSIFIER_CONSTANTS = (
    "FILL_RATIO_RESEARCH_ASSIST_MAX = 0.20",
    "FILL_RATIO_REJECT_MIN = 0.50",
    "UNFILLABLE_GAP_REJECT_CAP = 3",
)

# Ftmp-5afddbce task 003 ships ``etc_installer/preflights.py`` as the
# Python rewrite of install.sh's gh-stack / impeccable / mergiraf /
# @google/design.md preflight blocks. Per task 006 AC-006-2, the F011
# impeccable-preflight INFO assertions in this file migrate from
# grep-on-install.sh to grep-on-preflights.py once task 003 ships.
# Pre-task-003, the migrated tests SKIP via
# skipif(not PREFLIGHTS_PATH.exists(), reason=PREFLIGHTS_PENDING_REASON).
PREFLIGHTS_PATH = REPO_ROOT / "etc_installer" / "preflights.py"
PREFLIGHTS_PENDING_REASON = (
    "etc_installer/preflights.py not yet shipped (pending Ftmp-5afddbce "
    "task 003 preflights.py)"
)

# Module-level reference so static analyzers see ``pytest`` as accessed via
# the tmp_path fixture indirection. Mirrors test_build_stacked_prs precedent.
_ = pytest


# ── Module-scoped text fixtures ──────────────────────────────────────────


@pytest.fixture(scope="module")
def skill_design_text() -> str:
    """Read ``skills/design/SKILL.md`` once per module.

    Wave 1 task creates this file. Pre-Wave-1 the file does not exist —
    the fixture raises in that case, and every test that depends on the
    fixture surfaces a clear missing-file error rather than a confusing
    AssertionError on substring grep.
    """
    assert SKILL_DESIGN.exists(), (
        f"missing source skill: {SKILL_DESIGN}; F011 Wave 1 task creates "
        f"this file. TDD-red expected pre-Wave-1."
    )
    return SKILL_DESIGN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def agent_design_text() -> str:
    """Read ``agents/design.md`` once per module."""
    assert AGENT_DESIGN.exists(), (
        f"missing source agent: {AGENT_DESIGN}; F011 Wave 1 task creates "
        f"this file. TDD-red expected pre-Wave-1."
    )
    return AGENT_DESIGN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def agent_ux_text() -> str:
    """Read ``agents/ux-designer.md`` once per module.

    Per F011 spec.md BR-008 + AC14, this file persists on disk forward-only
    (F001-F010 references continue to work) but gains a deprecated frontmatter
    field with a redirect note. The file currently exists; Wave 1 edits add
    the deprecation frontmatter.
    """
    assert AGENT_UX.exists(), (
        f"missing source agent: {AGENT_UX}; F011 deprecates this agent but "
        f"keeps the file on disk for forward-only compatibility (BR-008)."
    )
    return AGENT_UX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def agent_ui_text() -> str:
    """Read ``agents/ui-designer.md`` once per module. See agent_ux_text."""
    assert AGENT_UI.exists(), (
        f"missing source agent: {AGENT_UI}; F011 deprecates this agent but "
        f"keeps the file on disk for forward-only compatibility (BR-008)."
    )
    return AGENT_UI.read_text(encoding="utf-8")


# ── Synthetic-git-repo helpers (F005 + F008 + F010 precedent) ────────────


def _git_init_repo(tmp_path: Path) -> Path:
    """Create a fresh git repo rooted at ``tmp_path``.

    Mirrors test_build_stacked_prs._git_init_repo: argv-list invocation,
    deterministic local user config (never modifies host's global config),
    initial-branch=main for reproducibility. Returns ``tmp_path``.
    """
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "f011-test@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "F011 Test"],
        check=True,
        capture_output=True,
    )
    return tmp_path


def _make_synthetic_feature_dir(
    tmp_path: Path,
    slug: str = "F999-synthetic",
    *,
    design_phase_promoted: bool = False,
) -> Path:
    """Create a synthetic feature dir under tmp_path with optional state.yaml.

    AC2 isolation guard: feature dirs ALWAYS live under tmp_path. NO real
    .etc_sdlc/features/* directory is touched. When ``design_phase_promoted``
    is True, a state.yaml is written with the design_phase.tier_0_promoted
    block (the contract the hook reads per BR-006).
    """
    feature_dir = tmp_path / ".etc_sdlc" / "features" / slug
    feature_dir.mkdir(parents=True, exist_ok=True)
    if design_phase_promoted:
        state_yaml = feature_dir / "state.yaml"
        # Minimal state.yaml shape — only the fields the hook reads. The
        # full schema lives in design.md; this is the synthetic projection
        # the hook contract requires.
        state_yaml.write_text(
            (
                "design_phase:\n"
                "  tier_0_promoted: true\n"
            ),
            encoding="utf-8",
        )
    return feature_dir


# ─────────────────────────────────────────────────────────────────────────
# Contract group (a): skills/design/SKILL.md exists with correct frontmatter.
# Per F011 spec.md AC2 + BR-002.
# ─────────────────────────────────────────────────────────────────────────


def test_skill_design_exists_with_required_frontmatter(
    skill_design_text: str,
) -> None:
    """Group (a): ``skills/design/SKILL.md`` exists with frontmatter
    ``name: design``, ``primary_phase: design``, and description mentioning
    the impeccable wrap.

    Per F011 spec.md AC2: "The file exists at skills/design/SKILL.md with
    frontmatter containing name: design, primary_phase: design, and a
    description mentioning 'design phase wrapping impeccable' or equivalent."
    Per BR-002: frontmatter mirrors /architect's shape.
    """
    # Frontmatter delimiters: opening "---\n" at file start, closing "\n---\n".
    assert skill_design_text.startswith("---\n"), (
        "skills/design/SKILL.md does not begin with '---\\n' frontmatter "
        "delimiter; F011 BR-002 mandates a YAML frontmatter block carrying "
        "name + primary_phase + description"
    )
    closing_idx = skill_design_text.find("\n---", 4)
    assert closing_idx != -1, (
        "skills/design/SKILL.md missing closing '---' frontmatter delimiter"
    )
    frontmatter = skill_design_text[4:closing_idx]

    assert "name: design" in frontmatter, (
        f"skills/design/SKILL.md frontmatter missing literal 'name: design'; "
        f"got frontmatter={frontmatter!r}"
    )
    assert "primary_phase: design" in frontmatter, (
        f"skills/design/SKILL.md frontmatter missing literal "
        f"'primary_phase: design'; got frontmatter={frontmatter!r}"
    )
    # Description mentions the impeccable wrap. Accept any case-sensitive
    # mention of both "impeccable" AND "wrap" within the frontmatter — the
    # exact phrasing is wordsmithing-tunable but both load-bearing tokens
    # MUST appear.
    assert "impeccable" in frontmatter.lower(), (
        "skills/design/SKILL.md frontmatter description missing 'impeccable' "
        "reference; F011 AC2 mandates 'design phase wrapping impeccable' "
        "or equivalent in the description"
    )
    assert "wrap" in frontmatter.lower(), (
        "skills/design/SKILL.md frontmatter description missing 'wrap' "
        "reference; F011 AC2 mandates 'design phase wrapping impeccable' "
        "or equivalent in the description"
    )


# ─────────────────────────────────────────────────────────────────────────
# Regression guard (#68): the /design skill must target impeccable's CURRENT
# surface — the `init` command, no fictional version pin, and the canonical
# skills-install channel. impeccable renamed `teach` → `init`, never shipped
# a v3.0.7, and is distributed via `npx impeccable skills install` (or the
# Claude Code plugin marketplace), NOT `npm install -g impeccable`. The stale
# strings broke /design for users on current impeccable (reported from the
# athletica-app project). This test keeps the stale strings from returning.
# ─────────────────────────────────────────────────────────────────────────


def test_skill_design_targets_current_impeccable_surface(
    skill_design_text: str,
) -> None:
    """Regression (#68): skills/design/SKILL.md targets impeccable's current
    `init` command + skills-install channel, with no fictional version pin.

    Asserts, against the skill body:
      - it dispatches ``/impeccable init`` (the current context-setup command),
      - it does NOT mention the renamed-away ``impeccable teach`` command,
      - it does NOT pin the fictional ``3.0.7`` version impeccable never shipped,
      - it does NOT tell users to ``npm install -g impeccable`` (wrong channel),
      - it references the canonical install channel (``impeccable skills
        install`` OR the ``plugin marketplace add pbakaus/impeccable`` path).
    """
    assert "/impeccable init" in skill_design_text, (
        "skills/design/SKILL.md does not dispatch '/impeccable init'; "
        "impeccable renamed its context-setup command from 'teach' to 'init' "
        "(verified against upstream pbakaus/impeccable). The skill must "
        "target the current command (#68)."
    )
    assert "impeccable teach" not in skill_design_text, (
        "skills/design/SKILL.md still references 'impeccable teach'; that "
        "command was renamed to 'init' upstream. The stale name breaks "
        "/design for users on current impeccable (#68)."
    )
    assert "3.0.7" not in skill_design_text, (
        "skills/design/SKILL.md still pins impeccable version '3.0.7'; "
        "impeccable never shipped that version (current CLI is 2.3.2). The "
        "fictional version gate must be removed entirely — replaced by a "
        "presence check, not another semver (#68)."
    )
    assert "npm install -g impeccable" not in skill_design_text, (
        "skills/design/SKILL.md still tells users to 'npm install -g "
        "impeccable'; impeccable is distributed as a skill/CLI via "
        "'npx impeccable skills install' (or the Claude Code plugin "
        "marketplace), NOT a global npm install (#68)."
    )
    canonical_channels = (
        "impeccable skills install",
        "plugin marketplace add pbakaus/impeccable",
    )
    assert any(channel in skill_design_text for channel in canonical_channels), (
        f"skills/design/SKILL.md missing the canonical impeccable install "
        f"channel; expected at least one of {canonical_channels!r} (#68)."
    )


# ─────────────────────────────────────────────────────────────────────────
# Contract group (b): skill body contains all 7 phase headers verbatim.
# Per F011 spec.md AC3 + BR-002.
# ─────────────────────────────────────────────────────────────────────────


def test_skill_design_contains_all_phase_headers_verbatim(
    skill_design_text: str,
) -> None:
    """Group (b): ``skills/design/SKILL.md`` contains all 7 phase headers
    verbatim (Phase 1, 2, 2.5, 2.75, 3, 4, 5).

    Per F011 spec.md AC3 + BR-002: /design mirrors /architect's structure
    with all sub-phase headers as first-class markers. The exact header
    strings are pinned so future edits cannot silently drop or rename
    a phase boundary.
    """
    for header in EXPECTED_PHASE_HEADERS:
        assert header in skill_design_text, (
            f"skills/design/SKILL.md missing verbatim phase header "
            f"{header!r}; F011 AC3 mandates all 7 phase headers verbatim"
        )

    # Order check: phases must appear in monotonically increasing offset
    # order — Phase 1 before Phase 2 before Phase 2.5, etc.
    indices = [skill_design_text.find(h) for h in EXPECTED_PHASE_HEADERS]
    assert indices == sorted(indices), (
        f"skills/design/SKILL.md phase headers out of order; got "
        f"first-occurrence indices "
        f"{dict(zip(EXPECTED_PHASE_HEADERS, indices, strict=True))}"
    )


# ─────────────────────────────────────────────────────────────────────────
# Contract group (c): classifier constants declared verbatim.
# Per F011 spec.md AC4 + BR-002 (Phase 2.75 mirrors /architect's).
# ─────────────────────────────────────────────────────────────────────────


def test_skill_design_declares_classifier_constants(
    skill_design_text: str,
) -> None:
    """Group (c): skills/design/SKILL.md declares the three classifier
    constants with identical values to /spec and /architect.

    Per F011 spec.md AC4: ``FILL_RATIO_RESEARCH_ASSIST_MAX = 0.20``,
    ``FILL_RATIO_REJECT_MIN = 0.50``, ``UNFILLABLE_GAP_REJECT_CAP = 3``.

    Per F006 GA-005 precedent: per-phase divergence is future work; at
    launch the constants are identical across all three Socratic phase
    skills. Test pins the literal values so drift is caught at red-green
    rather than at runtime classification.
    """
    for literal in EXPECTED_CLASSIFIER_CONSTANTS:
        assert literal in skill_design_text, (
            f"skills/design/SKILL.md missing classifier constant declaration "
            f"{literal!r}; F011 AC4 mandates the three constants with "
            f"identical values to /spec and /architect"
        )


# ─────────────────────────────────────────────────────────────────────────
# Contract group (d): Phase 1 documents the wrap-and-invoke contract.
# Per F011 spec.md AC7 + BR-003 + GA-001 (wrap-and-invoke) + GA-architect-5
# (partial wrap).
# ─────────────────────────────────────────────────────────────────────────


def test_skill_design_phase_1_documents_wrap_and_invoke(
    skill_design_text: str,
) -> None:
    """Group (d): Phase 1 documents the wrap-and-invoke contract: detect
    PRODUCT.md + DESIGN.md at repo root, dispatch ``/impeccable init`` via
    the Skill tool (NOT subprocess), Pattern A picker when both present.

    Per F011 spec.md BR-003 + AC7. The "via Skill tool, NOT subprocess"
    distinction is load-bearing (per F006 BR-010 chain semantics — auth
    context preservation requires the Skill tool, not subprocess).

    Slice on the Phase 1 header so the test is scoped to that region;
    these tokens may also appear elsewhere (e.g., Phase 5 reminder, edge
    cases) but the contract lives in Phase 1.
    """
    phase_1_marker = "### Phase 1: Intent Capture"
    phase_2_marker = "### Phase 2: Research"
    p1_idx = skill_design_text.find(phase_1_marker)
    assert p1_idx != -1, (
        f"skills/design/SKILL.md missing Phase 1 marker {phase_1_marker!r}"
    )
    p2_idx = skill_design_text.find(phase_2_marker, p1_idx)
    assert p2_idx != -1, (
        f"skills/design/SKILL.md missing Phase 2 marker {phase_2_marker!r} "
        f"after Phase 1"
    )
    phase_1_region = skill_design_text[p1_idx:p2_idx]

    # Detection of PRODUCT.md + DESIGN.md at repo root.
    assert "PRODUCT.md" in phase_1_region, (
        "Phase 1 region missing 'PRODUCT.md' reference; F011 BR-003 "
        "mandates Phase 1 detect PRODUCT.md at repo root"
    )
    assert "DESIGN.md" in phase_1_region, (
        "Phase 1 region missing 'DESIGN.md' reference; F011 BR-003 "
        "mandates Phase 1 detect DESIGN.md at repo root"
    )

    # Wrap-and-invoke contract: dispatch /impeccable init via Skill tool.
    # impeccable renamed its context-setup command from 'teach' to 'init'
    # (#68; verified against upstream pbakaus/impeccable).
    assert "/impeccable init" in phase_1_region, (
        "Phase 1 region missing '/impeccable init' wrap reference; "
        "F011 BR-003 + GA-001 mandates wrap-and-invoke contract documented "
        "in Phase 1, targeting impeccable's current 'init' command (#68)"
    )
    assert "Skill tool" in phase_1_region, (
        "Phase 1 region missing 'Skill tool' reference; F011 BR-003 "
        "requires dispatch via Skill tool (NOT subprocess) per F006 "
        "BR-010 chain semantics for auth-context preservation"
    )
    # The "NOT subprocess" distinction is load-bearing — appears as a
    # parenthetical, an emphasis, or a contrast clause. Accept any form
    # that mentions subprocess in the region (the contract being documented
    # explicitly says "not subprocess").
    assert "subprocess" in phase_1_region.lower(), (
        "Phase 1 region missing 'subprocess' contrast clause; F011 BR-003 "
        "contract is dispatch via Skill tool, NOT subprocess. The skill "
        "body must document the distinction explicitly."
    )

    # Pattern A picker is documented for the both-present case (per BR-003
    # decision matrix). "Pattern A" is the AskUserQuestion tool per
    # standards/process/interactive-user-input.md.
    assert "Pattern A" in phase_1_region, (
        "Phase 1 region missing 'Pattern A' picker reference; F011 BR-003 "
        "mandates a Pattern A picker (accept / refine / start over) when "
        "PRODUCT.md + DESIGN.md both present"
    )


# ─────────────────────────────────────────────────────────────────────────
# Contract group (e): Phase 5 documents 6 output artifacts + git tag pattern.
# Per F011 spec.md AC8 + AC9 + BR-004.
# ─────────────────────────────────────────────────────────────────────────


def test_skill_design_phase_5_documents_output_artifacts_and_git_tags(
    skill_design_text: str,
) -> None:
    """Group (e): Phase 5 documents writing ``gray-areas-design.md``,
    ``state.yaml.design_phase`` block, ``value-hypothesis.yaml.design_author_role``
    field, ``research/design-codebase.md``, ``design-tokens.json``,
    ``component-specs.md``, plus git tag pattern
    ``etc/feature/F<NNN>/design/{start,done}``.

    Per F011 spec.md AC8 + AC9 + BR-004. Slice on the Phase 5 header so
    the test is scoped to the output region — these path strings may also
    appear in Phase 2.5 (gray-areas-design.md) or Phase 1 (state.yaml
    reference) but the Phase 5 region is the canonical write site.
    """
    phase_5_marker = "### Phase 5: Output"
    p5_idx = skill_design_text.find(phase_5_marker)
    assert p5_idx != -1, (
        f"skills/design/SKILL.md missing Phase 5 marker {phase_5_marker!r}"
    )
    # Upper bound: end-of-file (Phase 5 is the final phase header in the
    # skill body; downstream sections like Definition of Done are siblings
    # at ## level, not ### Phase headers).
    phase_5_region = skill_design_text[p5_idx:]

    expected_artifacts = [
        "gray-areas-design.md",
        "design_phase",          # state.yaml.design_phase block
        "design_author_role",    # value-hypothesis.yaml field
        "research/design-codebase.md",
        "design-tokens.json",
        "component-specs.md",
    ]
    for artifact in expected_artifacts:
        assert artifact in phase_5_region, (
            f"Phase 5 region missing reference to {artifact!r}; F011 AC8 + "
            f"BR-004 mandate all 6 output artifacts appear in Phase 5"
        )

    # Git tag pattern. The skill body may render either the abstract
    # template ``etc/feature/F<NNN>/design/start`` (with placeholder) or
    # discuss the start/done suffixes. Both forms are acceptable; the
    # test asserts the load-bearing tokens.
    assert "etc/feature/F" in phase_5_region, (
        "Phase 5 region missing git tag prefix 'etc/feature/F'; F011 AC9 "
        "mandates the tag pattern 'etc/feature/F<NNN>/design/{start,done}'"
    )
    assert "design/start" in phase_5_region, (
        "Phase 5 region missing 'design/start' tag suffix; F011 AC9 "
        "mandates writing the start tag at Phase 5 entry"
    )
    assert "design/done" in phase_5_region, (
        "Phase 5 region missing 'design/done' tag suffix; F011 AC9 "
        "mandates writing the done tag at Phase 5 successful close"
    )


# ─────────────────────────────────────────────────────────────────────────
# Contract group (f): file-watch contract documented.
# Per F011 spec.md AC10 + BR-005 + GA-006 + GA-architect-3 (minimal schema).
# ─────────────────────────────────────────────────────────────────────────


def test_skill_design_documents_file_watch_contract(
    skill_design_text: str,
) -> None:
    """Group (f): skill body documents the file-watch contract — known
    JSON path, ``--sync-from <path>`` flag, minimal schema reference (per
    ADR-F011-004), pull-triggered NOT continuous watcher (per ADR-F011-002).

    Per F011 spec.md AC10 + BR-005. The browser-extension → /design handoff
    is file-watch (chosen over MCP server, polling REST, manual sync); the
    contract must be documented in the skill body so future maintainers
    don't reach for a daemon or watcher.
    """
    # File-watch contract phrase. Accept "file-watch" or "file watch" — both
    # spellings appear in spec.md and design.md.
    file_watch_tokens = ("file-watch", "file watch")
    assert any(token in skill_design_text for token in file_watch_tokens), (
        f"skills/design/SKILL.md missing file-watch contract documentation; "
        f"expected one of {file_watch_tokens!r} per F011 AC10 / BR-005 / GA-006"
    )

    # --sync-from flag for operator-selectable path.
    assert "--sync-from" in skill_design_text, (
        "skills/design/SKILL.md missing '--sync-from' flag reference; "
        "F011 BR-005 mandates operator-selectable path via --sync-from"
    )

    # Default paths from BR-005 — at least ONE must appear (operator picks one).
    default_paths = (
        "~/.impeccable/last-session.json",
        "design-iteration.json",
    )
    assert any(path in skill_design_text for path in default_paths), (
        f"skills/design/SKILL.md missing default file-watch path; expected "
        f"at least one of {default_paths!r} per F011 BR-005"
    )

    # Pull-triggered, NOT continuous watcher. Per ADR-F011-002 the contract
    # is pull-based; design.md "Designer iteration loop" calls this out
    # verbatim. Accept either spelling of the contrast.
    pull_tokens = ("pull-triggered", "pull triggered", "pull-based", "pull based")
    assert any(token in skill_design_text for token in pull_tokens), (
        f"skills/design/SKILL.md missing pull-triggered contract phrase; "
        f"expected one of {pull_tokens!r} per ADR-F011-002 (NOT continuous "
        f"watcher)"
    )

    # MCP server / polling REST / manual sync are explicitly NOT supported.
    # Accept any token that signals the explicit exclusion (per GA-006).
    not_supported_tokens = ("MCP server", "polling REST", "manual sync")
    assert any(token in skill_design_text for token in not_supported_tokens), (
        f"skills/design/SKILL.md missing explicit non-support of alternative "
        f"contracts; expected one of {not_supported_tokens!r} per F011 "
        f"AC10 / GA-006"
    )


# ─────────────────────────────────────────────────────────────────────────
# Contract group (g): conditional tier-0 promotion documented.
# Per F011 spec.md AC11 + BR-006 + GA-005 + GA-architect-4.
# ─────────────────────────────────────────────────────────────────────────


def test_skill_design_documents_conditional_tier_0_promotion(
    skill_design_text: str,
) -> None:
    """Group (g): skill body documents the conditional tier-0 promotion
    contract: ``state.yaml.design_phase.tier_0_promoted: bool``, cites
    ``hooks/tier-0-design-preflight.sh``.

    Per F011 spec.md AC11 + BR-006. Always-tier-0 is NOT supported (GA-005);
    the hook fires only when ``tier_0_promoted == true`` AND PRODUCT.md /
    DESIGN.md are missing. The hook file lives at
    ``hooks/tier-0-design-preflight.sh`` per GA-architect-4 (new hook,
    NOT extension of the absent existing tier-0 hook).
    """
    # The tier_0_promoted field name is load-bearing — the hook reads it.
    assert "tier_0_promoted" in skill_design_text, (
        "skills/design/SKILL.md missing 'tier_0_promoted' field reference; "
        "F011 AC11 + BR-006 mandate documenting the state.yaml field that "
        "the conditional tier-0 hook reads"
    )

    # The hook citation by path (F002 standards-doc citation pattern).
    assert "tier-0-design-preflight.sh" in skill_design_text, (
        "skills/design/SKILL.md missing 'tier-0-design-preflight.sh' "
        "reference; F011 GA-architect-4 + BR-006 mandate the skill body "
        "cite the new hook file by path"
    )

    # Conditional contract: only fires for user-facing surface features.
    # "user-facing" appears in spec.md AC11 + BR-006 + Edge Case 9.
    assert "user-facing" in skill_design_text, (
        "skills/design/SKILL.md missing 'user-facing' surface qualifier; "
        "F011 AC11 + BR-006 mandate the conditional contract is scoped "
        "to features with a user-facing surface (NOT backend-only)"
    )


# ─────────────────────────────────────────────────────────────────────────
# Contract group (h): agents/design.md exists with required frontmatter.
# Per F011 spec.md AC13 + BR-008.
# ─────────────────────────────────────────────────────────────────────────


def test_agent_design_exists_with_required_frontmatter(
    agent_design_text: str,
) -> None:
    """Group (h): ``agents/design.md`` exists with frontmatter
    ``primary_phase: design``, ``model: opus``, tools list including
    Read, Grep, Glob, Write, Edit.

    Per F011 spec.md AC13 + BR-008. The unified agent replaces the two
    homeless agents (ux-designer + ui-designer); F011 specs the new
    agent's frontmatter contract.
    """
    assert agent_design_text.startswith("---\n"), (
        "agents/design.md does not begin with '---\\n' frontmatter "
        "delimiter; F011 BR-008 mandates a YAML frontmatter block carrying "
        "primary_phase + model + tools"
    )
    closing_idx = agent_design_text.find("\n---", 4)
    assert closing_idx != -1, (
        "agents/design.md missing closing '---' frontmatter delimiter"
    )
    frontmatter = agent_design_text[4:closing_idx]

    assert "primary_phase: design" in frontmatter, (
        f"agents/design.md frontmatter missing literal 'primary_phase: "
        f"design'; got frontmatter={frontmatter!r}"
    )
    assert "model: opus" in frontmatter, (
        f"agents/design.md frontmatter missing literal 'model: opus'; F011 "
        f"BR-008 mandates the opus model default; got frontmatter={frontmatter!r}"
    )
    # Tools list per AC13: Read, Grep, Glob, Write, Edit. The list may be
    # rendered as comma-separated (``tools: Read, Grep, Glob, Write, Edit``)
    # or YAML sequence. Each tool name must appear in the frontmatter.
    required_tools = ["Read", "Grep", "Glob", "Write", "Edit"]
    for tool in required_tools:
        assert tool in frontmatter, (
            f"agents/design.md frontmatter missing tool {tool!r}; F011 "
            f"AC13 mandates tools list includes Read, Grep, Glob, Write, "
            f"Edit; got frontmatter={frontmatter!r}"
        )


# ─────────────────────────────────────────────────────────────────────────
# Contract group (i): install.sh F011 preflight INFO message verbatim.
# Per F011 spec.md AC15 + BR-009.
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not PREFLIGHTS_PATH.exists(),
    reason=PREFLIGHTS_PENDING_REASON,
)
def test_preflights_py_documents_impeccable_preflight_info() -> None:
    """Group (i) (Ftmp-5afddbce task 006 migration): ``etc_installer/preflights.py``
    declares the F011 impeccable INFO message verbatim.

    Migrated from grep-on-install.sh to grep-on-preflights.py per task
    006 AC-006-2. Per design.md ``preflights.py`` exposes verbatim
    ``F011_INFO_LINE`` (BR-005, AC-005) plus the F010/F016/F018 siblings.
    The full canonical line is preserved verbatim from install.sh:

        INFO: impeccable not detected. /design phase requires impeccable
        (etc F011+). Install via: npx impeccable skills install
        (recommended) or /plugin marketplace add pbakaus/impeccable
        (Claude Code). Features without a /design phase work without it.

    Note: F010's INFO line ends with "Single-wave builds work without it"
    — that's a DIFFERENT feature's contract. F011's line ends with
    "Features without a /design phase work without it." (different
    closing clause). Both INFO lines coexist in preflights.py after task
    003 ships; this test asserts F011's distinguishing phrase.
    """
    preflights_text = PREFLIGHTS_PATH.read_text(encoding="utf-8")

    assert "F011_INFO_LINE" in preflights_text, (
        "etc_installer/preflights.py missing 'F011_INFO_LINE' module-level "
        "constant; design.md mandates the verbatim INFO_LINE constants "
        "(BR-005 / AC-005)"
    )
    assert INSTALL_INFO_PREFIX in preflights_text, (
        f"etc_installer/preflights.py missing verbatim INFO message prefix "
        f"{INSTALL_INFO_PREFIX!r}; expected per F011 spec.md AC15 / BR-009"
    )
    assert INSTALL_F011_PHRASE in preflights_text, (
        f"etc_installer/preflights.py missing F011-specific phrase "
        f"{INSTALL_F011_PHRASE!r}; this phrase distinguishes the F011 INFO "
        f"line from F010's gh-stack INFO line per F011 AC15 / BR-009"
    )
    # Install instruction verbatim per BR-009. Impeccable's distribution
    # moved off `npm install -g` to the skills/plugin channel (#68); the
    # mandated install text follows it to `npx impeccable skills install`.
    assert "npx impeccable skills install" in preflights_text, (
        "etc_installer/preflights.py missing literal install instruction "
        "'npx impeccable skills install'; F011 BR-009 + AC15 mandate the "
        "verbatim text (updated for impeccable's current install channel, #68)"
    )


@pytest.mark.skipif(
    not PREFLIGHTS_PATH.exists(),
    reason=PREFLIGHTS_PENDING_REASON,
)
def test_preflights_py_impeccable_after_gh_stack_preflight() -> None:
    """Group (i) ordering (Ftmp-5afddbce task 006 migration): F011's
    impeccable INFO constant declaration lands AFTER F010's gh-stack
    INFO constant declaration in ``etc_installer/preflights.py``.

    Migrated from grep-on-install.sh to grep-on-preflights.py per task
    006 AC-006-2. Per F011 spec.md BR-009: chain order is client-detect
    → gh-stack → impeccable. Post-rewrite, the preflight chain still
    runs in the same order — `preflights.py` exposes the constants and
    the orchestrator (`install_steps.py`) calls `offer_install` for each
    in chain order. Asserting the source-declaration order of the
    constants encodes the chain order in the rewrite's source-of-truth.

    F010's INFO line is detectable by its distinguishing closing clause
    "Single-wave builds work without it" (different from F011's). Both
    INFO lines coexist post-F011-ship; the F010 line's offset must be
    LESS than the F011 line's offset.
    """
    preflights_text = PREFLIGHTS_PATH.read_text(encoding="utf-8")

    f010_phrase = "Single-wave builds work without it"
    f010_idx = preflights_text.find(f010_phrase)
    f011_idx = preflights_text.find(INSTALL_F011_PHRASE)

    assert f010_idx != -1, (
        f"etc_installer/preflights.py missing F010 gh-stack INFO closing "
        f"clause {f010_phrase!r}; F010 baseline must remain in preflights.py"
    )
    assert f011_idx != -1, (
        f"etc_installer/preflights.py missing F011 impeccable INFO phrase "
        f"{INSTALL_F011_PHRASE!r}; F011 BR-009 mandates this line"
    )
    assert f010_idx < f011_idx, (
        f"etc_installer/preflights.py preflight chain order violated: F010 "
        f"gh-stack INFO (offset {f010_idx}) must appear BEFORE F011 "
        f"impeccable INFO (offset {f011_idx}). F011 BR-009 mandates chain "
        f"order client-detect → gh-stack → impeccable."
    )


@pytest.mark.skipif(
    not PREFLIGHTS_PATH.exists(),
    reason=PREFLIGHTS_PENDING_REASON,
)
def test_preflights_py_impeccable_preflight_is_non_blocking() -> None:
    """Group (i) non-blocking (Ftmp-5afddbce task 006 migration): F011's
    impeccable preflight implementation in ``etc_installer/preflights.py``
    is INFO-level — the offer_install helper does not abort installation.

    Migrated from grep-on-install.sh to grep-on-preflights.py per task
    006 AC-006-2. Per F011 spec.md AC15 / BR-009 ("The check is INFO-level
    — install.sh continues regardless. Matches F010's gh-stack preflight
    pattern."). Post-rewrite, the Python implementation must NOT call
    sys.exit (the rewrite's equivalent of bash's `exit 1`) anywhere near
    the F011 INFO message.
    """
    preflights_text = PREFLIGHTS_PATH.read_text(encoding="utf-8")

    info_idx = preflights_text.find(INSTALL_F011_PHRASE)
    assert info_idx != -1, (
        f"etc_installer/preflights.py missing F011 INFO phrase "
        f"{INSTALL_F011_PHRASE!r}; cannot verify non-blocking behavior"
    )
    # Scope is tight: catch a `sys.exit` (or `raise SystemExit`) in the
    # same module region immediately surrounding the INFO message. The
    # rewrite's `preflights.py` is informational-only — abort behavior
    # lives in `install_steps.py` for hard-fail conditions (missing dist/,
    # etc.) which are unrelated.
    region_start = max(0, info_idx - 400)
    region_end = min(len(preflights_text), info_idx + 400)
    region = preflights_text[region_start:region_end]

    assert "sys.exit" not in region, (
        f"etc_installer/preflights.py region contains 'sys.exit' near the "
        f"F011 impeccable preflight message; preflight must be non-blocking "
        f"per AC15. region={region!r}"
    )
    assert "raise SystemExit" not in region, (
        f"etc_installer/preflights.py region contains 'raise SystemExit' "
        f"near the F011 impeccable preflight message; preflight must be "
        f"non-blocking per AC15. region={region!r}"
    )


# ─────────────────────────────────────────────────────────────────────────
# Contract group (j): agents/ux-designer.md + agents/ui-designer.md
# deprecation. Per F011 spec.md AC14 + BR-008 + GA-003.
# ─────────────────────────────────────────────────────────────────────────


def test_agent_ux_designer_marked_deprecated_with_redirect(
    agent_ux_text: str,
) -> None:
    """Group (j): ``agents/ux-designer.md`` has ``deprecated: true`` in
    frontmatter and a redirect note pointing to ``agents/design.md``.

    Per F011 spec.md AC14 + BR-008 + GA-003. The file persists on disk
    forward-only (F001-F010 references continue to resolve); the
    deprecation metadata signals to future authors that they should
    target ``agents/design.md`` instead.
    """
    assert agent_ux_text.startswith("---\n"), (
        "agents/ux-designer.md does not begin with '---\\n' frontmatter "
        "delimiter; F011 BR-008 mandates the deprecation frontmatter field"
    )
    closing_idx = agent_ux_text.find("\n---", 4)
    assert closing_idx != -1, (
        "agents/ux-designer.md missing closing '---' frontmatter delimiter"
    )
    frontmatter = agent_ux_text[4:closing_idx]

    assert "deprecated: true" in frontmatter, (
        f"agents/ux-designer.md frontmatter missing literal 'deprecated: "
        f"true'; F011 AC14 mandates the deprecation field; got "
        f"frontmatter={frontmatter!r}"
    )
    # Redirect note points to agents/design.md. The note may be in the
    # frontmatter (as a `replaced_by:` / `redirect_to:` field) OR in the
    # body (as a deprecation banner). Accept either location.
    assert "agents/design.md" in agent_ux_text, (
        "agents/ux-designer.md missing redirect reference to "
        "'agents/design.md'; F011 AC14 + BR-008 mandate a redirect note "
        "pointing operators to the unified agent"
    )


def test_agent_ui_designer_marked_deprecated_with_redirect(
    agent_ui_text: str,
) -> None:
    """Group (j): ``agents/ui-designer.md`` has ``deprecated: true`` in
    frontmatter and a redirect note pointing to ``agents/design.md``.

    Symmetric to ``test_agent_ux_designer_marked_deprecated_with_redirect``
    — per F011 BR-008 both agents are deprecated together; both files
    persist on disk forward-only with the same deprecation contract.
    """
    assert agent_ui_text.startswith("---\n"), (
        "agents/ui-designer.md does not begin with '---\\n' frontmatter "
        "delimiter; F011 BR-008 mandates the deprecation frontmatter field"
    )
    closing_idx = agent_ui_text.find("\n---", 4)
    assert closing_idx != -1, (
        "agents/ui-designer.md missing closing '---' frontmatter delimiter"
    )
    frontmatter = agent_ui_text[4:closing_idx]

    assert "deprecated: true" in frontmatter, (
        f"agents/ui-designer.md frontmatter missing literal 'deprecated: "
        f"true'; F011 AC14 mandates the deprecation field; got "
        f"frontmatter={frontmatter!r}"
    )
    assert "agents/design.md" in agent_ui_text, (
        "agents/ui-designer.md missing redirect reference to "
        "'agents/design.md'; F011 AC14 + BR-008 mandate a redirect note "
        "pointing operators to the unified agent"
    )


# ─────────────────────────────────────────────────────────────────────────
# Test isolation contract (AC2): synthetic feature dirs + synthetic git
# repos under tmp_path; no real .etc_sdlc/features/* or real project repo
# touched. F005 + F008 + F010 precedent.
# ─────────────────────────────────────────────────────────────────────────


def test_synthetic_feature_dir_isolates_from_real_features(
    tmp_path: Path,
) -> None:
    """AC2: synthetic feature directories live under ``tmp_path``, never
    under the real ``.etc_sdlc/features/`` tree.

    Self-check: confirm the helper constructs a feature dir whose path
    is rooted under ``tmp_path``. If this assertion ever fails, the
    test harness has corrupted real project state.
    """
    feature_dir = _make_synthetic_feature_dir(
        tmp_path, slug="F999-synthetic", design_phase_promoted=True
    )
    assert feature_dir.is_dir(), (
        f"synthetic feature dir not created at {feature_dir!r}"
    )
    assert str(feature_dir).startswith(str(tmp_path)), (
        f"synthetic feature dir {feature_dir!r} is NOT under tmp_path "
        f"{tmp_path!r}; F011 tests must NEVER touch real "
        f".etc_sdlc/features/*"
    )
    # Critically: NEVER under the real project's .etc_sdlc/features tree.
    real_features = REPO_ROOT / ".etc_sdlc" / "features"
    assert not str(feature_dir).startswith(str(real_features)), (
        f"synthetic feature dir {feature_dir!r} is inside the real project's "
        f".etc_sdlc/features/ tree {real_features!r}; F011 tests must "
        f"NEVER touch real project state"
    )
    # state.yaml with the design_phase block was written.
    state_yaml = feature_dir / "state.yaml"
    assert state_yaml.is_file(), (
        f"synthetic state.yaml not created at {state_yaml!r}"
    )
    state_text = state_yaml.read_text(encoding="utf-8")
    assert "tier_0_promoted: true" in state_text, (
        f"synthetic state.yaml missing tier_0_promoted contract; "
        f"got {state_text!r}"
    )


def test_synthetic_git_repo_isolates_from_project_repo(tmp_path: Path) -> None:
    """AC2: synthetic git repos constructed via ``subprocess.run(["git",
    "init", str(tmp_path), ...])`` per F005 + F008 + F010 precedent.

    Self-check: confirm the harness's git-init helper produces a repo
    rooted under ``tmp_path`` and that the repo's ``.git`` directory
    lives inside ``tmp_path`` (NOT inside the project's real repo).
    Mirrors test_build_stacked_prs.test_synthetic_git_repo_isolates_from_project_repo.
    """
    repo = _git_init_repo(tmp_path)
    assert repo == tmp_path, (
        f"helper returned a path {repo!r} that is not the requested tmp_path "
        f"{tmp_path!r}"
    )
    git_dir = tmp_path / ".git"
    assert git_dir.is_dir(), (
        f"synthetic repo's .git directory not found at {git_dir!r}"
    )
    # Critically: synthetic .git/ lives under tmp_path, NOT under the real repo.
    assert str(git_dir).startswith(str(tmp_path)), (
        f"synthetic .git directory at {git_dir!r} is NOT under tmp_path "
        f"{tmp_path!r}; F011 tests must NEVER touch the real project repo"
    )
    assert not str(git_dir).startswith(str(REPO_ROOT) + "/"), (
        f"synthetic .git directory at {git_dir!r} is inside the project "
        f"repo {REPO_ROOT!r}; F011 tests must NEVER touch the real repo"
    )


# ─────────────────────────────────────────────────────────────────────────
# Hook contract test: hooks/tier-0-design-preflight.sh exists and is
# executable. Per F011 spec.md BR-006 + GA-architect-4. The detailed
# behavior tests (block vs proceed matrix) are deferred to Wave 1's hook
# implementation task; this test asserts presence + executability so the
# downstream hook tests have a baseline to build on.
# ─────────────────────────────────────────────────────────────────────────


def test_hook_tier_0_design_preflight_exists_and_is_executable() -> None:
    """Hook contract: ``hooks/tier-0-design-preflight.sh`` exists and is
    a regular file (executable bit set by Wave 1's hook implementation
    task).

    Per F011 spec.md BR-006 + GA-architect-4. The hook is a NEW file
    (NOT extension of the absent existing tier-0 hook). The detailed
    block-vs-proceed decision matrix tests live in Wave 1's hook
    implementation task; this baseline test asserts the file exists so
    those tests have something to invoke.
    """
    assert HOOK_TIER_0.is_file(), (
        f"missing hook: {HOOK_TIER_0}; F011 GA-architect-4 + BR-006 mandate "
        f"a new hook file at this path. Wave 1 creates it. TDD-red expected "
        f"pre-Wave-1."
    )
    # Sanity: executable bit set. POSIX file modes — check user-execute bit.
    mode = HOOK_TIER_0.stat().st_mode
    # 0o100 == owner-execute bit (S_IXUSR).
    assert mode & 0o100, (
        f"hook {HOOK_TIER_0!r} is not user-executable; mode={oct(mode)}. "
        f"Wave 1's hook implementation must chmod +x the file so the hook "
        f"runtime can invoke it."
    )


# ─────────────────────────────────────────────────────────────────────────
# Sanity: regex documented for tier_0_promoted field (state.yaml contract).
# This verifies the test harness can grep the documented contract pattern
# pre-Wave-1, surfacing the missing file via the skill_design_text fixture
# rather than a confusing regex error.
# ─────────────────────────────────────────────────────────────────────────


def test_skill_design_documents_state_yaml_design_phase_schema(
    skill_design_text: str,
) -> None:
    """Schema contract: skill body documents the state.yaml.design_phase
    block schema fields (classification, design_author_role,
    impeccable_version_pinned, tier_0_promoted, completed_at,
    phase_2_75_metrics).

    Per F011 spec.md BR-004 + design.md Data Model section. The schema
    fields appear in Phase 5 (the write site) and/or the skill body's
    state.yaml shape documentation. Test greps the union — at least one
    occurrence of each load-bearing field name must appear anywhere in
    the skill body.
    """
    expected_fields = [
        "classification",
        "design_author_role",
        "impeccable_version_pinned",
        "tier_0_promoted",
        "completed_at",
        "phase_2_75_metrics",
    ]
    for field in expected_fields:
        assert field in skill_design_text, (
            f"skills/design/SKILL.md missing state.yaml.design_phase schema "
            f"field {field!r}; F011 BR-004 + design.md Data Model mandate "
            f"the field appears in the skill body"
        )

    # The git tag pattern is also asserted with a regex sanity-check.
    # Per F011 AC9 the pattern is ``etc/feature/F<NNN>/design/{start,done}``.
    # Compile a sanity-regex matching the pattern shape — any rendering
    # of an actual F<NNN> value or the literal placeholder counts.
    tag_pattern = re.compile(r"etc/feature/F[<\w]+>?/design/(start|done)")
    assert tag_pattern.search(skill_design_text), (
        f"skills/design/SKILL.md missing git tag pattern matching "
        f"{tag_pattern.pattern!r}; F011 AC9 mandates the start/done tags "
        f"under etc/feature/F<NNN>/design/"
    )
