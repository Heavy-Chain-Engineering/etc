"""Tests for scripts/review_gate.py (F-2026-06-02 build review gate).

Two subcommands:
  plan --feature-dir DIR  → JSON {agents, changed_files,
                             architect_reviewer_fires, skip_reason}
  aggregate --findings F... [--skip-review-gate REASON]
                          → severity-gated exit (0 proceed / 2 block / 1 error)

The tests build synthetic feature directories under pytest's tmp_path so the
gate runs against controlled inputs and never touches the real repo.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).parent.parent / "scripts" / "review_gate.py"


def _load_module() -> ModuleType:
    """Import review_gate.py in-process so its logic is unit-tested (and the
    branches are visible to coverage, which cannot trace subprocess invocations).
    """
    spec = importlib.util.spec_from_file_location("review_gate_under_test", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


review_gate = _load_module()


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=20,
    )


def _make_feature(
    tmp_path: Path,
    *,
    infrastructure_only: bool,
    design_body: str,
    tasks: dict[str, list[str]] | None = None,
) -> Path:
    """Create a feature dir with state.yaml, design.md, and wave task files.

    `tasks` maps a task id (e.g. "001") to its files_in_scope list.
    """
    feature_dir = tmp_path / "F-test-feature"
    feature_dir.mkdir()
    (feature_dir / "design.md").write_text(design_body, encoding="utf-8")
    flag = "true" if infrastructure_only else "false"
    (feature_dir / "state.yaml").write_text(
        f"spec_phase:\n  infrastructure_only: {flag}\n", encoding="utf-8"
    )
    tasks_dir = feature_dir / "tasks"
    tasks_dir.mkdir()
    for task_id, files in (tasks or {}).items():
        lines = [f'task_id: "{task_id}"', "files_in_scope:"]
        lines.extend(f"  - {path}" for path in files)
        (tasks_dir / f"{task_id}-task.yaml").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    return feature_dir


# A design body whose vocabulary the layer-review registry will detect as a
# touched layer (so architect-reviewer would fire when not infrastructure_only).
_ARCHITECTURAL_DESIGN = """# Design

## Data Model

