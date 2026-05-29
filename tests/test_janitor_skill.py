"""Contract tests for the /janitor orchestrator skill (F-2026-05-29, task 005).

`skills/janitor/SKILL.md` is plain-markdown orchestration prose that Claude
reads at invocation, not executable code. These are grep-style contract tests
(mirroring `tests/test_build_autonomous_skill.py`): they assert the SKILL.md
contains the load-bearing strings that encode each acceptance criterion of the
janitor pipeline. If a clause is removed or renamed, the matching test fails.

Each test class maps to one or more spec ACs. The pipeline is the strict linear
sequence (design.md "Architecture Overview"):

    survey → select → isolate → dispatch → verify → boundary-check → deliver
           → record → teardown
"""

from __future__ import annotations

from pathlib import Path

SKILL_PATH = Path(__file__).parent.parent / "skills" / "janitor" / "SKILL.md"


def _skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


class TestSkillFileExists:
    """The skill file exists and carries the house frontmatter."""

    def test_skill_file_exists(self) -> None:
        assert SKILL_PATH.exists()

    def test_has_name_frontmatter(self) -> None:
        text = _skill_text()
        assert text.startswith("---")
        assert "name: janitor" in text

    def test_has_description_frontmatter(self) -> None:
        assert "description:" in _skill_text()

    def test_has_house_format_sections(self) -> None:
        text = _skill_text()
        for section in (
            "## Response Format",
            "## Subagent Dispatch",
            "## Before Starting",
            "## Workflow",
            "## Definition of Done",
        ):
            assert section in text, section


class TestDualInvocationAC001:
    """AC-001: both modes run the full pipeline; autonomous issues zero prompts;
    nothing-to-clean exits 0 with no PR and no leftover branch/worktree."""

    def test_both_invocations_documented(self) -> None:
        text = _skill_text()
        assert "/janitor" in text
        assert "/janitor --autonomous" in text

    def test_autonomous_is_zero_prompts(self) -> None:
        text = _skill_text()
        assert "zero prompts" in text.lower() or "no prompts" in text.lower()
        # The hands-off absolute: no AskUserQuestion / Pattern B on that path.
        assert "AskUserQuestion" in text

    def test_full_pipeline_steps_present(self) -> None:
        text = _skill_text().lower()
        for step in (
            "survey",
            "select",
            "isolate",
            "dispatch",
            "verify",
            "boundary",
            "deliver",
            "record",
            "teardown",
        ):
            assert step in text, step

    def test_nothing_to_clean_exits_clean(self) -> None:
        text = _skill_text()
        assert "nothing to clean" in text.lower()
        # No PR and no leftover branch/worktree on the empty path.
        assert "exit 0" in text.lower() or "code 0" in text.lower()


class TestWorktreeIsolationAC002AC003:
    """AC-002 / AC-003: mandatory worktree on a fresh branch off main; primary
    tree byte-identical; branch base == main HEAD; worktree torn down."""

    def test_git_worktree_off_main(self) -> None:
        text = _skill_text()
        assert "git worktree add" in text
        assert "main" in text

    def test_branch_namespace(self) -> None:
        assert "claude/janitor/" in _skill_text()

    def test_primary_tree_unchanged_invariant(self) -> None:
        text = _skill_text()
        assert "git status --porcelain" in text

    def test_merge_base_equals_main_head(self) -> None:
        text = _skill_text().lower()
        assert "merge-base" in text or "merge base" in text

    def test_worktree_removed_on_completion_or_abort(self) -> None:
        text = _skill_text()
        assert "git worktree remove" in text


