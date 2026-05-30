"""python(CLI) runtime-verify profile — reference profile behavior tests.

Exercises the Gap A per-profile primitive
`standards/code/profiles/python/runtime-verify.sh` against a REAL temp
project (no mocks). The profile reads `{feature_path, live_ac_ids}` JSON on
stdin, selects the behavioral test bound to each AC id, runs it via pytest,
and emits `{results:[{ac_id, status, evidence}]}` on stdout.

AC->test binding under test: the `test_ac_N_*` name convention (the marker
fallback path), chosen over `@pytest.mark.ac` to avoid editing a shared
pytest config outside this task's files_in_scope.

Fixtures stood up here:
  - AC-1: a passing `test_ac_1_*`  -> status "pass"
  - AC-2: a failing `test_ac_2_*`  -> status "fail"
  - AC-3: declared-live, NO test   -> status "no-test"
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ETC_ROOT = Path(__file__).resolve().parent.parent
PROFILE = ETC_ROOT / "standards" / "code" / "profiles" / "python" / "runtime-verify.sh"


def _seed_project(tmp_path: Path) -> Path:
    """Create a real project dir with a passing and a failing AC test."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_ac_1_passes.py").write_text(
        "def test_ac_1_passes():\n    assert 1 + 1 == 2\n"
    )
    (tests_dir / "test_ac_2_fails.py").write_text(
        "def test_ac_2_fails():\n    assert 1 + 1 == 3\n"
    )
    # AC-3 intentionally has no matching test.
    return tmp_path


def _run_profile(feature_path: Path, live_ac_ids: list[str]) -> subprocess.CompletedProcess[str]:
    payload = json.dumps({"feature_path": str(feature_path), "live_ac_ids": live_ac_ids})
    return subprocess.run(
        ["bash", str(PROFILE)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _results_by_ac(stdout: str) -> dict[str, dict[str, str]]:
    payload = json.loads(stdout)
    return {r["ac_id"]: r for r in payload["results"]}


class TestRuntimeVerifyPythonProfile:
    def test_should_report_pass_when_ac_test_passes(self, tmp_path: Path) -> None:
        project = _seed_project(tmp_path)
        proc = _run_profile(project, ["AC-1", "AC-2", "AC-3"])
        results = _results_by_ac(proc.stdout)
        assert results["AC-1"]["status"] == "pass"

    def test_should_report_fail_when_ac_test_fails(self, tmp_path: Path) -> None:
        project = _seed_project(tmp_path)
        proc = _run_profile(project, ["AC-1", "AC-2", "AC-3"])
        results = _results_by_ac(proc.stdout)
        assert results["AC-2"]["status"] == "fail"

    def test_should_report_no_test_when_no_test_matches_ac(self, tmp_path: Path) -> None:
        project = _seed_project(tmp_path)
        proc = _run_profile(project, ["AC-1", "AC-2", "AC-3"])
        results = _results_by_ac(proc.stdout)
        assert results["AC-3"]["status"] == "no-test"

    def test_should_emit_one_result_per_declared_live_ac(self, tmp_path: Path) -> None:
        project = _seed_project(tmp_path)
        proc = _run_profile(project, ["AC-1", "AC-2", "AC-3"])
        results = _results_by_ac(proc.stdout)
        assert set(results) == {"AC-1", "AC-2", "AC-3"}

    def test_should_carry_pytest_summary_as_evidence_on_fail(self, tmp_path: Path) -> None:
        project = _seed_project(tmp_path)
        proc = _run_profile(project, ["AC-2"])
        results = _results_by_ac(proc.stdout)
        assert results["AC-2"]["evidence"].strip() != ""

    def test_should_exit_zero_when_profile_ran(self, tmp_path: Path) -> None:
        project = _seed_project(tmp_path)
        proc = _run_profile(project, ["AC-1", "AC-2", "AC-3"])
        assert proc.returncode == 0

    def test_should_not_steal_higher_numbered_ac_test_when_ac_id_is_prefix(
        self, tmp_path: Path
    ) -> None:
        # AC-1 must not bind to test_ac_12_* (substring-collision guard).
        project = _seed_project(tmp_path)
        (project / "tests" / "test_ac_12_other.py").write_text(
            "def test_ac_12_other():\n    assert False\n"
        )
        proc = _run_profile(project, ["AC-1"])
        results = _results_by_ac(proc.stdout)
        assert results["AC-1"]["status"] == "pass"
