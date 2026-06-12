"""Behavioral tests for the ARCHITECTURE.md tier-0 wiring (F-2026-06-10).

Brownfield-architecture-baseline introduces ARCHITECTURE.md as the third
root tier-0 artifact — but it is a *brownfield-only* doc, so the wiring is
deliberately asymmetric:

  - check-tier-0.sh adds ARCHITECTURE.md to its SELF-EXEMPTION list ONLY
    (so /init-project can create it) — and the BLOCK CONDITION is unchanged.
    The block still fires on DOMAIN.md/PROJECT.md only; a missing
    ARCHITECTURE.md never blocks anything (forward-only, AC-1).
  - inject-standards.sh conditionally injects an ARCHITECTURE.md summary into
    subagent onboarding when the file exists, fail-open when absent (mirroring
    the INVARIANTS.md seam, AC-2).
  - the starter role-manifest templates add ARCHITECTURE.md to
    default_consumes (AC-2).

House pattern (see tests/test_check_value_hypothesis_schema.py):
subprocess-invoke the hook with a JSON payload on stdin; assert exit code
(0 = allow, 2 = block). Fixtures mirror REAL payload shapes — the Claude
shape carries tool_input.file_path; the Codex shape is tool_name=apply_patch
with the patch text in tool_input.command.

Test naming: test_should_<behavior>_when_<condition>.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK_TIER0 = REPO_ROOT / "hooks" / "check-tier-0.sh"
INJECT_STANDARDS = REPO_ROOT / "hooks" / "inject-standards.sh"
ROLE_TEMPLATES_DIR = REPO_ROOT / "skills" / "init-project" / "templates" / "roles"


# ── helpers ─────────────────────────────────────────────────────────────────


def _run(hook: Path, payload: dict[str, object], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
        cwd=cwd,
    )


def _git_repo(tmp_path: Path) -> Path:
    """A real git repo root — check-tier-0 resolves REPO_ROOT via git top-level."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _claude_edit(file_path: Path, cwd: Path) -> dict[str, object]:
    return {
        "tool_name": "Write",
        "tool_input": {"file_path": str(file_path)},
        "cwd": str(cwd),
    }


def _codex_edit(file_path: Path, cwd: Path) -> dict[str, object]:
    rel = file_path.relative_to(cwd).as_posix()
    patch = (
        "*** Begin Patch\n"
        f"*** Update File: {rel}\n"
        "@@\n"
        "+content\n"
        "*** End Patch\n"
    )
    return {
        "tool_name": "apply_patch",
        "tool_input": {"command": patch},
        "cwd": str(cwd),
    }


def _tier0_present(repo: Path) -> None:
    (repo / "DOMAIN.md").write_text("# Domain\n", encoding="utf-8")
    (repo / "PROJECT.md").write_text("# Project\n", encoding="utf-8")


# ── AC-1: check-tier-0 self-exemption (ONLY) + unchanged block condition ─────


def test_should_allow_editing_architecture_md_when_tier0_absent(tmp_path: Path) -> None:
    """ARCHITECTURE.md is on the self-exemption list — /init-project must be
    able to create it even before DOMAIN.md/PROJECT.md exist (it is created
    by the same brownfield init flow)."""
    repo = _git_repo(tmp_path)
    result = _run(CHECK_TIER0, _claude_edit(repo / "ARCHITECTURE.md", repo), repo)
    assert result.returncode == 0, (
        f"editing ARCHITECTURE.md itself must be exempt; got "
        f"{result.returncode}: {result.stderr}"
    )


def test_should_allow_creating_architecture_md_via_codex_when_tier0_absent(
    tmp_path: Path,
) -> None:
    """Same exemption under the Codex apply_patch payload shape."""
    repo = _git_repo(tmp_path)
    result = _run(CHECK_TIER0, _codex_edit(repo / "ARCHITECTURE.md", repo), repo)
    assert result.returncode == 0, result.stderr


