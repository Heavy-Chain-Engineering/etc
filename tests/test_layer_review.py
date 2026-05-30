"""Tests for scripts/layer_review.py (F-2026-05-26 Layered Architecture Review).

Covers the rubric registry schema contract (AC-001..005, AC-013), the
`detect` subcommand (AC-006, EC-001, EC-006), the `check` subcommand
(AC-007, AC-008, EC-002), and the registry-absent/malformed error path
(EC-003). The module is the single source of truth for both detection
and completeness checking (BR-009).

The engine exposes pure functions under a CLI (mirrors
scripts/value_hypothesis.py + scripts/spec_coupling_check.py):
    - DEFAULT_REGISTRY (Path)
    - ISO_25010 (frozenset[str]) — the 8 closed-vocab quality attributes
    - SEVERITIES (frozenset[str])
    - load_registry(path) -> Registry        (raises RegistryError)
    - detect_layers(design_text, registry) -> list[str]
    - check_completeness(design_text, registry) -> CheckResult
    - main(argv) -> int

Coverage of scripts/layer_review.py >= 95% (AC-012).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "layer_review.py"
REGISTRY_PATH = REPO_ROOT / "standards" / "architecture" / "layer-rubrics.yaml"

ISO_25010_CHARACTERISTICS = frozenset(
    {
        "functional_suitability",
        "performance_efficiency",
        "compatibility",
        "usability",
        "reliability",
        "security",
        "maintainability",
        "portability",
    }
)

SEVERITY_VALUES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"})

CORE_LAYERS = frozenset(
    {
        "data-access",
        "domain-service",
        "api-contract",
        "presentation-frontend",
        "infra-ops",
    }
)


def _load_module() -> ModuleType:
    """Import scripts/layer_review.py directly (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("layer_review", MODULE_PATH)
    if spec is None or spec.loader is None:
        msg = f"Cannot load module at {MODULE_PATH}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["layer_review"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def engine() -> ModuleType:
    """Module under test, imported once per test module."""
    return _load_module()


@pytest.fixture(scope="module")
def registry(engine: ModuleType) -> object:
    """The real shipped registry, parsed once."""
    return engine.load_registry(REGISTRY_PATH)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the script as a subprocess (exercises the exit-code contract)."""
    return subprocess.run(
        ["python3", str(MODULE_PATH), *args],
        capture_output=True,
        text=True,
        timeout=15,
    )


# ── Fixtures: synthetic design.md bodies ────────────────────────────────


def _layer_table(layer_id: str, rows: list[tuple[str, str]]) -> str:
    """Render a Layer Impact Analysis subsection for one layer.

    Each row is (item_id, answer). The table columns are
    (item id | criterion | answer-or-N/A | severity) per BR-008.
    """
    lines = [
        f"### {layer_id}",
        "",
        "| Item | Criterion | Answer / N/A | Severity |",
        "|------|-----------|--------------|----------|",
    ]
    for item_id, answer in rows:
        lines.append(f"| {item_id} | the criterion | {answer} | CRITICAL |")
    lines.append("")
    return "\n".join(lines)


def _design_touching_data_access_only() -> str:
    return (
        "# Design: add a new report query\n\n"
        "## Architecture Overview\n\n"
        "We add a new SELECT against the filings table with a WHERE clause "
        "on the status column, plus a migration to add an index.\n"
    )


def _design_touching_no_layer() -> str:
    return (
        "# Design: rename a docs file\n\n"
        "## Architecture Overview\n\n"
        "We rename a markdown file in the docs corpus. Pure prose edit; "
        "nothing structural changes.\n"
    )


def _design_signals_only_in_excluded_regions() -> str:
    return (
        "# Design: docs-only change\n\n"
        "## Architecture Overview\n\n"
        "A pure documentation edit.\n\n"
        "```sql\n"
        "SELECT * FROM filings WHERE status = 'open' JOIN audits;\n"
        "ALTER TABLE filings ADD COLUMN flag boolean;\n"
        "```\n\n"
        "## Out of Scope\n\n"
        "Any change to the filings table, its index, or the migration.\n\n"
        "## Future\n\n"
        "A later feature may add a JOIN and a new column.\n"
    )


# ── #54 — infrastructure_only features are exempt from layer detection ───


def _write_feature(
    tmp_path: object, *, infra_only: bool | None, design_text: str
) -> str:
    """Write design.md + sibling state.yaml in a feature dir; return design path.

    ``infra_only`` of ``None`` writes NO state.yaml at all (the default-not-exempt
    path); ``True``/``False`` writes ``spec_phase.infrastructure_only`` accordingly.
    """
    from pathlib import Path

    feature_dir = Path(str(tmp_path)) / "F-2026-05-30-meta-feature"
    feature_dir.mkdir(parents=True, exist_ok=True)
    design_path = feature_dir / "design.md"
    design_path.write_text(design_text, encoding="utf-8")
    if infra_only is not None:
        (feature_dir / "state.yaml").write_text(
            f"spec_phase:\n  infrastructure_only: {str(infra_only).lower()}\n",
            encoding="utf-8",
        )
    return str(design_path)


def test_should_exempt_detect_when_feature_infrastructure_only(
    tmp_path: object,
) -> None:
    # Arrange — a design loaded with data-access signals, but the feature is
    # infrastructure_only (harness tooling). #54: detection over-fired here.
    design = _write_feature(
        tmp_path, infra_only=True, design_text=_design_touching_data_access_only()
    )

    # Act
    result = _run_cli("detect", "--design", design)

    # Assert — exempt: empty layer list, exit 0, a note on stderr.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
    assert "infrastructure_only" in result.stderr


def test_should_detect_normally_when_state_not_infrastructure_only(
    tmp_path: object,
) -> None:
    design = _write_feature(
        tmp_path, infra_only=False, design_text=_design_touching_data_access_only()
    )
    result = _run_cli("detect", "--design", design)
    assert result.returncode == 0, result.stderr
    assert "data-access" in result.stdout


def test_should_detect_normally_when_no_sibling_state(tmp_path: object) -> None:
    # Default-not-exempt: an arbitrary design path with no sibling state.yaml
    # detects as usual (the exemption only fires on an explicit declaration).
    design = _write_feature(
        tmp_path, infra_only=None, design_text=_design_touching_data_access_only()
    )
    result = _run_cli("detect", "--design", design)
    assert result.returncode == 0, result.stderr
    assert "data-access" in result.stdout


def test_should_pass_check_when_infrastructure_only_even_if_incomplete(
    tmp_path: object,
) -> None:
    # A design with data-access signals but NO Layer Impact Analysis section
    # would normally fail `check` (exit 2). infrastructure_only exempts it.
    design = _write_feature(
        tmp_path, infra_only=True, design_text=_design_touching_data_access_only()
    )
    result = _run_cli("check", "--design", design)
    assert result.returncode == 0, result.stderr
    assert "infrastructure_only" in result.stderr


# ── AC-001 / AC-013: registry schema contract ───────────────────────────


def test_should_parse_registry_with_layers_and_cross_cutting_when_loaded(
    registry: object,
) -> None:
    assert len(registry.layers) > 0  # type: ignore[attr-defined]
    assert len(registry.cross_cutting_concerns) > 0  # type: ignore[attr-defined]


def test_should_populate_required_layer_fields_when_loaded(
    registry: object,
) -> None:
    for layer in registry.layers:  # type: ignore[attr-defined]
        assert layer.id
        assert layer.name
        assert layer.detection_signals
        assert layer.rubric


def test_should_populate_required_item_fields_when_loaded(
    registry: object,
) -> None:
    all_layers = list(registry.layers) + list(  # type: ignore[attr-defined]
        registry.cross_cutting_concerns  # type: ignore[attr-defined]
    )
    for layer in all_layers:
        for item in layer.rubric:
            assert item.id
            assert item.criterion.strip()
            assert item.quality_attribute
            assert item.severity_if_missed
            assert isinstance(item.mechanizable, bool)


def test_should_carry_boolean_mechanizable_on_every_item_when_loaded(
    registry: object,
) -> None:
    all_layers = list(registry.layers) + list(  # type: ignore[attr-defined]
        registry.cross_cutting_concerns  # type: ignore[attr-defined]
    )
    flags = [
        item.mechanizable
        for layer in all_layers
        for item in layer.rubric
    ]
    assert flags  # non-empty
    assert all(isinstance(flag, bool) for flag in flags)


# ── AC-002: core layers + cross-cutting concerns ────────────────────────


def test_should_define_five_core_layers_when_loaded(registry: object) -> None:
    layer_ids = {layer.id for layer in registry.layers}  # type: ignore[attr-defined]
    assert CORE_LAYERS <= layer_ids


def test_should_define_at_least_five_cross_cutting_concerns_when_loaded(
    registry: object,
) -> None:
    assert len(registry.cross_cutting_concerns) >= 5  # type: ignore[attr-defined]


# ── AC-003: flagship data-access rubric ─────────────────────────────────


def test_should_cover_seven_data_access_topics_when_loaded(
    registry: object,
) -> None:
    data_access = next(
        layer for layer in registry.layers if layer.id == "data-access"  # type: ignore[attr-defined]
    )
    assert len(data_access.rubric) >= 7
    blob = " ".join(item.criterion.lower() for item in data_access.rubric)
    for topic in ("index", "row", "full", "n+1", "paginat", "migration", "transaction"):
        assert topic in blob, f"data-access rubric missing topic: {topic}"


# ── AC-004: real rubrics for non-flagship core layers ───────────────────


def test_should_give_each_non_flagship_layer_three_real_items_when_loaded(
    registry: object,
) -> None:
    for layer in registry.layers:  # type: ignore[attr-defined]
        if layer.id == "data-access":
            continue
        assert len(layer.rubric) >= 3, f"{layer.id} has < 3 rubric items"
        for item in layer.rubric:
            assert item.criterion.strip()


# ── AC-005: ISO 25010 closed vocabulary ─────────────────────────────────


def test_should_use_only_iso_25010_attributes_when_loaded(
    registry: object,
) -> None:
    all_layers = list(registry.layers) + list(  # type: ignore[attr-defined]
        registry.cross_cutting_concerns  # type: ignore[attr-defined]
    )
    for layer in all_layers:
        for item in layer.rubric:
            assert item.quality_attribute in ISO_25010_CHARACTERISTICS


def test_should_use_only_known_severities_when_loaded(registry: object) -> None:
    all_layers = list(registry.layers) + list(  # type: ignore[attr-defined]
        registry.cross_cutting_concerns  # type: ignore[attr-defined]
    )
    for layer in all_layers:
        for item in layer.rubric:
            assert item.severity_if_missed in SEVERITY_VALUES


def test_should_expose_iso_vocab_constant_when_imported(
    engine: ModuleType,
) -> None:
    assert engine.ISO_25010 == ISO_25010_CHARACTERISTICS


# ── AC-006 / EC-001 / EC-006: detect ────────────────────────────────────


def test_should_detect_only_data_access_when_design_touches_it(
    engine: ModuleType, registry: object
) -> None:
    touched = engine.detect_layers(_design_touching_data_access_only(), registry)
    assert touched == ["data-access"]


def test_should_return_empty_list_when_design_touches_no_layer(
    engine: ModuleType, registry: object
) -> None:
    touched = engine.detect_layers(_design_touching_no_layer(), registry)
    assert touched == []


def test_should_exclude_fenced_and_out_of_scope_signals_when_detecting(
    engine: ModuleType, registry: object
) -> None:
    touched = engine.detect_layers(
        _design_signals_only_in_excluded_regions(), registry
    )
    assert touched == []


def test_should_emit_touched_layers_json_when_detect_cli_runs(
    tmp_path: Path,
) -> None:
    design = tmp_path / "design.md"
    design.write_text(_design_touching_data_access_only(), encoding="utf-8")
    result = _run_cli("detect", "--design", str(design))
    assert result.returncode == 0
    assert json.loads(result.stdout) == ["data-access"]


def test_should_emit_empty_json_array_when_detect_cli_finds_no_layer(
    tmp_path: Path,
) -> None:
    design = tmp_path / "design.md"
    design.write_text(_design_touching_no_layer(), encoding="utf-8")
    result = _run_cli("detect", "--design", str(design))
    assert result.returncode == 0
    assert json.loads(result.stdout) == []


# ── AC-007 / AC-008 / EC-002: check ─────────────────────────────────────


def _complete_design() -> str:
    """data-access touched, every rubric item answered (one as reasoned N/A)."""
    overview = _design_touching_data_access_only()
    rows: list[tuple[str, str]] = []
    engine = _load_module()
    reg = engine.load_registry(REGISTRY_PATH)
    data_access = next(layer for layer in reg.layers if layer.id == "data-access")
    for i, item in enumerate(data_access.rubric):
        answer = "N/A: read-only feature" if i == 0 else "Yes, index added"
        rows.append((item.id, answer))
    section = "## Layer Impact Analysis\n\n" + _layer_table("data-access", rows)
    return overview + "\n" + section + "\n"


def _incomplete_design(blank_answer: str) -> str:
    overview = _design_touching_data_access_only()
    engine = _load_module()
    reg = engine.load_registry(REGISTRY_PATH)
    data_access = next(layer for layer in reg.layers if layer.id == "data-access")
    rows: list[tuple[str, str]] = []
    for i, item in enumerate(data_access.rubric):
        answer = blank_answer if i == 0 else "Yes, index added"
        rows.append((item.id, answer))
    section = "## Layer Impact Analysis\n\n" + _layer_table("data-access", rows)
    return overview + "\n" + section + "\n"


def test_should_report_complete_when_every_item_answered(
    engine: ModuleType, registry: object
) -> None:
    result = engine.check_completeness(_complete_design(), registry)
    assert result.complete is True
    assert result.unfilled == []


def test_should_report_incomplete_when_a_cell_is_empty(
    engine: ModuleType, registry: object
) -> None:
    result = engine.check_completeness(_incomplete_design(""), registry)
    assert result.complete is False
    assert result.unfilled


def test_should_treat_whitespace_only_answer_as_unfilled(
    engine: ModuleType, registry: object
) -> None:
    result = engine.check_completeness(_incomplete_design("   "), registry)
    assert result.complete is False
    assert result.unfilled


def test_should_accept_reasoned_na_as_filled(
    engine: ModuleType, registry: object
) -> None:
    result = engine.check_completeness(
        _incomplete_design("N/A: no schema change, read-only"), registry
    )
    assert result.complete is True
    assert result.unfilled == []


def test_should_exit_zero_when_check_cli_sees_complete_design(
    tmp_path: Path,
) -> None:
    design = tmp_path / "design.md"
    design.write_text(_complete_design(), encoding="utf-8")
    result = _run_cli("check", "--design", str(design))
    assert result.returncode == 0


def test_should_exit_nonzero_and_list_cells_when_check_cli_sees_incomplete(
    tmp_path: Path,
) -> None:
    design = tmp_path / "design.md"
    design.write_text(_incomplete_design(""), encoding="utf-8")
    result = _run_cli("check", "--design", str(design))
    assert result.returncode == 2
    assert "data-access" in result.stdout


def test_should_exit_zero_when_check_cli_sees_no_touched_layer(
    tmp_path: Path,
) -> None:
    design = tmp_path / "design.md"
    design.write_text(_design_touching_no_layer(), encoding="utf-8")
    result = _run_cli("check", "--design", str(design))
    assert result.returncode == 0


# ── EC-003: registry absent / malformed ─────────────────────────────────


def test_should_raise_registry_error_when_registry_absent(
    engine: ModuleType, tmp_path: Path
) -> None:
    missing = tmp_path / "nope.yaml"
    with pytest.raises(engine.RegistryError, match="not found"):
        engine.load_registry(missing)


def test_should_raise_registry_error_when_registry_unreadable(
    engine: ModuleType, tmp_path: Path
) -> None:
    # A directory exists() but read_text() raises IsADirectoryError (OSError).
    a_dir = tmp_path / "registry_dir"
    a_dir.mkdir()
    with pytest.raises(engine.RegistryError, match="read error"):
        engine.load_registry(a_dir)


def test_should_raise_registry_error_when_registry_malformed(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("layers: [unclosed\n", encoding="utf-8")
    with pytest.raises(engine.RegistryError, match="parse error"):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_top_level_not_mapping(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(engine.RegistryError):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_item_field_missing(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n"
        "  - id: data-access\n"
        "    name: Data Access\n"
        "    detection_signals: [table]\n"
        "    rubric:\n"
        "      - id: x\n"
        "        criterion: missing other fields\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_quality_attribute_invalid(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n"
        "  - id: data-access\n"
        "    name: Data Access\n"
        "    detection_signals: [table]\n"
        "    rubric:\n"
        "      - id: x\n"
        "        criterion: c\n"
        "        quality_attribute: not_a_real_attribute\n"
        "        severity_if_missed: HIGH\n"
        "        mechanizable: true\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError, match="quality_attribute"):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_severity_invalid(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n"
        "  - id: data-access\n"
        "    name: Data Access\n"
        "    detection_signals: [table]\n"
        "    rubric:\n"
        "      - id: x\n"
        "        criterion: c\n"
        "        quality_attribute: reliability\n"
        "        severity_if_missed: SOMETIMES\n"
        "        mechanizable: true\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError, match="severity"):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_mechanizable_not_bool(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n"
        "  - id: data-access\n"
        "    name: Data Access\n"
        "    detection_signals: [table]\n"
        "    rubric:\n"
        "      - id: x\n"
        "        criterion: c\n"
        "        quality_attribute: reliability\n"
        "        severity_if_missed: HIGH\n"
        "        mechanizable: maybe\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError, match="mechanizable"):
        engine.load_registry(bad)


def test_should_exit_one_when_cli_design_file_absent(tmp_path: Path) -> None:
    result = _run_cli("detect", "--design", str(tmp_path / "missing.md"))
    assert result.returncode == 1
    assert "not found" in result.stderr.lower()


def test_should_exit_one_when_cli_registry_absent(tmp_path: Path) -> None:
    design = tmp_path / "design.md"
    design.write_text(_design_touching_data_access_only(), encoding="utf-8")
    result = _run_cli(
        "detect",
        "--design",
        str(design),
        "--registry",
        str(tmp_path / "missing.yaml"),
    )
    assert result.returncode == 1
    assert "registry" in result.stderr.lower()


def test_should_exit_two_for_usage_error_when_no_subcommand(
    tmp_path: Path,
) -> None:
    result = _run_cli()
    assert result.returncode == 2


def test_should_default_to_shipped_registry_when_no_registry_flag(
    engine: ModuleType,
) -> None:
    assert engine.DEFAULT_REGISTRY == REGISTRY_PATH


# ── In-process main() dispatch (coverage of the CLI surface) ─────────────


def test_should_print_touched_layers_when_main_detect(
    engine: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    design = tmp_path / "design.md"
    design.write_text(_design_touching_data_access_only(), encoding="utf-8")
    code = engine.main(["detect", "--design", str(design)])
    out = capsys.readouterr().out
    assert code == 0
    assert json.loads(out) == ["data-access"]


def test_should_return_zero_when_main_check_complete(
    engine: ModuleType, tmp_path: Path
) -> None:
    design = tmp_path / "design.md"
    design.write_text(_complete_design(), encoding="utf-8")
    assert engine.main(["check", "--design", str(design)]) == 0


def test_should_return_two_and_list_cells_when_main_check_incomplete(
    engine: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    design = tmp_path / "design.md"
    design.write_text(_incomplete_design(""), encoding="utf-8")
    code = engine.main(["check", "--design", str(design)])
    out = capsys.readouterr().out
    assert code == 2
    assert "data-access/" in out


def test_should_return_one_when_main_design_absent(
    engine: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = engine.main(["detect", "--design", str(tmp_path / "missing.md")])
    err = capsys.readouterr().err
    assert code == 1
    assert "not found" in err.lower()


def test_should_return_one_when_main_registry_absent(
    engine: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    design = tmp_path / "design.md"
    design.write_text(_design_touching_data_access_only(), encoding="utf-8")
    code = engine.main(
        [
            "check",
            "--design",
            str(design),
            "--registry",
            str(tmp_path / "missing.yaml"),
        ]
    )
    err = capsys.readouterr().err
    assert code == 1
    assert "registry" in err.lower()


def test_should_return_one_when_main_design_is_directory(
    engine: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a_dir = tmp_path / "design_dir"
    a_dir.mkdir()
    code = engine.main(["detect", "--design", str(a_dir)])
    err = capsys.readouterr().err
    assert code == 1
    assert "read" in err.lower()


def test_should_raise_usage_exit_when_main_has_no_subcommand(
    engine: ModuleType,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        engine.main([])
    assert exc_info.value.code == 2


def test_should_raise_registry_error_when_layers_not_a_list(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("layers: 5\ncross_cutting_concerns: []\n", encoding="utf-8")
    with pytest.raises(engine.RegistryError, match="layers"):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_layer_entry_not_mapping(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n  - just-a-string\ncross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError, match="mapping"):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_layer_missing_name(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n"
        "  - id: x\n"
        "    detection_signals: [foo]\n"
        "    rubric: []\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError, match="name"):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_detection_signals_missing(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n"
        "  - id: x\n"
        "    name: X\n"
        "    rubric:\n"
        "      - id: i\n"
        "        criterion: c\n"
        "        quality_attribute: reliability\n"
        "        severity_if_missed: LOW\n"
        "        mechanizable: false\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError, match="detection_signals"):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_rubric_item_not_mapping(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n"
        "  - id: x\n"
        "    name: X\n"
        "    detection_signals: [foo]\n"
        "    rubric:\n"
        "      - just-a-string\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError, match="mapping"):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_criterion_blank(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n"
        "  - id: x\n"
        "    name: X\n"
        "    detection_signals: [foo]\n"
        "    rubric:\n"
        "      - id: i\n"
        "        criterion: '   '\n"
        "        quality_attribute: reliability\n"
        "        severity_if_missed: LOW\n"
        "        mechanizable: false\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError, match="criterion"):
        engine.load_registry(bad)


# ── Detection nuance + cross-cutting walk parsing ────────────────────────


def test_should_not_match_signal_inside_a_larger_word(
    engine: ModuleType, registry: object
) -> None:
    text = (
        "# Design\n\n## Architecture Overview\n\n"
        "The comfortable, portable layout is uneditable.\n"
    )
    assert engine.detect_layers(text, registry) == []


def test_should_skip_unparseable_subsection_table_rows(
    engine: ModuleType, registry: object
) -> None:
    # A two-column table under a touched layer leaves cells unfilled.
    design = (
        _design_touching_data_access_only()
        + "\n## Layer Impact Analysis\n\n### data-access\n\n"
        + "| Item | Criterion |\n|------|-----------|\n"
        + "| da-index-coverage | just two columns |\n"
    )
    result = engine.check_completeness(design, registry)
    assert result.complete is False


def test_should_report_complete_in_process_when_no_layer_touched(
    engine: ModuleType, registry: object
) -> None:
    result = engine.check_completeness(_design_touching_no_layer(), registry)
    assert result.complete is True
    assert result.unfilled == []


def test_should_stop_parsing_at_heading_after_analysis_section(
    engine: ModuleType, registry: object
) -> None:
    rows = [
        (item.id, "answered")
        for item in next(
            layer for layer in registry.layers if layer.id == "data-access"  # type: ignore[attr-defined]
        ).rubric
    ]
    design = (
        _design_touching_data_access_only()
        + "\n## Layer Impact Analysis\n\n"
        + _layer_table("data-access", rows)
        + "\n## Some Later Section\n\n| da-index-coverage | x | | LOW |\n"
    )
    # The later section's stray row must NOT be parsed; completeness holds.
    result = engine.check_completeness(design, registry)
    assert result.complete is True


def test_should_raise_registry_error_when_layer_missing_id(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n"
        "  - name: X\n"
        "    detection_signals: [foo]\n"
        "    rubric:\n"
        "      - id: i\n"
        "        criterion: c\n"
        "        quality_attribute: reliability\n"
        "        severity_if_missed: LOW\n"
        "        mechanizable: false\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError, match="id"):
        engine.load_registry(bad)


def test_should_raise_registry_error_when_rubric_empty(
    engine: ModuleType, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "layers:\n"
        "  - id: x\n"
        "    name: X\n"
        "    detection_signals: [foo]\n"
        "    rubric: []\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    with pytest.raises(engine.RegistryError, match="rubric"):
        engine.load_registry(bad)


def test_should_ignore_blank_detection_signal_token(
    engine: ModuleType, tmp_path: Path
) -> None:
    reg_yaml = tmp_path / "reg.yaml"
    reg_yaml.write_text(
        "layers:\n"
        "  - id: x\n"
        "    name: X\n"
        "    detection_signals: ['   ', table]\n"
        "    rubric:\n"
        "      - id: i\n"
        "        criterion: c\n"
        "        quality_attribute: reliability\n"
        "        severity_if_missed: LOW\n"
        "        mechanizable: false\n"
        "cross_cutting_concerns: []\n",
        encoding="utf-8",
    )
    reg = engine.load_registry(reg_yaml)
    # The blank token is ignored; "table" still matches.
    assert engine.detect_layers("uses a table here", reg) == ["x"]
    assert engine.detect_layers("nothing relevant", reg) == []


def test_should_exclude_section_then_resume_at_sibling_heading(
    engine: ModuleType, registry: object
) -> None:
    design = (
        "# Design\n\n"
        "## Out of Scope\n\n"
        "Touching the filings table or its index.\n\n"
        "## Architecture Overview\n\n"
        "We add a migration and an index on the status column.\n"
    )
    # The data-access signals in Out-of-Scope are excluded, but the ones in
    # the resumed Architecture Overview section ARE detected.
    assert engine.detect_layers(design, registry) == ["data-access"]