class TestSubagentDispatchAC007AC014:
    """AC-007 / AC-014: dispatch the janitor fix-subagent one category at a time;
    preview → draft, autonomous → ready, mixed → draft; gh fallback; PR body."""

    def test_dispatches_janitor_subagent(self) -> None:
        text = _skill_text()
        assert "agents/janitor.md" in text
        assert "Task" in text  # the dispatch tool

    def test_one_category_per_dispatch(self) -> None:
        text = _skill_text().lower()
        assert "one category" in text or "one category at a time" in text

    def test_trust_level_read_via_script(self) -> None:
        text = _skill_text()
        assert "janitor_trust.py level" in text

    def test_preview_draft_autonomous_ready_branching(self) -> None:
        text = _skill_text().lower()
        assert "draft" in text
        assert "ready-for-review" in text or "ready for review" in text
        # preview→draft, autonomous→ready
        assert "preview" in text
        assert "autonomous" in text

    def test_mixed_batch_is_draft(self) -> None:
        text = _skill_text().lower()
        assert "mixed" in text and "draft" in text

    def test_gh_fallback_to_local_branch(self) -> None:
        text = _skill_text().lower()
        # gh absent / PR-open fails → degrade to local branch, branch survives.
        assert "gh" in text
        assert "local branch" in text
        assert "degrad" in text or "fallback" in text

    def test_pr_body_names_categories_and_boundary_result(self) -> None:
        text = _skill_text()
        assert "Janitorial Services" in text
        body = text.lower()
        assert "categor" in body
        assert "boundary" in body and "clean" in body


class TestVerifyAndBoundaryAC006AC010:
    """AC-006 / AC-010: gates green before any PR; boundary check aborts on
    violation; never push origin/main, never --no-verify, never disable sandbox,
    never self-merge; v1 categories only; ceilings."""

    def test_gates_green_before_pr(self) -> None:
        text = _skill_text().lower()
        assert "green" in text
        # red gate aborts with no PR
        assert "red" in text
        assert "abort" in text

    def test_boundary_check_invoked(self) -> None:
        text = _skill_text()
        assert "janitor_boundary_check.py" in text

    def test_boundary_violation_aborts_no_pr(self) -> None:
        text = _skill_text().lower()
        assert "violation" in text
        assert "no pr" in text or "opens no pr" in text or "open no pr" in text

    def test_never_push_origin_main(self) -> None:
        text = _skill_text()
        assert "origin/main" in text
        body = text.lower()
        assert "never push" in body or "must not push" in body or "no push" in body

    def test_never_self_merge(self) -> None:
        text = _skill_text().lower()
        assert "self-merge" in text or "never merge" in text or "merges its own" in text

    def test_never_skip_git_hooks(self) -> None:
        assert "--no-verify" in _skill_text()

    def test_never_disable_sandbox(self) -> None:
        assert "dangerouslyDisableSandbox" in _skill_text()

    def test_v1_category_list(self) -> None:
        text = _skill_text()
        for category in ("lint-format", "dead-code", "whitespace-eof-imports"):
            assert category in text, category

    def test_ceilings_documented(self) -> None:
        text = _skill_text()
        assert "30" in text  # 30-min wall-clock
        assert "50" in text  # ~50 subagent turns
        assert "3" in text   # batch max 3 / file ceiling

    def test_state_under_etc_sdlc_janitor(self) -> None:
        assert ".etc_sdlc/janitor/" in _skill_text()


class TestTrustCommandSurfaceAC012:
    """AC-012: operator trust command surface (table + demote)."""

    def test_trust_table_command(self) -> None:
        assert "/janitor trust" in _skill_text()

    def test_trust_demote_command(self) -> None:
        assert "/janitor trust demote" in _skill_text()


class TestSingleSourceBoundaryAC013:
    """AC-013: single source of truth for the boundary standard."""

    def test_references_boundary_standard(self) -> None:
        assert "standards/process/janitor-write-boundary.md" in _skill_text()


class TestNoForbiddenStrings:
    """Static scan (AC-010): the skill never instructs an unsafe primitive in a
    way that would push, bypass hooks, or disable the sandbox."""

    def test_no_no_verify_as_instruction(self) -> None:
        # --no-verify only appears in a prohibition context, never as a command.
        text = _skill_text()
        for line in text.splitlines():
            if "--no-verify" in line:
                low = line.lower()
                assert (
                    "never" in low
                    or "not" in low
                    or "must not" in low
                    or "prohibit" in low
                    or "no " in low
                )

    def test_no_disable_sandbox_as_instruction(self) -> None:
        text = _skill_text()
        for line in text.splitlines():
            if "dangerouslyDisableSandbox" in line:
                low = line.lower()
                assert "never" in low or "not" in low or "prohibit" in low
