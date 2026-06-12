"""Contract tests for the published-asset guard wiring (F-2026-06-12, task 003).

Wave 0 shipped the helper (`scripts/janitor_assets.py`) and the standard
(`standards/process/janitor-write-boundary.md`, pinned by
`tests/test_janitor_write_boundary_assets.py`). This wave wires the two
consumers — the fix-subagent manifest (`agents/janitor.md`) and the
orchestrator skill (`skills/janitor/SKILL.md`).

Both consumers are plain-markdown prose Claude reads at dispatch/invocation,
not executable code, so these are grep-style contract tests (mirroring
`tests/test_janitor_skill.py` and `tests/test_janitor_write_boundary_assets.py`):
they assert each file carries the load-bearing strings that encode the
acceptance criteria. If a clause is removed or renamed, the matching test fails.

The two verbatim greppable strings are owned by the standard (single source of
truth, spec BR-007); the mirrors reuse them EXACTLY. They are duplicated here so
a drift in either the standard or a mirror trips a test.

Maps to task 003 acceptance criteria:
    AC-1 — agents/janitor.md dead-code category (b) gains the published-asset
           clause (abort success=false absent orchestrator-supplied evidence);
           the agent's tool grants are unchanged (no gh/network); the clause is
           grepped and the tools line is pinned.
    AC-2 — skills/janitor/SKILL.md survey/select classifies via
           scripts/janitor_assets.py before candidate finalization, runs the org
           search at select (orchestrator-side gh crossing), records the evidence
           (or operator-confirm or fail-closed drop) in runs.jsonl for every
           published-asset candidate, applies identically in both lanes
           (autonomous fail-closed = drop recorded), and leaves the
           non-published-asset flow byte-equivalent (no search, no new prompts).
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_PATH = _REPO_ROOT / "agents" / "janitor.md"
SKILL_PATH = _REPO_ROOT / "skills" / "janitor" / "SKILL.md"

# Verbatim greppable strings OWNED by the standard (spec BR-007). The mirrors
# reuse them exactly; pinned identically in tests/test_janitor_write_boundary_assets.py.
PUBLISHED_API_SURFACE_PHRASE = "a published API surface"
REPO_LOCAL_INSUFFICIENT_PHRASE = (
    "Repo-local unreferenced-ness alone is never sufficient evidence for this "
    "file class"
)


def _agent_text() -> str:
    return AGENT_PATH.read_text(encoding="utf-8")


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


# ── AC-1: agent manifest ─────────────────────────────────────────────────


class TestAgentFileExists:
    """The fix-subagent manifest exists and is readable."""

    def test_should_find_agent_when_resolving_repo_path(self) -> None:
        assert AGENT_PATH.exists()


class TestAgentDeadCodePublishedAssetClause:
    """AC-1: dead-code category (b) gains the published-asset abort clause."""

    def test_should_name_published_asset_in_dead_code_context(self) -> None:
        # The clause lives in the dead-code category (b) discussion, not a
        # detached section. Both tokens present is the cheap structural check;
        # the abort + evidence tests below pin the behavior.
        text = _agent_text()
        assert "published-asset" in text
        assert "dead-code" in text

    def test_should_abort_success_false_without_orchestrator_evidence(self) -> None:
        # BR-004 / GA-001: the networkless subagent aborts any published-asset
        # deletion whose dispatch lacks orchestrator-supplied search evidence.
        text = _agent_text()
        low = text.lower()
        assert "published-asset" in text
        assert "success=false" in low or "success = false" in low
        # The trigger is *missing orchestrator-supplied evidence*, not a guess.
        assert "evidence" in low
        assert "orchestrator" in low

    def test_should_reuse_standard_verbatim_repo_local_phrase(self) -> None:
        # Mirror cites the standard's exact phrasing (single source of truth).
        assert REPO_LOCAL_INSUFFICIENT_PHRASE in _agent_text()

    def test_should_cite_published_api_surface_phrase(self) -> None:
        assert PUBLISHED_API_SURFACE_PHRASE in _agent_text()

    def test_should_cite_the_write_boundary_standard(self) -> None:
        # Layers cite the standard rather than duplicating its glob list
        # (spec BR-007); the agent must reference it as the glob source.
        assert "standards/process/janitor-write-boundary.md" in _agent_text()

    def test_should_not_duplicate_the_glob_list(self) -> None:
        # The agent cites the standard; it must NOT carry its own copy of all
        # three globs (single source of truth). A single illustrative glob is
        # acceptable, but not the full triplet that would fork the list.
        text = _agent_text()
        triplet = ("public/**" in text) + ("static/**" in text) + ("www/**" in text)
        assert triplet < 3, "agent duplicates the standard's full glob triplet"


class TestAgentToolGrantsUnchanged:
    """AC-1: the agent's tool grants are unchanged — no gh/network added."""

    def test_should_pin_the_exact_tools_line(self) -> None:
        # The toolset IS the security boundary: the published-asset clause must
        # NOT widen it. Pin the frontmatter tools line verbatim.
        text = _agent_text()
        assert "tools: Read, Edit, Write, Bash, Grep, Glob" in text

    def test_should_not_grant_gh_or_network_tools(self) -> None:
        tools_line = next(
            line for line in _agent_text().splitlines() if line.startswith("tools:")
        )
        for forbidden in ("gh", "WebFetch", "WebSearch", "curl", "network"):
            assert forbidden not in tools_line, forbidden

    def test_should_keep_subagent_networkless(self) -> None:
        # The subagent never runs gh itself; the clause reinforces, not relaxes.
        low = _agent_text().lower()
        assert "networkless" in low or "no authority" in low


