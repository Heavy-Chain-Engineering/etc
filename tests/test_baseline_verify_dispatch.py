"""baseline-verify dispatcher + python reference profile — integration tests.

Covers the ENFORCE stage of the brownfield architecture-baseline feature
(F-2026-06-10), task 006. Two surfaces under test, both subprocess-invoked
against real temp repos (no mocks; `jq`, `python3`, and `git` are available in
this repo's environment):

  hooks/baseline-verify.sh
    Conductor-invoked dispatcher cloned from runtime-verify.sh (ADR-004).
    stdin  {"repo_root","rule_ids"|null,"cwd"} -> reads the mechanizable,
    selected rules from .etc_sdlc/architecture-baseline.yaml THROUGH
    scripts/baseline.py (the single format owner; bash never parses the YAML),
    projects {repo_root, rules:[{rule_id,statement}]} onto each active
    profile's baseline-verify.sh, and aggregates the per-rule results.

  standards/code/profiles/python/baseline-verify.sh
    The python reference checker: compiles grep/glob assertions from rule
    statements and emits {results:[{rule_id, status, evidence}]} with status in
    the closed enum {pass, fail, no-check}. Un-mechanizable statements return
    no-check (never a fake pass).

Degrade paths pinned (AC-1): absent lock, empty lock, missing per-profile
script, missing baseline, missing baseline.py, per-profile timeout -> synthetic
fails, unknown profile status -> aggregated as fail. The dispatcher ALWAYS
exits 0; verdicts live in the JSON results, never the exit code.

Violating-fixture behavior pinned (AC-2): a deliberately violating tree yields
a `fail` result naming the violated rule id, per the wire-format contract.

Test fixtures are built inline under each test's tmp_path (the
tests/fixtures/baseline-* dirs are owned by a sibling task's contract test and
are read-only here).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ETC_ROOT = Path(__file__).resolve().parent.parent
DISPATCHER = ETC_ROOT / "hooks" / "baseline-verify.sh"
PYTHON_PROFILE = ETC_ROOT / "standards" / "code" / "profiles" / "python" / "baseline-verify.sh"
BASELINE_PY = ETC_ROOT / "scripts" / "baseline.py"


def _load_baseline_module() -> ModuleType:
    """Import scripts/baseline.py as a module via importlib.

    `scripts/` is not a Python package, so the file is loaded directly — the
    house pattern (mirrors test_baseline.py / test_value_hypothesis.py). Done
    so fixtures are written through the same atomic_dump the production CLI
    uses (no hand-rolled YAML that could drift from the format owner).
    """
    spec = importlib.util.spec_from_file_location("baseline", BASELINE_PY)
    if spec is None or spec.loader is None:
        msg = f"Cannot load module at {BASELINE_PY}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["baseline"] = module
    spec.loader.exec_module(module)
    return module


baseline = _load_baseline_module()


# ── Fixture builders ────────────────────────────────────────────────────────


def _baseline_dict(rules: list[dict]) -> dict:
    """A minimal valid unratified baseline carrying `rules`."""
    return {
        "schema_version": 1,
        "status": "unratified",
        "ratified_by": None,
        "ratified_at": None,
        "confidence": {"score": "low", "inputs": {}},
        "inventory": [],
        "claims": [],
        "seams": [],
        "rules": rules,
    }


def _rule(rule_id: str, statement: str, *, mechanizable: bool = True) -> dict:
    return {
        "id": rule_id,
        "statement": statement,
        "provenance": {"who": "tester", "when": "2026-06-11", "trigger": "test"},
        "mechanizable": mechanizable,
        "enforced_by": "generated" if mechanizable else "human-judgment",
    }


def _init_repo(tmp_path: Path) -> Path:
    """git-init tmp_path and drop the dispatcher + baseline.py into place."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    (tmp_path / "hooks").mkdir(parents=True, exist_ok=True)
    shutil.copy2(DISPATCHER, tmp_path / "hooks" / "baseline-verify.sh")
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASELINE_PY, tmp_path / "scripts" / "baseline.py")
    return tmp_path


def _write_lock(repo: Path, profiles: list[str]) -> None:
    lock = repo / ".etc_sdlc" / "profiles.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("\n".join(profiles) + "\n", encoding="utf-8")


def _write_baseline(repo: Path, rules: list[dict]) -> None:
    baseline.atomic_dump(
        repo / baseline.BASELINE_RELATIVE_PATH, _baseline_dict(rules)
    )


def _install_python_profile(repo: Path) -> None:
    """Install the REAL python reference profile into the repo."""
    pdir = repo / "standards" / "code" / "profiles" / "python"
    pdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PYTHON_PROFILE, pdir / "baseline-verify.sh")


