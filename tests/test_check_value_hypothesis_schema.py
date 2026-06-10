"""First behavioral tests for hooks/check-value-hypothesis-schema.sh.

Audit init 8: this is a BLOCKING gate (exit 2 on schema-invalid
value-hypothesis.yaml) that was the only wired hook with zero tests, and it
parsed payloads with raw jq — `.tool_input.file_path` is empty under Codex
apply_patch payloads, so the gate silently failed open on Codex for the
exact 8-feature schema drift it was built to stop. The hook now routes
through hooks/helpers/hook_payload.py; these tests pin both payload shapes.

House pattern: subprocess-invoke the hook with the JSON payload on stdin;
assert exit code (0 = allow, 2 = block). Fixtures mirror REAL payload
shapes (fake-client-fidelity discipline): the Claude shape carries
tool_input.file_path; the Codex shape is tool_name=apply_patch with the
patch text in tool_input.command (parsed by hook_payload.parse_apply_patch).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "check-value-hypothesis-schema.sh"

VALID_VH = """\
schema_version: 1
feature_id: F-2026-06-09-test-feature
spec_author_role: Engineer
who: operators of the etc harness
current_cost: schema drift ships unreviewed because .etc_sdlc is gitignored
predicted:
  metric: schema-invalid value-hypothesis files written per month
  direction: decrease
  threshold: 0
  window_days: 30
how_we_know: count validator failures at /metrics time over the window
status: pending
validation:
  measured_at: null
  measured_value: null
  evidence: null
"""

# The pre-F019 drift shape this gate exists to block.
INVALID_VH = """\
who: someone
what: something
why: because
"""


def _run_hook(payload: dict[str, object], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
        cwd=cwd,
    )


def _project(tmp_path: Path, vh_content: str) -> Path:
    """A fake project with the real validator available and one vh file."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    real = (REPO_ROOT / "scripts" / "value_hypothesis.py").read_text(encoding="utf-8")
    (scripts / "value_hypothesis.py").write_text(real, encoding="utf-8")
    feature = tmp_path / ".etc_sdlc" / "features" / "active" / "F-2026-06-09-test-feature"
    feature.mkdir(parents=True)
    (feature / "value-hypothesis.yaml").write_text(vh_content, encoding="utf-8")
    return feature / "value-hypothesis.yaml"


def _claude_payload(vh_path: Path, cwd: Path) -> dict[str, object]:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": str(vh_path)},
        "cwd": str(cwd),
    }


def _codex_payload(vh_path: Path, cwd: Path) -> dict[str, object]:
    rel = vh_path.relative_to(cwd).as_posix()
    patch = (
        "*** Begin Patch\n"
        f"*** Update File: {rel}\n"
        "@@\n"
        "+who: someone\n"
        "*** End Patch\n"
    )
    return {
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
        "cwd": str(cwd),
    }


def test_valid_schema_is_allowed_claude_shape(tmp_path: Path) -> None:
    vh = _project(tmp_path, VALID_VH)
    result = _run_hook(_claude_payload(vh, tmp_path), tmp_path)
    assert result.returncode == 0, result.stderr


def test_invalid_schema_blocks_claude_shape(tmp_path: Path) -> None:
    vh = _project(tmp_path, INVALID_VH)
    result = _run_hook(_claude_payload(vh, tmp_path), tmp_path)
    assert result.returncode == 2, (
        f"drift-shape value-hypothesis must BLOCK; got {result.returncode}: "
        f"{result.stderr}"
    )
    assert "canonical" in result.stderr


def test_invalid_schema_blocks_codex_apply_patch_shape(tmp_path: Path) -> None:
    """THE fail-open regression: under apply_patch payloads the old raw-jq
    parse found no file_path and exited 0 — the blocking gate vanished for
    Codex clients. It must block now."""
    vh = _project(tmp_path, INVALID_VH)
    result = _run_hook(_codex_payload(vh, tmp_path), tmp_path)
    assert result.returncode == 2, (
        f"Codex apply_patch editing an invalid value-hypothesis.yaml must "
        f"BLOCK (gate previously failed open); got {result.returncode}: "
        f"{result.stderr}"
    )


def test_valid_schema_is_allowed_codex_shape(tmp_path: Path) -> None:
    vh = _project(tmp_path, VALID_VH)
    result = _run_hook(_codex_payload(vh, tmp_path), tmp_path)
    assert result.returncode == 0, result.stderr


def test_non_vh_file_is_ignored(tmp_path: Path) -> None:
    _project(tmp_path, VALID_VH)
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / "src" / "main.py")},
        "cwd": str(tmp_path),
    }
    result = _run_hook(payload, tmp_path)
    assert result.returncode == 0


def test_malformed_payload_degrades_to_allow(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(HOOK)],
        input="not json at all",
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
    )
    assert result.returncode == 0
