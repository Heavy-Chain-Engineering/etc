"""Tests for scripts/design_token_gate.py (#69 Layer-3 design-token gate).

One subcommand:
  scan --tokens <design-tokens.json>
       (--files <f...> | --dir <d> [--include <glob,glob>]) [--strict]
    → JSON {tokens_file, scanned_files, allowed_color_count,
            violations: [...], verdict} where verdict ∈ {CLEAN, VIOLATIONS}

The gate is advisory by default: exit 0 even with violations; only --strict
turns a VIOLATIONS verdict into exit 2. A missing/unreadable/empty tokens file
is a hard error (exit 1) — never a false "clean".

The tests build synthetic projects under pytest's tmp_path so the gate runs
against controlled inputs and never touches the real repo.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).parent.parent / "scripts" / "design_token_gate.py"


def _load_module() -> ModuleType:
    """Import design_token_gate.py in-process so its logic is unit-tested (and
    the branches are visible to coverage, which cannot trace subprocess calls).
    """
    spec = importlib.util.spec_from_file_location(
        "design_token_gate_under_test", SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


design_token_gate = _load_module()


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=20,
    )


def _write_tokens(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "design-tokens.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _flat_tokens() -> dict[str, object]:
    """A flat token map {name: color}: the gate collects leaf color strings."""
    return {
        "color-primary": "#3366ff",
        "color-bg": "#FFFFFF",
        "color-accent": "rgb(255, 0, 0)",
    }


def _w3c_tokens() -> dict[str, object]:
    """The W3C design-tokens shape: nested groups whose leaves are
    {"$value": "...", "$type": "color"}.
    """
    return {
        "color": {
            "primary": {"$value": "#3366ff", "$type": "color"},
            "surface": {"$value": "#ffffff", "$type": "color"},
        }
    }


# ── scan: violation detection ────────────────────────────────────────────────


def test_should_flag_hardcoded_hex_not_in_tokens_when_scanning(
    tmp_path: Path,
) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "VIOLATIONS"
    values = [v["value"] for v in payload["violations"]]
    assert "#abcdef" in values
    assert payload["violations"][0]["kind"] == "color"


def test_should_not_flag_color_present_in_tokens_when_scanning(
    tmp_path: Path,
) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: #3366ff; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    assert payload["verdict"] == "CLEAN"
    assert payload["violations"] == []


def test_should_report_file_and_line_when_violation_found(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: red; }\nb { color: #abcdef; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    violation = payload["violations"][0]
    assert violation["file"] == str(src)
    assert violation["line"] == 2


# ── scan: normalization ──────────────────────────────────────────────────────


def test_should_treat_3_digit_hex_as_equal_to_6_digit_when_scanning(
    tmp_path: Path,
) -> None:
    # Token defines #ffffff; source uses #fff — must NOT flag (same color).
    tokens = _write_tokens(tmp_path, {"bg": "#ffffff"})
    src = tmp_path / "styles.css"
    src.write_text("a { color: #fff; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    assert payload["verdict"] == "CLEAN"


def test_should_treat_hex_case_insensitively_when_scanning(tmp_path: Path) -> None:
    # Token defines #ABCDEF; source uses #abcdef — same color, not a violation.
    tokens = _write_tokens(tmp_path, {"accent": "#ABCDEF"})
    src = tmp_path / "styles.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    assert payload["verdict"] == "CLEAN"


def test_should_normalize_3_digit_token_to_match_6_digit_source(
    tmp_path: Path,
) -> None:
    # Token defines #fff; source uses #ffffff — same color.
    tokens = _write_tokens(tmp_path, {"bg": "#fff"})
    src = tmp_path / "styles.css"
    src.write_text("a { color: #ffffff; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    assert payload["verdict"] == "CLEAN"


# ── scan: CSS color functions ────────────────────────────────────────────────


def test_should_detect_rgb_function_violation_when_scanning(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: rgb(1, 2, 3); }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    assert payload["verdict"] == "VIOLATIONS"
    values = [v["value"] for v in payload["violations"]]
    assert any("rgb(1, 2, 3)" in value for value in values)


def test_should_detect_hsl_function_violation_when_scanning(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: hsl(120, 50%, 50%); }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    assert payload["verdict"] == "VIOLATIONS"


def test_should_not_flag_rgb_function_present_in_tokens(tmp_path: Path) -> None:
    # Token defines rgb(255, 0, 0); source uses the same (whitespace-normalized).
    tokens = _write_tokens(tmp_path, {"accent": "rgb(255, 0, 0)"})
    src = tmp_path / "styles.css"
    src.write_text("a { color: rgb(255,0,0); }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    assert payload["verdict"] == "CLEAN"


# ── scan: W3C token shape ────────────────────────────────────────────────────


def test_should_collect_allowed_colors_from_w3c_value_shape(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _w3c_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: #3366ff; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    assert payload["verdict"] == "CLEAN"
    assert payload["allowed_color_count"] == 2


def test_should_flag_violation_against_w3c_token_shape(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _w3c_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: #112233; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    assert payload["verdict"] == "VIOLATIONS"


# ── scan: directory + include globs + skip-list ──────────────────────────────


def test_should_scan_directory_with_default_globs_when_dir_given(
    tmp_path: Path,
) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.css").write_text("a { color: #abcdef; }\n", encoding="utf-8")
    (project / "b.tsx").write_text(
        "const c = '#fedcba';\n", encoding="utf-8"
    )

    result = _run("scan", "--tokens", str(tokens), "--dir", str(project))

    payload = json.loads(result.stdout)
    files = [v["value"] for v in payload["violations"]]
    assert "#abcdef" in files
    assert "#fedcba" in files
    assert payload["verdict"] == "VIOLATIONS"


def test_should_honor_include_globs_when_scanning_directory(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.css").write_text("a { color: #abcdef; }\n", encoding="utf-8")
    (project / "b.txt").write_text("color: #fedcba;\n", encoding="utf-8")

    result = _run(
        "scan",
        "--tokens",
        str(tokens),
        "--dir",
        str(project),
        "--include",
        "*.css",
    )

    payload = json.loads(result.stdout)
    values = [v["value"] for v in payload["violations"]]
    assert "#abcdef" in values
    # b.txt is excluded by the include glob.
    assert "#fedcba" not in values


def test_should_skip_node_modules_and_dist_when_scanning_directory(
    tmp_path: Path,
) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    project = tmp_path / "project"
    (project / "node_modules").mkdir(parents=True)
    (project / "dist").mkdir(parents=True)
    (project / "node_modules" / "vendor.css").write_text(
        "a { color: #abcdef; }\n", encoding="utf-8"
    )
    (project / "dist" / "bundle.css").write_text(
        "a { color: #fedcba; }\n", encoding="utf-8"
    )
    (project / "app.css").write_text("a { color: #010203; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--dir", str(project))

    payload = json.loads(result.stdout)
    values = [v["value"] for v in payload["violations"]]
    assert "#010203" in values
    assert "#abcdef" not in values
    assert "#fedcba" not in values


def test_should_skip_the_tokens_file_itself_when_scanning_directory(
    tmp_path: Path,
) -> None:
    # The tokens file lives inside the scanned dir; its own color literals
    # must never be reported as violations.
    project = tmp_path / "project"
    project.mkdir()
    tokens = project / "design-tokens.json"
    tokens.write_text(json.dumps({"bg": "#abcdef"}), encoding="utf-8")
    (project / "app.css").write_text("a { color: #abcdef; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--dir", str(project))

    payload = json.loads(result.stdout)
    # #abcdef is a defined token, and the tokens file is skipped — CLEAN.
    assert payload["verdict"] == "CLEAN"


# ── scan: advisory vs strict ─────────────────────────────────────────────────


def test_should_exit_0_when_violations_and_not_strict(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "VIOLATIONS"


def test_should_exit_2_when_violations_and_strict(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    result = _run(
        "scan", "--tokens", str(tokens), "--files", str(src), "--strict"
    )

    assert result.returncode == 2


def test_should_exit_0_when_clean_and_strict(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: #3366ff; }\n", encoding="utf-8")

    result = _run(
        "scan", "--tokens", str(tokens), "--files", str(src), "--strict"
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "CLEAN"


# ── scan: tokens-file error handling ─────────────────────────────────────────


def test_should_exit_1_when_tokens_file_missing(tmp_path: Path) -> None:
    src = tmp_path / "styles.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    result = _run(
        "scan", "--tokens", str(tmp_path / "absent.json"), "--files", str(src)
    )

    assert result.returncode == 1
    assert "ERROR" in result.stderr


def test_should_exit_1_when_tokens_file_empty(tmp_path: Path) -> None:
    tokens = tmp_path / "design-tokens.json"
    tokens.write_text("", encoding="utf-8")
    src = tmp_path / "styles.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    assert result.returncode == 1
    assert "ERROR" in result.stderr


def test_should_exit_1_when_tokens_file_unparseable(tmp_path: Path) -> None:
    tokens = tmp_path / "design-tokens.json"
    tokens.write_text("{not valid json", encoding="utf-8")
    src = tmp_path / "styles.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    assert result.returncode == 1
    assert "ERROR" in result.stderr


# ── scan: skip flag + usage ──────────────────────────────────────────────────


def test_should_report_scanned_files_and_token_count_in_payload(
    tmp_path: Path,
) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: #3366ff; }\n", encoding="utf-8")

    result = _run("scan", "--tokens", str(tokens), "--files", str(src))

    payload = json.loads(result.stdout)
    assert payload["tokens_file"] == str(tokens)
    assert str(src) in payload["scanned_files"]
    assert payload["allowed_color_count"] == 3


def test_should_exit_1_when_neither_files_nor_dir_given(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())

    result = _run("scan", "--tokens", str(tokens))

    assert result.returncode == 1
    assert "ERROR" in result.stderr


def test_should_proceed_with_skip_flag_when_reason_present(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    result = _run(
        "scan",
        "--tokens",
        str(tokens),
        "--files",
        str(src),
        "--strict",
        "--skip-design-token-gate",
        "operator override: legacy CSS, tracked in #99",
    )

    assert result.returncode == 0
    assert "operator override" in result.stdout


def test_should_exit_1_when_skip_reason_empty(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "styles.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    result = _run(
        "scan",
        "--tokens",
        str(tokens),
        "--files",
        str(src),
        "--skip-design-token-gate",
        "",
    )

    assert result.returncode == 1
    assert "ERROR" in result.stderr


# ── in-process unit tests (logic + full-branch coverage) ─────────────────────


def test_should_normalize_3_digit_hex_to_6_digit() -> None:
    assert design_token_gate.normalize_color("#fff") == "#ffffff"
    assert design_token_gate.normalize_color("#ABC") == "#aabbcc"


def test_should_normalize_6_digit_hex_to_lowercase() -> None:
    assert design_token_gate.normalize_color("#ABCDEF") == "#abcdef"


def test_should_normalize_8_digit_hex_to_lowercase() -> None:
    assert design_token_gate.normalize_color("#AABBCCDD") == "#aabbccdd"


def test_should_normalize_rgb_function_whitespace() -> None:
    assert design_token_gate.normalize_color("rgb(255, 0, 0)") == "rgb(255,0,0)"
    assert design_token_gate.normalize_color("RGB( 255,0,0 )") == "rgb(255,0,0)"


def test_should_return_none_when_value_is_not_a_color() -> None:
    assert design_token_gate.normalize_color("not a color") is None
    assert design_token_gate.normalize_color("16px") is None
    assert design_token_gate.normalize_color("#gg") is None


def test_should_collect_leaf_colors_from_flat_map() -> None:
    allowed = design_token_gate.collect_allowed_colors(_flat_tokens())

    assert design_token_gate.normalize_color("#3366ff") in allowed
    assert design_token_gate.normalize_color("rgb(255, 0, 0)") in allowed


def test_should_collect_leaf_colors_from_w3c_value_shape_in_process() -> None:
    allowed = design_token_gate.collect_allowed_colors(_w3c_tokens())

    assert design_token_gate.normalize_color("#3366ff") in allowed
    assert len(allowed) == 2


def test_should_ignore_non_color_leaves_when_collecting() -> None:
    payload = {"spacing": "16px", "font": "Inter", "n": 4, "flag": True}

    allowed = design_token_gate.collect_allowed_colors(payload)

    assert allowed == frozenset()


def test_should_collect_colors_from_nested_lists() -> None:
    payload = {"palette": ["#111111", "#222222", "16px"]}

    allowed = design_token_gate.collect_allowed_colors(payload)

    assert design_token_gate.normalize_color("#111111") in allowed
    assert design_token_gate.normalize_color("#222222") in allowed


def test_should_find_color_literals_in_a_line() -> None:
    found = design_token_gate.find_color_literals(
        "color: #abc; background: rgb(1,2,3); border: 1px solid #112233;"
    )

    assert "#abc" in found
    assert "rgb(1,2,3)" in found
    assert "#112233" in found


def test_should_load_tokens_returns_error_when_missing(tmp_path: Path) -> None:
    colors, error = design_token_gate.load_allowed_colors(tmp_path / "nope.json")

    assert colors is None
    assert error is not None


def test_should_load_tokens_returns_error_when_empty(tmp_path: Path) -> None:
    path = tmp_path / "design-tokens.json"
    path.write_text("   \n", encoding="utf-8")

    colors, error = design_token_gate.load_allowed_colors(path)

    assert colors is None
    assert error is not None


def test_should_load_tokens_returns_colors_when_valid(tmp_path: Path) -> None:
    path = _write_tokens(tmp_path, _flat_tokens())

    colors, error = design_token_gate.load_allowed_colors(path)

    assert error is None
    assert colors is not None
    assert design_token_gate.normalize_color("#3366ff") in colors


def test_should_resolve_skip_reason_to_none_when_blank() -> None:
    assert design_token_gate._resolve_skip("   ") is None
    assert design_token_gate._resolve_skip(None) is None
    assert design_token_gate._resolve_skip("ok") == "ok"


def test_should_scan_files_and_return_violations(tmp_path: Path) -> None:
    src = tmp_path / "a.css"
    src.write_text("x { color: #abcdef; }\n", encoding="utf-8")
    allowed = frozenset({"#3366ff"})

    violations = design_token_gate.scan_files([src], allowed)

    assert len(violations) == 1
    assert violations[0].value == "#abcdef"
    assert violations[0].line == 1


def test_should_skip_unreadable_file_when_scanning(tmp_path: Path) -> None:
    # A directory passed where a file is expected is unreadable as text;
    # the scanner must skip it rather than crash.
    allowed = frozenset({"#3366ff"})

    violations = design_token_gate.scan_files([tmp_path], allowed)

    assert violations == []


def test_should_collect_default_globs_when_no_include(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()
    (project / "a.css").write_text("a{}", encoding="utf-8")
    (project / "b.md").write_text("# doc", encoding="utf-8")

    files = design_token_gate.collect_dir_files(project, None, None)

    names = {p.name for p in files}
    assert "a.css" in names
    assert "b.md" not in names


def test_should_main_returns_2_when_strict_and_violations(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "a.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    code = design_token_gate.main(
        ["scan", "--tokens", str(tokens), "--files", str(src), "--strict"]
    )

    assert code == 2


def test_should_main_returns_0_when_advisory_and_violations(
    tmp_path: Path, capsys
) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "a.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    code = design_token_gate.main(
        ["scan", "--tokens", str(tokens), "--files", str(src)]
    )
    captured = capsys.readouterr()

    assert code == 0
    payload = json.loads(captured.out)
    assert payload["verdict"] == "VIOLATIONS"


def test_should_main_returns_1_when_skip_reason_blank(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "a.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    code = design_token_gate.main(
        [
            "scan",
            "--tokens",
            str(tokens),
            "--files",
            str(src),
            "--skip-design-token-gate",
            "  ",
        ]
    )

    assert code == 1


def test_should_main_returns_0_with_skip_reason_recorded(
    tmp_path: Path, capsys
) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    src = tmp_path / "a.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    code = design_token_gate.main(
        [
            "scan",
            "--tokens",
            str(tokens),
            "--files",
            str(src),
            "--strict",
            "--skip-design-token-gate",
            "legacy CSS, tracked in #99",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    payload = json.loads(captured.out)
    assert payload["skip_reason"] == "legacy CSS, tracked in #99"


def test_should_main_returns_1_when_no_files_or_dir(tmp_path: Path) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())

    code = design_token_gate.main(["scan", "--tokens", str(tokens)])

    assert code == 1


def test_should_main_returns_1_when_tokens_missing(tmp_path: Path) -> None:
    src = tmp_path / "a.css"
    src.write_text("a { color: #abcdef; }\n", encoding="utf-8")

    code = design_token_gate.main(
        ["scan", "--tokens", str(tmp_path / "absent.json"), "--files", str(src)]
    )

    assert code == 1


def test_should_main_scans_dir_with_include_globs(tmp_path: Path, capsys) -> None:
    tokens = _write_tokens(tmp_path, _flat_tokens())
    project = tmp_path / "p"
    project.mkdir()
    (project / "a.css").write_text("a { color: #abcdef; }\n", encoding="utf-8")
    (project / "b.txt").write_text("color: #fedcba;\n", encoding="utf-8")

    code = design_token_gate.main(
        [
            "scan",
            "--tokens",
            str(tokens),
            "--dir",
            str(project),
            "--include",
            "*.css",
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    payload = json.loads(captured.out)
    values = [v["value"] for v in payload["violations"]]
    assert "#abcdef" in values
    assert "#fedcba" not in values


def test_should_parse_include_to_none_when_blank() -> None:
    assert design_token_gate._parse_include(None) is None
    assert design_token_gate._parse_include("   ") is None
    assert design_token_gate._parse_include("*.css, *.scss") == ("*.css", "*.scss")


def test_should_render_payload_with_skip_reason() -> None:
    payload = design_token_gate._render_payload(
        Path("tokens.json"),
        [Path("a.css")],
        frozenset({"#ffffff"}),
        [],
        "an override reason",
    )

    assert payload["skip_reason"] == "an override reason"
    assert payload["verdict"] == "CLEAN"


def test_should_resolve_scan_files_from_dir_when_no_files(tmp_path: Path) -> None:
    tokens = tmp_path / "design-tokens.json"
    tokens.write_text("{}", encoding="utf-8")
    project = tmp_path / "p"
    project.mkdir()
    (project / "a.css").write_text("a{}", encoding="utf-8")
    args = argparse.Namespace(files=[], dir=str(project), include=None)

    resolved = design_token_gate._resolve_scan_files(args, tokens)

    assert any(path.name == "a.css" for path in resolved)


def test_should_load_tokens_returns_error_when_unparseable(tmp_path: Path) -> None:
    path = tmp_path / "design-tokens.json"
    path.write_text("{not json", encoding="utf-8")

    colors, error = design_token_gate.load_allowed_colors(path)

    assert colors is None
    assert error is not None
    assert "not valid JSON" in error


def test_should_not_append_violation_when_literal_in_allowed(tmp_path: Path) -> None:
    src = tmp_path / "a.css"
    src.write_text("x { color: #abcdef; }\n", encoding="utf-8")
    allowed = frozenset({"#abcdef"})

    violations = design_token_gate.scan_files([src], allowed)

    assert violations == []


def test_should_skip_directory_matched_by_glob(tmp_path: Path) -> None:
    # A directory named like a glob match (e.g. ends in .css) must be skipped:
    # collect_dir_files only collects files.
    project = tmp_path / "p"
    project.mkdir()
    (project / "weird.css").mkdir()
    (project / "real.css").write_text("a{}", encoding="utf-8")

    files = design_token_gate.collect_dir_files(project, ("*.css",), None)

    names = {p.name for p in files}
    assert "real.css" in names
    assert "weird.css" not in names


def test_should_skip_files_inside_skip_dirs(tmp_path: Path) -> None:
    project = tmp_path / "p"
    (project / "node_modules").mkdir(parents=True)
    (project / "node_modules" / "v.css").write_text("a{}", encoding="utf-8")
    (project / "app.css").write_text("a{}", encoding="utf-8")

    files = design_token_gate.collect_dir_files(project, ("*.css",), None)

    names = {p.name for p in files}
    assert "app.css" in names
    assert "v.css" not in names


def test_should_skip_tokens_file_in_collect_dir_files(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()
    tokens = project / "design-tokens.json"
    tokens.write_text("{}", encoding="utf-8")
    (project / "app.css").write_text("a{}", encoding="utf-8")

    files = design_token_gate.collect_dir_files(project, ("*",), tokens)

    assert tokens not in files
    assert any(p.name == "app.css" for p in files)