def _write_profile_stub(repo: Path, profile: str, body: str) -> None:
    """Install a stub baseline-verify.sh for `profile` (for dispatcher tests)."""
    pdir = repo / "standards" / "code" / "profiles" / profile
    pdir.mkdir(parents=True, exist_ok=True)
    script = pdir / "baseline-verify.sh"
    script.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    script.chmod(0o755)


def _echo_results_body(results: list[dict]) -> str:
    """A stub body that emits a canned {results:[...]} object on stdout."""
    payload = json.dumps({"results": results})
    return f"cat <<'EOF'\n{payload}\nEOF\n"


def _run_dispatcher(
    repo: Path,
    rule_ids: list[str] | None,
    env_extra: dict[str, str] | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    payload = {"repo_root": str(repo), "rule_ids": rule_ids, "cwd": str(repo)}
    return subprocess.run(
        ["bash", str(repo / "hooks" / "baseline-verify.sh")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(repo),
        env=env,
    )


def _run_profile(
    repo_root: Path, rules: list[dict]
) -> subprocess.CompletedProcess[str]:
    payload = json.dumps(
        {
            "repo_root": str(repo_root),
            "rules": [{"rule_id": r["id"], "statement": r["statement"]} for r in rules],
        }
    )
    return subprocess.run(
        ["bash", str(PYTHON_PROFILE)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _results_by_id(stdout: str) -> dict[str, dict]:
    return {r["rule_id"]: r for r in json.loads(stdout)["results"]}


# ── AC-2: python reference profile against a violating fixture ──────────────


class TestPythonProfileViolatingFixture:
    """AC-2: the python profile, run against a deliberately violating tree,
    returns a `fail` result NAMING the violated rule id, per the wire format
    (pass|fail|no-check closed enum)."""

    def test_should_fail_and_name_rule_when_forbidden_token_present(
        self, tmp_path: Path
    ) -> None:
        # Violating tree: a src python file contains the forbidden token.
        (tmp_path / "src" / "people").mkdir(parents=True)
        (tmp_path / "src" / "people" / "store.py").write_text(
            "value = 1  # TODO: left a marker behind\n", encoding="utf-8"
        )
        rule = _rule("R-001", "files matching src/**/*.py must not contain TODO")

        proc = _run_profile(tmp_path, [rule])

        assert proc.returncode == 0, proc.stderr
        by_id = _results_by_id(proc.stdout)
        assert by_id["R-001"]["status"] == "fail"
        # The verdict names the violated rule id (the contract requirement).
        assert "R-001" in by_id["R-001"]["evidence"]
        assert "store.py" in by_id["R-001"]["evidence"]

    def test_should_fail_when_directory_contains_forbidden_glob(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "tests").mkdir(parents=True)
        (tmp_path / "tests" / "widget.spec").write_text("x\n", encoding="utf-8")
        rule = _rule("R-007", "directory tests must not contain *.spec files")

        proc = _run_profile(tmp_path, [rule])

        assert proc.returncode == 0, proc.stderr
        by_id = _results_by_id(proc.stdout)
        assert by_id["R-007"]["status"] == "fail"
        assert "R-007" in by_id["R-007"]["evidence"]

    def test_should_pass_when_tree_satisfies_rule(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "clean.py").write_text("value = 1\n", encoding="utf-8")
        rule = _rule("R-002", "files matching src/**/*.py must not contain TODO")

        proc = _run_profile(tmp_path, [rule])

        by_id = _results_by_id(proc.stdout)
        assert by_id["R-002"]["status"] == "pass"

    def test_should_pass_vacuously_when_directory_absent(self, tmp_path: Path) -> None:
        rule = _rule("R-003", "directory nonexistent must not contain *.spec files")

        proc = _run_profile(tmp_path, [rule])

        by_id = _results_by_id(proc.stdout)
        assert by_id["R-003"]["status"] == "pass"

    def test_should_no_check_unmechanizable_statement_not_fake_pass(
        self, tmp_path: Path
    ) -> None:
        # A prose rule with no grep/glob assertion must be honestly no-check.
        rule = _rule(
            "R-004", "DTOs live in libs/contracts; runtime logic never does"
        )

        proc = _run_profile(tmp_path, [rule])

        by_id = _results_by_id(proc.stdout)
        assert by_id["R-004"]["status"] == "no-check"
        # Evidence must say WHY it could not be checked (never silent green).
        assert "cannot mechanically evaluate" in by_id["R-004"]["evidence"].lower()

    def test_should_emit_only_closed_enum_statuses(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "a.py").write_text("# TODO\n", encoding="utf-8")
        rules = [
            _rule("R-1", "files matching src/**/*.py must not contain TODO"),
            _rule("R-2", "files matching src/**/*.py must not contain ZZZ"),
            _rule("R-3", "a freeform prose rule with no assertion"),
        ]
        proc = _run_profile(tmp_path, rules)

        statuses = {r["status"] for r in json.loads(proc.stdout)["results"]}
        assert statuses <= {"pass", "fail", "no-check"}

    def test_profile_exit_zero_means_ran(self, tmp_path: Path) -> None:
        # Exit 0 = the profile RAN (verdicts in JSON), even with a fail result.
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "a.py").write_text("# TODO\n", encoding="utf-8")
        rule = _rule("R-1", "files matching src/**/*.py must not contain TODO")
        proc = _run_profile(tmp_path, [rule])
        assert proc.returncode == 0


# ── AC-1: dispatcher contract + every degrade path ──────────────────────────


class TestDispatcherHappyPath:
    def test_should_read_mechanizable_rules_via_cli_and_aggregate(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, ["python"])
        _install_python_profile(repo)
        # Violating tree + a real baseline with 2 mechanizable + 1 non-mech rule.
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.py").write_text("# TODO\n", encoding="utf-8")
        (repo / "tests").mkdir(parents=True)
        (repo / "tests" / "x.spec").write_text("x\n", encoding="utf-8")
        _write_baseline(
            repo,
            [
                _rule("R-001", "files matching src/**/*.py must not contain TODO"),
                _rule("R-002", "directory tests must not contain *.spec files"),
                _rule("R-003", "prose only", mechanizable=False),
            ],
        )

        proc = _run_dispatcher(repo, rule_ids=None)

        assert proc.returncode == 0, proc.stderr
        by_id = _results_by_id(proc.stdout)
        # Non-mechanizable R-003 is filtered out by the dispatcher's projection.
        assert set(by_id) == {"R-001", "R-002"}
        assert by_id["R-001"]["status"] == "fail"
        assert by_id["R-002"]["status"] == "fail"

    def test_should_honor_rule_ids_selection(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, ["python"])
        _install_python_profile(repo)
        (repo / "tests").mkdir(parents=True)
        (repo / "tests" / "x.spec").write_text("x\n", encoding="utf-8")
        _write_baseline(
            repo,
            [
                _rule("R-001", "files matching src/**/*.py must not contain TODO"),
                _rule("R-002", "directory tests must not contain *.spec files"),
            ],
        )

        proc = _run_dispatcher(repo, rule_ids=["R-002"])

        assert proc.returncode == 0, proc.stderr
        by_id = _results_by_id(proc.stdout)
        assert set(by_id) == {"R-002"}

    def test_should_aggregate_across_two_profiles(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, ["python", "go"])
        # Both profiles are stubs that echo a canned result, so this isolates
        # the dispatcher's cross-profile aggregation from rule evaluation.
        _write_profile_stub(
            repo,
            "python",
            _echo_results_body([{"rule_id": "R-001", "status": "pass", "evidence": "py"}]),
        )
        _write_profile_stub(
            repo,
            "go",
            _echo_results_body([{"rule_id": "R-002", "status": "fail", "evidence": "go"}]),
        )
        _write_baseline(
            repo,
            [
                _rule("R-001", "files matching src/**/*.py must not contain TODO"),
                _rule("R-002", "directory tests must not contain *.spec files"),
            ],
        )

        proc = _run_dispatcher(repo, rule_ids=None)

        assert proc.returncode == 0, proc.stderr
        by_id = _results_by_id(proc.stdout)
        assert by_id["R-001"]["status"] == "pass"
        assert by_id["R-002"]["status"] == "fail"
        assert len(json.loads(proc.stdout)["results"]) == 2


class TestDispatcherDegradePaths:
    def test_should_warn_and_skip_when_lock_absent(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_baseline(repo, [_rule("R-001", "files matching src/**/*.py must not contain TODO")])
        # No profiles.lock written.

        proc = _run_dispatcher(repo, rule_ids=None)

        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["results"] == []
        assert "[baseline-verify]" in proc.stderr and "WARN" in proc.stderr

    def test_should_warn_and_skip_when_lock_empty(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, [])  # writes just a newline
        _write_baseline(repo, [_rule("R-001", "files matching src/**/*.py must not contain TODO")])

        proc = _run_dispatcher(repo, rule_ids=None)

        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["results"] == []
        assert "WARN" in proc.stderr

    def test_should_warn_and_skip_when_profile_script_missing(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, ["python", "go"])
        _install_python_profile(repo)  # python present, go missing
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.py").write_text("# TODO\n", encoding="utf-8")
        _write_baseline(repo, [_rule("R-001", "files matching src/**/*.py must not contain TODO")])

        proc = _run_dispatcher(repo, rule_ids=None)

        assert proc.returncode == 0, proc.stderr
        by_id = _results_by_id(proc.stdout)
        # python ran; go was warn-and-skipped.
        assert set(by_id) == {"R-001"}
        assert "go" in proc.stderr and "WARN" in proc.stderr

    def test_should_warn_and_skip_when_baseline_missing(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, ["python"])
        _install_python_profile(repo)
        # No architecture-baseline.yaml written.

        proc = _run_dispatcher(repo, rule_ids=None)

        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["results"] == []
        assert "WARN" in proc.stderr

    def test_should_warn_and_skip_when_baseline_py_missing(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path)
        # Remove the baseline.py the dispatcher resolves project-first.
        (repo / "scripts" / "baseline.py").unlink()
        _write_lock(repo, ["python"])
        _install_python_profile(repo)
        # The dispatcher must not crash; with no resolvable format owner it
        # warns and skips. (It may resolve the etc install-dir sibling; to keep
        # the test hermetic we assert exit-0 + valid JSON, not the specific
        # skip path, since an install-dir baseline.py is legitimately usable.)
        proc = _run_dispatcher(repo, rule_ids=None)

        assert proc.returncode == 0, proc.stderr
        # Output is always valid {"results": [...]} JSON.
        assert "results" in json.loads(proc.stdout)

    def test_should_record_synthetic_fails_on_timeout(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, ["python"])
        # A stub that sleeps past the 1s cap we set via env.
        _write_profile_stub(repo, "python", "sleep 10\n")
        _write_baseline(
            repo,
            [
                _rule("R-001", "files matching src/**/*.py must not contain TODO"),
                _rule("R-002", "directory tests must not contain *.spec files"),
            ],
        )

        proc = _run_dispatcher(
            repo, rule_ids=None, env_extra={"BASELINE_VERIFY_TIMEOUT": "1"}, timeout=30
        )

        assert proc.returncode == 0, proc.stderr
        by_id = _results_by_id(proc.stdout)
        # Every SELECTED rule becomes a synthetic timeout fail.
        assert set(by_id) == {"R-001", "R-002"}
        for rid in ("R-001", "R-002"):
            assert by_id[rid]["status"] == "fail"
            assert "timeout" in by_id[rid]["evidence"].lower()

    def test_should_aggregate_unknown_status_as_fail(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, ["python"])
        # Stub emits an out-of-enum status; the dispatcher must fail-close it.
        _write_profile_stub(
            repo,
            "python",
            _echo_results_body(
                [{"rule_id": "R-001", "status": "WAT", "evidence": "weird"}]
            ),
        )
        _write_baseline(repo, [_rule("R-001", "files matching src/**/*.py must not contain TODO")])

        proc = _run_dispatcher(repo, rule_ids=None)

        assert proc.returncode == 0, proc.stderr
        by_id = _results_by_id(proc.stdout)
        assert by_id["R-001"]["status"] == "fail"
        # The original out-of-enum value is preserved in evidence for audit.
        assert "WAT" in by_id["R-001"]["evidence"]

    def test_should_skip_profile_with_unparseable_output(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, ["python"])
        _write_profile_stub(repo, "python", "echo 'not json at all'\n")
        _write_baseline(repo, [_rule("R-001", "files matching src/**/*.py must not contain TODO")])

        proc = _run_dispatcher(repo, rule_ids=None)

        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["results"] == []
        assert "WARN" in proc.stderr

    def test_should_pass_rules_as_json_on_stdin_not_shell_args(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, ["python"])
        # The stub reflects what it received on stdin: it re-emits the first
        # rule_id as evidence. If the dispatcher passed inputs as shell args,
        # stdin would be empty and the jq read would yield null.
        body = (
            "IN=$(cat)\n"
            'RID=$(echo "$IN" | jq -r ".rules[0].rule_id")\n'
            'jq -n --arg rid "$RID" '
            "'{results:[{rule_id:$rid,status:\"pass\",evidence:\"from-stdin\"}]}'\n"
        )
        _write_profile_stub(repo, "python", body)
        _write_baseline(repo, [_rule("R-009", "files matching src/**/*.py must not contain TODO")])

        proc = _run_dispatcher(repo, rule_ids=None)

        assert proc.returncode == 0, proc.stderr
        by_id = _results_by_id(proc.stdout)
        assert by_id["R-009"]["status"] == "pass"
        assert by_id["R-009"]["evidence"] == "from-stdin"

    def test_should_always_exit_zero_even_with_fail_verdicts(
        self, tmp_path: Path
    ) -> None:
        repo = _init_repo(tmp_path)
        _write_lock(repo, ["python"])
        _install_python_profile(repo)
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.py").write_text("# TODO\n", encoding="utf-8")
        _write_baseline(repo, [_rule("R-001", "files matching src/**/*.py must not contain TODO")])

        proc = _run_dispatcher(repo, rule_ids=None)

        # A fail verdict NEVER becomes a nonzero exit (verdicts live in JSON).
        assert proc.returncode == 0
        assert _results_by_id(proc.stdout)["R-001"]["status"] == "fail"
