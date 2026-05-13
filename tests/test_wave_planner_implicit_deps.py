"""Contract tests for wave-planner implicit-dependency rejection (F008 / BR-008).

Covers PRD .etc_sdlc/features/F008-wave-planner-implicit-deps/spec.md
acceptance criteria AC10-AC13 via:

- In-process unit tests that call ``tasks_module._scan_implicit_deps`` directly
  with synthetic task dicts (the helper is a pure function — no disk required).
- Subprocess-based end-to-end tests that drive ``cmd_waves`` via
  ``python3 scripts/tasks.py waves --feature F999-test`` with
  ``cwd=str(tmp_path)`` so the script sees a synthetic
  ``<tmp_path>/.etc_sdlc/features/F999-<slug>/tasks/`` workspace as the active
  feature directory. NO test reads or writes real
  ``.etc_sdlc/features/F-NNN/tasks/`` directories — the F001-F007 task corpus
  is protected by construction.

Precedent: tests/test_completion_report.py (the F005 contract test). Same
tmp_path-with-subprocess-cwd pattern; synthetic feature dir under
``<tmp_path>/.etc_sdlc/features/F999-<slug>/tasks/``; ``subprocess.run``
invocation of ``tasks.py`` with ``cwd=str(tmp_path)`` so the script sees the
synthetic feature as the active workspace.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
TASKS_SCRIPT = SCRIPTS_DIR / "tasks.py"

# Make scripts/ importable so the in-process unit tests can drive the helper
# directly. Mirrors tests/test_completion_report.py's sys.path manipulation.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import tasks as tasks_module  # pyright: ignore[reportMissingImports]  # noqa: E402

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_task(
    task_id: str,
    *,
    title: str = "Synthetic task",
    status: str = "pending",
    context: str = "",
    acceptance_criteria: list[str] | None = None,
    dependencies: list[str] | None = None,
) -> dict:
    """Build a minimal task dict for in-memory tests."""
    return {
        "task_id": task_id,
        "title": title,
        "assigned_agent": "backend-developer",
        "status": status,
        "files_in_scope": ["src/app.py"],
        "acceptance_criteria": list(acceptance_criteria or ["Tests pass"]),
        "dependencies": list(dependencies or []),
        "context": context,
    }


def _make_feature_dir(tmp_path: Path, slug: str = "F999-test") -> Path:
    """Create ``<tmp_path>/.etc_sdlc/features/<slug>/tasks/`` and return it."""
    tasks_dir = tmp_path / ".etc_sdlc" / "features" / slug / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return tasks_dir


def _write_task_yaml(
    tasks_dir: Path,
    task_id: str,
    *,
    title: str = "Synthetic task",
    status: str = "pending",
    context: str = "",
    acceptance_criteria: list[str] | None = None,
    dependencies: list[str] | None = None,
) -> Path:
    """Write a minimal task YAML to ``tasks_dir`` and return the path."""
    criteria = acceptance_criteria or ["Tests pass"]
    deps = dependencies or []
    lines = [
        f'task_id: "{task_id}"',
        f'title: "{title}"',
        "assigned_agent: backend-developer",
        f"status: {status}",
        "requires_reading: []",
        "files_in_scope:",
        "  - src/app.py",
        "acceptance_criteria:",
    ]
    for crit in criteria:
        lines.append(f'  - "{crit}"')
    if deps:
        lines.append("dependencies:")
        for dep in deps:
            lines.append(f'  - "{dep}"')
    else:
        lines.append("dependencies: []")
    if context:
        lines.append("context: |")
        for line in context.split("\n"):
            lines.append(f"  {line}" if line else "  ")

    path = tasks_dir / f"{task_id}-synthetic.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run_waves(tmp_path: Path, feature: str) -> subprocess.CompletedProcess[str]:
    """Run ``tasks.py waves --feature <feature>`` with ``cwd=tmp_path``."""
    return subprocess.run(
        [sys.executable, str(TASKS_SCRIPT), "waves", "--feature", feature],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


# ── BR-002 / AC10: each phrasing fires ───────────────────────────────────


def test_should_promote_edge_when_context_says_stub_until_task() -> None:
    """AC10 + BR-002 phrasing 1: ``stub until task <NNN>``.

    The helper must promote a hard dep edge from the source task to the
    captured task ID and surface a (source, target, phrase, field) tuple.

    Phrasing is constructed to match ONLY pattern 1 — using a period after
    the captured ID so the ``until task N lands`` pattern does not also
    match (would require the literal ``lands`` token after the digits).
    """
    source = _make_task("001", context="render a stub until task 003 ships.")
    target = _make_task("003", title="Target")
    tasks = [source, target]

    augmented, promoted = tasks_module._scan_implicit_deps(tasks)

    augmented_source = next(t for t in augmented if t["task_id"] == "001")
    assert "003" in augmented_source["dependencies"], (
        "expected '003' to be promoted into 001's dependencies; "
        f"got {augmented_source['dependencies']!r}"
    )
    assert len(promoted) == 1, f"expected exactly one promoted edge; got {promoted!r}"
    src_id, tgt_id, phrase, field = promoted[0]
    assert src_id == "001"
    assert tgt_id == "003"
    assert phrase.lower().startswith("stub until task 003")
    assert field == "context"


def test_should_promote_edge_when_context_says_placeholder_for_task() -> None:
    """AC10 + BR-002 phrasing 2: ``placeholder for task <NNN>``."""
    source = _make_task(
        "001", context="This module is a placeholder for task 005 until ready."
    )
    target = _make_task("005", title="Target")
    tasks = [source, target]

    augmented, promoted = tasks_module._scan_implicit_deps(tasks)

    augmented_source = next(t for t in augmented if t["task_id"] == "001")
    assert "005" in augmented_source["dependencies"]
    assert len(promoted) == 1
    src_id, tgt_id, phrase, field = promoted[0]
    assert src_id == "001"
    assert tgt_id == "005"
    assert "placeholder for task 005" in phrase.lower()
    assert field == "context"


def test_should_promote_edge_when_context_says_until_task_lands() -> None:
    """AC10 + BR-002 phrasing 3: ``until task <NNN> lands``.

    Phrasing is constructed to match ONLY pattern 3 — no leading
    ``stub`` keyword (which would also fire pattern 1) and no
    ``placeholder for`` (which would also fire pattern 2).
    """
    source = _make_task("001", context="Block this work until task 010 lands.")
    target = _make_task("010", title="Target")
    tasks = [source, target]

    augmented, promoted = tasks_module._scan_implicit_deps(tasks)

    augmented_source = next(t for t in augmented if t["task_id"] == "001")
    assert "010" in augmented_source["dependencies"]
    assert len(promoted) == 1
    src_id, tgt_id, phrase, field = promoted[0]
    assert src_id == "001"
    assert tgt_id == "010"
    assert "until task 010 lands" in phrase.lower()
    assert field == "context"


def test_should_match_case_insensitively_when_phrasing_uses_mixed_case() -> None:
    """BR-002 — patterns compile with ``re.IGNORECASE``.

    Sanity check: a phrasing in mixed case still promotes the edge.
    Uses a non-overlapping ``Placeholder For Task`` phrasing so only
    pattern 2 fires.
    """
    source = _make_task("001", context="Placeholder For Task 002 only.")
    target = _make_task("002", title="Target")
    tasks = [source, target]

    augmented, promoted = tasks_module._scan_implicit_deps(tasks)

    augmented_source = next(t for t in augmented if t["task_id"] == "001")
    assert "002" in augmented_source["dependencies"]
    assert len(promoted) == 1


# ── BR-006 / AC8: fail-fast on unknown task ID ───────────────────────────


def test_should_exit_one_with_error_when_referenced_task_id_unknown(
    tmp_path: Path,
) -> None:
    """AC10 (fail-fast clause) + BR-006: unknown captured ID exits 1.

    Drive the failure end-to-end via subprocess so we observe the real
    exit code and the stderr message. The synthetic feature contains a
    single task whose context references a non-existent task 999.
    """
    tasks_dir = _make_feature_dir(tmp_path, slug="F999-failfast")
    _write_task_yaml(
        tasks_dir,
        "001",
        title="Source",
        context="stub until task 999 lands",
    )

    result = _run_waves(tmp_path, feature="F999-failfast")

    assert result.returncode == 1, (
        f"expected exit 1 on unknown captured task id; got {result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # Per BR-006: stderr must contain the literal "references task" plus the
    # source id, the missing captured id, and the matched phrase verbatim.
    assert "references task" in result.stderr, (
        f"missing 'references task' substring in stderr={result.stderr!r}"
    )
    assert "001" in result.stderr, (
        f"missing source task id '001' in stderr={result.stderr!r}"
    )
    assert "999" in result.stderr, (
        f"missing missing-reference id '999' in stderr={result.stderr!r}"
    )
    assert "stub until task 999" in result.stderr.lower(), (
        f"missing matched phrase in stderr={result.stderr!r}"
    )


# ── BR-005 / AC7: idempotency ────────────────────────────────────────────


def test_should_not_double_add_dep_when_explicit_edge_already_exists() -> None:
    """AC10 + BR-005: idempotency.

    If the captured task ID already lives in ``dependencies``, the helper
    must NOT double-add it. The promoted-edge tuple list still records
    the matched-phrase entry exactly once (de-duplicated within itself).

    Phrasing matches only pattern 1 — no ``lands`` token after the digits.
    """
    source = _make_task(
        "001",
        context="render a stub until task 003 ships.",
        dependencies=["003"],
    )
    target = _make_task("003", title="Target")
    tasks = [source, target]

    augmented, promoted = tasks_module._scan_implicit_deps(tasks)

    augmented_source = next(t for t in augmented if t["task_id"] == "001")
    # No duplicate entry in dependencies.
    assert augmented_source["dependencies"].count("003") == 1, (
        f"expected '003' to appear exactly once; got "
        f"{augmented_source['dependencies']!r}"
    )
    # Single de-duplicated edge tuple.
    assert len(promoted) == 1, (
        f"expected one promoted-edge tuple; got {promoted!r}"
    )


# ── BR-003 / AC5: both fields scanned ────────────────────────────────────


def test_should_promote_edge_when_acceptance_criterion_contains_phrase() -> None:
    """AC10 + AC5 + BR-003: ``acceptance_criteria`` items are scanned.

    The source task has empty context but one AC string contains the
    phrasing. The promoted-edge tuple's source_field must be
    ``acceptance_criteria[0]``, distinguishing the AC-source from a
    context-source match.

    Phrasing matches only pattern 1 — no trailing ``lands`` keyword.
    """
    source = _make_task(
        "001",
        context="",
        acceptance_criteria=["Renders a stub until task 004 ships."],
    )
    target = _make_task("004", title="Target")
    tasks = [source, target]

    augmented, promoted = tasks_module._scan_implicit_deps(tasks)

    augmented_source = next(t for t in augmented if t["task_id"] == "001")
    assert "004" in augmented_source["dependencies"]
    assert len(promoted) == 1
    src_id, tgt_id, _, field = promoted[0]
    assert src_id == "001"
    assert tgt_id == "004"
    assert field == "acceptance_criteria[0]", (
        f"expected source_field 'acceptance_criteria[0]'; got {field!r}"
    )


def test_should_record_two_edges_when_phrase_appears_in_context_and_ac() -> None:
    """Edge Case 7: same captured task in BOTH ``context`` and an AC.

    Idempotency (BR-005) keeps the dependencies list with one entry, but
    the promoted-edge tuple list records both occurrences (different
    source_field values) so operators see both in the audit trail.

    Each field uses a non-overlapping phrasing (pattern 1 vs pattern 2)
    so exactly one match fires per field — total of two edge tuples.
    """
    source = _make_task(
        "001",
        context="render a stub until task 002 ships.",
        acceptance_criteria=["UI placeholder for task 002 visible."],
    )
    target = _make_task("002", title="Target")
    tasks = [source, target]

    augmented, promoted = tasks_module._scan_implicit_deps(tasks)

    augmented_source = next(t for t in augmented if t["task_id"] == "001")
    assert augmented_source["dependencies"].count("002") == 1
    assert len(promoted) == 2, (
        f"expected two distinct promoted-edge tuples (one per source field); "
        f"got {promoted!r}"
    )
    fields = {edge[3] for edge in promoted}
    assert "context" in fields
    assert "acceptance_criteria[0]" in fields


# ── BR-007 / AC9: cmd_waves prints promoted-edge notes ───────────────────


def test_should_print_promoted_edge_note_when_cmd_waves_runs(
    tmp_path: Path,
) -> None:
    """AC10 + AC9 + BR-007: ``tasks.py waves`` surfaces promoted edges.

    End-to-end test: write two synthetic task YAMLs into a tmp feature
    directory (one with an implicit dep, one without), run ``tasks.py
    waves --feature F999-notes`` via subprocess, and assert stdout contains
    the literal ``note: promoted task`` substring AND the matched phrase.
    """
    tasks_dir = _make_feature_dir(tmp_path, slug="F999-notes")
    _write_task_yaml(
        tasks_dir,
        "001",
        title="Source",
        context="stub until task 002 lands",
    )
    _write_task_yaml(tasks_dir, "002", title="Target")

    result = _run_waves(tmp_path, feature="F999-notes")

    assert result.returncode == 0, (
        f"waves command failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "note: promoted task" in result.stdout, (
        f"missing literal 'note: promoted task' substring in stdout="
        f"{result.stdout!r}"
    )
    # The promoted-edge note must include both task IDs and the matched phrase.
    assert "001" in result.stdout
    assert "002" in result.stdout
    assert "stub until task 002" in result.stdout.lower(), (
        f"missing matched phrase in stdout={result.stdout!r}"
    )


def test_should_not_print_any_note_when_no_implicit_dep_present(
    tmp_path: Path,
) -> None:
    """AC9 graceful-empty clause: when no edges are promoted, no notes appear.

    Two tasks, no implicit phrasings — ``tasks.py waves`` runs cleanly and
    its stdout contains zero ``note: promoted`` lines.
    """
    tasks_dir = _make_feature_dir(tmp_path, slug="F999-clean")
    _write_task_yaml(tasks_dir, "001", title="Plain source", context="")
    _write_task_yaml(tasks_dir, "002", title="Plain target", context="")

    result = _run_waves(tmp_path, feature="F999-clean")

    assert result.returncode == 0, (
        f"waves command failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "note: promoted" not in result.stdout, (
        f"unexpected promoted-edge note when no implicit deps present; "
        f"stdout={result.stdout!r}"
    )


# ── compute_waves signature contract ─────────────────────────────────────


def test_should_return_two_tuple_when_compute_waves_invoked() -> None:
    """AC2 (compute_waves invokes the scan first) + the modified signature.

    ``compute_waves`` now returns a 2-tuple (waves, promoted_edges). The
    in-memory promotion must be visible by the time the tuple is returned.

    Phrasing matches only pattern 1 — no trailing ``lands`` keyword.
    """
    source = _make_task("001", context="render a stub until task 002 ships.")
    target = _make_task("002", title="Target")

    result = tasks_module.compute_waves([source, target])

    # Must be a 2-tuple of (waves, promoted_edges).
    assert isinstance(result, tuple), (
        f"compute_waves must return a tuple; got {type(result).__name__}"
    )
    assert len(result) == 2, (
        f"compute_waves must return a 2-tuple; got {len(result)} elements"
    )
    waves, promoted = result
    assert isinstance(waves, dict), "first element must be the wave map"
    assert isinstance(promoted, list), "second element must be the edges list"
    # Edge promotion is visible: 001 must depend on 002 and therefore
    # cannot share a wave with it.
    assert any(
        "001" in [t["task_id"] for t in tasks_in_wave]
        for tasks_in_wave in waves.values()
    ), f"task 001 should appear in some wave; got {waves!r}"
    assert len(promoted) == 1


# ── AC11 guard: no real .etc_sdlc/features/F-NNN/ access ─────────────────


def test_should_use_only_tmp_path_when_running_subprocess_tests(
    tmp_path: Path,
) -> None:
    """AC11 self-check: every subprocess test must invoke with cwd=tmp_path.

    This test is deliberately tiny and proves the harness wrapper's
    contract: ``_run_waves`` always passes ``cwd=str(tmp_path)`` so the
    real ``.etc_sdlc/features/F001-F007*/tasks/`` corpus is invisible to
    the spawned process. We assert the behavior by running the helper on
    an empty feature dir and expecting the "No tasks found." stdout —
    proof that ``cwd`` was honored (otherwise the script would discover
    real tasks in the repo cwd).
    """
    _make_feature_dir(tmp_path, slug="F999-empty")

    result = _run_waves(tmp_path, feature="F999-empty")

    assert result.returncode == 0, (
        f"waves command failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "No tasks found." in result.stdout, (
        f"expected the empty-feature stdout 'No tasks found.'; got "
        f"stdout={result.stdout!r}. If this fails, the subprocess saw a "
        f"different cwd than tmp_path, indicating the F001-F007 corpus "
        f"protection (AC11) is broken."
    )


# Module-level reference so static analyzers see ``pytest`` as used even when
# only the imported symbol is needed for a fixture-style indirection. The
# ``pytest`` import is required by pytest's collection machinery via tmp_path.
_ = pytest
