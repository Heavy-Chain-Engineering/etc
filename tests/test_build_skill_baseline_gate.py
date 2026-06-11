"""Contract tests for the /build three-state baseline gate + wave-gate wiring.

Two consumer surfaces are wired into skills/build/SKILL.md by this feature
(F-2026-06-10-brownfield-architecture-baseline, task 010):

1. **Step 1d** — a Step 1c-sibling gate that branches on the
   ``baseline.py status`` stdout TOKEN (``missing`` | ``unratified`` |
   ``ratified`` | ``malformed``), mirroring Step 1c's soft/hard/IO-error
   three-branch shape. ``missing`` emits an EXACT verbatim soft warning and
   PROCEEDS; ``unratified`` and ``malformed`` STOP; ``ratified`` proceeds. A
   ``baseline_exempt`` declaration with a recorded reason takes the soft path
   with the reason quoted (audited bypass).

2. **Step 6c-baseline** — baseline-verify joins the per-wave gate sequence
   AFTER 6c-runtime (mirroring runtime-verify's 6c-runtime block): the
   conductor pipes JSON to ``hooks/baseline-verify.sh``, reads the aggregated
   results, and treats any ``fail`` as a wave failure — verdicts come from the
   results JSON, NEVER the dispatcher's exit code (the dispatcher always
   exits 0). Skip-silently when no baseline exists or no mechanizable rules.

Grep-based, consistent with the other ``*_skill*`` / ``*_md_*`` contract
tests in the suite. The deviation rationale (hard-block scoped to
recorded-intent states) is ADR-002.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_SKILL_PATH = REPO_ROOT / "skills" / "build" / "SKILL.md"

# The exact soft-warning string the missing-baseline branch must emit. The
# contract greps for it VERBATIM — do not paraphrase, reflow, or mutate it in
# the skill body (mirrors Step 1c's verbatim-warning discipline).
SOFT_WARNING = (
    "WARNING: no architecture baseline found for this brownfield repo. "
    "Consider /init-project --phase=baseline to discover, verify, and ratify "
    "the repo's architectural patterns. Proceeding without baseline conformance."
)


def _read_build_skill() -> str:
    assert BUILD_SKILL_PATH.exists(), f"Build skill not found: {BUILD_SKILL_PATH}"
    return BUILD_SKILL_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC-1: Step 1d three-state baseline gate                                      #
# --------------------------------------------------------------------------- #


def test_should_add_step_1d_baseline_gate_when_skill_is_read() -> None:
    """A Step 1d heading must exist as the Step 1c sibling gate."""
    # Arrange
    content = _read_build_skill()

    # Act / Assert
    assert "Step 1d:" in content, (
        "skills/build/SKILL.md is missing the Step 1d baseline gate "
        "(the Step 1c-sibling three-state gate)."
    )


def test_should_invoke_baseline_status_token_when_gate_runs() -> None:
    """Step 1d must call baseline.py status with the ~/.claude prefix."""
    # Arrange
    content = _read_build_skill()

    # Act / Assert — Codex path-rewrite depends on the ~/.claude prefix verbatim.
    assert "python3 ~/.claude/scripts/baseline.py status" in content, (
        "Step 1d must invoke `python3 ~/.claude/scripts/baseline.py status "
        '"$REPO_ROOT"` to obtain the status token.'
    )


def test_should_branch_on_token_not_exit_code_when_gate_runs() -> None:
    """The gate must document branching on the TOKEN, never the exit code."""
    # Arrange
    content = _read_build_skill()

    # Act / Assert — phrasing is case-insensitive; the intent is what matters.
    assert "branch on the token" in content.lower(), (
        "Step 1d must state it branches on the status TOKEN, never the exit "
        "code (the baseline.py status contract)."
    )


def test_should_emit_exact_soft_warning_when_baseline_missing() -> None:
    """The missing branch must carry the EXACT verbatim soft-warning string."""
    # Arrange
    content = _read_build_skill()

    # Act / Assert
    assert SOFT_WARNING in content, (
        "Step 1d's `missing` branch must emit the EXACT verbatim soft warning "
        f"string. Expected verbatim:\n{SOFT_WARNING}"
    )


def test_should_name_init_project_baseline_phase_in_soft_warning() -> None:
    """The soft warning must name the backfill resume path."""
    # Arrange
    content = _read_build_skill()

    # Act / Assert
    assert "/init-project --phase=baseline" in content, (
        "Step 1d must name `/init-project --phase=baseline` as the backfill "
        "offer in the missing-baseline soft warning."
    )


def test_should_proceed_on_missing_baseline_when_legacy_repo() -> None:
    """The missing branch is forward-only: it must PROCEED, never block."""
    # Arrange
    content = _read_build_skill()
    step_1d = _slice_step(content, "Step 1d:", "### Step 2:")

    # Act / Assert — the missing branch must say PROCEED (legacy repos never blocked).
    assert "PROCEED" in step_1d, (
        "Step 1d's `missing` branch must PROCEED (forward-only: a legacy repo "
        "with no baseline is never blocked)."
    )


def test_should_stop_with_ratify_command_when_unratified() -> None:
    """The unratified branch must STOP and name the ratify command."""
    # Arrange
    content = _read_build_skill()
    step_1d = _slice_step(content, "Step 1d:", "### Step 2:")

    # Act / Assert
    assert "baseline.py ratify" in step_1d, (
        "Step 1d's `unratified` branch must name the `baseline.py ratify` "
        "resume command in its STOP message."
    )


def test_should_cite_adr_002_recorded_intent_when_unratified() -> None:
    """The unratified STOP must state it is a recorded-intent hard block per ADR-002."""
    # Arrange
    content = _read_build_skill()
    step_1d = _slice_step(content, "Step 1d:", "### Step 2:")

    # Act / Assert
    assert "recorded-intent" in step_1d and "ADR-002" in step_1d, (
        "Step 1d's `unratified` STOP must state it is a recorded-intent hard "
        "block per ADR-002 (the scoped advisory-default deviation)."
    )


def test_should_stop_as_infrastructure_failure_when_malformed() -> None:
    """The malformed branch must STOP as an infrastructure failure."""
    # Arrange
    content = _read_build_skill()
    step_1d = _slice_step(content, "Step 1d:", "### Step 2:")

    # Act / Assert
    assert "malformed" in step_1d and "infrastructure failure" in step_1d, (
        "Step 1d's `malformed` branch must STOP as an infrastructure failure "
        "(a corrupt ratification record is never treated as ratified)."
    )


def test_should_treat_exit_1_as_infrastructure_stop_when_io_error() -> None:
    """An exit-1 (IO error) from baseline.py status must route to the STOP branch."""
    # Arrange
    content = _read_build_skill()
    step_1d = _slice_step(content, "Step 1d:", "### Step 2:")

    # Act / Assert — exit 1 is the IO-error sibling of the malformed STOP.
    assert "exit 1" in step_1d, (
        "Step 1d must treat a `baseline.py status` exit 1 (IO error) as the "
        "infrastructure-failure STOP branch (distinct from the evaluable token)."
    )


def test_should_have_all_four_status_tokens_when_gate_branches() -> None:
    """The gate must enumerate all four status tokens explicitly."""
    # Arrange
    content = _read_build_skill()
    step_1d = _slice_step(content, "Step 1d:", "### Step 2:")

    # Act
    tokens = ["missing", "unratified", "ratified", "malformed"]

    # Assert — the four-token closed set must be present, all spelled out.
    missing_tokens = [t for t in tokens if t not in step_1d]
    assert missing_tokens == [], (
        f"Step 1d must branch on all four status tokens; missing: {missing_tokens}"
    )


def test_should_bypass_via_baseline_exempt_reason_with_audit() -> None:
    """A non-empty baseline_exempt reason must take the soft path, quoting the reason."""
    # Arrange
    content = _read_build_skill()
    step_1d = _slice_step(content, "Step 1d:", "### Step 2:")

    # Act / Assert — the exempt hatch is an audited bypass: reason quoted, soft path.
    assert "baseline_exempt" in step_1d, (
        "Step 1d must honor the `baseline_exempt` hatch (a recorded non-empty "
        "reason takes the soft path with the reason quoted — an audited bypass)."
    )


# --------------------------------------------------------------------------- #
# AC-2: Step 6c-baseline wave-gate wiring                                      #
# --------------------------------------------------------------------------- #


def test_should_add_6c_baseline_block_when_skill_is_read() -> None:
    """A 6c-baseline block must exist as the wave-gate sibling of 6c-runtime."""
    # Arrange
    content = _read_build_skill()

    # Act / Assert
    assert "6c-baseline" in content, (
        "skills/build/SKILL.md is missing the 6c-baseline wave-gate block "
        "(the baseline-verify sibling of 6c-runtime)."
    )


def test_should_place_baseline_block_after_runtime_in_wave_sequence() -> None:
    """6c-baseline must appear AFTER 6c-runtime and BEFORE the 6d done tags."""
    # Arrange
    content = _read_build_skill()

    # Act
    idx_runtime = content.find("6c-runtime.")
    idx_baseline = content.find("6c-baseline.")
    idx_6d = content.find("**6d.")

    # Assert — ordering: runtime block, then baseline block, then 6d done tags.
    assert idx_runtime != -1 and idx_baseline != -1 and idx_6d != -1, (
        "Expected 6c-runtime, 6c-baseline, and 6d markers all present."
    )
    assert idx_runtime < idx_baseline < idx_6d, (
        "6c-baseline must sit AFTER 6c-runtime and BEFORE 6d (the done tags) "
        "in the wave-gate sequence."
    )


def test_should_pipe_json_contract_to_baseline_verify_dispatcher() -> None:
    """The conductor must pipe the {repo_root, rule_ids, cwd} JSON to the hook."""
    # Arrange
    content = _read_build_skill()
    block = _slice_step(content, "6c-baseline.", "**6d.")

    # Act / Assert — the documented dispatcher contract, invoked via stdin JSON.
    assert "bash hooks/baseline-verify.sh" in block, (
        "Step 6c-baseline must invoke `bash hooks/baseline-verify.sh` with the "
        "JSON contract piped on stdin."
    )
    for field in ("repo_root", "rule_ids", "cwd"):
        assert field in block, (
            f"Step 6c-baseline's stdin JSON must carry the `{field}` field "
            "(the {repo_root, rule_ids, cwd} dispatcher contract)."
        )


def test_should_pass_null_rule_ids_for_all_mechanizable_rules() -> None:
    """rule_ids must be null in the wave-gate call (all mechanizable rules)."""
    # Arrange
    content = _read_build_skill()
    block = _slice_step(content, "6c-baseline.", "**6d.")

    # Act / Assert
    assert "null" in block, (
        "Step 6c-baseline must pass `rule_ids: null` (all mechanizable rules) "
        "in the dispatcher JSON."
    )


def test_should_read_verdicts_from_json_never_exit_code() -> None:
    """The gate must read verdicts from the results JSON, never the exit code."""
    # Arrange
    content = _read_build_skill()
    block = _slice_step(content, "6c-baseline.", "**6d.")

    # Act / Assert — the dispatcher always exits 0; verdicts live in JSON.
    assert "exit code" in block and "JSON" in block, (
        "Step 6c-baseline must state verdicts come from the results JSON, "
        "never the dispatcher exit code (the dispatcher always exits 0)."
    )


def test_should_fail_wave_on_any_baseline_fail_verdict() -> None:
    """Any `fail` result must fail the wave (zero-tolerance, mirrors verify-green)."""
    # Arrange
    content = _read_build_skill()
    block = _slice_step(content, "6c-baseline.", "**6d.")

    # Act / Assert
    assert "fail" in block and "wave" in block, (
        "Step 6c-baseline must treat any `fail` result as a wave failure "
        "(zero-tolerance close, mirroring verify-green)."
    )


def test_should_not_write_done_tag_on_baseline_failure() -> None:
    """A baseline failure must withhold the phase-N/done tag (wave-failure shape)."""
    # Arrange
    content = _read_build_skill()
    block = _slice_step(content, "6c-baseline.", "**6d.")

    # Act / Assert
    assert "done" in block and "tag" in block, (
        "Step 6c-baseline must withhold the `phase-N/done` tag on a baseline "
        "failure (the existing 6c wave-failure shape)."
    )


def test_should_skip_silently_when_no_baseline_or_no_rules() -> None:
    """Skip-silently when no baseline exists or no mechanizable rules."""
    # Arrange
    content = _read_build_skill()
    block = _slice_step(content, "6c-baseline.", "**6d.")

    # Act / Assert
    assert "skip" in block.lower(), (
        "Step 6c-baseline must skip-silently when no baseline exists or there "
        "are no mechanizable rules (warn-and-skip parity with verify-green)."
    )


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #


def _slice_step(content: str, start_marker: str, end_marker: str) -> str:
    """Return the SKILL.md substring between two markers (start inclusive).

    Scopes a grep assertion to exactly one step block so a string appearing
    elsewhere in the 2000+-line skill cannot satisfy the assertion by accident.
    """
    start = content.find(start_marker)
    assert start != -1, f"marker not found in build skill: {start_marker!r}"
    end = content.find(end_marker, start)
    if end == -1:
        end = len(content)
    return content[start:end]
