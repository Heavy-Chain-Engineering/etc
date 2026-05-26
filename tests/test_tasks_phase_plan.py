"""Tests for compute_phase_plan + the `phases` CLI in scripts/tasks.py.

Covers F-2026-05-26-phase-wave-decoupling AC-01..AC-06:
  - AC-01: flat task list → one phase whose waves equal compute_waves.
  - AC-02: decomposed list → one phase per top-level WBS group.
  - AC-03: cross-phase dependency orders the dependent phase later.
  - AC-04: every pending leaf task appears in exactly one (phase, wave) cell.
  - AC-05: compute_waves output is byte-identical for a fixed input
           (regression pin — BR-05).
  - AC-06: the `phases` CLI prints the ordered plan and exits 0.

`tasks.py` is a single-file CLI; pure functions are imported via importlib
(the module filename is a plain identifier, but it lives under scripts/ which
is not a package, so spec_from_file_location is the precedent — mirrors
tests/test_compile_metrics.py).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

TASKS_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "tasks.py"


def _load_tasks_module() -> ModuleType:
    """Import scripts/tasks.py as a module for direct function access.

    The module is registered in ``sys.modules`` BEFORE ``exec_module`` so
    dataclasses can resolve their own ``__module__`` namespace (needed by
    ``field(default_factory=...)`` under ``from __future__ import
    annotations``).
    """
    spec = importlib.util.spec_from_file_location("tasks_under_test", TASKS_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _task(
    task_id: str,
    *,
    parent: str | None = None,
    status: str = "pending",
    deps: list[str] | None = None,
) -> dict[str, object]:
    """Build a minimal task dict mirroring the loaded-YAML shape."""
    task: dict[str, object] = {
        "task_id": task_id,
        "title": f"task {task_id}",
        "assigned_agent": "backend-developer",
        "status": status,
        "files_in_scope": [f"src/{task_id}.py"],
        "acceptance_criteria": ["tests pass"],
        "dependencies": deps or [],
    }
    if parent is not None:
        task["parent_task"] = parent
    return task


def _run_tasks(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(TASKS_SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=10,
    )


def _phase_task_ids(phase: object) -> list[str]:
    """Flatten one phase's waves into an ordered list of task_ids."""
    ids: list[str] = []
    for wave in phase.waves:  # type: ignore[attr-defined]
        ids.extend(wave.task_ids)
    return ids


# ── AC-01: flat fallback ────────────────────────────────────────────────


class TestFlatFallback:
    def test_should_produce_one_phase_when_all_tasks_are_depth_one_leaves(
        self,
    ) -> None:
        tasks_module = _load_tasks_module()
        tasks = [_task("001"), _task("002"), _task("003")]

        plan = tasks_module.compute_phase_plan(tasks)

        assert len(plan) == 1
        assert plan[0].name == "phase-0"
        assert plan[0].top_level_task_id is None

    def test_should_match_compute_waves_when_feature_is_flat(self) -> None:
        tasks_module = _load_tasks_module()
        tasks = [
            _task("001"),
            _task("002", deps=["001"]),
            _task("003", deps=["001"]),
        ]

        plan = tasks_module.compute_phase_plan(tasks)
        waves, _ = tasks_module.compute_waves(
            [dict(t) for t in tasks]
        )

        plan_waves = {w.wave_num: list(w.task_ids) for w in plan[0].waves}
        expected = {
            num: [t.get("task_id") for t in wave_tasks]
            for num, wave_tasks in waves.items()
        }
        assert plan_waves == expected


# ── AC-02 / AC-03 / EC-3: decomposed feature ────────────────────────────


class TestDecomposedGrouping:
    def test_should_produce_one_phase_per_top_level_group_when_decomposed(
        self,
    ) -> None:
        tasks_module = _load_tasks_module()
        tasks = [
            _task("001", status="decomposed"),
            _task("001.001", parent="001"),
            _task("001.002", parent="001"),
            _task("002", status="decomposed"),
            _task("002.001", parent="002"),
        ]

        plan = tasks_module.compute_phase_plan(tasks)

        assert len(plan) == 2
        top_level = [p.top_level_task_id for p in plan]
        assert set(top_level) == {"001", "002"}

    def test_should_order_dependent_phase_after_its_dependency(self) -> None:
        tasks_module = _load_tasks_module()
        tasks = [
            _task("001", status="decomposed"),
            _task("001.001", parent="001"),
            _task("001.002", parent="001"),
            _task("002", status="decomposed"),
            _task("002.001", parent="002", deps=["001.002"]),
        ]

        plan = tasks_module.compute_phase_plan(tasks)

        order = [p.top_level_task_id for p in plan]
        assert order.index("001") < order.index("002")

    def test_should_produce_one_phase_when_single_top_level_has_children(
        self,
    ) -> None:
        tasks_module = _load_tasks_module()
        tasks = [
            _task("001", status="decomposed"),
            _task("001.001", parent="001"),
            _task("001.002", parent="001", deps=["001.001"]),
        ]

        plan = tasks_module.compute_phase_plan(tasks)

        assert len(plan) == 1
        assert plan[0].top_level_task_id == "001"
        assert len(plan[0].waves) >= 1


