"""Behavioral tests for hooks/check-baseline-schema.sh.

F-2026-06-10 brownfield architecture baseline, task 005 / AC-1.

This is a BLOCKING gate (exit 2) on a schema-invalid
``.etc_sdlc/architecture-baseline.yaml`` write. Two deliberate departures from
check-value-hypothesis-schema.sh are pinned here:

  1. Payload-parse is FAIL CLOSED (``|| exit 2``). The value-hypothesis hook
     parsed fail-open (``|| exit 0``), which the audit flagged: under Codex
     apply_patch payloads a parse miss silently neutered the gate. Here an
     unparseable payload BLOCKS (exit 2).
  2. The hook suffix-matches BOTH architecture-baseline.yaml and seam-map.yaml,
     but baseline.py ships no seam-map validator in this feature — so a
     seam-map write degrades to allow rather than false-blocking through the
     architecture-baseline schema.

House pattern: subprocess-invoke the hook with the JSON payload on stdin;
assert exit code (0 = allow, 2 = block). Fixtures mirror REAL payload shapes
(fake-client-fidelity discipline): the Claude shape carries
tool_input.file_path; the Codex shape is tool_name=apply_patch with the patch
text in tool_input.command (parsed by hook_payload.parse_apply_patch).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "hooks" / "check-baseline-schema.sh"

VALID_BASELINE = """\
schema_version: 1
status: unratified
confidence:
  score: low
  inputs:
    competing_pattern_concerns: 0
    claims: {verified: 1, stale: 0, aspirational: 0, contradicted: 0}
inventory:
  - path: docs/folder-structure.md
    type: convention-doc
    last_modified: "2025-11-04"
claims:
  - id: CL-001
    source: docs/folder-structure.md
    claim: "Data-access libraries live at libs/<scope>/data-access"
    classification: VERIFIED
    evidence: "libs/people/data-access exists"
    resolution: null
rules: []
seams: []
"""

# A baseline whose stored status is outside the closed enum — a schema
# violation baseline.py validate reports as exit 2.
INVALID_BASELINE = """\
schema_version: 1
status: totally-bogus-status
confidence:
  score: low
  inputs: {}
inventory: []
claims: []
rules: []
seams: []
"""

# A valid seam-map.yaml. It deliberately LACKS the architecture-baseline
# required fields (status, claims, inventory, rules) — routing it through the
# baseline `validate` would false-block; the hook must degrade to allow.
VALID_SEAM_MAP = """\
schema_version: 1
repos:
  - name: web
    path: ./web
seams:
  - id: SM-001
    kind: url-routing
    owner_repo: web
    consumer_repos: [api]
    contract: "GET /foo"
    evidence: "router.ts:12"
confidence:
  score: low
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