# ── AC-2: orchestrator skill ─────────────────────────────────────────────


class TestSkillFileExists:
    """The orchestrator skill exists and is readable."""

    def test_should_find_skill_when_resolving_repo_path(self) -> None:
        assert SKILL_PATH.exists()


class TestSkillClassifiesViaHelperBeforeFinalization:
    """AC-2: survey/select classifies published-asset paths via the helper
    BEFORE candidate finalization."""

    def test_should_invoke_classify_helper(self) -> None:
        text = _skill_text()
        assert "janitor_assets.py" in text
        assert "classify" in text

    def test_should_classify_before_candidate_finalization(self) -> None:
        low = _skill_text().lower()
        assert "before" in low
        # Classification anchors at the survey/select layer.
        assert "classif" in low
        assert "candidate" in low

    def test_should_anchor_at_survey_or_select(self) -> None:
        low = _skill_text().lower()
        assert "survey" in low
        assert "select" in low


class TestSkillRunsOrgSearchAtSelect:
    """AC-2: the org search runs at select (orchestrator-side gh crossing)."""

    def test_should_run_consumer_search_via_helper(self) -> None:
        text = _skill_text()
        assert "consumer-search" in text

    def test_should_name_the_gh_trust_crossing(self) -> None:
        low = _skill_text().lower()
        # The search is the orchestrator's single gh trust crossing, not the
        # subagent's.
        assert "gh" in low
        assert "trust" in low and ("crossing" in low or "boundary" in low)

    def test_should_keep_search_orchestrator_side(self) -> None:
        low = _skill_text().lower()
        assert "orchestrator" in low
        # The subagent stays networkless — the skill says the search is its job.
        assert "consumer" in low and "search" in low


class TestSkillPerCandidateComposition:
    """AC-2: the select-step decision flow matches evaluate_candidate's
    composition (classify → OTHER short-circuits with NO search; PUBLISHED_ASSET
    delegates to the consumer search). The CLI surfaces are unchanged; the prose
    must describe the per-candidate evaluation through that composition."""

    def test_should_describe_per_candidate_evaluation(self) -> None:
        low = _skill_text().lower()
        # Each candidate is decided one at a time via the classify→search
        # composition (evaluate_candidate's semantics).
        assert "evaluate_candidate" in low or "per-candidate" in low
        assert "candidate" in low

    def test_should_name_evaluate_candidate_composition(self) -> None:
        # The skill references the single composition entry point by name so a
        # reader maps the prose to the helper's structurally-enforced semantics.
        assert "evaluate_candidate" in _skill_text()

    def test_should_short_circuit_other_with_no_search(self) -> None:
        low = _skill_text().lower()
        # OTHER classification short-circuits: cleared-other, no gh crossing.
        assert "cleared-other" in low
        assert "no search" in low or "no org search" in low

    def test_should_keep_existing_cli_invocations(self) -> None:
        # The skill still shells out to the unchanged classify / consumer-search
        # CLI surfaces where it crosses to the helper (the composition is the
        # decision flow, not a new CLI subcommand).
        text = _skill_text()
        assert "janitor_assets.py classify" in text
        assert "janitor_assets.py consumer-search" in text


class TestSkillVerdictVocabulary:
    """AC-2: the closed verdict vocabulary is the FOUR tokens the helper now
    returns; the skill pins each and never invents a fifth."""

    def test_should_pin_all_four_closed_tokens(self) -> None:
        low = _skill_text().lower()
        for token in ("cleared", "blocked", "fail-closed", "cleared-other"):
            assert token in low, token

    def test_should_distinguish_cleared_other_from_searched_cleared(self) -> None:
        low = _skill_text().lower()
        # cleared-other = classification cleared it, no search was needed —
        # explicitly distinct from a searched `cleared` (zero-hit). That
        # distinction is the audit value.
        assert "cleared-other" in low
        assert "no search" in low or "never searched" in low or "not searched" in low

    def test_should_state_the_vocabulary_is_closed(self) -> None:
        low = _skill_text().lower()
        # The four tokens are the closed set; the skill says so.
        assert "closed" in low and "vocabulary" in low


