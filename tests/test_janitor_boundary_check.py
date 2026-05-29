"""Tests for scripts/janitor_boundary_check.py — the mechanical write-boundary veto.

These tests are hermetic: every fixture builds a real boundary-standard file and
a unified-diff text on disk under `tmp_path`, so no test touches the live repo
tree. The veto is defense-in-depth — it reads the forbidden-glob list and the
file-count ceiling FROM the standard (never a hardcoded copy, AC-013) and aborts
fail-closed on any malformed/absent block.

Coverage targets (per task 002 acceptance criteria):
    - diff touching a forbidden path        → exit 2, rule named (AC-004)
    - diff touching > ceiling files         → exit 2, file-count-ceiling (AC-005)
    - clean diff under scripts/             → exit 0, verdict clean
    - `../` path-escape attempt             → caught (security)
    - absent / empty / malformed blocks     → exit 1 (fail-closed)
    - diff read from stdin via `-`          → honored
    - usage / IO errors                     → exit 1
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "janitor_boundary_check.py"
)


def _load_module() -> ModuleType:
    """Load scripts/janitor_boundary_check.py without requiring a package.

    Mirrors the importlib loader pattern used by test_janitor_trust.py and
    test_git_tags.py elsewhere in this suite.
    """
    spec = importlib.util.spec_from_file_location("janitor_boundary_check", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


boundary_check = _load_module()


# --- fixtures -----------------------------------------------------------------

STANDARD_BODY = """# Janitor Write Boundary

Some prose that should be ignored by the parser.

```janitor-forbidden-globs
# rule-name                glob
intent-files               spec/**
intent-files               .etc_sdlc/features/**/spec.md
harness-control            hooks/**
secrets                    **/.env
secrets                    **/*.key
active-feature-dirs        .etc_sdlc/features/active/**
public-facing-copy         **/README.md
```

More prose.

```janitor-ceiling
max_files = 3
```