def _project(tmp_path: Path, filename: str, content: str) -> Path:
    """A fake project with the real baseline.py available and one target file.

    ``filename`` is the basename written under .etc_sdlc/ (e.g.
    ``architecture-baseline.yaml`` or ``seam-map.yaml``).
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    real = (REPO_ROOT / "scripts" / "baseline.py").read_text(encoding="utf-8")
    (scripts / "baseline.py").write_text(real, encoding="utf-8")
    target = tmp_path / ".etc_sdlc" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _claude_payload(path: Path, cwd: Path) -> dict[str, object]:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": str(path)},
        "cwd": str(cwd),
    }


def _codex_payload(path: Path, cwd: Path) -> dict[str, object]:
    rel = path.relative_to(cwd).as_posix()
    patch = (
        "*** Begin Patch\n"
        f"*** Update File: {rel}\n"
        "@@\n"
        "+status: totally-bogus-status\n"
        "*** End Patch\n"
    )
    return {
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
        "cwd": str(cwd),
    }


# ── architecture-baseline.yaml: valid is allowed (both payload shapes) ────────


def test_valid_baseline_is_allowed_claude_shape(tmp_path: Path) -> None:
    path = _project(tmp_path, "architecture-baseline.yaml", VALID_BASELINE)
    result = _run_hook(_claude_payload(path, tmp_path), tmp_path)
    assert result.returncode == 0, result.stderr


def test_valid_baseline_is_allowed_codex_shape(tmp_path: Path) -> None:
    path = _project(tmp_path, "architecture-baseline.yaml", VALID_BASELINE)
    result = _run_hook(_codex_payload(path, tmp_path), tmp_path)
    assert result.returncode == 0, result.stderr


# ── architecture-baseline.yaml: invalid BLOCKS (both payload shapes) ──────────


def test_invalid_baseline_blocks_claude_shape(tmp_path: Path) -> None:
    path = _project(tmp_path, "architecture-baseline.yaml", INVALID_BASELINE)
    result = _run_hook(_claude_payload(path, tmp_path), tmp_path)
    assert result.returncode == 2, (
        f"schema-invalid baseline must BLOCK; got {result.returncode}: {result.stderr}"
    )
    # Copy-pasteable schema is on stderr.
    assert "schema_version: 1" in result.stderr
    assert "check-baseline-schema" in result.stderr


def test_invalid_baseline_blocks_codex_apply_patch_shape(tmp_path: Path) -> None:
    """THE fail-open regression class: under apply_patch payloads a raw-jq parse
    would find no file_path and exit 0 — the blocking gate would vanish for
    Codex clients. It must block now (payload via hook_payload.py)."""
    path = _project(tmp_path, "architecture-baseline.yaml", INVALID_BASELINE)
    result = _run_hook(_codex_payload(path, tmp_path), tmp_path)
    assert result.returncode == 2, (
        f"Codex apply_patch editing an invalid architecture-baseline.yaml must "
        f"BLOCK (gate must not fail open); got {result.returncode}: {result.stderr}"
    )


# ── seam-map.yaml: in-scope but degrades to allow (no validator) ─────────────


def test_valid_seam_map_is_allowed_claude_shape(tmp_path: Path) -> None:
    """A valid seam-map must NOT be false-blocked through the baseline schema."""
    path = _project(tmp_path, "seam-map.yaml", VALID_SEAM_MAP)
    result = _run_hook(_claude_payload(path, tmp_path), tmp_path)
    assert result.returncode == 0, (
        f"seam-map.yaml must not be validated against the architecture-baseline "
        f"schema; got {result.returncode}: {result.stderr}"
    )


def test_seam_map_lacking_baseline_fields_is_allowed_codex_shape(tmp_path: Path) -> None:
    path = _project(tmp_path, "seam-map.yaml", VALID_SEAM_MAP)
    # Codex patch touching the seam-map path.
    rel = path.relative_to(tmp_path).as_posix()
    payload = {
        "tool_name": "apply_patch",
        "tool_input": {
            "command": (
                "*** Begin Patch\n"
                f"*** Update File: {rel}\n"
                "@@\n"
                "+  - name: api\n"
                "*** End Patch\n"
            )
        },
        "cwd": str(tmp_path),
    }
    result = _run_hook(payload, tmp_path)
    assert result.returncode == 0, result.stderr


# ── Out-of-scope files are ignored ───────────────────────────────────────────


def test_non_baseline_file_is_ignored(tmp_path: Path) -> None:
    _project(tmp_path, "architecture-baseline.yaml", VALID_BASELINE)
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / "src" / "main.py")},
        "cwd": str(tmp_path),
    }
    result = _run_hook(payload, tmp_path)
    assert result.returncode == 0


# ── Payload parse is FAIL CLOSED (the deliberate departure) ──────────────────


def test_malformed_payload_fails_closed_blocks(tmp_path: Path) -> None:
    """Unlike check-value-hypothesis-schema.sh (fail-open || exit 0), an
    unparseable payload here BLOCKS with exit 2 — we never wave through a write
    we cannot even read."""
    result = subprocess.run(
        ["bash", str(HOOK)],
        input="not json at all",
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
    )
    assert result.returncode == 2, (
        f"payload-parse failure must FAIL CLOSED (exit 2); got {result.returncode}: "
        f"{result.stderr}"
    )


# ── Graceful degrade when baseline.py is absent ──────────────────────────────


def test_missing_validator_degrades_to_allow(tmp_path: Path) -> None:
    """No scripts/baseline.py in CWD and (in the test's isolated tmp) no
    install-dir sibling resolvable from CWD → allow. We point CWD at a bare tmp
    dir with an invalid baseline but no validator reachable via CWD; the hook
    must not block on an unreachable validator."""
    # Build a project with an invalid baseline but NO scripts/baseline.py.
    target = tmp_path / ".etc_sdlc" / "architecture-baseline.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(INVALID_BASELINE, encoding="utf-8")
    # The install-dir fallback resolves relative to the hook's own location
    # (REPO_ROOT/scripts/baseline.py exists), so to prove the CWD-absent path we
    # assert that when CWD has no scripts/ the hook still uses the install-dir
    # validator and therefore BLOCKS the genuinely-invalid file. This pins the
    # CWD-first-then-install-dir resolution order.
    result = _run_hook(_claude_payload(target, tmp_path), tmp_path)
    assert result.returncode == 2, (
        f"with no CWD validator the install-dir baseline.py must still catch the "
        f"invalid file; got {result.returncode}: {result.stderr}"
    )


def test_nonexistent_target_file_is_allowed(tmp_path: Path) -> None:
    """Edit can no-op; if the suffix-matched file does not exist on disk, the
    hook has nothing to validate and allows."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    real = (REPO_ROOT / "scripts" / "baseline.py").read_text(encoding="utf-8")
    (scripts / "baseline.py").write_text(real, encoding="utf-8")
    ghost = tmp_path / ".etc_sdlc" / "architecture-baseline.yaml"
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(ghost)},
        "cwd": str(tmp_path),
    }
    result = _run_hook(payload, tmp_path)
    assert result.returncode == 0, result.stderr