# ── AC-04: totality — no drops, no dupes ─────────────────────────────────


class TestTotality:
    def test_should_place_every_pending_leaf_in_exactly_one_cell(self) -> None:
        tasks_module = _load_tasks_module()
        tasks = [
            _task("001", status="decomposed"),
            _task("001.001", parent="001"),
            _task("001.002", parent="001", deps=["001.001"]),
            _task("002", status="decomposed"),
            _task("002.001", parent="002", deps=["001.002"]),
            _task("003"),
        ]

        plan = tasks_module.compute_phase_plan(tasks)

        placed: list[str] = []
        for phase in plan:
            placed.extend(_phase_task_ids(phase))
        expected_pending = {"001.001", "001.002", "002.001", "003"}
        assert sorted(placed) == sorted(expected_pending)
        assert len(placed) == len(set(placed))


# ── Edge cases EC-1 / EC-2 / EC-4 ────────────────────────────────────────


class TestEdgeCases:
    def test_should_return_empty_plan_when_no_tasks(self) -> None:
        tasks_module = _load_tasks_module()
        assert tasks_module.compute_phase_plan([]) == []

    def test_should_return_empty_plan_when_all_tasks_completed(self) -> None:
        tasks_module = _load_tasks_module()
        tasks = [
            _task("001", status="completed"),
            _task("002", status="completed"),
        ]
        assert tasks_module.compute_phase_plan(tasks) == []

    def test_should_not_loop_forever_on_circular_cross_phase_dependency(
        self,
    ) -> None:
        tasks_module = _load_tasks_module()
        tasks = [
            _task("001", status="decomposed"),
            _task("001.001", parent="001", deps=["002.001"]),
            _task("002", status="decomposed"),
            _task("002.001", parent="002", deps=["001.001"]),
        ]

        plan = tasks_module.compute_phase_plan(tasks)

        placed: list[str] = []
        for phase in plan:
            placed.extend(_phase_task_ids(phase))
        assert sorted(placed) == ["001.001", "002.001"]


# ── AC-05: compute_waves regression pin ──────────────────────────────────


class TestComputeWavesRegression:
    def test_should_keep_compute_waves_output_stable_for_fixed_input(
        self,
    ) -> None:
        tasks_module = _load_tasks_module()
        tasks = [
            _task("001"),
            _task("002", deps=["001"]),
            _task("003", deps=["001"]),
            _task("004", deps=["002", "003"]),
        ]

        waves, promoted = tasks_module.compute_waves(tasks)

        wave_ids = {
            num: [t.get("task_id") for t in wave_tasks]
            for num, wave_tasks in waves.items()
        }
        assert wave_ids == {
            0: ["001"],
            1: ["002", "003"],
            2: ["004"],
        }
        assert promoted == []


# ── AC-06: phases CLI ────────────────────────────────────────────────────


class TestPhasesCli:
    def _seed(self, tmp_path: Path) -> None:
        tasks_dir = (
            tmp_path / ".etc_sdlc" / "features" / "active" / "F-demo" / "tasks"
        )
        tasks_dir.mkdir(parents=True, exist_ok=True)
        specs = [
            ("001", "decomposed", None, None),
            ("001.001", "pending", "001", None),
            ("001.002", "pending", "001", "001.001"),
            ("002", "decomposed", None, None),
            ("002.001", "pending", "002", "001.002"),
        ]
        for task_id, status, parent, dep in specs:
            lines = [
                f'task_id: "{task_id}"',
                f'title: "task {task_id}"',
                "assigned_agent: backend-developer",
                f"status: {status}",
            ]
            if parent:
                lines.append(f'parent_task: "{parent}"')
            lines.append("requires_reading: []")
            lines.append("files_in_scope:")
            lines.append(f"  - src/{task_id}.py")
            lines.append("acceptance_criteria:")
            lines.append('  - "tests pass"')
            if dep:
                lines.append("dependencies:")
                lines.append(f'  - "{dep}"')
            else:
                lines.append("dependencies: []")
            (tasks_dir / f"{task_id}.yaml").write_text("\n".join(lines) + "\n")

    def test_should_print_ordered_phase_plan_and_exit_zero(
        self, tmp_path: Path
    ) -> None:
        self._seed(tmp_path)

        result = _run_tasks(tmp_path, "phases", "--feature", "F-demo")

        assert result.returncode == 0
        assert "Phase" in result.stdout
        assert "Wave" in result.stdout
        # phase for 001 must be printed before phase for 002
        assert result.stdout.index("001") < result.stdout.index("002")