def test_should_block_source_edit_when_only_architecture_md_present(tmp_path: Path) -> None:
    """THE forward-only pin: ARCHITECTURE.md is NOT added to the block
    condition. A repo with ARCHITECTURE.md but no DOMAIN.md/PROJECT.md must
    STILL block source edits — presence of ARCHITECTURE.md must not satisfy
    Tier 0, and it must not be a new required file either."""
    repo = _git_repo(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
    result = _run(CHECK_TIER0, _claude_edit(repo / "src" / "main.py", repo), repo)
    assert result.returncode == 2, (
        "block condition must be unchanged — DOMAIN.md/PROJECT.md still gate "
        f"source edits regardless of ARCHITECTURE.md; got {result.returncode}"
    )
    assert "DOMAIN.md" in result.stderr
    assert "PROJECT.md" in result.stderr


def test_should_not_require_architecture_md_when_tier0_present(tmp_path: Path) -> None:
    """The block condition is unchanged: a missing ARCHITECTURE.md never
    blocks. With DOMAIN.md + PROJECT.md present and no ARCHITECTURE.md, a
    source edit is allowed — ARCHITECTURE.md is NOT a required tier-0 file."""
    repo = _git_repo(tmp_path)
    _tier0_present(repo)
    result = _run(CHECK_TIER0, _claude_edit(repo / "src" / "main.py", repo), repo)
    assert result.returncode == 0, (
        f"missing ARCHITECTURE.md must never block (forward-only); got "
        f"{result.returncode}: {result.stderr}"
    )


def test_should_block_source_edit_when_all_tier0_missing(tmp_path: Path) -> None:
    """Regression guard: the original block behavior is fully intact."""
    repo = _git_repo(tmp_path)
    result = _run(CHECK_TIER0, _claude_edit(repo / "src" / "main.py", repo), repo)
    assert result.returncode == 2, result.stderr
    assert "BLOCKED" in result.stderr


# ── AC-2: inject-standards conditional ARCHITECTURE.md injection ─────────────


def _subagent_payload(cwd: Path) -> dict[str, object]:
    return {"agent_type": "backend-developer", "cwd": str(cwd)}


def test_should_inject_architecture_summary_when_file_exists(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    marker = "ARCH-MARKER-libs-contracts-owns-dtos"
    (repo / "ARCHITECTURE.md").write_text(
        f"# Architecture\n\n{marker}\n", encoding="utf-8"
    )
    result = _run(INJECT_STANDARDS, _subagent_payload(repo), repo)
    assert result.returncode == 0, result.stderr
    assert marker in result.stdout, (
        "ARCHITECTURE.md content must be injected into onboarding when present"
    )


def test_should_fail_open_when_architecture_md_absent(tmp_path: Path) -> None:
    """Fail-open, mirroring the INVARIANTS.md seam — no ARCHITECTURE.md means
    no architecture section, but onboarding still emits (exit 0) and the base
    sections remain intact."""
    repo = _git_repo(tmp_path)
    result = _run(INJECT_STANDARDS, _subagent_payload(repo), repo)
    assert result.returncode == 0, result.stderr
    assert "Project Architecture" not in result.stdout
    # base onboarding still present
    assert "Engineering Standards" in result.stdout


def test_should_label_injected_architecture_section_distinctly(tmp_path: Path) -> None:
    """A discoverable section header so subagents can find it — and so it is
    not confused with the Project Invariants seam."""
    repo = _git_repo(tmp_path)
    (repo / "ARCHITECTURE.md").write_text("# Arch\n", encoding="utf-8")
    result = _run(INJECT_STANDARDS, _subagent_payload(repo), repo)
    assert "Project Architecture" in result.stdout


# ── AC-2: role-manifest templates add ARCHITECTURE.md to default_consumes ────


def _starter_role_files() -> list[Path]:
    return sorted(ROLE_TEMPLATES_DIR.glob("*.yaml"))


def test_should_have_starter_role_templates() -> None:
    files = _starter_role_files()
    assert files, "expected starter role-manifest templates to exist"


def test_should_add_architecture_md_to_default_consumes_in_every_role() -> None:
    """Every starter role manifest must list ARCHITECTURE.md in
    default_consumes so brownfield normative context reaches every agent."""
    for role_file in _starter_role_files():
        data = yaml.safe_load(role_file.read_text(encoding="utf-8"))
        consumes = data.get("default_consumes") or []
        assert "ARCHITECTURE.md" in consumes, (
            f"{role_file.name} default_consumes is missing ARCHITECTURE.md"
        )


def test_should_keep_default_consumes_a_valid_list_in_every_role() -> None:
    """Guard: the edit must not corrupt the YAML or change the field type."""
    for role_file in _starter_role_files():
        data = yaml.safe_load(role_file.read_text(encoding="utf-8"))
        consumes = data.get("default_consumes")
        assert isinstance(consumes, list), f"{role_file.name}: default_consumes not a list"
        assert "DOMAIN.md" in consumes, f"{role_file.name}: lost DOMAIN.md"
        assert "PROJECT.md" in consumes, f"{role_file.name}: lost PROJECT.md"
