"""Contract tests for the /rule-sweep skill (the in-flight rule capture + sweep loop).

`/rule-sweep` is the ENFORCE-arm in-flight loop of
F-2026-06-10-brownfield-architecture-baseline (task 012): a human states a rule
mid-build, the rule lands in the machine baseline via ``baseline.py append-rule``,
the conductor sweeps the repo for violations and dispatches file-isolated fix
agents through normal hooked Edit/Write, then ``baseline-verify`` re-runs so the
new rule is enforced going forward. It is the in-flight arm of
``standards/process/lessons-terminate-in-gates.md``.

Grep-based, consistent with the other ``*_skill*`` contract tests in the suite
(see ``test_build_skill_baseline_gate.py`` for the slice-and-grep pattern). The
tests pin the skill's required sections, its five-phase flow, the exact wave-1
substrate invocations it must instruct, and the three non-negotiable safety
contracts (never bypass hooks, never force-fix behavior-changing rewrites, never
silently drop a partial sweep).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULE_SWEEP_SKILL_PATH = REPO_ROOT / "skills" / "rule-sweep" / "SKILL.md"


def _read_skill() -> str:
    assert RULE_SWEEP_SKILL_PATH.exists(), (
        f"rule-sweep skill not found: {RULE_SWEEP_SKILL_PATH}"
    )
    return RULE_SWEEP_SKILL_PATH.read_text(encoding="utf-8")


def _slice(content: str, start_marker: str, end_marker: str) -> str:
    """Return the SKILL.md substring between two markers (start inclusive).

    Scopes a grep assertion to exactly one phase block so a string appearing
    elsewhere in the skill cannot satisfy the assertion by accident.
    """
    start = content.find(start_marker)
    assert start != -1, f"marker not found in rule-sweep skill: {start_marker!r}"
    end = content.find(end_marker, start)
    if end == -1:
        end = len(content)
    return content[start:end]


# --------------------------------------------------------------------------- #
# House SKILL.md shape (frontmatter + required sections)                       #
# --------------------------------------------------------------------------- #


def test_should_carry_house_frontmatter_when_skill_is_read() -> None:
    """The skill must open with name+description YAML frontmatter (house shape)."""
    content = _read_skill()

    assert content.startswith("---\n"), (
        "rule-sweep SKILL.md must open with `---` YAML frontmatter."
    )
    head = content[: content.find("---", 4)]
    assert "name: rule-sweep" in head, "frontmatter must declare `name: rule-sweep`."
    assert "description:" in head, "frontmatter must carry a `description:` field."


def test_should_have_response_format_section_when_skill_is_read() -> None:
    """House compact-skill shape requires a Response Format section."""
    content = _read_skill()

    assert "Response Format" in content, (
        "rule-sweep SKILL.md must declare a Response Format section "
        "(house compact-skill shape, per skills/hotfix and skills/checkpoint)."
    )


def test_should_have_definition_of_done_section_when_skill_is_read() -> None:
    """House compact-skill shape requires a Definition of Done section."""
    content = _read_skill()

    assert "Definition of Done" in content, (
        "rule-sweep SKILL.md must declare a Definition of Done section "
        "(house compact-skill shape)."
    )


def test_should_have_before_starting_section_when_skill_is_read() -> None:
    """The skill must read its required-reading set before any phase action."""
    content = _read_skill()

    assert "Before Starting" in content, (
        "rule-sweep SKILL.md must declare a Before Starting section naming its "
        "required reading."
    )


def test_should_reference_interactive_input_standard_when_skill_is_read() -> None:
    """Capture prompts use Pattern A/B — the standard must be cited."""
    content = _read_skill()

    assert "standards/process/interactive-user-input.md" in content, (
        "rule-sweep SKILL.md must cite interactive-user-input.md (Pattern A/B "
        "for the rule-capture prompts)."
    )


def test_should_use_pattern_b_marker_for_open_capture_when_skill_is_read() -> None:
    """The free-form rule statement is captured via the Pattern B visual marker."""
    content = _read_skill()

    assert "Your answer needed" in content, (
        "rule-sweep SKILL.md must use the Pattern B visual marker "
        "(`**▶ Your answer needed:**`) to capture the free-form rule statement."
    )


# --------------------------------------------------------------------------- #
# The five-phase flow                                                          #
# --------------------------------------------------------------------------- #


def test_should_declare_all_five_phases_when_skill_is_read() -> None:
    """The required flow is five phases: capture, append, sweep, report, re-verify."""
    content = _read_skill()

    for phase in (
        "Phase 1",
        "Phase 2",
        "Phase 3",
        "Phase 4",
        "Phase 5",
    ):
        assert phase in content, (
            f"rule-sweep SKILL.md must declare {phase} of the five-phase flow."
        )


def test_should_order_phases_capture_append_sweep_report_verify() -> None:
    """The five phase HEADINGS must appear in the required execution order."""
    content = _read_skill()

    idx = [content.find(f"### Phase {n}:") for n in range(1, 6)]
    assert all(i != -1 for i in idx), (
        "all five `### Phase N:` headings must be present."
    )
    assert idx == sorted(idx), (
        "Phases 1-5 must appear in order: capture -> append-rule -> sweep -> "
        "report -> re-verify."
    )


# --------------------------------------------------------------------------- #
# AC-1: capture (sanitized) + append-rule with provenance + mechanizable flag  #
# --------------------------------------------------------------------------- #


def test_should_sanitize_rule_statement_at_capture_when_phase1_runs() -> None:
    """Discovered/operator-stated text is untrusted — sanitized at the capture site."""
    content = _read_skill()
    phase1 = _slice(content, "### Phase 1:", "### Phase 2:")

    assert "saniti" in phase1.lower(), (
        "Phase 1 must sanitize the operator-stated rule at the capture site "
        "(untrusted-input defense; control chars stripped, length-capped)."
    )


def test_should_capture_who_and_trigger_provenance_when_phase1_runs() -> None:
    """Provenance {who, when, trigger} must be captured at the rule site."""
    content = _read_skill()
    phase1 = _slice(content, "### Phase 1:", "### Phase 2:")

    assert "who" in phase1.lower(), "Phase 1 must capture the `who` provenance."
    assert "trigger" in phase1.lower(), (
        "Phase 1 must capture the `trigger` provenance."
    )


def test_should_suggest_mechanizable_against_v1_grammar_when_phase1_runs() -> None:
    """The mechanizable suggestion is driven by the v1 statement grammar."""
    content = _read_skill()
    phase1 = _slice(content, "### Phase 1:", "### Phase 2:")

    assert "mechanizable" in phase1.lower(), (
        "Phase 1 must suggest a mechanizable flag based on whether the "
        "statement fits the v1 grammar."
    )
    assert "files matching" in phase1.lower(), (
        "Phase 1 must name the v1 'files matching GLOB must not contain NEEDLE' "
        "grammar shape when judging mechanizability."
    )
    assert "must not contain" in phase1.lower(), (
        "Phase 1 must name the v1 'directory DIR must not contain GLOB files' "
        "grammar shape when judging mechanizability."
    )


def test_should_invoke_append_rule_with_provenance_when_phase2_runs() -> None:
    """Phase 2 records the rule via baseline.py append-rule with full provenance."""
    content = _read_skill()
    phase2 = _slice(content, "### Phase 2:", "### Phase 3:")

    assert "python3 ~/.claude/scripts/baseline.py append-rule" in phase2, (
        "Phase 2 must invoke `python3 ~/.claude/scripts/baseline.py append-rule` "
        "(the ~/.claude prefix is load-bearing for the Codex path rewrite)."
    )
    for flag in ("--statement", "--who", "--trigger"):
        assert flag in phase2, (
            f"Phase 2's append-rule call must pass `{flag}` (provenance {{who, "
            "when, trigger}})."
        )
    assert "--mechanizable" in phase2, (
        "Phase 2 must pass `--mechanizable` when the rule fits the v1 grammar."
    )


def test_should_read_back_rule_id_when_phase2_runs() -> None:
    """append-rule prints R-NNN; the skill must capture it for the sweep."""
    content = _read_skill()
    phase2 = _slice(content, "### Phase 2:", "### Phase 3:")

    assert "R-NNN" in phase2 or "R-" in phase2, (
        "Phase 2 must capture the printed `R-NNN` rule id (it scopes the "
        "Phase 3 mechanizable sweep)."
    )


# --------------------------------------------------------------------------- #
# AC-2: repo-wide sweep -> file-isolated fix agents via hooked Edit/Write      #
# --------------------------------------------------------------------------- #


def test_should_find_mechanizable_violations_via_dispatcher_when_phase3_runs() -> None:
    """For mechanizable rules the sweep runs baseline-verify with the new rule id."""
    content = _read_skill()
    phase3 = _slice(content, "### Phase 3:", "### Phase 4:")

    assert "bash hooks/baseline-verify.sh" in phase3, (
        "Phase 3 must run `bash hooks/baseline-verify.sh` to find violations of "
        "a mechanizable rule."
    )
    for field in ("repo_root", "rule_ids", "cwd"):
        assert field in phase3, (
            f"Phase 3's dispatcher JSON must carry the `{field}` field "
            "(the {repo_root, rule_ids, cwd} contract)."
        )


def test_should_scope_sweep_to_new_rule_id_when_phase3_runs() -> None:
    """The sweep targets the just-appended rule id, not all rules."""
    content = _read_skill()
    phase3 = _slice(content, "### Phase 3:", "### Phase 4:")

    assert "rule_ids" in phase3 and "R-" in phase3, (
        "Phase 3 must pass the new rule id in `rule_ids` (sweep only the rule "
        "just captured, not the whole baseline)."
    )


def test_should_survey_non_mechanizable_rules_via_grep_or_glob_when_phase3() -> None:
    """Non-mechanizable rules get a grep/Glob-driven survey, not the dispatcher."""
    content = _read_skill()
    phase3 = _slice(content, "### Phase 3:", "### Phase 4:")

    assert "Grep" in phase3 or "Glob" in phase3 or "grep" in phase3, (
        "Phase 3 must survey non-mechanizable rules via grep/Glob (the "
        "dispatcher returns no-check for statements outside the v1 grammar)."
    )


def test_should_dispatch_fix_agents_in_file_isolated_batches_when_phase3() -> None:
    """Fix work is dispatched to agents in file-isolated batches via the Agent tool."""
    content = _read_skill()
    phase3 = _slice(content, "### Phase 3:", "### Phase 4:")

    assert "Agent tool" in phase3, (
        "Phase 3 must dispatch fix agents via the Agent tool (the conductor "
        "never edits production files itself — mirrors /build's dispatch)."
    )
    assert "file-isolat" in phase3.lower() or "file isolat" in phase3.lower(), (
        "Phase 3 must dispatch in file-isolated batches (no two agents touch "
        "the same file — /build's dispatch discipline)."
    )


def test_should_route_fixes_through_hooked_edit_write_when_phase3_runs() -> None:
    """Fixes go through normal hooked Edit/Write — the skill never bypasses hooks."""
    content = _read_skill()
    phase3 = _slice(content, "### Phase 3:", "### Phase 4:")

    assert "hooked Edit/Write" in phase3 or "hooked Edit" in phase3, (
        "Phase 3 must route fixes through normal hooked Edit/Write (all existing "
        "gates active during the sweep)."
    )


def test_should_never_force_fix_behavior_changing_rewrites_when_phase3() -> None:
    """Behavior-changing rewrites are listed as remaining with a reason, never forced."""
    content = _read_skill()
    phase3 = _slice(content, "### Phase 3:", "### Phase 4:")

    assert "behavior-changing" in phase3.lower(), (
        "Phase 3 must name behavior-changing rewrites as the never-force-fix "
        "class (they are reported as remaining with a reason)."
    )
    assert "never force" in phase3.lower() or "not force" in phase3.lower(), (
        "Phase 3 must state behavior-changing rewrites are NEVER force-fixed."
    )


# --------------------------------------------------------------------------- #
# AC-2: report files-changed AND violations-remaining; partials never silent   #
# --------------------------------------------------------------------------- #


def test_should_report_files_changed_with_paths_when_phase4_runs() -> None:
    """The report must list files-changed WITH their paths."""
    content = _read_skill()
    phase4 = _slice(content, "### Phase 4:", "### Phase 5:")

    assert "files-changed" in phase4 or "files changed" in phase4.lower(), (
        "Phase 4 must report files-changed."
    )
    assert "path" in phase4.lower(), (
        "Phase 4 must report files-changed WITH their paths."
    )


def test_should_report_violations_remaining_with_paths_when_phase4_runs() -> None:
    """The report must list violations-remaining WITH paths and a reason."""
    content = _read_skill()
    phase4 = _slice(content, "### Phase 4:", "### Phase 5:")

    assert "violations-remaining" in phase4 or "violations remaining" in phase4.lower(), (
        "Phase 4 must report violations-remaining."
    )
    assert "reason" in phase4.lower(), (
        "Phase 4 must give a reason for each remaining violation "
        "(e.g. behavior-changing rewrite, outside the grammar)."
    )


def test_should_record_partial_sweeps_never_silent_when_phase4_runs() -> None:
    """A partial sweep is recorded, never silent (the covr never-silent-partial rule)."""
    content = _read_skill()
    phase4 = _slice(content, "### Phase 4:", "### Phase 5:")

    assert "partial" in phase4.lower(), (
        "Phase 4 must name partial sweeps explicitly."
    )
    assert "never silent" in phase4.lower() or "never go silent" in phase4.lower(), (
        "Phase 4 must state partial sweeps are recorded, NEVER silent "
        "(the violations-remaining honesty contract)."
    )


# --------------------------------------------------------------------------- #
# AC-3: post-sweep baseline-verify re-run so the rule is enforced going fwd    #
# --------------------------------------------------------------------------- #


def test_should_rerun_baseline_verify_after_sweep_when_phase5_runs() -> None:
    """Phase 5 re-runs baseline-verify so the rule is live (enforced going forward)."""
    content = _read_skill()
    phase5 = _slice(content, "### Phase 5:", "## Constraints")

    assert "bash hooks/baseline-verify.sh" in phase5, (
        "Phase 5 must re-run `bash hooks/baseline-verify.sh` after the sweep to "
        "confirm the new rule is enforced going forward."
    )


def test_should_read_verdicts_from_json_not_exit_code_when_phase5_runs() -> None:
    """Verdicts come from the results JSON — the dispatcher always exits 0."""
    content = _read_skill()
    phase5 = _slice(content, "### Phase 5:", "## Constraints")

    assert "exit code" in phase5.lower() and "json" in phase5.lower(), (
        "Phase 5 must read verdicts from the results JSON, never the dispatcher "
        "exit code (the dispatcher always exits 0)."
    )


def test_should_confirm_rule_is_live_when_phase5_runs() -> None:
    """Phase 5 confirms the rule is enforced (live) going forward."""
    content = _read_skill()
    phase5 = _slice(content, "### Phase 5:", "## Constraints")

    assert "enforced going forward" in phase5.lower() or "rule is live" in phase5.lower(), (
        "Phase 5 must confirm the rule is now enforced going forward."
    )


# --------------------------------------------------------------------------- #
# Missing-baseline handling (must not crash)                                   #
# --------------------------------------------------------------------------- #


def test_should_handle_missing_baseline_without_crashing_when_skill_is_read() -> None:
    """No baseline -> offer bootstrap; the skill must not crash."""
    content = _read_skill()

    assert "python3 ~/.claude/scripts/baseline.py status" in content, (
        "The skill must check `baseline.py status` first so a missing baseline "
        "is detected, not crashed into."
    )
    assert "missing" in content, (
        "The skill must branch on the `missing` status token."
    )


def test_should_offer_bootstrap_paths_when_baseline_missing() -> None:
    """Missing-baseline offers /init-project --phase=baseline OR baseline.py init."""
    content = _read_skill()

    assert "/init-project --phase=baseline" in content, (
        "Missing-baseline handling must offer `/init-project --phase=baseline` "
        "as a bootstrap path."
    )
    assert "baseline.py init" in content, (
        "Missing-baseline handling must offer the `baseline.py init` "
        "(empty-discover) bootstrap path as the operator's alternative."
    )


# --------------------------------------------------------------------------- #
# Safety / scope: never bypass hooks; siblings own init-project + baseline.py  #
# --------------------------------------------------------------------------- #


def test_should_never_bypass_hooks_when_skill_is_read() -> None:
    """The skill must state it never bypasses hooks (gates active during the sweep)."""
    content = _read_skill()

    assert "never bypass" in content.lower() or "not bypass" in content.lower(), (
        "The skill must state it NEVER bypasses hooks during the sweep "
        "(generated checkers are read-only; fixes use the normal hooked path)."
    )


def test_should_cite_lessons_terminate_in_gates_when_skill_is_read() -> None:
    """This is the in-flight arm of lessons-terminate-in-gates — it must say so."""
    content = _read_skill()

    assert "lessons-terminate-in-gates" in content, (
        "The skill must cite standards/process/lessons-terminate-in-gates.md "
        "(it is the in-flight arm: a stated rule terminates in a live gate)."
    )
