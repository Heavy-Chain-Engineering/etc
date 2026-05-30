"""Tests for scripts/lesson_gate_audit.py (F-2026-05-30 lessons-terminate-in-gates).

Covers task 001.001: the classifier core, the dual-shape frontmatter parse,
and memory-dir resolution. The CLI + audit_memory_dir are built by the sibling
task 001.002 on top of these functions and are not exercised here.

The engine exposes pure functions under a CLI (mirrors
scripts/layer_review.py + scripts/value_hypothesis.py); scripts/ is not a
package, so the module is loaded by path:
    - resolve_memory_dir(override=None) -> Path
    - parse_frontmatter(text) -> dict | None
    - classify_lesson(frontmatter, filename, repo_root) -> tuple[str, str]
    - LessonRecord / AuditReport (frozen dataclasses)

Classification literals: gated | none-yet | note-only | missing | dangling,
plus the caller-skip sentinel `exempt` for non-lesson memories.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "lesson_gate_audit.py"


def _load_module() -> ModuleType:
    """Import scripts/lesson_gate_audit.py directly (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("lesson_gate_audit", MODULE_PATH)
    if spec is None or spec.loader is None:
        msg = f"Cannot load module at {MODULE_PATH}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lesson_gate_audit"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def engine() -> ModuleType:
    """Module under test, imported once per test module."""
    return _load_module()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway repo root seeded with a couple of real gate paths."""
    (tmp_path / "standards" / "process").mkdir(parents=True)
    (tmp_path / "standards" / "process" / "real-gate.md").write_text("gate")
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "check-thing.sh").write_text("#!/bin/sh\n")
    (tmp_path / "skills" / "metrics").mkdir(parents=True)
    (tmp_path / "skills" / "metrics" / "SKILL.md").write_text("# skill")
    return tmp_path


# ── resolve_memory_dir (AC-1, AC-7 resolution half) ─────────────────────


def test_should_default_to_cwd_slug_memory_dir_when_no_override(
    engine: ModuleType,
) -> None:
    result = engine.resolve_memory_dir()

    slug = str(Path.cwd()).replace("/", "-")
    expected = Path.home() / ".claude" / "projects" / slug / "memory"
    assert result == expected


def test_should_short_circuit_default_when_override_given(
    engine: ModuleType, tmp_path: Path
) -> None:
    override = tmp_path / "elsewhere" / "memory"

    result = engine.resolve_memory_dir(override)

    assert result == override


# ── dataclass surface (AC-1) ────────────────────────────────────────────


def test_should_expose_frozen_lesson_record_with_named_fields(
    engine: ModuleType, tmp_path: Path
) -> None:
    record = engine.LessonRecord(
        name="feedback-x",
        path=tmp_path / "feedback-x.md",
        classification="gated",
        terminates_in=["standards/process/real-gate.md"],
        detail="",
    )

    with pytest.raises((AttributeError, TypeError)):
        record.classification = "dangling"  # type: ignore[misc]


def test_should_expose_frozen_audit_report_with_named_fields(
    engine: ModuleType,
) -> None:
    report = engine.AuditReport(records=[], counts={"gated": 0}, gated_pct=0.0, memory_dir="/x")

    assert report.counts == {"gated": 0}
    assert report.gated_pct == 0.0
    assert report.memory_dir == "/x"


# ── parse_frontmatter: dual shape + degrade (AC-2, AC-3) ────────────────


def test_should_parse_nested_metadata_type_shape(engine: ModuleType) -> None:
    text = "---\nname: feedback-x\nmetadata:\n  node_type: memory\n  type: feedback\n---\n\nbody\n"

    parsed = engine.parse_frontmatter(text)

    assert parsed is not None
    assert parsed["metadata"]["type"] == "feedback"


def test_should_parse_flat_top_level_type_shape(engine: ModuleType) -> None:
    text = "---\nname: lessons-x\ntype: project\n---\n\nbody\n"

    parsed = engine.parse_frontmatter(text)

    assert parsed is not None
    assert parsed["type"] == "project"


def test_should_return_none_when_frontmatter_absent(engine: ModuleType) -> None:
    assert engine.parse_frontmatter("no frontmatter here\njust body\n") is None


def test_should_return_none_when_frontmatter_malformed(engine: ModuleType) -> None:
    text = "---\nname: [unterminated\n  bad: : :\n---\nbody\n"

    assert engine.parse_frontmatter(text) is None


# ── union classifier (AC-2, ADR-001) ────────────────────────────────────


def test_should_classify_non_lesson_memory_as_exempt(engine: ModuleType, repo: Path) -> None:
    frontmatter = {"name": "venlink-standard", "type": "reference"}

    classification, _ = engine.classify_lesson(frontmatter, "venlink-standard.md", repo)

    assert classification == "exempt"


def test_should_treat_lessons_named_file_typed_project_as_lesson_class(
    engine: ModuleType, repo: Path
) -> None:
    # The live mis-typed case: filename startswith lessons- but type=project.
    frontmatter = {"name": "Fake Client Fidelity", "type": "project"}

    classification, _ = engine.classify_lesson(frontmatter, "lessons-fake-client-fidelity.md", repo)

    # Lesson-class by filename, terminates_in absent -> missing (not exempt).
    assert classification == "missing"


def test_should_treat_type_feedback_as_lesson_class_without_filename_prefix(
    engine: ModuleType, repo: Path
) -> None:
    frontmatter = {"metadata": {"type": "feedback"}}

    classification, _ = engine.classify_lesson(frontmatter, "weird-name.md", repo)

    assert classification == "missing"


# ── classification algorithm (AC-3..6) ──────────────────────────────────


def test_should_classify_missing_when_terminates_in_absent(engine: ModuleType, repo: Path) -> None:
    classification, _ = engine.classify_lesson({"type": "feedback"}, "feedback-x.md", repo)

    assert classification == "missing"


def test_should_classify_note_only_when_terminates_in_is_note_only(
    engine: ModuleType, repo: Path
) -> None:
    frontmatter = {"type": "feedback", "terminates_in": "note-only"}

    classification, _ = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "note-only"


def test_should_classify_none_yet_when_tracker_token_present(
    engine: ModuleType, repo: Path
) -> None:
    frontmatter = {"type": "feedback", "terminates_in": "none-yet: #42"}

    classification, _ = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "none-yet"


def test_should_downgrade_none_yet_to_missing_when_tracker_absent(
    engine: ModuleType, repo: Path
) -> None:
    frontmatter = {"type": "feedback", "terminates_in": "none-yet"}

    classification, detail = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "missing"
    assert detail == "none-yet without tracker"


def test_should_classify_gated_when_path_exists(engine: ModuleType, repo: Path) -> None:
    frontmatter = {
        "type": "feedback",
        "terminates_in": "standards/process/real-gate.md",
    }

    classification, _ = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "gated"


def test_should_classify_dangling_when_path_missing(engine: ModuleType, repo: Path) -> None:
    frontmatter = {
        "type": "feedback",
        "terminates_in": "standards/process/ghost-gate.md",
    }

    classification, _ = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "dangling"


def test_should_strip_anchor_and_step_descriptor_before_resolving(
    engine: ModuleType, repo: Path
) -> None:
    # A skill-step ref with both an anchor and a trailing Step N descriptor:
    # only the leading SKILL.md path token is resolved.
    frontmatter = {
        "type": "feedback",
        "terminates_in": "skills/metrics/SKILL.md#feedback-loop Step 4",
    }

    classification, _ = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "gated"


def test_should_strip_colon_line_descriptor_before_resolving(
    engine: ModuleType, repo: Path
) -> None:
    frontmatter = {
        "type": "feedback",
        "terminates_in": "hooks/check-thing.sh:12",
    }

    classification, _ = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "gated"


def test_should_classify_gated_when_every_list_entry_exists(engine: ModuleType, repo: Path) -> None:
    frontmatter = {
        "type": "feedback",
        "terminates_in": [
            "standards/process/real-gate.md",
            "hooks/check-thing.sh",
        ],
    }

    classification, _ = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "gated"


def test_should_classify_dangling_when_one_list_entry_missing(
    engine: ModuleType, repo: Path
) -> None:
    frontmatter = {
        "type": "feedback",
        "terminates_in": [
            "standards/process/real-gate.md",
            "hooks/ghost.sh",
        ],
    }

    classification, _ = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "dangling"


def test_should_classify_missing_when_lesson_named_but_frontmatter_unparseable(
    engine: ModuleType, repo: Path
) -> None:
    # The caller passes None when parse_frontmatter failed; a lesson-by-filename
    # still classifies (degrades to missing) rather than crashing.
    classification, detail = engine.classify_lesson(None, "feedback-broken.md", repo)

    assert classification == "missing"
    assert detail == "frontmatter unparseable"


def test_should_classify_unparseable_non_lesson_file_as_exempt(
    engine: ModuleType, repo: Path
) -> None:
    classification, _ = engine.classify_lesson(None, "venlink-standard.md", repo)

    assert classification == "exempt"


def test_should_not_open_or_disclose_a_traversal_path_value(engine: ModuleType, repo: Path) -> None:
    # A ../../-style value yields only a boolean existence result; the engine
    # never reads it. Resolving outside the repo simply does not exist here.
    frontmatter = {
        "type": "feedback",
        "terminates_in": "../../../../etc/passwd",
    }

    classification, _ = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "dangling"


# ── defensive degrade branches (never-crash contract) ──────────────────


def test_should_return_none_when_frontmatter_is_a_yaml_scalar(
    engine: ModuleType,
) -> None:
    # A frontmatter block that parses to a non-mapping (a bare scalar) is not
    # a usable mapping and degrades to None rather than crashing downstream.
    text = "---\njust a scalar string\n---\nbody\n"

    assert engine.parse_frontmatter(text) is None


def test_should_classify_missing_when_terminates_in_is_a_mapping(
    engine: ModuleType, repo: Path
) -> None:
    # An unexpected YAML shape (mapping) for terminates_in is an open loop,
    # not a crash.
    frontmatter = {"type": "feedback", "terminates_in": {"unexpected": "shape"}}

    classification, detail = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "missing"
    assert "unrecognized terminates_in shape" in detail


def test_should_classify_dangling_when_path_token_is_empty_after_strip(
    engine: ModuleType, repo: Path
) -> None:
    # A value that is nothing but a descriptor strips to an empty token, which
    # cannot resolve to any gate -> dangling (never a path read).
    frontmatter = {"type": "feedback", "terminates_in": "#only-an-anchor"}

    classification, _ = engine.classify_lesson(frontmatter, "feedback-x.md", repo)

    assert classification == "dangling"


def test_should_treat_non_string_type_as_non_lesson_when_filename_neutral(
    engine: ModuleType, repo: Path
) -> None:
    # A non-string type with a neutral filename reads as no declared type and
    # is exempt (the caller skips it).
    frontmatter = {"type": 123, "metadata": {"type": []}}

    classification, _ = engine.classify_lesson(frontmatter, "neutral-name.md", repo)

    assert classification == "exempt"


# ── audit_memory_dir + CLI (task 001.002) ──────────────────────────────


def _write(path: Path, body: str) -> None:
    """Write a memory file, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def memory(tmp_path: Path) -> Path:
    """A memory dir holding one of each lesson-class verdict + non-lessons.

    The seeded gate-refs (standards/process/real-gate.md, hooks/ghost.sh) are
    resolved at audit time against whatever ``repo_root`` the consuming test
    passes — every consumer requests the ``repo`` fixture itself and passes it
    as ``repo_root`` — so this fixture only builds the memory files.
    """
    mem = tmp_path / "memory"
    # gated — a present gate path
    _write(
        mem / "feedback-gated.md",
        "---\ntype: feedback\nterminates_in: standards/process/real-gate.md\n---\nbody\n",
    )
    # missing — terminates_in absent
    _write(mem / "feedback-missing.md", "---\ntype: feedback\n---\nbody\n")
    # dangling — gate path does not exist
    _write(
        mem / "feedback-dangling.md",
        "---\ntype: feedback\nterminates_in: hooks/ghost.sh\n---\nbody\n",
    )
    # note-only
    _write(
        mem / "feedback-note.md",
        "---\ntype: feedback\nterminates_in: note-only\n---\nbody\n",
    )
    # none-yet with tracker
    _write(
        mem / "feedback-noneyet.md",
        '---\ntype: feedback\nterminates_in: "none-yet: #42"\n---\nbody\n',
    )
    # non-lesson exempt file — must be excluded from records entirely
    _write(mem / "venlink-standard.md", "---\ntype: reference\n---\nbody\n")
    # malformed frontmatter, lesson-class by filename -> missing
    _write(mem / "feedback-broken.md", "---\nname: [unterminated\n bad: : :\n---\nbody\n")
    # MEMORY.md — index file, always skipped
    _write(mem / "MEMORY.md", "---\ntype: feedback\n---\nindex\n")
    return mem


def test_should_collect_one_record_per_lesson_class_file_excluding_exempt(
    engine: ModuleType, memory: Path, repo: Path
) -> None:
    report = engine.audit_memory_dir(memory, repo)

    names = {record.name for record in report.records}
    # 6 lesson-class files; the reference file + MEMORY.md are excluded.
    assert names == {
        "feedback-gated",
        "feedback-missing",
        "feedback-dangling",
        "feedback-note",
        "feedback-noneyet",
        "feedback-broken",
    }


def test_should_classify_each_record_by_its_terminates_in(
    engine: ModuleType, memory: Path, repo: Path
) -> None:
    report = engine.audit_memory_dir(memory, repo)
    by_name = {record.name: record.classification for record in report.records}

    assert by_name["feedback-gated"] == "gated"
    assert by_name["feedback-missing"] == "missing"
    assert by_name["feedback-dangling"] == "dangling"
    assert by_name["feedback-note"] == "note-only"
    assert by_name["feedback-noneyet"] == "none-yet"
    assert by_name["feedback-broken"] == "missing"


def test_should_count_each_status_and_compute_gated_pct(
    engine: ModuleType, memory: Path, repo: Path
) -> None:
    report = engine.audit_memory_dir(memory, repo)

    assert report.counts["gated"] == 1
    assert report.counts["missing"] == 2
    assert report.counts["dangling"] == 1
    assert report.counts["note-only"] == 1
    assert report.counts["none-yet"] == 1
    # 1 gated of 6 lesson-class files.
    assert report.gated_pct == pytest.approx(1 / 6)


def test_should_skip_memory_index_file(engine: ModuleType, memory: Path, repo: Path) -> None:
    report = engine.audit_memory_dir(memory, repo)

    assert all(record.name != "MEMORY" for record in report.records)


def test_should_report_zero_pct_without_zerodivision_when_empty(
    engine: ModuleType, tmp_path: Path, repo: Path
) -> None:
    empty = tmp_path / "empty-memory"
    empty.mkdir()

    report = engine.audit_memory_dir(empty, repo)

    assert report.records == []
    assert report.gated_pct == 0.0


def test_should_return_clean_report_when_memory_dir_absent(
    engine: ModuleType, tmp_path: Path, repo: Path
) -> None:
    absent = tmp_path / "does-not-exist"

    report = engine.audit_memory_dir(absent, repo)

    assert report.records == []
    assert report.gated_pct == 0.0
    assert report.memory_dir == str(absent)


# ── CLI: JSON contract (the /metrics read contract) ─────────────────────


def test_should_emit_json_with_stable_top_level_keys(
    engine: ModuleType, memory: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = engine.main(
        [
            "audit",
            "--memory-dir",
            str(memory),
            "--repo-root",
            str(repo),
            "--format",
            "json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert list(payload.keys()) == ["counts", "gated_pct", "memory_dir", "records"]


def test_should_emit_json_records_with_contract_fields(
    engine: ModuleType, memory: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    engine.main(
        ["audit", "--memory-dir", str(memory), "--repo-root", str(repo)]
    )  # json is the default format

    payload = json.loads(capsys.readouterr().out)
    record = payload["records"][0]
    assert set(record.keys()) == {"name", "classification", "terminates_in", "detail"}


def test_should_default_format_to_json(
    engine: ModuleType, memory: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    engine.main(["audit", "--memory-dir", str(memory), "--repo-root", str(repo)])

    # Parses as JSON without an explicit --format json.
    payload = json.loads(capsys.readouterr().out)
    assert "gated_pct" in payload


# ── CLI: text contract ──────────────────────────────────────────────────


def test_should_emit_human_text_table_when_format_text(
    engine: ModuleType, memory: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = engine.main(
        ["audit", "--memory-dir", str(memory), "--repo-root", str(repo), "--format", "text"]
    )

    assert code == 0
    out = capsys.readouterr().out
    assert "feedback-gated" in out
    assert "gated" in out
    # Not JSON.
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


# ── CLI: advisory exit-0 contract (ADR-002, AC-7/8/12) ──────────────────


def test_should_exit_zero_when_memory_dir_absent(
    engine: ModuleType, tmp_path: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    absent = tmp_path / "nope"

    code = engine.main(
        ["audit", "--memory-dir", str(absent), "--repo-root", str(repo), "--format", "json"]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["records"] == []
    assert payload["gated_pct"] == 0.0


def test_should_exit_two_on_argparse_usage_error(engine: ModuleType) -> None:
    # An unknown subcommand is a usage error -> argparse SystemExit(2).
    with pytest.raises(SystemExit) as excinfo:
        engine.main(["bogus-subcommand"])

    assert excinfo.value.code == 2


# ── Live-corpus smoke (forward-only: all lesson-class are missing) ──────


def test_should_not_crash_on_live_corpus_and_all_missing(engine: ModuleType) -> None:
    live = engine.resolve_memory_dir()
    if not live.is_dir():
        pytest.skip(f"live memory dir absent: {live}")

    report = engine.audit_memory_dir(live, REPO_ROOT)

    # Forward-only: no live lesson has declared terminates_in yet.
    assert all(record.classification == "missing" for record in report.records)
    assert report.records, "expected lesson-class records in the live corpus"