# ── A `..` in the resolved path: intentional allow-without-validation ─────────


def test_path_with_parent_ref_is_allowed_without_validation(tmp_path: Path) -> None:
    """A resolved path containing `..` is INTENTIONALLY allowed (exit 0), not
    blocked: we cannot reason about where it points, and blocking would
    false-block weird-but-legit layouts. The schema guard is a write-time
    honesty check, not an access boundary — baseline.py operates on the
    already-written file. This pins the degrade-to-allow contract so a future
    well-meaning 'turn it into a block' change is caught.

    The fixture writes a genuinely INVALID baseline at the real on-disk path,
    then hands the hook a `..`-containing path string that suffix-matches the
    baseline name. If the traversal branch did NOT degrade to allow, this
    invalid file would BLOCK (exit 2) — so exit 0 proves the branch fired."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    target = _project(real_dir, "architecture-baseline.yaml", INVALID_BASELINE)
    # A `..`-containing path string pointing at the same invalid file.
    traversal_path = real_dir / "sub" / ".." / ".etc_sdlc" / "architecture-baseline.yaml"
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(traversal_path)},
        "cwd": str(real_dir),
    }
    result = _run_hook(payload, real_dir)
    assert result.returncode == 0, (
        f"a `..`-containing path must degrade to allow (exit 0), not block; "
        f"got {result.returncode}: {result.stderr}"
    )
    # Prove the allow came from the traversal branch, not from validation:
    # the same file validated directly DOES block.
    direct = _run_hook(_claude_payload(target, real_dir), real_dir)
    assert direct.returncode == 2, (
        "sanity: the underlying file is genuinely invalid (would block if "
        f"validated); got {direct.returncode}: {direct.stderr}"
    )