class TestSkillRecordsEvidenceInRunsJsonl:
    """AC-2: evidence / operator-confirm / fail-closed drop recorded in
    runs.jsonl for EVERY published-asset candidate, cleared or not."""

    def test_should_record_in_runs_jsonl(self) -> None:
        assert "runs.jsonl" in _skill_text()

    def test_should_record_for_every_candidate_cleared_or_not(self) -> None:
        low = _skill_text().lower()
        assert "every published-asset candidate" in low
        assert "cleared or not" in low

    def test_should_name_the_three_record_outcomes(self) -> None:
        low = _skill_text().lower()
        # The cleared-search evidence, the operator-confirm record, OR the
        # fail-closed drop — all three land in the run record.
        assert "evidence" in low
        assert "operator-confirm" in low or "operator confirm" in low
        assert "fail-closed" in low and "drop" in low

    def test_should_record_query_org_scope_timestamp_evidence(self) -> None:
        low = _skill_text().lower()
        # BR-006: the cleared evidence carries query, org scope, ISO-8601 stamp.
        assert "query" in low
        assert "scope" in low or "org" in low
        assert "timestamp" in low or "iso-8601" in low or "searched_at" in low

    def test_should_record_cleared_other_distinct_from_searched_cleared(
        self,
    ) -> None:
        # The audit value of the feature: the run record distinguishes a
        # classification-only clear (cleared-other, no search ran) from a
        # searched zero-hit clear (cleared, evidence dict attached). Both
        # statuses appear in the run-record description.
        low = _skill_text().lower()
        assert "cleared-other" in low
        assert "cleared" in low
        # The distinction is explicitly about whether a search ran / evidence.
        assert "no search" in low or "no evidence" in low or "no org search" in low


class TestSkillBothLanesIdentical:
    """AC-2: applies identically in /janitor and /janitor --autonomous;
    autonomous fail-closed = drop recorded; interactive = operator-confirm."""

    def test_should_apply_in_both_lanes(self) -> None:
        text = _skill_text()
        assert "/janitor" in text
        assert "/janitor --autonomous" in text

    def test_should_state_identical_treatment(self) -> None:
        low = _skill_text().lower()
        assert "identical" in low or "both lanes" in low

    def test_should_drop_and_record_on_autonomous_fail_closed(self) -> None:
        low = _skill_text().lower()
        assert "autonomous" in low
        assert "drop" in low and "fail-closed" in low

    def test_should_operator_confirm_on_interactive_fail_closed(self) -> None:
        low = _skill_text().lower()
        # The interactive lane routes a fail-closed search to operator-confirm,
        # never a silent clear.
        assert "operator-confirm" in low or "operator confirm" in low
        assert "interactive" in low


class TestSkillNonPublishedAssetFlowUnchanged:
    """AC-2: the non-published-asset flow is byte-equivalent to today — no org
    search, no new prompts."""

    def test_should_exempt_non_published_asset_candidates(self) -> None:
        low = _skill_text().lower()
        # The guard fires ONLY for published-asset candidates; everything else
        # (e.g. src/helper.py dead-code) flows as before.
        assert "non-published-asset" in low or "other" in low
        assert "no search" in low or "no org search" in low

    def test_should_add_no_new_prompts_to_other_flow(self) -> None:
        low = _skill_text().lower()
        # No new prompt is introduced for the ordinary (OTHER-classified) flow.
        assert "no new prompt" in low or "no new prompts" in low


class TestSkillReusesStandardVerbatimPhrases:
    """AC-2 / BR-007: the skill cites the standard's verbatim greppable phrases
    rather than duplicating its glob list."""

    def test_should_reuse_repo_local_insufficient_phrase(self) -> None:
        assert REPO_LOCAL_INSUFFICIENT_PHRASE in _skill_text()

    def test_should_cite_published_api_surface_phrase(self) -> None:
        assert PUBLISHED_API_SURFACE_PHRASE in _skill_text()

    def test_should_cite_the_write_boundary_standard(self) -> None:
        assert "standards/process/janitor-write-boundary.md" in _skill_text()

    def test_should_not_duplicate_full_glob_triplet_outside_existing(self) -> None:
        # The skill already does not carry the triplet; the new clause must cite
        # the standard, not fork the list.
        text = _skill_text()
        triplet = ("public/**" in text) + ("static/**" in text) + ("www/**" in text)
        assert triplet < 3, "skill duplicates the standard's full glob triplet"
