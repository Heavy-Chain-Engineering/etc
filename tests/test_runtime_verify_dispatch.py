"""hooks/runtime-verify.sh — dispatcher integration tests (Gap A, F-2026-05-30).

The dispatcher (ADR-001) iterates `.etc_sdlc/profiles.lock` and invokes each
active profile's `standards/code/profiles/<p>/runtime-verify.sh`, passing
`{feature_path, live_ac_ids}` as JSON on stdin (never as shell args) and
aggregating each profile's stdout `{results:[...]}` into one combined object.

These tests subprocess-invoke the real bash hook against a temp git repo
holding a fake `profiles.lock` and stub per-profile `runtime-verify.sh`
scripts. `jq` is available in this repo's environment.

Coverage:
  1. Aggregation across two stub profiles (AC-2).
  2. Absent profiles.lock -> warn-and-skip, empty results, no crash (AC-1, AC-2).
  3. Missing per-profile runtime-verify.sh -> warn-and-skip (AC-2).
  4. Per-profile time cap exceeded -> each live AC recorded fail/timeout (AC-11).
  5. Inputs reach the profile as JSON on stdin, not as shell args.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ETC_ROOT = Path(__file__).resolve().parent.parent
HOOK = ETC_ROOT / "hooks" / "runtime-verify.sh"


def _init_repo(tmp_path: Path) -> Path:
    """Make tmp_path a git repo and drop the dispatcher in at hooks/."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    hooks_dst = tmp_path / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HOOK, hooks_dst / "runtime-verify.sh")
    return tmp_path


def _write_lock(repo: Path, profiles: list[str]) -> None:
    lock = repo / ".etc_sdlc" / "profiles.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("\n".join(profiles) + "\n", encoding="utf-8")


def _write_profile_stub(repo: Path, profile: str, body: str) -> None:
    """Install a stub runtime-verify.sh for `profile`."""
    pdir = repo / "standards" / "code" / "profiles" / profile
    pdir.mkdir(parents=True, exist_ok=True)
    script = pdir / "runtime-verify.sh"
    script.write_text("#!/bin/bash\n" + body, encoding="utf-8")
    script.chmod(0o755)


def _echo_results_body(results: list[dict]) -> str:
    """A stub body that emits a canned {results:[...]} object on stdout."""
    payload = json.dumps({"results": results})
    # Single-quote the JSON for the heredoc-free echo; payload has no single quotes.
    return f"cat <<'EOF'\n{payload}\nEOF\n"


def _run(repo: Path, stdin_obj: dict, env_extra: dict[str, str] | None = None,
         timeout: int = 30) -> subprocess.CompletedProcess[str]:
    import os
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    payload = dict(stdin_obj)
    payload.setdefault("cwd", str(repo))
    return subprocess.run(
        ["bash", str(repo / "hooks" / "runtime-verify.sh")],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=timeout,
        cwd=str(repo), env=env,
    )


def test_should_aggregate_results_across_profiles_when_multiple_active(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lock(repo, ["python", "go"])
    _write_profile_stub(repo, "python", _echo_results_body(
        [{"ac_id": "AC-3", "status": "pass", "evidence": "py ok"}]))
    _write_profile_stub(repo, "go", _echo_results_body(
        [{"ac_id": "AC-7", "status": "fail", "evidence": "go nope"}]))

    proc = _run(repo, {"feature_path": "f/x", "live_ac_ids": ["AC-3", "AC-7"]})

    assert proc.returncode == 0, proc.stderr
    combined = json.loads(proc.stdout)
    by_id = {r["ac_id"]: r for r in combined["results"]}
    assert by_id["AC-3"]["status"] == "pass"
    assert by_id["AC-7"]["status"] == "fail"
    assert len(combined["results"]) == 2


def test_should_warn_and_skip_with_empty_results_when_lock_absent(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    # no profiles.lock written

    proc = _run(repo, {"feature_path": "f/x", "live_ac_ids": ["AC-3"]})

    assert proc.returncode == 0, proc.stderr
    combined = json.loads(proc.stdout)
    assert combined["results"] == []
    assert "WARN" in proc.stderr


def test_should_warn_and_skip_when_profile_script_missing(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lock(repo, ["python", "go"])
    # only python has a stub; go's runtime-verify.sh is missing
    _write_profile_stub(repo, "python", _echo_results_body(
        [{"ac_id": "AC-3", "status": "pass", "evidence": "py ok"}]))

    proc = _run(repo, {"feature_path": "f/x", "live_ac_ids": ["AC-3"]})

    assert proc.returncode == 0, proc.stderr
    combined = json.loads(proc.stdout)
    assert [r["ac_id"] for r in combined["results"]] == ["AC-3"]
    assert "go" in proc.stderr and "WARN" in proc.stderr


def test_should_record_fail_with_timeout_evidence_when_profile_exceeds_cap(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lock(repo, ["python"])
    # stub sleeps well past the 1s cap we set via env
    _write_profile_stub(repo, "python", "sleep 10\n")

    proc = _run(
        repo,
        {"feature_path": "f/x", "live_ac_ids": ["AC-3", "AC-4"]},
        env_extra={"RUNTIME_VERIFY_TIMEOUT": "1"},
        timeout=30,
    )

    assert proc.returncode == 0, proc.stderr
    combined = json.loads(proc.stdout)
    by_id = {r["ac_id"]: r for r in combined["results"]}
    assert set(by_id) == {"AC-3", "AC-4"}
    for ac in ("AC-3", "AC-4"):
        assert by_id[ac]["status"] == "fail"
        assert "timeout" in by_id[ac]["evidence"].lower()


def test_should_pass_inputs_as_json_on_stdin_not_shell_args(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _write_lock(repo, ["python"])
    # The stub reflects what it received: it reads stdin and re-emits feature_path
    # as the evidence string for a single result. If inputs were passed as shell
    # args, $1 would be empty and stdin would be empty.
    body = (
        'IN=$(cat)\n'
        'FP=$(echo "$IN" | jq -r ".feature_path")\n'
        'AC=$(echo "$IN" | jq -r ".live_ac_ids[0]")\n'
        'jq -n --arg fp "$FP" --arg ac "$AC" '
        "'{results:[{ac_id:$ac,status:\"pass\",evidence:$fp}]}'\n"
    )
    _write_profile_stub(repo, "python", body)

    proc = _run(repo, {"feature_path": "feat/inject", "live_ac_ids": ["AC-9"]})

    assert proc.returncode == 0, proc.stderr
    combined = json.loads(proc.stdout)
    assert combined["results"][0]["ac_id"] == "AC-9"
    assert combined["results"][0]["evidence"] == "feat/inject"