A new database table with an index and a schema migration.
"""


# ── plan ─────────────────────────────────────────────────────────────────


def test_should_always_include_core_reviewers_when_planning(tmp_path: Path) -> None:
    feature_dir = _make_feature(
        tmp_path, infrastructure_only=True, design_body="# Design\n"
    )

    result = _run("plan", "--feature-dir", str(feature_dir))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "code-reviewer" in payload["agents"]
    assert "security-reviewer" in payload["agents"]


def test_should_not_fire_architect_reviewer_when_infrastructure_only(
    tmp_path: Path,
) -> None:
    feature_dir = _make_feature(
        tmp_path,
        infrastructure_only=True,
        design_body=_ARCHITECTURAL_DESIGN,
    )

    result = _run("plan", "--feature-dir", str(feature_dir))

    payload = json.loads(result.stdout)
    assert payload["architect_reviewer_fires"] is False
    assert "architect-reviewer" not in payload["agents"]
    assert payload["skip_reason"]


def test_should_fire_architect_reviewer_when_layers_touched(tmp_path: Path) -> None:
    feature_dir = _make_feature(
        tmp_path,
        infrastructure_only=False,
        design_body=_ARCHITECTURAL_DESIGN,
    )

    result = _run("plan", "--feature-dir", str(feature_dir))

    payload = json.loads(result.stdout)
    assert payload["architect_reviewer_fires"] is True
    assert "architect-reviewer" in payload["agents"]
    assert payload["skip_reason"] is None


def test_should_not_fire_architect_reviewer_when_no_layers_touched(
    tmp_path: Path,
) -> None:
    feature_dir = _make_feature(
        tmp_path,
        infrastructure_only=False,
        design_body="# Design\n\nA prose-only change with no layer vocabulary.\n",
    )

    result = _run("plan", "--feature-dir", str(feature_dir))

    payload = json.loads(result.stdout)
    assert payload["architect_reviewer_fires"] is False
    assert payload["skip_reason"]


def test_should_union_files_in_scope_from_wave_tasks_when_planning(
    tmp_path: Path,
) -> None:
    feature_dir = _make_feature(
        tmp_path,
        infrastructure_only=True,
        design_body="# Design\n",
        tasks={
            "001": ["scripts/a.py", "tests/test_a.py"],
            "002": ["scripts/b.py", "scripts/a.py"],
        },
    )

    result = _run("plan", "--feature-dir", str(feature_dir))

    payload = json.loads(result.stdout)
    assert "scripts/a.py" in payload["changed_files"]
    assert "scripts/b.py" in payload["changed_files"]
    assert "tests/test_a.py" in payload["changed_files"]
    # Union deduplicates a.py
    assert payload["changed_files"].count("scripts/a.py") == 1


def test_should_exit_1_when_feature_dir_missing(tmp_path: Path) -> None:
    result = _run("plan", "--feature-dir", str(tmp_path / "nope"))

    assert result.returncode == 1


# ── aggregate ──────────────────────────────────────────────────────────────


def _write_findings(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


_CLEAN = "## Review Findings\nGATE: CLEAN\n"
_MEDIUM = (
    "## Review Findings\n"
    "- [MEDIUM] scripts/a.py:12 — naming nit\n"
    "GATE: PASS\n"
)
_HIGH = (
    "## Review Findings\n"
    "- [HIGH] scripts/a.py:30 — unsafe id generator\n"
    "GATE: BLOCK\n"
)
_CRITICAL = (
    "## Review Findings\n"
    "- [CRITICAL] scripts/a.py:5 — multi-tenant scope leak\n"
    "GATE: BLOCK\n"
)


def test_should_proceed_when_all_findings_clean(tmp_path: Path) -> None:
    findings = _write_findings(tmp_path, "code.md", _CLEAN)

    result = _run("aggregate", "--findings", str(findings))

    assert result.returncode == 0


def test_should_proceed_when_only_medium_or_low_findings(tmp_path: Path) -> None:
    findings = _write_findings(tmp_path, "code.md", _MEDIUM)

    result = _run("aggregate", "--findings", str(findings))

    assert result.returncode == 0
    assert "MEDIUM" in result.stdout


def test_should_block_when_a_high_finding_present(tmp_path: Path) -> None:
    findings = _write_findings(tmp_path, "sec.md", _HIGH)

    result = _run("aggregate", "--findings", str(findings))

    assert result.returncode == 2
    assert "HIGH" in result.stdout


def test_should_block_when_a_critical_finding_present(tmp_path: Path) -> None:
    findings = _write_findings(tmp_path, "sec.md", _CRITICAL)

    result = _run("aggregate", "--findings", str(findings))

    assert result.returncode == 2


def test_should_block_when_critical_present_across_multiple_files(
    tmp_path: Path,
) -> None:
    clean = _write_findings(tmp_path, "code.md", _CLEAN)
    critical = _write_findings(tmp_path, "sec.md", _CRITICAL)

    result = _run("aggregate", "--findings", str(clean), str(critical))

    assert result.returncode == 2


def test_should_block_when_findings_block_unparseable(tmp_path: Path) -> None:
    findings = _write_findings(
        tmp_path, "broken.md", "The agent rambled but emitted no findings block.\n"
    )

    result = _run("aggregate", "--findings", str(findings))

    assert result.returncode == 2
    assert "INSUFFICIENT_EVIDENCE" in result.stdout


def test_should_block_when_findings_file_missing(tmp_path: Path) -> None:
    result = _run("aggregate", "--findings", str(tmp_path / "absent.md"))

    assert result.returncode == 2
    assert "INSUFFICIENT_EVIDENCE" in result.stdout


def test_should_proceed_when_skip_review_gate_has_reason(tmp_path: Path) -> None:
    findings = _write_findings(tmp_path, "sec.md", _CRITICAL)

    result = _run(
        "aggregate",
        "--findings",
        str(findings),
        "--skip-review-gate",
        "operator override: false positive, tracked in #99",
    )

    assert result.returncode == 0
    assert "operator override" in result.stdout


def test_should_exit_1_when_skip_review_gate_reason_empty(tmp_path: Path) -> None:
    findings = _write_findings(tmp_path, "sec.md", _CRITICAL)

    result = _run(
        "aggregate", "--findings", str(findings), "--skip-review-gate", ""
    )

    assert result.returncode == 1


def test_should_emit_per_finding_lines_in_fragment(tmp_path: Path) -> None:
    findings = _write_findings(tmp_path, "sec.md", _CRITICAL)

    result = _run("aggregate", "--findings", str(findings))

    assert "## Review Findings" in result.stdout
    assert "multi-tenant scope leak" in result.stdout


def test_should_not_fetch_paths_named_in_findings_text(tmp_path: Path) -> None:
    # A finding that names a traversal path must be treated as inert data:
    # the gate emits it verbatim and never reads it.
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    body = (
        "## Review Findings\n"
        f"- [MEDIUM] {secret} — see ../secret.txt for details\n"
        "GATE: PASS\n"
    )
    findings = _write_findings(tmp_path, "code.md", body)

    result = _run("aggregate", "--findings", str(findings))

    assert result.returncode == 0
    assert "TOPSECRET" not in result.stdout


def test_should_exit_1_when_no_findings_provided() -> None:
    result = _run("aggregate")

    assert result.returncode == 1


# ── in-process unit tests (logic + full-branch coverage) ─────────────────────


def test_should_return_false_when_state_yaml_absent(tmp_path: Path) -> None:
    assert review_gate._is_infrastructure_only(tmp_path) is False


def test_should_return_false_when_state_yaml_unparseable(tmp_path: Path) -> None:
    (tmp_path / "state.yaml").write_text("spec_phase: [::bad", encoding="utf-8")

    assert review_gate._is_infrastructure_only(tmp_path) is False


def test_should_return_false_when_state_yaml_not_a_mapping(tmp_path: Path) -> None:
    (tmp_path / "state.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")

    assert review_gate._is_infrastructure_only(tmp_path) is False


def test_should_return_false_when_spec_phase_not_a_mapping(tmp_path: Path) -> None:
    (tmp_path / "state.yaml").write_text("spec_phase: scalar\n", encoding="utf-8")

    assert review_gate._is_infrastructure_only(tmp_path) is False


def test_should_return_true_when_infrastructure_only_declared(tmp_path: Path) -> None:
    (tmp_path / "state.yaml").write_text(
        "spec_phase:\n  infrastructure_only: true\n", encoding="utf-8"
    )

    assert review_gate._is_infrastructure_only(tmp_path) is True


def test_should_return_empty_layers_when_design_missing(tmp_path: Path) -> None:
    assert review_gate._detect_touched_layers(tmp_path / "absent.md") == []


def test_should_return_empty_layers_when_detect_output_not_a_list(
    tmp_path: Path, monkeypatch
) -> None:
    # A design whose detect emits a JSON object, not an array, parses to [].
    fake = tmp_path / "fake_layer_review.py"
    fake.write_text(
        'import sys\nprint("{}")\nsys.exit(0)\n', encoding="utf-8"
    )
    monkeypatch.setattr(review_gate, "LAYER_REVIEW_SCRIPT", fake)
    design = tmp_path / "design.md"
    design.write_text("# d\n", encoding="utf-8")

    assert review_gate._detect_touched_layers(design) == []


def test_should_return_empty_layers_when_detect_output_unparseable(
    tmp_path: Path, monkeypatch
) -> None:
    fake = tmp_path / "fake_layer_review.py"
    fake.write_text('print("not json")\n', encoding="utf-8")
    monkeypatch.setattr(review_gate, "LAYER_REVIEW_SCRIPT", fake)
    design = tmp_path / "design.md"
    design.write_text("# d\n", encoding="utf-8")

    assert review_gate._detect_touched_layers(design) == []


def test_should_return_empty_layers_when_detect_exits_nonzero(
    tmp_path: Path, monkeypatch
) -> None:
    fake = tmp_path / "fake_layer_review.py"
    fake.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")
    monkeypatch.setattr(review_gate, "LAYER_REVIEW_SCRIPT", fake)
    design = tmp_path / "design.md"
    design.write_text("# d\n", encoding="utf-8")

    assert review_gate._detect_touched_layers(design) == []


def test_should_return_empty_scope_when_tasks_dir_absent(tmp_path: Path) -> None:
    assert review_gate._files_in_scope_from_tasks(tmp_path) == []


def test_should_skip_task_when_yaml_unparseable(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [::nope", encoding="utf-8")

    assert review_gate._task_files(bad) == []


def test_should_skip_task_when_yaml_not_a_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "list.yaml"
    bad.write_text("- one\n- two\n", encoding="utf-8")

    assert review_gate._task_files(bad) == []


def test_should_skip_task_when_files_in_scope_not_a_list(tmp_path: Path) -> None:
    bad = tmp_path / "scope.yaml"
    bad.write_text("files_in_scope: nope\n", encoding="utf-8")

    assert review_gate._task_files(bad) == []


def test_should_return_empty_diff_when_git_unavailable(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(review_gate.subprocess, "run", _boom)

    assert review_gate._git_diff_files("main") == []


def test_should_return_empty_diff_when_git_exits_nonzero(monkeypatch) -> None:
    class _Result:
        returncode = 128
        stdout = ""

    monkeypatch.setattr(
        review_gate.subprocess, "run", lambda *_args, **_kwargs: _Result()
    )

    assert review_gate._git_diff_files("main") == []


def test_should_return_diff_lines_when_git_succeeds(monkeypatch) -> None:
    class _Result:
        returncode = 0
        stdout = "scripts/x.py\n\ntests/test_x.py\n"

    monkeypatch.setattr(
        review_gate.subprocess, "run", lambda *_args, **_kwargs: _Result()
    )

    assert review_gate._git_diff_files("main") == ["scripts/x.py", "tests/test_x.py"]


def test_should_merge_git_diff_into_changed_files_when_planning(
    tmp_path: Path, monkeypatch
) -> None:
    feature_dir = _make_feature(
        tmp_path,
        infrastructure_only=True,
        design_body="# Design\n",
        tasks={"001": ["scripts/a.py"]},
    )

    class _Result:
        returncode = 0
        stdout = "scripts/a.py\nscripts/new.py\n"

    monkeypatch.setattr(
        review_gate.subprocess, "run", lambda *a, **k: _Result()
    )
    plan = review_gate.build_plan(feature_dir, "main")

    assert plan.changed_files == ["scripts/a.py", "scripts/new.py"]


def test_should_mark_insufficient_when_heading_absent() -> None:
    block = review_gate.parse_findings_block("a.md", "no block here\n")

    assert block.insufficient is True


def test_should_mark_insufficient_when_gate_line_absent() -> None:
    text = "## Review Findings\n- [LOW] x — nit\n"

    block = review_gate.parse_findings_block("a.md", text)

    assert block.insufficient is True


def test_should_parse_findings_when_block_well_formed() -> None:
    text = (
        "## Review Findings\n"
        "- [HIGH] x:1 — bad\n"
        "junk line ignored\n"
        "- [low] y:2 — minor\n"
        "GATE: BLOCK\n"
    )

    block = review_gate.parse_findings_block("a.md", text)

    assert block.insufficient is False
    assert block.findings[0].severity == "HIGH"
    assert block.findings[1].severity == "LOW"


def test_should_capture_empty_text_when_finding_has_no_body() -> None:
    text = "## Review Findings\n- [MEDIUM]\nGATE: PASS\n"

    block = review_gate.parse_findings_block("a.md", text)

    assert block.findings[0].text == ""


def test_should_return_none_max_severity_when_no_findings() -> None:
    block = review_gate.parse_findings_block("a.md", "## Review Findings\nGATE: CLEAN\n")

    assert review_gate._max_severity([block]) is None


def test_should_return_top_severity_when_mixed_findings() -> None:
    text = "## Review Findings\n- [LOW] a — n\n- [CRITICAL] b — m\nGATE: BLOCK\n"
    block = review_gate.parse_findings_block("a.md", text)

    assert review_gate._max_severity([block]) == "CRITICAL"


def test_should_render_clean_verdict_when_no_findings() -> None:
    block = review_gate.parse_findings_block("a.md", "## Review Findings\nGATE: CLEAN\n")

    fragment = review_gate.render_fragment([block], blocking=False, override_reason=None)

    assert "PROCEED (CLEAN)" in fragment


def test_should_render_insufficient_verdict_when_block_missing() -> None:
    block = review_gate.parse_findings_block("a.md", "nothing\n")

    fragment = review_gate.render_fragment([block], blocking=True, override_reason=None)

    assert "INSUFFICIENT_EVIDENCE" in fragment


def test_should_resolve_override_to_none_when_blank() -> None:
    assert review_gate._resolve_override("   ") is None
    assert review_gate._resolve_override(None) is None
    assert review_gate._resolve_override("ok") == "ok"


def test_should_exit_2_when_main_invoked_with_blocking_findings(
    tmp_path: Path,
) -> None:
    findings = tmp_path / "f.md"
    findings.write_text(
        "## Review Findings\n- [CRITICAL] x — leak\nGATE: BLOCK\n", encoding="utf-8"
    )

    code = review_gate.main(["aggregate", "--findings", str(findings)])

    assert code == 2


def test_should_fire_architect_and_return_layer_strings_when_layers_touched(
    tmp_path: Path, monkeypatch
) -> None:
    feature_dir = _make_feature(
        tmp_path,
        infrastructure_only=False,
        design_body=_ARCHITECTURAL_DESIGN,
    )
    # Cross-check diff is irrelevant here; stub it empty for determinism.
    monkeypatch.setattr(review_gate, "_git_diff_files", lambda _base: [])

    plan = review_gate.build_plan(feature_dir, "main")

    assert plan.architect_reviewer_fires is True
    assert review_gate.ARCHITECT_REVIEWER in plan.agents


def test_should_return_layer_strings_when_detect_emits_array(tmp_path: Path) -> None:
    design = tmp_path / "design.md"
    design.write_text(_ARCHITECTURAL_DESIGN, encoding="utf-8")

    layers = review_gate._detect_touched_layers(design)

    assert layers
    assert all(isinstance(layer, str) for layer in layers)


def test_should_emit_plan_json_when_cli_plan_succeeds(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    feature_dir = _make_feature(
        tmp_path, infrastructure_only=True, design_body="# Design\n"
    )
    monkeypatch.setattr(review_gate, "_git_diff_files", lambda _base: [])

    code = review_gate.main(["plan", "--feature-dir", str(feature_dir)])
    captured = capsys.readouterr()

    assert code == 0
    payload = json.loads(captured.out)
    assert payload["agents"]


def test_should_return_1_when_cli_plan_dir_missing(tmp_path: Path) -> None:
    code = review_gate.main(["plan", "--feature-dir", str(tmp_path / "missing")])

    assert code == 1


def test_should_mark_insufficient_when_findings_path_is_a_directory(
    tmp_path: Path,
) -> None:
    block = review_gate.read_findings_block(tmp_path)

    assert block.insufficient is True


def test_should_record_override_in_fragment_when_reason_present() -> None:
    block = review_gate.parse_findings_block(
        "a.md", "## Review Findings\n- [CRITICAL] x — leak\nGATE: BLOCK\n"
    )

    fragment = review_gate.render_fragment(
        [block], blocking=True, override_reason="tracked in #99"
    )

    assert "Override (--skip-review-gate): tracked in #99" in fragment
    assert "PROCEED (overridden)" in fragment


def test_should_return_0_when_main_aggregate_overridden(tmp_path: Path) -> None:
    findings = tmp_path / "f.md"
    findings.write_text(
        "## Review Findings\n- [CRITICAL] x — leak\nGATE: BLOCK\n", encoding="utf-8"
    )

    code = review_gate.main(
        ["aggregate", "--findings", str(findings), "--skip-review-gate", "reason"]
    )

    assert code == 0


def test_should_return_1_when_main_aggregate_skip_reason_blank(
    tmp_path: Path,
) -> None:
    findings = tmp_path / "f.md"
    findings.write_text(
        "## Review Findings\nGATE: CLEAN\n", encoding="utf-8"
    )

    code = review_gate.main(
        ["aggregate", "--findings", str(findings), "--skip-review-gate", "  "]
    )

    assert code == 1


def test_should_return_1_when_main_aggregate_has_no_findings() -> None:
    code = review_gate.main(["aggregate"])

    assert code == 1


def test_should_skip_architect_with_reason_when_no_layers_touched_in_plan(
    tmp_path: Path, monkeypatch
) -> None:
    feature_dir = _make_feature(
        tmp_path,
        infrastructure_only=False,
        design_body="# Design\n\nprose only, no layer vocabulary\n",
    )
    monkeypatch.setattr(review_gate, "_git_diff_files", lambda _base: [])

    plan = review_gate.build_plan(feature_dir, "main")

    assert plan.architect_reviewer_fires is False
    assert plan.skip_reason == "no architectural layers touched"


def test_should_be_blocking_when_a_block_is_insufficient() -> None:
    insufficient = review_gate.parse_findings_block("a.md", "no block\n")
    clean = review_gate.parse_findings_block(
        "b.md", "## Review Findings\nGATE: CLEAN\n"
    )

    assert review_gate._is_blocking([insufficient, clean]) is True


def test_should_dedupe_scope_across_tasks_in_order(tmp_path: Path) -> None:
    feature_dir = _make_feature(
        tmp_path,
        infrastructure_only=True,
        design_body="# Design\n",
        tasks={"001": ["a", "b"], "002": ["b", "c"]},
    )

    scope = review_gate._files_in_scope_from_tasks(feature_dir)

    assert scope == ["a", "b", "c"]
