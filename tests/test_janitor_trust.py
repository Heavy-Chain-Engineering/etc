"""Tests for scripts/janitor_trust.py — the sole writer of trust.yaml.

These tests are hermetic: every `gh`/git invocation is routed through an
injectable runner seam (`gh_runner`) so no test touches a real GitHub
remote or git history. The seam takes an argv list and returns the
captured stdout (str) exactly as `subprocess.run(...).stdout` would, or
raises FileNotFoundError to simulate a missing `gh` binary.

Coverage targets (per task 003 acceptance criteria):
    - fresh / missing trust.yaml  → every category preview
    - malformed trust.yaml        → every category preview
    - clean streak reaches N=5    → category auto-promotes to autonomous
    - merged-with-edits PR        → streak resets to 0
    - closed-unmerged PR          → streak resets to 0
    - gh absent                   → reconcile is a no-op, file untouched
    - demote                      → autonomous → preview, streak → 0
    - level / table CLI surfaces
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "janitor_trust.py"
)


def _load_janitor_trust() -> ModuleType:
    """Load scripts/janitor_trust.py without requiring scripts to be a package.

    Mirrors the importlib loader pattern used by test_git_tags.py and
    test_value_hypothesis.py elsewhere in this suite.
    """
    spec = importlib.util.spec_from_file_location("janitor_trust", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


janitor_trust = _load_janitor_trust()


# ── Fakes / fixtures ────────────────────────────────────────────────────


def _gh_runner_from(
    *,
    merged: list[dict[str, Any]] | None = None,
    closed: list[dict[str, Any]] | None = None,
    commits_by_number: dict[int, int] | None = None,
    absent: bool = False,
    list_raises: BaseException | None = None,
    list_returns: str | None = None,
    view_raises: BaseException | None = None,
) -> Callable[[list[str]], str]:
    """Build a fake gh runner.

    `merged` / `closed` are the PR records `gh pr list` would return for the
    respective `--state`. `commits_by_number` maps a PR number to the number
    of commits on its branch (as `gh pr view --json commits` would report).
    `absent=True` simulates the `gh` binary not being installed.

    Failure-injection hooks (for the degrade-path tests):
    `list_raises` — raised on any `gh pr list` call (e.g. a non-zero gh exit
    surfacing as `subprocess.CalledProcessError`). `list_returns` — overrides
    `gh pr list` stdout with a raw string (e.g. garbage that fails JSON parse).
    `view_raises` — raised on any `gh pr view` call, simulating a sub-call
    that fails INSIDE commit-count after pr-list already succeeded.
    """
    merged = merged or []
    closed = closed or []
    commits_by_number = commits_by_number or {}

    def runner(argv: list[str]) -> str:
        if absent:
            raise FileNotFoundError(argv[0])
        if argv[:3] == ["gh", "pr", "list"]:
            if list_raises is not None:
                raise list_raises
            if list_returns is not None:
                return list_returns
            state = argv[argv.index("--state") + 1]
            records = merged if state == "merged" else closed
            return json.dumps(records)
        if argv[:3] == ["gh", "pr", "view"]:
            if view_raises is not None:
                raise view_raises
            number = int(argv[3])
            count = commits_by_number.get(number, 1)
            return json.dumps({"commits": [{} for _ in range(count)]})
        raise AssertionError(f"unexpected gh argv: {argv}")

    return runner


def _write_runs(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )


def _pr(number: int, branch: str, merged_at: str) -> dict[str, Any]:
    return {"number": number, "headRefName": branch, "mergedAt": merged_at}


# ── load / default-safe behaviour ───────────────────────────────────────


def test_should_default_all_categories_to_preview_when_file_missing(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "trust.yaml"

    state = janitor_trust.load_trust(trust_path)

    assert janitor_trust.category_level(state, "lint-format") == "preview"
    assert janitor_trust.category_level(state, "dead-code") == "preview"


def test_should_default_to_preview_when_file_is_malformed(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text("this: [is, : not valid yaml", encoding="utf-8")

    state = janitor_trust.load_trust(trust_path)

    assert janitor_trust.category_level(state, "whitespace-eof-imports") == "preview"


def test_should_default_to_preview_when_top_level_is_not_a_mapping(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text("- just\n- a\n- list\n", encoding="utf-8")

    state = janitor_trust.load_trust(trust_path)

    assert janitor_trust.category_level(state, "lint-format") == "preview"


def test_should_treat_autonomous_entry_with_substreak_as_preview(
    tmp_path: Path,
) -> None:
    # Invariant: autonomous IFF clean_streak >= N. A stored autonomous entry
    # whose streak is below N is malformed → demote to preview (never trust
    # a corrupt cache into autonomy).
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text(
        "schema_version: 1\n"
        "categories:\n"
        "  lint-format: {trust: autonomous, clean_streak: 2, promoted_at: null}\n",
        encoding="utf-8",
    )

    state = janitor_trust.load_trust(trust_path)

    assert janitor_trust.category_level(state, "lint-format") == "preview"


def test_should_read_back_autonomous_when_streak_meets_n(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text(
        "schema_version: 1\n"
        "categories:\n"
        "  lint-format: {trust: autonomous, clean_streak: 5, "
        'promoted_at: "2026-05-29T11:00:00Z"}\n',
        encoding="utf-8",
    )

    state = janitor_trust.load_trust(trust_path)

    assert janitor_trust.category_level(state, "lint-format") == "autonomous"


def test_should_default_to_preview_when_categories_block_not_a_mapping(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text(
        "schema_version: 1\ncategories: not-a-mapping\n", encoding="utf-8"
    )

    state = janitor_trust.load_trust(trust_path)

    assert state["categories"] == {}


def test_should_coerce_non_integer_streak_to_zero(tmp_path: Path) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text(
        "schema_version: 1\n"
        "categories:\n"
        '  lint-format: {trust: preview, clean_streak: "lots", promoted_at: null}\n',
        encoding="utf-8",
    )

    state = janitor_trust.load_trust(trust_path)

    assert state["categories"]["lint-format"]["clean_streak"] == 0
    assert janitor_trust.category_level(state, "lint-format") == "preview"


def test_should_default_to_preview_when_entry_is_not_a_mapping(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text(
        "schema_version: 1\ncategories:\n  lint-format: 7\n", encoding="utf-8"
    )

    state = janitor_trust.load_trust(trust_path)

    assert state["categories"]["lint-format"]["clean_streak"] == 0


def test_should_default_to_preview_when_file_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text("schema_version: 1\ncategories: {}\n", encoding="utf-8")

    def _raise(*_args: Any, **_kwargs: Any) -> str:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", _raise)

    state = janitor_trust.load_trust(trust_path)

    assert state == janitor_trust.empty_state()


# ── atomic write round-trip ─────────────────────────────────────────────


def test_should_round_trip_state_through_atomic_write(tmp_path: Path) -> None:
    trust_path = tmp_path / "nested" / "trust.yaml"
    state = janitor_trust.empty_state()
    state["categories"]["lint-format"] = {
        "trust": "autonomous",
        "clean_streak": 5,
        "promoted_at": "2026-05-29T11:00:00Z",
    }

    janitor_trust.save_trust(trust_path, state)
    reloaded = janitor_trust.load_trust(trust_path)

    assert janitor_trust.category_level(reloaded, "lint-format") == "autonomous"
    assert reloaded["schema_version"] == janitor_trust.SCHEMA_VERSION


def test_should_carry_schema_version_in_empty_state() -> None:
    state = janitor_trust.empty_state()

    assert state["schema_version"] == janitor_trust.SCHEMA_VERSION
    assert state["categories"] == {}


# ── reconcile ───────────────────────────────────────────────────────────


def test_should_promote_category_when_clean_streak_reaches_n(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    branches = [f"claude/janitor/lint-format-{i}" for i in range(janitor_trust.N)]
    _write_runs(
        runs_path,
        [{"branch": b, "categories": ["lint-format"]} for b in branches],
    )
    merged = [
        _pr(i + 1, b, f"2026-05-2{i}T10:00:00Z") for i, b in enumerate(branches)
    ]
    runner = _gh_runner_from(
        merged=merged,
        commits_by_number={i + 1: 1 for i in range(janitor_trust.N)},
    )

    janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    state = janitor_trust.load_trust(trust_path)
    assert janitor_trust.category_level(state, "lint-format") == "autonomous"
    assert state["categories"]["lint-format"]["clean_streak"] == janitor_trust.N
    assert state["categories"]["lint-format"]["promoted_at"] is not None


def test_should_stay_preview_when_clean_streak_below_n(tmp_path: Path) -> None:
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    branches = [f"claude/janitor/lint-format-{i}" for i in range(3)]
    _write_runs(
        runs_path,
        [{"branch": b, "categories": ["lint-format"]} for b in branches],
    )
    merged = [
        _pr(i + 1, b, f"2026-05-2{i}T10:00:00Z") for i, b in enumerate(branches)
    ]
    runner = _gh_runner_from(
        merged=merged, commits_by_number={1: 1, 2: 1, 3: 1}
    )

    janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    state = janitor_trust.load_trust(trust_path)
    assert janitor_trust.category_level(state, "lint-format") == "preview"
    assert state["categories"]["lint-format"]["clean_streak"] == 3


def test_should_reset_streak_when_pr_merged_with_edits(tmp_path: Path) -> None:
    # Newest PR (highest mergedAt) merged with an extra commit → streak 0
    # regardless of older clean merges.
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    branches = [f"claude/janitor/lint-format-{i}" for i in range(5)]
    _write_runs(
        runs_path,
        [{"branch": b, "categories": ["lint-format"]} for b in branches],
    )
    merged = [
        _pr(i + 1, b, f"2026-05-2{i}T10:00:00Z") for i, b in enumerate(branches)
    ]
    # PR 5 is the newest and has 2 commits (operator edited) → reset.
    commits = {1: 1, 2: 1, 3: 1, 4: 1, 5: 2}
    runner = _gh_runner_from(merged=merged, commits_by_number=commits)

    janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    state = janitor_trust.load_trust(trust_path)
    assert janitor_trust.category_level(state, "lint-format") == "preview"
    assert state["categories"]["lint-format"]["clean_streak"] == 0


def test_should_reset_streak_when_newest_pr_closed_unmerged(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    clean_branches = [f"claude/janitor/lint-format-{i}" for i in range(5)]
    closed_branch = "claude/janitor/lint-format-rejected"
    rows = [{"branch": b, "categories": ["lint-format"]} for b in clean_branches]
    rows.append({"branch": closed_branch, "categories": ["lint-format"]})
    _write_runs(runs_path, rows)
    merged = [
        _pr(i + 1, b, f"2026-05-1{i}T10:00:00Z")
        for i, b in enumerate(clean_branches)
    ]
    # closed PR is the most recent activity → resets the streak.
    closed = [
        {
            "number": 99,
            "headRefName": closed_branch,
            "mergedAt": None,
            "closedAt": "2026-05-27T10:00:00Z",
        }
    ]
    runner = _gh_runner_from(
        merged=merged,
        closed=closed,
        commits_by_number={i + 1: 1 for i in range(5)},
    )

    janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    state = janitor_trust.load_trust(trust_path)
    assert janitor_trust.category_level(state, "lint-format") == "preview"
    assert state["categories"]["lint-format"]["clean_streak"] == 0


def test_should_count_only_consecutive_clean_merges_newest_first(
    tmp_path: Path,
) -> None:
    # Older non-clean merge must NOT break a newer consecutive clean run.
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    branches = [f"claude/janitor/dead-code-{i}" for i in range(6)]
    _write_runs(
        runs_path,
        [{"branch": b, "categories": ["dead-code"]} for b in branches],
    )
    merged = [
        _pr(i + 1, b, f"2026-05-1{i}T10:00:00Z") for i, b in enumerate(branches)
    ]
    # Oldest (PR 1) was dirty; the newest 5 are clean → streak == 5 → promote.
    commits = {1: 3, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1}
    runner = _gh_runner_from(merged=merged, commits_by_number=commits)

    janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    state = janitor_trust.load_trust(trust_path)
    assert state["categories"]["dead-code"]["clean_streak"] == 5
    assert janitor_trust.category_level(state, "dead-code") == "autonomous"


def test_should_leave_file_untouched_when_gh_absent(tmp_path: Path) -> None:
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(
        runs_path, [{"branch": "claude/janitor/x", "categories": ["lint-format"]}]
    )
    original = (
        "schema_version: 1\n"
        "categories:\n"
        "  lint-format: {trust: preview, clean_streak: 4, promoted_at: null}\n"
    )
    trust_path.write_text(original, encoding="utf-8")
    runner = _gh_runner_from(absent=True)

    janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    assert trust_path.read_text(encoding="utf-8") == original


def test_should_not_create_file_when_gh_absent_and_no_prior_state(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(runs_path, [])
    runner = _gh_runner_from(absent=True)

    janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    assert not trust_path.exists()


def _seed_trust(trust_path: Path) -> str:
    """Write a prior preview-with-streak trust file; return its exact bytes.

    Used by the degrade-path tests to assert the file is left byte-untouched
    (content + mtime) when a gh-boundary failure forces the documented no-op.
    """
    original = (
        "schema_version: 1\n"
        "categories:\n"
        "  lint-format: {trust: preview, clean_streak: 4, promoted_at: null}\n"
    )
    trust_path.write_text(original, encoding="utf-8")
    return original


def test_should_no_op_when_gh_pr_list_exits_nonzero(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # gh healthy but a non-zero exit (no remote, auth scope, rate limit)
    # surfaces as CalledProcessError → degrade to the documented no-op.
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(
        runs_path, [{"branch": "claude/janitor/x", "categories": ["lint-format"]}]
    )
    original = _seed_trust(trust_path)
    before_mtime = trust_path.stat().st_mtime_ns
    runner = _gh_runner_from(
        list_raises=subprocess.CalledProcessError(1, ["gh", "pr", "list"])
    )

    with caplog.at_level("WARNING"):
        result = janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    assert result is False
    assert trust_path.read_text(encoding="utf-8") == original
    assert trust_path.stat().st_mtime_ns == before_mtime
    assert "CalledProcessError" in caplog.text


def test_should_no_op_when_gh_returns_garbage_json(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Malformed gh output (truncated stream, non-JSON banner) → JSONDecodeError
    # must degrade to the no-op, not crash the CLI.
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(
        runs_path, [{"branch": "claude/janitor/x", "categories": ["lint-format"]}]
    )
    original = _seed_trust(trust_path)
    before_mtime = trust_path.stat().st_mtime_ns
    runner = _gh_runner_from(list_returns="not json at all <<<")

    with caplog.at_level("WARNING"):
        result = janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    assert result is False
    assert trust_path.read_text(encoding="utf-8") == original
    assert trust_path.stat().st_mtime_ns == before_mtime
    assert "JSONDecodeError" in caplog.text


def test_should_no_op_when_commit_count_subcall_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # pr-list succeeds but a sub-call INSIDE _collect_events
    # (_gh_branch_commit_count → gh pr view) fails — the field-reported shape.
    # The whole gh-deriving span must degrade, not just the two pr-list calls.
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(
        runs_path,
        [{"branch": "claude/janitor/lint-format-0", "categories": ["lint-format"]}],
    )
    original = _seed_trust(trust_path)
    before_mtime = trust_path.stat().st_mtime_ns
    merged = [_pr(1, "claude/janitor/lint-format-0", "2026-05-20T10:00:00Z")]
    runner = _gh_runner_from(
        merged=merged,
        view_raises=subprocess.CalledProcessError(1, ["gh", "pr", "view"]),
    )

    with caplog.at_level("WARNING"):
        result = janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    assert result is False
    assert trust_path.read_text(encoding="utf-8") == original
    assert trust_path.stat().st_mtime_ns == before_mtime
    assert "CalledProcessError" in caplog.text


def test_should_propagate_unexpected_error_not_at_gh_boundary(
    tmp_path: Path,
) -> None:
    # A real bug in our own code (here: a non-gh-boundary failure) must still
    # crash loudly — the fix must not widen to a bare `except Exception`.
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(
        runs_path, [{"branch": "claude/janitor/x", "categories": ["lint-format"]}]
    )

    def _boom(argv: list[str]) -> str:
        raise ZeroDivisionError("not a gh-boundary failure")

    with pytest.raises(ZeroDivisionError, match="not a gh-boundary failure"):
        janitor_trust.reconcile(trust_path, runs_path, gh_runner=_boom)


def test_should_ignore_prs_without_a_matching_run_ledger_entry(
    tmp_path: Path,
) -> None:
    # A merged PR whose branch is not in runs.jsonl has no known category and
    # is skipped (cannot be credited to any streak).
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(runs_path, [])
    merged = [_pr(1, "some/other-branch", "2026-05-20T10:00:00Z")]
    runner = _gh_runner_from(merged=merged, commits_by_number={1: 1})

    janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    state = janitor_trust.load_trust(trust_path)
    assert state["categories"] == {}


def test_should_skip_prs_when_runs_ledger_absent(tmp_path: Path) -> None:
    # No runs.jsonl at all → no branch→category mapping → nothing credited.
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"  # never created
    merged = [_pr(1, "claude/janitor/lint-format-0", "2026-05-20T10:00:00Z")]
    runner = _gh_runner_from(merged=merged, commits_by_number={1: 1})

    janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    state = janitor_trust.load_trust(trust_path)
    assert state["categories"] == {}


def test_should_ignore_malformed_runs_jsonl_lines(tmp_path: Path) -> None:
    trust_path = tmp_path / "trust.yaml"
    runs_path = tmp_path / "runs.jsonl"
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    runs_path.write_text(
        "{ this is not json\n"
        '{"branch": "claude/janitor/lint-format-0", "categories": ["lint-format"]}\n'
        "\n",
        encoding="utf-8",
    )
    merged = [_pr(1, "claude/janitor/lint-format-0", "2026-05-20T10:00:00Z")]
    runner = _gh_runner_from(merged=merged, commits_by_number={1: 1})

    janitor_trust.reconcile(trust_path, runs_path, gh_runner=runner)

    state = janitor_trust.load_trust(trust_path)
    assert state["categories"]["lint-format"]["clean_streak"] == 1


def test_should_unlink_temp_file_when_atomic_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trust_path = tmp_path / "trust.yaml"

    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(janitor_trust.os, "replace", _raise)

    with pytest.raises(OSError, match="disk full"):
        janitor_trust.save_trust(trust_path, janitor_trust.empty_state())

    # No partial/temp artifacts left behind in the target directory.
    leftovers = [p for p in tmp_path.iterdir() if p.name != "trust.yaml"]
    assert leftovers == []
    assert not trust_path.exists()


# ── demote ──────────────────────────────────────────────────────────────


def test_should_demote_autonomous_category_to_preview(tmp_path: Path) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text(
        "schema_version: 1\n"
        "categories:\n"
        "  lint-format: {trust: autonomous, clean_streak: 5, "
        'promoted_at: "2026-05-29T11:00:00Z"}\n',
        encoding="utf-8",
    )

    janitor_trust.demote(trust_path, "lint-format")

    state = janitor_trust.load_trust(trust_path)
    assert janitor_trust.category_level(state, "lint-format") == "preview"
    assert state["categories"]["lint-format"]["clean_streak"] == 0


def test_should_demote_unknown_category_as_idempotent_preview(
    tmp_path: Path,
) -> None:
    trust_path = tmp_path / "trust.yaml"

    janitor_trust.demote(trust_path, "never-seen")

    state = janitor_trust.load_trust(trust_path)
    assert janitor_trust.category_level(state, "never-seen") == "preview"
    assert state["categories"]["never-seen"]["clean_streak"] == 0


# ── CLI surfaces ────────────────────────────────────────────────────────


def test_should_print_level_and_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text(
        "schema_version: 1\n"
        "categories:\n"
        "  lint-format: {trust: autonomous, clean_streak: 5, "
        'promoted_at: "2026-05-29T11:00:00Z"}\n',
        encoding="utf-8",
    )

    code = janitor_trust.main(["level", "lint-format", "--state-dir", str(tmp_path)])

    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "autonomous"


def test_should_print_preview_for_unknown_category_via_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = janitor_trust.main(["level", "mystery", "--state-dir", str(tmp_path)])

    out = capsys.readouterr().out.strip()
    assert code == 0
    assert out == "preview"


def test_should_render_table_with_categories_and_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text(
        "schema_version: 1\n"
        "categories:\n"
        "  lint-format: {trust: autonomous, clean_streak: 5, "
        'promoted_at: "2026-05-29T11:00:00Z"}\n'
        "  dead-code: {trust: preview, clean_streak: 2, promoted_at: null}\n",
        encoding="utf-8",
    )

    code = janitor_trust.main(["table", "--state-dir", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "lint-format" in out
    assert "autonomous" in out
    assert "dead-code" in out


def test_should_render_table_when_no_categories_yet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = janitor_trust.main(["table", "--state-dir", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 0
    assert "no categories" in out.lower()


def test_should_demote_via_cli_and_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trust_path = tmp_path / "trust.yaml"
    trust_path.write_text(
        "schema_version: 1\n"
        "categories:\n"
        "  lint-format: {trust: autonomous, clean_streak: 5, "
        'promoted_at: "2026-05-29T11:00:00Z"}\n',
        encoding="utf-8",
    )

    code = janitor_trust.main(["demote", "lint-format", "--state-dir", str(tmp_path)])

    state = janitor_trust.load_trust(trust_path)
    assert code == 0
    assert janitor_trust.category_level(state, "lint-format") == "preview"


def test_should_no_op_reconcile_via_cli_when_gh_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force the default subprocess-backed runner to behave as gh-absent by
    # making subprocess.run raise FileNotFoundError.
    runs_path = tmp_path / "runs.jsonl"
    _write_runs(runs_path, [])
    trust_path = tmp_path / "trust.yaml"

    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise FileNotFoundError("gh")

    monkeypatch.setattr(janitor_trust.subprocess, "run", _raise)

    code = janitor_trust.main(["reconcile", "--state-dir", str(tmp_path)])

    assert code == 0
    assert not trust_path.exists()


def test_should_reconcile_via_cli_using_injected_default_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_path = tmp_path / "runs.jsonl"
    branches = [f"claude/janitor/lint-format-{i}" for i in range(janitor_trust.N)]
    _write_runs(
        runs_path,
        [{"branch": b, "categories": ["lint-format"]} for b in branches],
    )
    merged = [
        _pr(i + 1, b, f"2026-05-2{i}T10:00:00Z") for i, b in enumerate(branches)
    ]
    fake = _gh_runner_from(
        merged=merged,
        commits_by_number={i + 1: 1 for i in range(janitor_trust.N)},
    )

    class _Completed:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def _fake_run(argv: list[str], **_kwargs: Any) -> _Completed:
        return _Completed(fake(argv))

    monkeypatch.setattr(janitor_trust.subprocess, "run", _fake_run)

    code = janitor_trust.main(["reconcile", "--state-dir", str(tmp_path)])

    state = janitor_trust.load_trust(tmp_path / "trust.yaml")
    assert code == 0
    assert janitor_trust.category_level(state, "lint-format") == "autonomous"


def test_should_return_one_when_cli_hits_os_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _raise(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("read-only filesystem")

    monkeypatch.setattr(janitor_trust.os, "replace", _raise)

    code = janitor_trust.main(
        ["demote", "lint-format", "--state-dir", str(tmp_path)]
    )

    err = capsys.readouterr().err
    assert code == 1
    assert "janitor_trust error" in err


def test_should_exit_nonzero_on_unknown_subcommand() -> None:
    with pytest.raises(SystemExit) as excinfo:
        janitor_trust.main(["bogus"])

    assert excinfo.value.code != 0