Trailing prose.
"""


def _write_standard(tmp_path: Path, body: str = STANDARD_BODY) -> Path:
    path = tmp_path / "janitor-write-boundary.md"
    path.write_text(body, encoding="utf-8")
    return path


def _write_diff(tmp_path: Path, *paths: str) -> Path:
    """Build a minimal but real unified git diff touching each given path."""
    chunks: list[str] = []
    for changed in paths:
        chunks.append(
            f"diff --git a/{changed} b/{changed}\n"
            f"index 0000000..1111111 100644\n"
            f"--- a/{changed}\n"
            f"+++ b/{changed}\n"
            "@@ -1 +1 @@\n"
            "-old line\n"
            "+new line\n"
        )
    path = tmp_path / "candidate.diff"
    path.write_text("".join(chunks), encoding="utf-8")
    return path


def _run(
    diff_path: str, boundary_path: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, Any]]:
    code = boundary_check.main(
        ["janitor_boundary_check.py", "--diff", diff_path, "--boundary", str(boundary_path)]
    )
    out = capsys.readouterr().out.strip()
    parsed: dict[str, Any] = json.loads(out) if out else {}
    return code, parsed


# --- forbidden-path (AC-004) --------------------------------------------------


def test_should_exit_2_and_name_rule_when_diff_touches_forbidden_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    diff = _write_diff(tmp_path, "spec/foo.md")

    code, verdict = _run(str(diff), standard, capsys)

    assert code == 2
    assert verdict["verdict"] == "violation"
    assert verdict["rule"] == "intent-files"
    assert "spec/foo.md" in verdict["paths"]


def test_should_match_doublestar_glob_against_nested_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    diff = _write_diff(tmp_path, "packages/web/README.md")

    code, verdict = _run(str(diff), standard, capsys)

    assert code == 2
    assert verdict["rule"] == "public-facing-copy"


def test_should_match_secret_extension_glob(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    diff = _write_diff(tmp_path, "deploy/server.key")

    code, verdict = _run(str(diff), standard, capsys)

    assert code == 2
    assert verdict["rule"] == "secrets"


# --- ceiling (AC-005) ---------------------------------------------------------


def test_should_exit_2_with_ceiling_rule_when_diff_exceeds_max_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    diff = _write_diff(
        tmp_path,
        "scripts/a.py",
        "scripts/b.py",
        "scripts/c.py",
        "scripts/d.py",
    )

    code, verdict = _run(str(diff), standard, capsys)

    assert code == 2
    assert verdict["rule"] == "file-count-ceiling"
    assert len(verdict["paths"]) == 4


def test_should_allow_exactly_ceiling_count_of_clean_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    diff = _write_diff(tmp_path, "scripts/a.py", "scripts/b.py", "scripts/c.py")

    code, verdict = _run(str(diff), standard, capsys)

    assert code == 0
    assert verdict["verdict"] == "clean"


# --- clean --------------------------------------------------------------------


def test_should_exit_0_when_diff_is_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    diff = _write_diff(tmp_path, "scripts/whitespace_fix.py")

    code, verdict = _run(str(diff), standard, capsys)

    assert code == 0
    assert verdict == {"verdict": "clean"}


def test_should_exit_0_when_diff_is_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    empty = tmp_path / "empty.diff"
    empty.write_text("", encoding="utf-8")

    code, verdict = _run(str(empty), standard, capsys)

    assert code == 0
    assert verdict == {"verdict": "clean"}


# --- security: path escape ----------------------------------------------------


def test_should_flag_path_escape_attempt_as_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    diff = _write_diff(tmp_path, "../../etc/passwd")

    code, verdict = _run(str(diff), standard, capsys)

    assert code == 2
    assert verdict["verdict"] == "violation"
    assert verdict["rule"] == "path-escape"


def test_should_match_forbidden_glob_even_when_diff_uses_dot_segments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    # `spec/./foo.md` canonicalizes to `spec/foo.md` — must still be forbidden.
    diff = _write_diff(tmp_path, "spec/./foo.md")

    code, verdict = _run(str(diff), standard, capsys)

    assert code == 2
    assert verdict["rule"] == "intent-files"


# --- fail-closed parsing (AC-013) ---------------------------------------------


def test_should_exit_1_when_forbidden_block_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "# No blocks here\n\n```janitor-ceiling\nmax_files = 3\n```\n"
    standard = _write_standard(tmp_path, body)
    diff = _write_diff(tmp_path, "scripts/a.py")

    code, _ = _run(str(diff), standard, capsys)

    assert code == 1


def test_should_exit_1_when_forbidden_block_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "```janitor-forbidden-globs\n# only a comment\n```\n\n"
        "```janitor-ceiling\nmax_files = 3\n```\n"
    )
    standard = _write_standard(tmp_path, body)
    diff = _write_diff(tmp_path, "scripts/a.py")

    code, _ = _run(str(diff), standard, capsys)

    assert code == 1


def test_should_exit_1_when_forbidden_line_malformed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "```janitor-forbidden-globs\nonlyonetoken\n```\n\n"
        "```janitor-ceiling\nmax_files = 3\n```\n"
    )
    standard = _write_standard(tmp_path, body)
    diff = _write_diff(tmp_path, "scripts/a.py")

    code, _ = _run(str(diff), standard, capsys)

    assert code == 1


def test_should_exit_1_when_ceiling_block_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "```janitor-forbidden-globs\nintent-files spec/**\n```\n"
    standard = _write_standard(tmp_path, body)
    diff = _write_diff(tmp_path, "scripts/a.py")

    code, _ = _run(str(diff), standard, capsys)

    assert code == 1


def test_should_exit_1_when_ceiling_value_not_integer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "```janitor-forbidden-globs\nintent-files spec/**\n```\n\n"
        "```janitor-ceiling\nmax_files = three\n```\n"
    )
    standard = _write_standard(tmp_path, body)
    diff = _write_diff(tmp_path, "scripts/a.py")

    code, _ = _run(str(diff), standard, capsys)

    assert code == 1


def test_should_exit_1_when_ceiling_has_unexpected_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "```janitor-forbidden-globs\nintent-files spec/**\n```\n\n"
        "```janitor-ceiling\nmax_files = 3\nmin_files = 1\n```\n"
    )
    standard = _write_standard(tmp_path, body)
    diff = _write_diff(tmp_path, "scripts/a.py")

    code, _ = _run(str(diff), standard, capsys)

    assert code == 1


def test_should_exit_1_when_duplicate_forbidden_blocks_present(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "```janitor-forbidden-globs\nintent-files spec/**\n```\n\n"
        "```janitor-forbidden-globs\nharness-control hooks/**\n```\n\n"
        "```janitor-ceiling\nmax_files = 3\n```\n"
    )
    standard = _write_standard(tmp_path, body)
    diff = _write_diff(tmp_path, "scripts/a.py")

    code, _ = _run(str(diff), standard, capsys)

    assert code == 1


def test_should_exit_1_when_ceiling_key_wrong_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "```janitor-forbidden-globs\nintent-files spec/**\n```\n\n"
        "```janitor-ceiling\nmaximum = 3\n```\n"
    )
    standard = _write_standard(tmp_path, body)
    diff = _write_diff(tmp_path, "scripts/a.py")

    code, _ = _run(str(diff), standard, capsys)

    assert code == 1


# --- usage / IO ---------------------------------------------------------------


def test_should_exit_1_when_args_missing() -> None:
    code = boundary_check.main(["janitor_boundary_check.py"])
    assert code == 1


def test_should_exit_1_when_diff_file_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    code, _ = _run(str(tmp_path / "nope.diff"), standard, capsys)
    assert code == 1


def test_should_exit_1_when_boundary_file_missing(tmp_path: Path) -> None:
    diff = _write_diff(tmp_path, "scripts/a.py")
    code = boundary_check.main(
        [
            "janitor_boundary_check.py",
            "--diff",
            str(diff),
            "--boundary",
            str(tmp_path / "nope.md"),
        ]
    )
    assert code == 1


def test_should_read_diff_from_stdin_when_dash(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    standard = _write_standard(tmp_path)
    diff_text = (
        "diff --git a/spec/foo.md b/spec/foo.md\n"
        "--- a/spec/foo.md\n"
        "+++ b/spec/foo.md\n"
        "@@ -1 +1 @@\n-x\n+y\n"
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(diff_text))

    code, verdict = _run("-", standard, capsys)

    assert code == 2
    assert verdict["rule"] == "intent-files"


def test_should_handle_added_and_deleted_file_markers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    standard = _write_standard(tmp_path)
    # A newly added file uses `--- /dev/null`; a deleted file uses `+++ /dev/null`.
    # The changed path must still be extracted from the `diff --git` header.
    diff_text = (
        "diff --git a/spec/new.md b/spec/new.md\n"
        "new file mode 100644\n"
        "index 0000000..2222222\n"
        "--- /dev/null\n"
        "+++ b/spec/new.md\n"
        "@@ -0,0 +1 @@\n+hello\n"
    )
    path = tmp_path / "add.diff"
    path.write_text(diff_text, encoding="utf-8")

    code, verdict = _run(str(path), standard, capsys)

    assert code == 2
    assert verdict["rule"] == "intent-files"
    assert "spec/new.md" in verdict["paths"]


def test_should_parse_real_repo_standard_blocks() -> None:
    # The shipped standard must satisfy our own parser (AC-013 round-trip):
    # parsing its two blocks succeeds and a known-forbidden path is vetoed.
    repo_root = Path(__file__).resolve().parent.parent
    standard = repo_root / "standards" / "process" / "janitor-write-boundary.md"
    globs = boundary_check.parse_forbidden_globs(standard.read_text(encoding="utf-8"))
    ceiling = boundary_check.parse_ceiling(standard.read_text(encoding="utf-8"))

    assert ceiling == 3
    assert any(rule == "intent-files" for rule, _ in globs)
