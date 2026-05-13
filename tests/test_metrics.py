"""Contract tests for skills/metrics/SKILL.md — three-layer metrics report.

Covers PRD .etc_sdlc/features/metrics-and-release-notes/spec.md acceptance
criteria AC-012 (three layers, three sources, three labeled sections),
AC-014 (auto-transition pending → unmeasured before counting), AC-015
(role breakdown with counts and percentages), AC-016 (grandfather skip
in outcome layer), and AC-017 (locality — no ~/.claude/, no network,
no reads outside the project working tree).

Style: structural greps against `skills/metrics/SKILL.md` content, in
the precedent of tests/test_spec_three_state.py and
tests/test_build_release.py. No agent loop is executed; the SKILL body
is the artifact under test.

Some semantics (e.g. AC-014's runtime "before counting" timing) cannot
be expressed as a pure content grep — for those points the tests assert
that the SKILL body documents the required ordering, and integration
tests in a future PRD will exercise the runtime behavior end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_SRC = REPO_ROOT / "skills" / "metrics" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    assert SKILL_SRC.exists(), f"missing {SKILL_SRC}"
    return SKILL_SRC.read_text(encoding="utf-8")


# ── Section-slicing helpers ────────────────────────────────────────────────


def _section(text: str, header: str, next_headers: tuple[str, ...]) -> str:
    """Return the slice of SKILL.md between `header` and the next of
    `next_headers` (or end-of-file if none follow). Used to scope greps
    to a single workflow step or section."""
    start = text.index(header)
    candidates = [text.find(h, start + len(header)) for h in next_headers]
    candidates = [c for c in candidates if c != -1]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


def _step1_block(text: str) -> str:
    return _section(
        text,
        "### Step 1:",
        ("### Step 2:", "### Step 3:", "### Step 4:", "### Step 5:"),
    )


def _step2_block(text: str) -> str:
    return _section(
        text,
        "### Step 2:",
        ("### Step 3:", "### Step 4:", "### Step 5:"),
    )


def _step3_block(text: str) -> str:
    return _section(
        text,
        "### Step 3:",
        ("### Step 4:", "### Step 5:"),
    )


def _step4_block(text: str) -> str:
    return _section(text, "### Step 4:", ("### Step 5:",))


def _constraints_block(text: str) -> str:
    return _section(text, "## Constraints", ("## Definition of Done",))


# ── AC-012: three layers, three sources, three labeled sections ─────────────


class TestThreeLayerAggregation:
    """AC-012 / BR-010: exactly three sources, three labeled sections,
    no cross-derivation between layers."""

    def test_skill_names_three_labeled_sections_in_order(
        self, skill_text: str
    ) -> None:
        """AC-012: report must emit exactly three labeled sections —
        Process, Outcome, Cost — in that order."""
        process_idx = skill_text.find("## Process")
        outcome_idx = skill_text.find("## Outcome")
        cost_idx = skill_text.find("## Cost")
        assert process_idx != -1, "SKILL.md must reference a `## Process` section"
        assert outcome_idx != -1, "SKILL.md must reference an `## Outcome` section"
        assert cost_idx != -1, "SKILL.md must reference a `## Cost` section"
        assert process_idx < outcome_idx < cost_idx, (
            "SKILL.md must order the three sections Process → Outcome → Cost "
            "(matches AC-012 / Step 5 layout)"
        )

    def test_skill_names_process_source_git_tags(self, skill_text: str) -> None:
        """AC-012: process layer derives from git tags via the git_tags.py CLI.

        The skill must invoke the CLI (works from any project) instead of
        the import-style form (only resolves inside this checkout).
        """
        assert "git_tags" in skill_text, (
            "SKILL.md must reference scripts/git_tags as the process-layer reader"
        )
        assert (
            "python3 ~/.claude/scripts/git_tags.py list-etc-tags" in skill_text
        ), (
            "SKILL.md must invoke 'python3 ~/.claude/scripts/git_tags.py "
            "list-etc-tags' for process metrics"
        )

    def test_skill_no_longer_uses_python_import_for_git_tags(
        self, skill_text: str
    ) -> None:
        """The legacy `from scripts.git_tags import` form must be gone."""
        assert "from scripts.git_tags import" not in skill_text, (
            "SKILL.md must NOT use 'from scripts.git_tags import' — the "
            "helpers are installed under ~/.claude/scripts/, not the user's "
            "project. Use the CLI form."
        )

    def test_skill_names_outcome_source_value_hypothesis(
        self, skill_text: str
    ) -> None:
        """AC-012: outcome layer derives from value-hypothesis.yaml files
        loaded via the value_hypothesis.py CLI."""
        assert "value_hypothesis" in skill_text, (
            "SKILL.md must reference scripts/value_hypothesis as the "
            "outcome-layer reader"
        )
        assert "value-hypothesis.yaml" in skill_text, (
            "SKILL.md must reference value-hypothesis.yaml as the outcome source"
        )
        assert (
            "python3 ~/.claude/scripts/value_hypothesis.py load" in skill_text
        ), (
            "SKILL.md must invoke 'python3 ~/.claude/scripts/value_hypothesis.py "
            "load' to read hypotheses (helpers live at ~/.claude/scripts/, "
            "not in the user's project)"
        )

    def test_skill_no_longer_uses_python_import_for_value_hypothesis(
        self, skill_text: str
    ) -> None:
        """The legacy `from scripts.value_hypothesis import` form must be gone."""
        assert "from scripts.value_hypothesis import" not in skill_text, (
            "SKILL.md must NOT use 'from scripts.value_hypothesis import' — "
            "use the CLI form so it resolves from any project working dir"
        )

    def test_skill_names_cost_source_telemetry_db(self, skill_text: str) -> None:
        """AC-012: cost layer derives from .etc_sdlc/telemetry.db via the
        telemetry.py aggregate CLI subcommand."""
        assert "telemetry" in skill_text, (
            "SKILL.md must reference scripts/telemetry as the cost-layer reader"
        )
        assert ".etc_sdlc/telemetry.db" in skill_text, (
            "SKILL.md must reference .etc_sdlc/telemetry.db as the cost-source path"
        )
        assert (
            "python3 ~/.claude/scripts/telemetry.py aggregate" in skill_text
        ), (
            "SKILL.md must invoke 'python3 ~/.claude/scripts/telemetry.py "
            "aggregate' to retrieve cost-layer rollups"
        )
        # SQL-driven aggregation is required (vs. cross-derivation from outcome).
        assert "aggregat" in skill_text.lower() or "GROUP BY" in skill_text, (
            "SKILL.md must describe aggregating telemetry events for the cost "
            "layer (e.g. group-by event_type)"
        )

    def test_skill_no_longer_uses_python_import_for_telemetry(
        self, skill_text: str
    ) -> None:
        """The legacy `from scripts.telemetry import` form must be gone."""
        assert "from scripts.telemetry import" not in skill_text, (
            "SKILL.md must NOT use 'from scripts.telemetry import' — use "
            "the CLI form instead"
        )

    def test_skill_forbids_cross_layer_derivation(self, skill_text: str) -> None:
        """BR-010: the three layers MUST NOT cross-derive — outcome counts
        are never inferred from cost data, and vice versa."""
        lowered = skill_text.lower()
        # The text must explicitly forbid cross-derivation. Either by
        # citing BR-010 directly or by stating the no-cross-derivation rule.
        has_br010_citation = "br-010" in lowered
        has_negative_statement = (
            "no cross-derivation" in lowered
            or "do not cross-derive" in lowered
            or "never cross-derive" in lowered
            or "cross-derivation" in lowered
        )
        assert has_br010_citation or has_negative_statement, (
            "SKILL.md must explicitly state that the three layers do not "
            "cross-derive (BR-010)"
        )


# ── AC-014: pending → unmeasured auto-transition before counting ────────────


class TestUnmeasuredAutoTransition:
    """AC-014 / BR-011: hypotheses with status `pending` past `window_days`
    since the release tag are auto-set to `unmeasured` BEFORE the outcome
    counts are computed."""

    def test_step1_describes_pending_to_unmeasured_transition(
        self, skill_text: str
    ) -> None:
        block = _step1_block(skill_text)
        assert "pending" in block.lower(), (
            "Step 1 must reference the pending status as the source state"
        )
        assert "unmeasured" in block.lower(), (
            "Step 1 must reference unmeasured as the auto-transition target"
        )

    def test_step1_describes_window_days_check_against_release_tag(
        self, skill_text: str
    ) -> None:
        """The auto-transition is keyed on (now - release_tag_date) > window_days."""
        block = _step1_block(skill_text)
        assert "window_days" in block, (
            "Step 1 must reference predicted.window_days as the window "
            "threshold (AC-014)"
        )
        # The release tag is the window anchor.
        assert "release" in block.lower(), (
            "Step 1 must reference the release tag as the window anchor"
        )

    def test_skill_orders_auto_transition_before_outcome_counts(
        self, skill_text: str
    ) -> None:
        """AC-014: auto-transition MUST happen BEFORE the outcome counts.
        The SKILL must place Step 1 (auto-transition) ahead of Step 3
        (outcome layer rendering) and state the ordering explicitly."""
        step1_idx = skill_text.index("### Step 1:")
        step3_idx = skill_text.index("### Step 3:")
        assert step1_idx < step3_idx, (
            "Step 1 (auto-transition) must precede Step 3 (outcome rendering)"
        )
        # Step 1 heading or body must mention the "before" semantics.
        block = _step1_block(skill_text).lower()
        assert "before" in block, (
            "Step 1 must explicitly state the transition runs BEFORE the "
            "report is computed (AC-014)"
        )

    def test_skill_calls_transition_subcommand_via_cli(
        self, skill_text: str
    ) -> None:
        """The auto-transition uses the value_hypothesis.py transition CLI
        subcommand so the BR-011 state machine is enforced. The CLI handles
        load + transition_status + atomic dump in a single invocation; the
        skill body should describe that CLI call so a runtime conductor can
        execute it."""
        block = _step1_block(skill_text)
        assert (
            "python3 ~/.claude/scripts/value_hypothesis.py transition" in block
        ), (
            "Step 1 must invoke 'python3 ~/.claude/scripts/value_hypothesis.py "
            "transition <path> unmeasured' so the BR-011 state machine "
            "governs the pending → unmeasured edge and the file is rewritten "
            "atomically by the CLI"
        )


# ── AC-015: role breakdown rendering ───────────────────────────────────────


class TestRoleBreakdownRendering:
    """AC-015 / BR-012: % validated headline is segmented by author_role
    with both counts and percentages, plus an overall total."""

    def test_outcome_section_describes_per_role_rows(
        self, skill_text: str
    ) -> None:
        block = _step3_block(skill_text)
        # The five canonical roles must each be enumerated.
        for role in ("SME", "Engineer", "PM", "Designer", "Other"):
            assert role in block, (
                f"Step 3 must enumerate the {role!r} role in the outcome "
                f"breakdown (AC-015)"
            )

    def test_outcome_section_describes_counts_and_percentages(
        self, skill_text: str
    ) -> None:
        """AC-015: the table must render both counts and percentages."""
        block = _step3_block(skill_text)
        # The required column set: validated/invalidated/unmeasured counts,
        # plus a % validated column.
        assert "Validated" in block, "outcome table must have a Validated column"
        assert "Invalidated" in block, (
            "outcome table must have an Invalidated column"
        )
        assert "Unmeasured" in block, (
            "outcome table must have an Unmeasured column"
        )
        # Headline metric is a percentage.
        assert "% Validated" in block or "% validated" in block.lower(), (
            "outcome table must render the % Validated headline column"
        )

    def test_outcome_section_describes_total_row(self, skill_text: str) -> None:
        """AC-015: the role breakdown ends with a Total row aggregating
        across roles."""
        block = _step3_block(skill_text)
        assert "Total" in block, (
            "Step 3 must describe a final Total row aggregating across roles "
            "(AC-015)"
        )

    def test_outcome_section_uses_author_role_field(
        self, skill_text: str
    ) -> None:
        """The breakdown is keyed on the value-hypothesis.yaml author_role
        field captured by /spec (BR-004)."""
        block = _step3_block(skill_text)
        assert "author_role" in block, (
            "Step 3 must key the breakdown on the value-hypothesis "
            "author_role field"
        )

    def test_outcome_section_handles_zero_division(
        self, skill_text: str
    ) -> None:
        """For a role with zero tracked features, the percentage column
        renders as `n/a` rather than dividing by zero."""
        block = _step3_block(skill_text)
        # The skill must say what happens when the denominator is zero.
        assert "n/a" in block.lower() or "zero" in block.lower(), (
            "Step 3 must specify how zero-tracked roles are rendered (n/a)"
        )


# ── AC-016: grandfather skip — features without value-hypothesis.yaml ──────


class TestGrandfatherSkip:
    """AC-016 / BR-013 / GA-002 / GA-003: features lacking
    value-hypothesis.yaml (or with directories not matching ^F\\d{3}-)
    are excluded from outcome-layer counts but may appear in process/cost."""

    def test_skill_describes_outcome_layer_grandfather_skip(
        self, skill_text: str
    ) -> None:
        block = _step3_block(skill_text)
        # The skill must explicitly say grandfathered features are skipped
        # in the outcome layer.
        assert "grandfather" in block.lower() or "skip" in block.lower(), (
            "Step 3 must describe the grandfather skip in the outcome layer "
            "(AC-016)"
        )

    def test_skill_uses_feature_id_regex_to_filter(
        self, skill_text: str
    ) -> None:
        """AC-016 / GA-002: directories not matching ^F\\d{3}- are skipped."""
        # The regex pattern must appear somewhere in the SKILL body.
        # Accept either the canonical regex literal or an explicit reference.
        has_regex = (
            r"^F\d{3}-" in skill_text
            or "F<NNN>-" in skill_text
            or "F\\d{3}" in skill_text
        )
        assert has_regex, (
            "SKILL.md must reference the ^F\\d{3}- regex (or F<NNN>- pattern) "
            "used to filter out grandfathered slug-only directories (GA-002, "
            "AC-016)"
        )

    def test_skill_excludes_features_without_value_hypothesis(
        self, skill_text: str
    ) -> None:
        """A feature directory without value-hypothesis.yaml is excluded
        from outcome counts."""
        block = _step3_block(skill_text)
        # The text must connect "missing value-hypothesis.yaml" to "excluded
        # from outcome counts".
        lowered = block.lower()
        assert "value-hypothesis.yaml" in block, (
            "Step 3 must reference value-hypothesis.yaml in the skip rule"
        )
        assert "exclud" in lowered or "skip" in lowered, (
            "Step 3 must say features without value-hypothesis.yaml are "
            "excluded/skipped in the outcome layer"
        )

    def test_skill_allows_grandfathered_features_in_other_layers(
        self, skill_text: str
    ) -> None:
        """AC-016: grandfathered features MAY appear in process and cost
        layers — the skip is outcome-only."""
        # Look anywhere in the SKILL body — the constraint is global, not
        # confined to Step 3.
        lowered = skill_text.lower()
        # The skill must explicitly state outcome-only scope.
        has_process_inclusion = (
            "may appear in process" in lowered
            or "process metrics" in lowered
        )
        has_cost_inclusion = (
            "may appear" in lowered and "cost" in lowered
        ) or "cost metrics" in lowered
        assert has_process_inclusion and has_cost_inclusion, (
            "SKILL.md must state that grandfathered features may still appear "
            "in process and cost layers (AC-016, BR-013)"
        )


# ── AC-017: locality — no ~/.claude/ writes, no network, no out-of-tree I/O


class TestLocality:
    """AC-017 / BR-014 / security consideration 4: the skill performs no
    reads or writes outside the project working tree, makes no network
    calls, and never writes to ~/.claude/."""

    def test_skill_forbids_home_claude_writes(self, skill_text: str) -> None:
        """AC-017 / BR-14: no ~/.claude/ writes for metrics purposes."""
        # The skill must explicitly disclaim ~/.claude/ writes.
        assert "~/.claude/" in skill_text, (
            "SKILL.md must reference ~/.claude/ when stating the no-write "
            "constraint (AC-017)"
        )
        lowered = skill_text.lower()
        # The negative statement must appear: "no writes to ~/.claude/" or
        # equivalent.
        assert (
            "no ~/.claude/" in lowered
            or "no `~/.claude/`" in lowered
            or "not write" in lowered and "~/.claude/" in skill_text
            or "no writes to ~/.claude" in lowered
        ), (
            "SKILL.md must explicitly forbid writes to ~/.claude/ (AC-017)"
        )

    def test_skill_forbids_network_calls(self, skill_text: str) -> None:
        """AC-017: no network calls; security consideration 4: no phone-home."""
        lowered = skill_text.lower()
        assert "network" in lowered, (
            "SKILL.md must reference network access in the locality "
            "constraint (AC-017)"
        )
        # Either "no network" or "no phone-home" satisfies the negative
        # statement.
        assert (
            "no network" in lowered
            or "no phone-home" in lowered
            or "no phone home" in lowered
        ), (
            "SKILL.md must explicitly forbid network calls / phone-home "
            "(AC-017, BR-014)"
        )

    def test_skill_constrains_reads_to_project_working_tree(
        self, skill_text: str
    ) -> None:
        """AC-017: reads are confined to the project working tree
        (.etc_sdlc/, .git/, scripts/, standards/)."""
        block = _constraints_block(skill_text).lower()
        assert "working tree" in block or "project working tree" in block, (
            "Constraints section must restrict reads to the project working "
            "tree (AC-017)"
        )

    def test_skill_cites_ac017_or_br014_for_locality(
        self, skill_text: str
    ) -> None:
        """The locality contract must be traceable back to AC-017 or BR-014
        in the SKILL body."""
        lowered = skill_text.lower()
        assert "ac-017" in lowered or "br-014" in lowered, (
            "SKILL.md must cite AC-017 or BR-014 alongside the locality "
            "constraint to make the contract traceable"
        )


# ── Definition-of-Done structural assertions ───────────────────────────────


class TestDefinitionOfDone:
    """The Definition of Done block is the operator-facing checklist that
    summarizes the skill's contract. Its presence and shape are part of
    the skill's contract."""

    def test_skill_has_definition_of_done_section(
        self, skill_text: str
    ) -> None:
        assert "## Definition of Done" in skill_text, (
            "SKILL.md must include a Definition of Done section that "
            "summarizes the contract"
        )

    def test_definition_of_done_names_three_sections(
        self, skill_text: str
    ) -> None:
        """The DoD must explicitly name the three labeled sections so the
        operator can verify them at a glance."""
        dod = _section(
            skill_text,
            "## Definition of Done",
            ("## Post-Completion Guidance",),
        )
        assert "## Process" in dod, "DoD must name the Process section"
        assert "## Outcome" in dod, "DoD must name the Outcome section"
        assert "## Cost" in dod, "DoD must name the Cost section"
