"""Tests for ``scripts/dispatch_prompt.py`` (Ftmp-19e49f7c — F-2026-05-23).

Covers AC-001..AC-009 + AC-012 of the Dispatch Prompt Assembler PRD plus
EC-001..EC-008 edge cases. Snapshot tests reference the F023 shipped
feature dir + the captured dispatch examples at
``.etc_sdlc/incidents/2026-05-22-dispatch-examples/``.

The assembler mechanizes ``standards/process/subagent-dispatch.md`` eight
required sections. Per spec BR-013 it is forward-only — existing F001-F024
dispatches are not retro-rewritten.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import dispatch_prompt  # noqa: E402

_SCRIPT_PATH = _REPO_ROOT / "scripts" / "dispatch_prompt.py"

_F023_SHIPPED = (
    _REPO_ROOT
    / ".etc_sdlc"
    / "features"
    / "shipped"
    / "F023-distributed-id-allocation-discipline"
)


# ── Synthetic-feature fixture builders ───────────────────────────────────


def _write_feature(
    root: Path,
    *,
    feature_id: str = "F999",
    summary_paragraph: str = "Test feature summary first paragraph.",
    summary_section: bool = True,
    summary_empty: bool = False,
    state_yaml_present: bool = True,
    state_yaml_extra: dict | None = None,
    tasks: list[dict] | None = None,
    task_yaml_malformed: bool = False,
    write_task_files: bool = True,
) -> Path:
    """Create a synthetic feature directory at ``root`` with spec/state/tasks.

    Returns the feature directory path. Behavior switches are wired to
    cover the edge cases in spec.md EC-001..EC-008.
    """
    feature_dir = root / f"{feature_id}-fixture"
    feature_dir.mkdir(parents=True, exist_ok=True)

    # spec.md
    if summary_section:
        if summary_empty:
            spec_text = "# PRD: Fixture\n\n## Summary\n\n## Scope\n\nbody.\n"
        else:
            spec_text = (
                f"# PRD: Fixture\n\n## Summary\n\n{summary_paragraph}\n\n"
                "Second paragraph that should NOT be included.\n\n"
                "## Scope\n\nbody.\n"
            )
    else:
        spec_text = "# PRD: Fixture\n\n## Scope\n\nno summary section here.\n"
    (feature_dir / "spec.md").write_text(spec_text)

    # state.yaml
    if state_yaml_present:
        state: dict = {
            "build": {"feature": feature_id},
            "feature_id": feature_id,
        }
        if state_yaml_extra is not None:
            state.update(state_yaml_extra)
        (feature_dir / "state.yaml").write_text(
            yaml.safe_dump(state, sort_keys=False)
        )

    # tasks/
    tasks_dir = feature_dir / "tasks"
    if write_task_files:
        tasks_dir.mkdir(exist_ok=True)
        for entry in tasks or []:
            task_id = entry["task_id"]
            slug = entry.get("slug", "fixture-task")
            path = tasks_dir / f"{task_id}-{slug}.yaml"
            if task_yaml_malformed and entry.get("malformed"):
                path.write_text("intent: [unbalanced\n  - bad\n")
            else:
                path.write_text(yaml.safe_dump(entry["yaml"], sort_keys=False))

    return feature_dir


def _default_task(task_id: str = "001", **overrides) -> dict:
    """Default well-formed task YAML payload (assembler-acceptable)."""
    base = {
        "task_id": task_id,
        "title": "fixture task",
        "assigned_agent": "backend-developer",
        "status": "in_progress",
        "requires_reading": [
            "standards/process/subagent-dispatch.md",
            "scripts/feature_id.py",
        ],
        "files_in_scope": [
            "scripts/fixture.py",
            "tests/test_fixture.py",
        ],
        "acceptance_criteria": [
            "AC-001: fixture AC one",
            "AC-002: fixture AC two",
        ],
        "dependencies": [],
    }
    base.update(overrides)
    return base


# ── AC-006: argument parsing / usage errors ──────────────────────────────


class TestCliArgumentValidation:
    """``argparse`` rejects missing arguments with exit code 2 + usage."""

    def test_should_exit_2_when_feature_path_missing(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "assemble", "--task-id", "001"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 2, (
            f"expected exit 2, got {result.returncode}; stderr={result.stderr!r}"
        )
        assert "--feature-path" in result.stderr

    def test_should_exit_2_when_task_id_missing(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                "/tmp/nope",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 2
        assert "--task-id" in result.stderr


# ── AC-007: non-existent feature path ────────────────────────────────────


class TestFeaturePathValidation:
    def test_should_exit_1_when_feature_path_does_not_exist(
        self, tmp_path: Path
    ) -> None:
        bogus = tmp_path / "no-such-feature"

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                str(bogus),
                "--task-id",
                "001",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1
        assert "does not exist" in result.stderr
        assert str(bogus) in result.stderr


# ── AC-008: task glob ambiguity / no match ───────────────────────────────


class TestTaskGlobMatching:
    def test_should_exit_1_when_task_id_matches_zero_files(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(tmp_path, tasks=[])

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "999",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1
        assert "no task YAML matching id 999" in result.stderr

    def test_should_exit_1_when_task_id_matches_multiple_files(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            tasks=[
                {
                    "task_id": "001",
                    "slug": "alpha",
                    "yaml": _default_task("001"),
                },
                {
                    "task_id": "001",
                    "slug": "beta",
                    "yaml": _default_task("001"),
                },
            ],
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "001",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1
        assert "ambiguous task-id 001" in result.stderr
        assert "matched 2 task YAMLs" in result.stderr


# ── EC-001/EC-002: missing or empty Summary section ──────────────────────


class TestSpecSummaryExtraction:
    def test_should_exit_1_when_spec_lacks_summary_section(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            summary_section=False,
            tasks=[{"task_id": "001", "yaml": _default_task("001")}],
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "001",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1
        assert "missing required ## Summary section" in result.stderr

    def test_should_exit_1_when_summary_section_is_empty(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            summary_empty=True,
            tasks=[{"task_id": "001", "yaml": _default_task("001")}],
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "001",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1
        assert "Summary section is empty" in result.stderr


# ── EC-003: malformed task YAML ──────────────────────────────────────────


class TestMalformedTaskYaml:
    def test_should_exit_1_when_task_yaml_is_malformed(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            tasks=[
                {
                    "task_id": "001",
                    "yaml": {},
                    "malformed": True,
                }
            ],
            task_yaml_malformed=True,
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "001",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1
        assert "failed to parse" in result.stderr


# ── EC-004: task YAML lacks acceptance_criteria field ────────────────────


class TestTaskYamlMissingAcs:
    def test_should_exit_1_when_task_yaml_missing_acceptance_criteria(
        self, tmp_path: Path
    ) -> None:
        broken = _default_task("001")
        del broken["acceptance_criteria"]
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": broken}]
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "001",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1
        assert "missing required field acceptance_criteria" in result.stderr


# ── EC-005: state.yaml absent ────────────────────────────────────────────


class TestStateYamlAbsent:
    def test_should_exit_1_when_state_yaml_absent(self, tmp_path: Path) -> None:
        feature_dir = _write_feature(
            tmp_path,
            state_yaml_present=False,
            tasks=[{"task_id": "001", "yaml": _default_task("001")}],
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "001",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 1
        assert "state.yaml does not exist" in result.stderr
        assert "has not been allocated" in result.stderr


# ── AC-002 + AC-003: section presence / task-intent omission ─────────────


class TestSectionAssembly:
    def test_should_include_all_eight_sections_when_task_has_intent(
        self, tmp_path: Path
    ) -> None:
        task = _default_task("001")
        task["intent"] = "This task wires a fixture for the assembler test."
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": task}]
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert "**Feature intent (F999):**" in prompt
        assert "**Task intent:**" in prompt
        assert "**Task YAML:**" in prompt
        assert "**Required reading" in prompt
        assert "**Files in scope:**" in prompt
        assert "**Acceptance criteria" in prompt
        assert "**Cross-task awareness:**" in prompt
        assert "Report back with:" in prompt

    def test_should_omit_task_intent_section_when_intent_absent(
        self, tmp_path: Path
    ) -> None:
        task = _default_task("001")  # no intent field
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": task}]
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert "**Task intent:**" not in prompt
        # Should still have task-yaml + acceptance + report-back sections.
        assert "**Task YAML:**" in prompt
        assert "**Acceptance criteria" in prompt


# ── AC-004 / AC-005 / EC-006: wiring-contract conditional ────────────────


class TestWiringContractClause:
    def test_should_include_wiring_contract_when_user_flow_ac_present(
        self, tmp_path: Path
    ) -> None:
        task = _default_task("001")
        task["acceptance_criteria"] = [
            "AC-001: As an operator, navigate from /home via Sidebar, "
            "complete profile, observe Account page.",
        ]
        task["files_in_scope"] = [
            "src/pages/Account.tsx",
            "src/pages/SidebarConfig.ts",  # parent-wire file
        ]
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": task}]
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert "## Wiring contract (user-facing surface)" in prompt
        # Verbatim clause body fragment from SKILL.md line 1110.
        assert (
            "Your task creates a user-facing surface" in prompt
        ), "wiring-contract clause body not appended verbatim"
        # Parent path substituted.
        assert "src/pages/SidebarConfig.ts" in prompt

    def test_should_omit_wiring_contract_when_no_user_flow_ac(
        self, tmp_path: Path
    ) -> None:
        task = _default_task("001")
        task["acceptance_criteria"] = [
            "AC-001: backend-only — returns 200 on POST.",
            "AC-002: backend-only — emits structured log.",
        ]
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": task}]
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert "## Wiring contract" not in prompt

    def test_should_render_deferred_placeholder_when_user_flow_lacks_parent(
        self, tmp_path: Path
    ) -> None:
        # EC-006: User-flow AC present but no parent wiring file in scope.
        task = _default_task("001")
        task["acceptance_criteria"] = [
            "AC-001: As an admin, navigate from /admin via Top-nav, "
            "open audit log, observe entries.",
        ]
        # Only one file — the target itself; no parent wire entry.
        task["files_in_scope"] = ["src/pages/AuditLog.tsx"]
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": task}]
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert "## Wiring contract" in prompt
        assert (
            "(deferred — no parent file in scope; escalate if you "
            "discover the surface needs to be wired)" in prompt
        )


# ── EC-007: empty/absent requires_reading emits "(none)" ─────────────────


class TestRequiresReadingNone:
    def test_should_emit_none_when_requires_reading_absent(
        self, tmp_path: Path
    ) -> None:
        task = _default_task("001")
        del task["requires_reading"]
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": task}]
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert "**Required reading" in prompt
        assert "(none)" in prompt

    def test_should_emit_none_when_requires_reading_empty(
        self, tmp_path: Path
    ) -> None:
        task = _default_task("001", requires_reading=[])
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": task}]
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert "**Required reading" in prompt
        assert "(none)" in prompt


# ── AC-009 + EC-008: token-budget warning ────────────────────────────────


def _large_ac_task() -> dict:
    """Task carrying enough ACs to push the prompt past 1000 tokens (~4000 chars)."""
    big_ac = "X" * 400
    return _default_task(
        "001",
        acceptance_criteria=[f"AC-{i:03d}: {big_ac}" for i in range(1, 16)],
    )


class TestTokenBudgetWarning:
    def test_should_emit_warning_to_stderr_when_prompt_exceeds_1000_tokens(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": _large_ac_task()}]
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "001",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0, result.stderr
        assert (
            "WARNING: assembled dispatch prompt" in result.stderr
            and "tokens exceeds 1000-token target" in result.stderr
        )
        # AC-009: stdout unaffected — must still contain the eight sections.
        assert "**Feature intent" in result.stdout
        assert "Report back with:" in result.stdout

    def test_should_not_emit_warning_when_prompt_within_budget(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            tasks=[{"task_id": "001", "yaml": _default_task("001")}],
        )

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "001",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "WARNING" not in result.stderr

    def test_should_not_emit_warning_when_token_count_equals_1000(self) -> None:
        # EC-008: strict greater-than per BR-010. Direct call to the helper.
        # 4000 chars => 1000 tokens exactly.
        prompt = "x" * 4000
        emitted = dispatch_prompt.maybe_emit_token_warning(prompt)

        assert emitted is False

    def test_should_emit_warning_when_token_count_exceeds_1000(self) -> None:
        prompt = "x" * 4004  # 1001 tokens
        emitted = dispatch_prompt.maybe_emit_token_warning(prompt)

        assert emitted is True


# ── BR-008: report-back format is verbatim with placeholders preserved ───


class TestReportBackFormat:
    def test_should_preserve_angle_bracket_placeholders_verbatim(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            tasks=[{"task_id": "001", "yaml": _default_task("001")}],
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert "<pytest/verify output>" in prompt
        assert "<key artifact path or diff>" in prompt
        assert "<one architectural decision you made beyond the spec>" in prompt
        assert "<any gaps>" in prompt


# ── BR-002: feature_id resolution priority ───────────────────────────────


class TestFeatureIdResolution:
    def test_should_prefer_build_feature_field_when_present(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            feature_id="F042",
            state_yaml_extra={"build": {"feature": "F042"}},
            tasks=[{"task_id": "001", "yaml": _default_task("001")}],
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert "**Feature intent (F042):**" in prompt

    def test_should_fall_back_to_directory_basename_when_no_id_field(
        self, tmp_path: Path
    ) -> None:
        # state.yaml has neither build.feature nor feature_id top-level.
        feature_dir = tmp_path / "F-2026-05-23-no-id-fixture"
        feature_dir.mkdir()
        (feature_dir / "spec.md").write_text(
            "# PRD\n\n## Summary\n\nFirst paragraph here.\n\n## Scope\n"
        )
        (feature_dir / "state.yaml").write_text(
            yaml.safe_dump({"unrelated": "field"})
        )
        tasks_dir = feature_dir / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "001-fixture.yaml").write_text(
            yaml.safe_dump(_default_task("001"))
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        # Directory basename used verbatim as the feature ID.
        assert "**Feature intent (F-2026-05-23-no-id-fixture):**" in prompt


# ── BR-007: cross-task awareness ─────────────────────────────────────────


class TestCrossTaskAwareness:
    def test_should_emit_fallback_line_when_no_wave_plan_in_state(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            tasks=[
                {"task_id": "001", "yaml": _default_task("001")},
                {"task_id": "002", "yaml": _default_task("002")},
            ],
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert (
            "(wave plan not yet computed; assume serial execution within feature)"
            in prompt
        )

    def test_should_enumerate_sibling_tasks_when_wave_plan_present(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            state_yaml_extra={
                "build": {
                    "feature": "F999",
                    "wave_plan": [
                        {
                            "wave": 0,
                            "tasks": ["001", "002", "003"],
                        },
                        {"wave": 1, "tasks": ["004"]},
                    ],
                }
            },
            tasks=[
                {"task_id": "001", "yaml": _default_task("001")},
                {
                    "task_id": "002",
                    "yaml": _default_task(
                        "002", title="docs: ADR for fixture decision"
                    ),
                },
                {
                    "task_id": "003",
                    "yaml": _default_task(
                        "003", title="tests: integration for fixture"
                    ),
                },
                {"task_id": "004", "yaml": _default_task("004")},
            ],
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        # Sibling task IDs and titles appear; target's own ID does NOT.
        assert "002" in prompt
        assert "003" in prompt
        assert "ADR for fixture decision" in prompt
        # Task 004 is in a different wave — must NOT be listed as a sibling.
        # The split between sibling and out-of-wave is best validated by
        # checking the wave-zero sibling lines explicitly.
        cross_task_section = prompt.split("**Cross-task awareness:**", 1)[1]
        cross_task_section = cross_task_section.split("Report back with:", 1)[0]
        assert "002" in cross_task_section
        assert "003" in cross_task_section
        assert "004" not in cross_task_section


# ── AC-002: snapshot against F023 task 001 ───────────────────────────────


@pytest.mark.skipif(
    not _F023_SHIPPED.is_dir(),
    reason="F023 shipped feature dir not present in this checkout",
)
class TestSnapshotF023Task001:
    def test_should_emit_eight_sections_and_f023_summary_intent(self) -> None:
        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=_F023_SHIPPED, task_id="001"
        )

        # Feature ID lifted from state.yaml id_history (final form) OR
        # build.feature OR directory basename — F023's state has the
        # build.feature = distributed-id-allocation-discipline; the
        # directory basename is F023-...; the resolver picks the
        # configured value. We only assert the eight-section presence
        # here; the exact ID rendering is covered in
        # TestFeatureIdResolution above.
        assert "**Feature intent" in prompt
        assert "**Task YAML:**" in prompt
        assert "**Required reading" in prompt
        assert "**Files in scope:**" in prompt
        assert "**Acceptance criteria" in prompt
        assert "**Cross-task awareness:**" in prompt
        assert "Report back with:" in prompt

        # Feature-intent paragraph is the first paragraph of F023's
        # Summary — a single contiguous block. Verify a fingerprint.
        assert (
            "Today `scripts/feature_id.py allocate-next`" in prompt
        ), "F023 Summary first paragraph fingerprint not found in prompt"

    def test_should_omit_legacy_tdd_reminder_line(self) -> None:
        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=_F023_SHIPPED, task_id="001"
        )

        # Anti-pattern #4 — must NEVER appear in any assembled dispatch.
        assert (
            "Dispatch hooks will enforce TDD" not in prompt
        ), "assembler MUST omit the legacy TDD-reminder line"


# ── AC-001: snapshot against F023 task 003 (matches captured example) ────


@pytest.mark.skipif(
    not _F023_SHIPPED.is_dir(),
    reason="F023 shipped feature dir not present in this checkout",
)
class TestSnapshotF023Task003:
    def test_should_emit_eight_sections_for_simple_adr_task(self) -> None:
        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=_F023_SHIPPED, task_id="003"
        )

        # The captured example at example-2-technical-writer-simple-adr.md
        # shows 6 of the 8 sections (older, hand-written prose). The
        # assembler MUST emit all 8 regardless, with feature-intent +
        # cross-task awareness added.
        assert "**Feature intent" in prompt
        assert "**Task YAML:**" in prompt
        assert "**Required reading" in prompt
        assert "**Files in scope:**" in prompt
        assert "**Acceptance criteria" in prompt
        assert "**Cross-task awareness:**" in prompt
        assert "Report back with:" in prompt
        # No legacy TDD reminder.
        assert "Dispatch hooks will enforce TDD" not in prompt


# ── In-process CLI tests (drive coverage on main/_cmd_assemble) ──────────


class TestCliInProcess:
    """Direct ``main()`` invocations to exercise CLI branches in-process."""

    def test_should_return_0_and_write_prompt_to_stdout_when_valid(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": _default_task("001")}]
        )

        exit_code = dispatch_prompt.main(
            [
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "001",
            ]
        )
        captured = capsys.readouterr()

        assert exit_code == 0
        assert "**Feature intent" in captured.out
        assert "WARNING" not in captured.err

    def test_should_return_1_and_write_error_to_stderr_when_path_missing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bogus = tmp_path / "no-such-feature"

        exit_code = dispatch_prompt.main(
            [
                "assemble",
                "--feature-path",
                str(bogus),
                "--task-id",
                "001",
            ]
        )
        captured = capsys.readouterr()

        assert exit_code == 1
        assert "error:" in captured.err
        assert "does not exist" in captured.err

    def test_should_return_0_and_warn_when_prompt_exceeds_budget(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": _large_ac_task()}]
        )

        exit_code = dispatch_prompt.main(
            [
                "assemble",
                "--feature-path",
                str(feature_dir),
                "--task-id",
                "001",
            ]
        )
        captured = capsys.readouterr()

        assert exit_code == 0
        assert "WARNING: assembled dispatch prompt" in captured.err
        assert "**Feature intent" in captured.out


# ── Internals: defensive-branch coverage ─────────────────────────────────


class TestAssemblerInternals:
    """Direct unit tests on internals — defensive branches the e2e tests skip."""

    def test_should_exit_1_when_spec_md_absent(self, tmp_path: Path) -> None:
        # spec.md absent but state.yaml + task YAML present.
        feature_dir = tmp_path / "F999-no-spec"
        feature_dir.mkdir()
        (feature_dir / "state.yaml").write_text(
            yaml.safe_dump({"feature_id": "F999"})
        )
        tasks_dir = feature_dir / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "001-fixture.yaml").write_text(
            yaml.safe_dump(_default_task("001"))
        )

        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=feature_dir, task_id="001"
            )

        assert "spec.md" in str(exc.value)
        assert "does not exist" in str(exc.value)

    def test_should_exit_1_when_tasks_dir_absent(self, tmp_path: Path) -> None:
        # state.yaml + spec.md present but no tasks/ subdir.
        feature_dir = tmp_path / "F999-no-tasks"
        feature_dir.mkdir()
        (feature_dir / "spec.md").write_text(
            "# PRD\n\n## Summary\n\nbody.\n"
        )
        (feature_dir / "state.yaml").write_text(
            yaml.safe_dump({"feature_id": "F999"})
        )

        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=feature_dir, task_id="001"
            )

        assert "no task YAML matching id 001" in str(exc.value)

    def test_should_treat_non_dict_state_yaml_as_empty(
        self, tmp_path: Path
    ) -> None:
        # state.yaml is valid YAML but parses to a list (not a dict).
        feature_dir = tmp_path / "F999-listy-state"
        feature_dir.mkdir()
        (feature_dir / "spec.md").write_text(
            "# PRD\n\n## Summary\n\nbody paragraph.\n"
        )
        (feature_dir / "state.yaml").write_text("- one\n- two\n")
        tasks_dir = feature_dir / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "001-fixture.yaml").write_text(
            yaml.safe_dump(_default_task("001"))
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        # Falls through to directory basename (BR-002 step 3).
        assert "**Feature intent (F999-listy-state):**" in prompt

    def test_should_exit_1_when_task_yaml_parses_to_list(
        self, tmp_path: Path
    ) -> None:
        # Task YAML is valid YAML but a list — not a mapping.
        feature_dir = tmp_path / "F999-bad-task-shape"
        feature_dir.mkdir()
        (feature_dir / "spec.md").write_text(
            "# PRD\n\n## Summary\n\nbody.\n"
        )
        (feature_dir / "state.yaml").write_text(
            yaml.safe_dump({"feature_id": "F999"})
        )
        tasks_dir = feature_dir / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "001-bad.yaml").write_text("- list\n- of\n- items\n")

        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=feature_dir, task_id="001"
            )

        assert "not a mapping" in str(exc.value)

    def test_should_render_dict_form_requires_reading_with_commentary(
        self,
    ) -> None:
        rendered = dispatch_prompt._render_reading_entry(
            1, {"path": "foo/bar.py", "why": "mirror this helper pattern"}
        )

        assert rendered == "1. foo/bar.py — mirror this helper pattern"

    def test_should_render_dict_form_requires_reading_without_commentary(
        self,
    ) -> None:
        rendered = dispatch_prompt._render_reading_entry(
            2, {"path": "scripts/feature_id.py"}
        )

        assert rendered == "2. scripts/feature_id.py"

    def test_should_render_files_in_scope_as_none_when_field_empty(
        self, tmp_path: Path
    ) -> None:
        task = _default_task("001", files_in_scope=[])
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": task}]
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        # Body shows ``(none)`` under the heading when no files.
        assert "**Files in scope:**\n(none)" in prompt

    def test_should_render_acceptance_criteria_as_none_when_list_empty(
        self,
    ) -> None:
        # Direct unit test on the renderer (the assembler-level call would
        # error if acceptance_criteria were absent; here the key exists
        # but the list is empty, which the spec leaves to the renderer).
        rendered = dispatch_prompt._render_acceptance_criteria(
            {"acceptance_criteria": []}
        )

        assert "(none)" in rendered
        assert "(0 ACs)" in rendered

    def test_should_render_no_sibling_line_when_target_alone_in_wave(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            state_yaml_extra={
                "build": {
                    "feature": "F999",
                    "wave_plan": [{"wave": 0, "tasks": ["001"]}],
                }
            },
            tasks=[{"task_id": "001", "yaml": _default_task("001")}],
        )

        prompt = dispatch_prompt.assemble_dispatch_prompt(
            feature_path=feature_dir, task_id="001"
        )

        assert "(no sibling tasks in this wave)" in prompt

    def test_should_return_empty_when_target_not_in_any_wave(self) -> None:
        # Direct unit test — task_id absent from every wave's tasks list.
        siblings = dispatch_prompt._siblings_in_same_wave(
            [{"wave": 0, "tasks": ["004", "005"]}], "001"
        )

        assert siblings == []

    def test_should_skip_non_dict_wave_entries(self) -> None:
        # Defensive: wave_plan list contains a non-dict element. Cast via
        # an explicit ``list[Any]`` to thread a polluted shape past the
        # type checker — runtime behavior under bad YAML is what we're
        # validating here.
        from typing import Any
        polluted_plan: list[Any] = [
            "not-a-dict",
            {"wave": 0, "tasks": ["001", "002"]},
        ]
        siblings = dispatch_prompt._siblings_in_same_wave(polluted_plan, "001")

        assert siblings == ["002"]

    def test_should_return_no_title_when_tasks_dir_missing(
        self, tmp_path: Path
    ) -> None:
        title = dispatch_prompt._read_one_title(tmp_path / "nope", "001")

        assert title == "(no title)"

    def test_should_return_no_title_when_sibling_yaml_missing(
        self, tmp_path: Path
    ) -> None:
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        title = dispatch_prompt._read_one_title(tasks_dir, "999")

        assert title == "(no title)"

    def test_should_return_no_title_when_sibling_yaml_malformed(
        self, tmp_path: Path
    ) -> None:
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "002-broken.yaml").write_text("intent: [unbalanced\n")

        title = dispatch_prompt._read_one_title(tasks_dir, "002")

        assert title == "(no title)"

    def test_should_return_no_title_when_sibling_yaml_is_list(
        self, tmp_path: Path
    ) -> None:
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "002-list.yaml").write_text("- one\n- two\n")

        title = dispatch_prompt._read_one_title(tasks_dir, "002")

        assert title == "(no title)"

    def test_should_return_no_title_when_title_field_absent(
        self, tmp_path: Path
    ) -> None:
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        (tasks_dir / "002-untitled.yaml").write_text(
            yaml.safe_dump({"task_id": "002", "status": "ready"})
        )

        title = dispatch_prompt._read_one_title(tasks_dir, "002")

        assert title == "(no title)"

    def test_should_skip_non_str_ac_entries_when_scanning_for_user_flow(
        self,
    ) -> None:
        # Defensive: a non-str AC entry should not crash the scanner.
        result = dispatch_prompt._has_user_flow_ac(
            [42, {"shape": "weird"}, "AC-001: backend only"]
        )

        assert result is False

    def test_should_return_last_entry_when_no_parent_marker_matches(
        self,
    ) -> None:
        # Two files, neither matches the sidebar/nav/router vocabulary.
        chosen = dispatch_prompt._identify_parent_wiring_file(
            ["src/pages/Foo.tsx", "src/pages/Bar.tsx"]
        )

        assert chosen == "src/pages/Bar.tsx"

    def test_should_coerce_non_str_to_empty(self) -> None:
        assert dispatch_prompt._coerce_str(None) == ""
        assert dispatch_prompt._coerce_str(42) == ""
        assert dispatch_prompt._coerce_str("  trimmed  ") == "trimmed"

    def test_should_raise_in_process_when_summary_missing(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            summary_section=False,
            tasks=[{"task_id": "001", "yaml": _default_task("001")}],
        )

        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=feature_dir, task_id="001"
            )

        assert "missing required ## Summary section" in str(exc.value)

    def test_should_raise_in_process_when_summary_empty(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            summary_empty=True,
            tasks=[{"task_id": "001", "yaml": _default_task("001")}],
        )

        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=feature_dir, task_id="001"
            )

        assert "Summary section is empty" in str(exc.value)

    def test_should_raise_in_process_when_state_yaml_absent(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            state_yaml_present=False,
            tasks=[{"task_id": "001", "yaml": _default_task("001")}],
        )

        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=feature_dir, task_id="001"
            )

        assert "state.yaml does not exist" in str(exc.value)

    def test_should_raise_in_process_when_no_task_yaml_match(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(tmp_path, tasks=[])

        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=feature_dir, task_id="999"
            )

        assert "no task YAML matching id 999" in str(exc.value)

    def test_should_raise_in_process_when_multiple_task_yaml_match(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            tasks=[
                {"task_id": "001", "slug": "alpha", "yaml": _default_task("001")},
                {"task_id": "001", "slug": "beta", "yaml": _default_task("001")},
            ],
        )

        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=feature_dir, task_id="001"
            )

        assert "ambiguous task-id 001" in str(exc.value)

    def test_should_raise_in_process_when_task_yaml_malformed(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _write_feature(
            tmp_path,
            tasks=[
                {"task_id": "001", "yaml": {}, "malformed": True},
            ],
            task_yaml_malformed=True,
        )

        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=feature_dir, task_id="001"
            )

        assert "failed to parse" in str(exc.value)

    def test_should_raise_in_process_when_task_yaml_missing_acs(
        self, tmp_path: Path
    ) -> None:
        broken = _default_task("001")
        del broken["acceptance_criteria"]
        feature_dir = _write_feature(
            tmp_path, tasks=[{"task_id": "001", "yaml": broken}]
        )

        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=feature_dir, task_id="001"
            )

        assert "missing required field acceptance_criteria" in str(exc.value)

    def test_should_raise_in_process_when_feature_path_missing(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(dispatch_prompt.DispatchAssemblyError) as exc:
            dispatch_prompt.assemble_dispatch_prompt(
                feature_path=tmp_path / "nope", task_id="001"
            )

        assert "does not exist" in str(exc.value)
