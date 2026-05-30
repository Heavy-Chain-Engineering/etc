#!/usr/bin/env python3
"""ETC runtime compatibility helpers.

This module is intentionally dependency-free. Hooks, skills, installers, and
CI checks can call it in small repos where only Python's standard library is
available.
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


SCHEMA_VERSION = 1
PASS_STATUSES = frozenset({"pass", "passed", "ok", "success", "complete", "completed"})

SHARED_ARTIFACT_FIELDS = frozenset(
    {
        "schema_version",
        "task_id",
        "client",
        "created_at",
        "updated_at",
        "source_commit",
        "changed_files",
        "status",
        "checks",
        "notes",
    }
)

ARTIFACT_SPECIFIC_FIELDS = {
    "readiness.json": frozenset(
        {
            "phase",
            "risk_tier",
            "files_in_scope",
            "acceptance_criteria",
            "required_reading",
            "test_strategy",
            "dependencies",
            "ready",
        }
    ),
    "reading-ledger.json": frozenset(
        {
            "required_reading",
            "read_entries",
            "coverage",
            "missing",
            "fresh",
        }
    ),
    "review.json": frozenset(
        {
            "reviewer",
            "review_type",
            "findings",
            "required_fixes",
            "verdict",
            "fresh_for_changed_files",
        }
    ),
    "completion.json": frozenset(
        {
            "test_evidence",
            "review_evidence",
            "acceptance_criteria_results",
            "unresolved_risks",
            "final_status",
        }
    ),
}

REQUIRED_TASK_ARTIFACTS = (
    "readiness.json",
    "reading-ledger.json",
    "review.json",
    "completion.json",
)

REQUIRED_SCHEMA_FILES = (
    "readiness.schema.json",
    "reading-ledger.schema.json",
    "review.schema.json",
    "completion.schema.json",
)

GENERATED_CODEX_SURFACES = (
    "AGENTS.md",
    "gate-classification.json",
    "standards",
    ".codex",
    ".agents/skills",
)

CODEX_OUTPUT_SCAN_SURFACES = (
    "AGENTS.md",
    "gate-classification.json",
    "standards",
    ".codex",
    ".agents/skills",
)

PROTECTED_HARNESS_PATHS = (
    "AGENTS.md",
    "compile-sdlc.py",
    "install.sh",
    "gate-classification.json",
    "spec/etc_sdlc.yaml",
    "scripts/etc_runtime.py",
)

PROTECTED_HARNESS_PREFIXES = (
    ".agents/",
    ".codex/",
    "hooks/",
    "skills/",
    "standards/",
)

UNSUPPORTED_CODEX_GAPS = (
    "Prompt hook lifecycle is represented by task proof artifacts.",
    "Agent hook lifecycle is represented by explicit subagent proof artifacts.",
    "ConfigChange lifecycle is represented by edit/Bash guards plus ci-check.",
)

CI_ENABLED = "enabled"
CI_AVAILABLE = "available-but-not-wired"
CI_UNSUPPORTED = "unsupported"
CLAUDE_HOME_NEEDLE = "~/." + "claude"
CLAUDE_HOME_MESSAGE = "hardcoded " + CLAUDE_HOME_NEEDLE + " in Codex output"
ETC_CODEX_BEGIN = "<!-- ETC_CODEX_BEGIN -->"
ETC_CODEX_END = "<!-- ETC_CODEX_END -->"


class PayloadNormalizationError(ValueError):
    """Raised when a hook payload cannot be normalized safely."""


@dataclass(frozen=True)
class ArtifactValidationResult:
    """Machine-readable result for task proof validation."""

    ok: bool
    errors: list[str]
    path: Path


@dataclass(frozen=True)
class SurfaceState:
    """Presence state for one required Codex install surface."""

    name: str
    present: bool
    path: Path


@dataclass(frozen=True)
class CodexCheckReport:
    """Deterministic Codex project validation result."""

    repo_root: Path
    errors: list[str]
    surfaces: list[SurfaceState]
    changed_files: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def normalize_hook_payload(payload: dict[str, Any], client: str = "codex") -> dict[str, Any]:
    """Normalize a client hook payload into ETC's stable internal shape."""
    if client != "codex":
        raise PayloadNormalizationError(f"Unsupported client for hook normalization: {client}")
    if not isinstance(payload, dict):
        raise PayloadNormalizationError("Hook payload must be a JSON object")

    event = str(payload.get("hook_event_name") or payload.get("event") or "unknown")
    tool_name = str(payload.get("tool_name") or "")
    tool_kind = _tool_kind(event, tool_name)
    cwd = str(payload.get("cwd") or os.getcwd())
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        raise PayloadNormalizationError("tool_input must be a JSON object when present")

    commands: list[str] = []
    file_changes: list[dict[str, str]] = []

    if tool_kind == "shell":
        command = tool_input.get("command")
        if isinstance(command, str) and command:
            commands.append(command)

    if tool_kind == "edit":
        if tool_name == "apply_patch":
            command = tool_input.get("command")
            if not isinstance(command, str) or not command.strip():
                raise PayloadNormalizationError("apply_patch payload missing tool_input.command")
            file_changes = _parse_apply_patch(command, cwd)
        else:
            file_path = tool_input.get("file_path")
            if isinstance(file_path, str) and file_path:
                file_changes = [
                    {
                        "path": _normalize_path(file_path, cwd),
                        "change_type": "modify",
                    }
                ]

    edited_files = _unique(change["path"] for change in file_changes)

    return {
        "schema_version": SCHEMA_VERSION,
        "client": client,
        "event": event,
        "tool_name": tool_name,
        "tool_kind": tool_kind,
        "cwd": cwd,
        "edited_files": edited_files,
        "file_changes": file_changes,
        "commands": commands,
        "raw_payload_available": True,
    }


def resolve_install_paths(
    client: str,
    scope: str,
    cwd: str | Path | None = None,
    home: str | Path | None = None,
) -> dict[str, Path]:
    """Resolve install paths without hardcoded Claude roots."""
    home_path = Path(home).expanduser() if home is not None else Path.home()
    cwd_path = Path(cwd).resolve() if cwd is not None else Path.cwd()
    project_root = _discover_project_root(cwd_path)

    if client == "codex":
        if scope == "project":
            config_root = project_root / ".codex"
            return {
                "config_root": config_root,
                "hooks": config_root / "hooks",
                "agents": config_root / "agents",
                "skills": project_root / ".agents" / "skills",
                "standards": project_root / "standards",
                "runtime": config_root / "scripts",
                "schemas": config_root / "schemas",
            }
        if scope == "user":
            config_root = home_path / ".codex"
            return {
                "config_root": config_root,
                "hooks": config_root / "hooks",
                "agents": config_root / "agents",
                "skills": home_path / ".agents" / "skills",
                "standards": home_path / "standards",
                "runtime": config_root / "scripts",
                "schemas": config_root / "schemas",
            }
        raise ValueError(f"Unsupported codex install scope: {scope}")

    if client == "claude":
        config_root = home_path / ".claude"
        return {
            "config_root": config_root,
            "hooks": config_root / "hooks",
            "agents": config_root / "agents",
            "skills": config_root / "skills",
            "runtime": config_root / "scripts",
            "schemas": config_root / "schemas",
        }

    raise ValueError(f"Unsupported client: {client}")


def validate_task_artifact(
    repo_root: str | Path,
    task_id: str,
    artifact_name: str,
    changed_files: list[str] | None = None,
) -> ArtifactValidationResult:
    """Validate a task-scoped proof artifact by schema and freshness."""
    root = Path(repo_root)
    artifact_path = root / ".etc_sdlc" / "tasks" / task_id / artifact_name
    errors: list[str] = []

    if artifact_name not in ARTIFACT_SPECIFIC_FIELDS:
        return ArtifactValidationResult(
            ok=False,
            errors=[f"unsupported artifact type: {artifact_name}"],
            path=artifact_path,
        )

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ArtifactValidationResult(
            ok=False,
            errors=[f"missing artifact: {artifact_path}"],
            path=artifact_path,
        )
    except json.JSONDecodeError as exc:
        return ArtifactValidationResult(
            ok=False,
            errors=[f"invalid JSON: {exc.msg}"],
            path=artifact_path,
        )

    if not isinstance(payload, dict):
        errors.append("artifact root must be a JSON object")
        return ArtifactValidationResult(ok=False, errors=errors, path=artifact_path)

    required_fields = SHARED_ARTIFACT_FIELDS | ARTIFACT_SPECIFIC_FIELDS[artifact_name]
    for field in sorted(required_fields):
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("task_id") != task_id:
        errors.append(f"task_id mismatch: expected {task_id}")
    if payload.get("client") != "codex":
        errors.append("client must be codex")

    errors.extend(_validate_pass_semantics(payload, artifact_name))

    updated_at = _parse_timestamp(payload.get("updated_at"), "updated_at", errors)
    declared_changed_files = payload.get("changed_files")
    if not isinstance(declared_changed_files, list):
        errors.append("changed_files must be a list")
        declared_changed_files = []

    for changed_file in changed_files or []:
        if changed_file not in declared_changed_files:
            errors.append(f"changed file not covered by artifact: {changed_file}")
        if updated_at is not None:
            changed_path = root / changed_file
            if changed_path.exists():
                changed_mtime = datetime.fromtimestamp(changed_path.stat().st_mtime, tz=UTC)
                if changed_mtime > updated_at:
                    errors.append(f"artifact stale for changed file: {changed_file}")

    if artifact_name == "reading-ledger.json":
        errors.extend(_validate_read_entries(payload.get("read_entries")))

    return ArtifactValidationResult(ok=not errors, errors=errors, path=artifact_path)


def validate_codex_project(repo_root: str | Path) -> CodexCheckReport:
    """Validate a project-local Codex harness install for CI."""
    root = _discover_project_root(Path(repo_root).resolve())
    surfaces = _codex_surface_states(root)
    changed_files = _git_changed_files(root)
    errors: list[str] = []

    errors.extend(_missing_surface_errors(surfaces))
    errors.extend(_generated_output_drift_errors(root))
    errors.extend(_gate_classification_errors(root))
    errors.extend(_task_artifact_errors(root, changed_files))
    errors.extend(_unauthorized_harness_change_errors(root, changed_files))
    errors.extend(_hardcoded_claude_home_errors(root))

    return CodexCheckReport(
        repo_root=root,
        errors=errors,
        surfaces=surfaces,
        changed_files=changed_files,
    )


def _codex_surface_states(repo_root: Path) -> list[SurfaceState]:
    runtime_executable = repo_root / ".codex" / "scripts" / "etc-runtime"
    runtime_module = repo_root / ".codex" / "scripts" / "etc_runtime.py"
    skills_dir = repo_root / ".agents" / "skills"
    agents_dir = repo_root / ".codex" / "agents"
    schemas_dir = repo_root / ".codex" / "schemas"
    expected_dir = repo_root / ".codex" / "expected"
    source_dir = repo_root / ".codex" / "source"
    return [
        SurfaceState(
            "instructions",
            (repo_root / "AGENTS.md").is_file(),
            repo_root / "AGENTS.md",
        ),
        SurfaceState("skills", _has_skill(skills_dir), skills_dir),
        SurfaceState("agents", _has_agent(agents_dir), agents_dir),
        SurfaceState(
            "hooks",
            (repo_root / ".codex" / "hooks.json").is_file()
            and (repo_root / ".codex" / "hooks").is_dir(),
            repo_root / ".codex",
        ),
        SurfaceState(
            "runtime",
            runtime_executable.is_file()
            and os.access(runtime_executable, os.X_OK)
            and runtime_module.is_file(),
            runtime_executable,
        ),
        SurfaceState("schemas", _has_required_schemas(schemas_dir), schemas_dir),
        SurfaceState(
            "standards",
            (repo_root / "standards" / "process" / "interactive-user-input.md").is_file()
            and (repo_root / "standards" / "process" / "codebase-navigation.md").is_file(),
            repo_root / "standards",
        ),
        SurfaceState(
            "expected",
            (expected_dir / "AGENTS.md").is_file(),
            expected_dir,
        ),
        SurfaceState(
            "source",
            (source_dir / "compile-sdlc.py").is_file()
            and (source_dir / "spec" / "etc_sdlc.yaml").is_file(),
            source_dir,
        ),
    ]


def _has_skill(path: Path) -> bool:
    return path.is_dir() and any(skill.is_file() for skill in path.glob("*/SKILL.md"))


def _has_agent(path: Path) -> bool:
    return path.is_dir() and any(agent.is_file() for agent in path.glob("*.toml"))


def _has_required_schemas(path: Path) -> bool:
    return path.is_dir() and all((path / schema).is_file() for schema in REQUIRED_SCHEMA_FILES)


def _missing_surface_errors(surfaces: list[SurfaceState]) -> list[str]:
    return [
        f"{surface.name} missing: {_display_path(surface.path)}"
        for surface in surfaces
        if not surface.present
    ]


def _generated_output_drift_errors(repo_root: Path) -> list[str]:
    expected_root = repo_root / ".codex" / "expected"
    if expected_root.is_dir():
        return _compare_generated_output(repo_root, expected_root)

    source_root = _codex_compile_source_root(repo_root)
    compiler = source_root / "compile-sdlc.py"
    spec = source_root / "spec" / "etc_sdlc.yaml"
    if not compiler.is_file():
        return ["compiler missing: compile-sdlc.py or .codex/source/compile-sdlc.py"]
    if not spec.is_file():
        return ["compiler spec missing: spec/etc_sdlc.yaml or .codex/source/spec/etc_sdlc.yaml"]

    with TemporaryDirectory(prefix="etc-codex-compile-") as temp_dir:
        output_dir = Path(temp_dir) / "codex"
        result = subprocess.run(
            [
                sys.executable,
                str(compiler),
                str(spec),
                "--client",
                "codex",
                "--output",
                str(output_dir),
            ],
            cwd=source_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            if not detail:
                detail = f"exit code {result.returncode}"
            return [f"fresh Codex compile failed: {detail}"]
        return _compare_generated_output(repo_root, output_dir)


def _codex_compile_source_root(repo_root: Path) -> Path:
    if (repo_root / "compile-sdlc.py").is_file() and (repo_root / "spec" / "etc_sdlc.yaml").is_file():
        return repo_root
    return repo_root / ".codex" / "source"


def _compare_generated_output(repo_root: Path, generated_root: Path) -> list[str]:
    errors: list[str] = []
    for relative_surface in GENERATED_CODEX_SURFACES:
        generated_surface = generated_root / relative_surface
        installed_surface = repo_root / relative_surface
        if generated_surface.is_file():
            if relative_surface == "AGENTS.md":
                errors.extend(_compare_agents_md(generated_surface, installed_surface))
            elif not installed_surface.is_file():
                errors.append(f"generated output drift: {relative_surface} missing")
            elif generated_surface.read_bytes() != installed_surface.read_bytes():
                errors.append(f"generated output drift: {relative_surface}")
        elif generated_surface.is_dir():
            errors.extend(
                _compare_generated_directory(
                    repo_root,
                    generated_root,
                    generated_surface,
                )
            )
    return errors


def _compare_agents_md(generated_file: Path, installed_file: Path) -> list[str]:
    if not installed_file.is_file():
        return ["generated output drift: AGENTS.md missing"]

    generated = generated_file.read_text(encoding="utf-8").rstrip() + "\n"
    installed = installed_file.read_text(encoding="utf-8")
    if installed == generated:
        return []

    managed = _managed_codex_block(installed)
    if managed == generated:
        return []

    return ["generated output drift: AGENTS.md"]


def _managed_codex_block(content: str) -> str | None:
    try:
        start = content.index(ETC_CODEX_BEGIN) + len(ETC_CODEX_BEGIN)
        stop = content.index(ETC_CODEX_END, start)
    except ValueError:
        return None
    return content[start:stop].strip() + "\n"


def _compare_generated_directory(
    repo_root: Path,
    generated_root: Path,
    generated_surface: Path,
) -> list[str]:
    errors: list[str] = []
    for generated_file in _iter_files(generated_surface):
        relative_file = generated_file.relative_to(generated_root).as_posix()
        installed_file = repo_root / relative_file
        if not installed_file.is_file():
            errors.append(f"generated output drift: {relative_file} missing")
        elif generated_file.read_bytes() != installed_file.read_bytes():
            errors.append(f"generated output drift: {relative_file}")
    return errors


def _gate_classification_errors(repo_root: Path) -> list[str]:
    path = repo_root / "gate-classification.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["gate classification missing: gate-classification.json"]
    except json.JSONDecodeError as exc:
        return [f"gate classification invalid JSON: {exc.msg}"]

    if not isinstance(payload, dict):
        return ["gate classification root must be a JSON object"]
    if payload.get("client") != "codex":
        return ["gate classification client must be codex"]

    gates = payload.get("gates")
    if not isinstance(gates, dict) or not gates:
        return ["gate classification must include gates"]

    errors: list[str] = []
    for gate_name, gate in sorted(gates.items()):
        if not isinstance(gate, dict):
            errors.append(f"gate classification invalid gate: {gate_name}")
            continue
        if gate.get("codex_bucket") == "uncategorized":
            errors.append(f"gate classification uncategorized: {gate_name}")
        if "active_hook" not in gate:
            errors.append(f"gate classification missing active_hook: {gate_name}")
        if "result_parity" not in gate:
            errors.append(f"gate classification missing result_parity: {gate_name}")
    return errors


def _task_artifact_errors(repo_root: Path, changed_files: list[str]) -> list[str]:
    tasks_dir = repo_root / ".etc_sdlc" / "tasks"
    if not tasks_dir.is_dir():
        return ["missing task artifacts directory: .etc_sdlc/tasks"]

    task_dirs = sorted(path for path in tasks_dir.iterdir() if path.is_dir())
    if not task_dirs:
        return ["missing task artifacts: .etc_sdlc/tasks has no task directories"]

    errors: list[str] = []
    for task_dir in task_dirs:
        for artifact_name in REQUIRED_TASK_ARTIFACTS:
            result = validate_task_artifact(
                repo_root,
                task_id=task_dir.name,
                artifact_name=artifact_name,
                changed_files=changed_files,
            )
            errors.extend(
                f"{task_dir.name}/{artifact_name}: {error}"
                for error in result.errors
            )
    return errors


def _unauthorized_harness_change_errors(
    repo_root: Path,
    changed_files: list[str],
) -> list[str]:
    authorized_files = _completion_artifact_changed_files(repo_root)
    errors: list[str] = []
    for changed_file in changed_files:
        if _is_protected_harness_path(changed_file) and changed_file not in authorized_files:
            errors.append(f"unauthorized harness/config change: {changed_file}")
    return errors


def _completion_artifact_changed_files(repo_root: Path) -> set[str]:
    task_root = repo_root / ".etc_sdlc" / "tasks"
    covered: set[str] = set()
    if not task_root.is_dir():
        return covered

    for artifact_path in sorted(task_root.glob("*/completion.json")):
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if not _is_pass_status(payload.get("final_status")):
            continue
        changed_files = payload.get("changed_files")
        if isinstance(changed_files, list):
            covered.update(
                changed_file
                for changed_file in changed_files
                if isinstance(changed_file, str)
            )
    return covered


def _is_protected_harness_path(path: str) -> bool:
    return path in PROTECTED_HARNESS_PATHS or path.startswith(PROTECTED_HARNESS_PREFIXES)


def _hardcoded_claude_home_errors(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for relative_surface in CODEX_OUTPUT_SCAN_SURFACES:
        surface = repo_root / relative_surface
        if surface.is_file():
            if _file_contains(surface, CLAUDE_HOME_NEEDLE):
                errors.append(
                    f"{CLAUDE_HOME_MESSAGE}: {relative_surface}"
                )
        elif surface.is_dir():
            for path in _iter_files(surface):
                if _file_contains(path, CLAUDE_HOME_NEEDLE):
                    errors.append(
                        f"{CLAUDE_HOME_MESSAGE}: {path.relative_to(repo_root).as_posix()}"
                    )
    return errors


def _git_changed_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return []

    return _unique(
        _parse_git_status_path(line)
        for line in result.stdout.splitlines()
        if line.strip()
    )


def _parse_git_status_path(line: str) -> str:
    path = line[3:].strip()
    if " -> " in path:
        return path.rsplit(" -> ", maxsplit=1)[-1]
    return path.strip('"')


def _iter_files(path: Path) -> list[Path]:
    return sorted(child for child in path.rglob("*") if child.is_file())


def _file_contains(path: Path, needle: str) -> bool:
    try:
        return needle in path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False


def _display_path(path: Path) -> str:
    return path.as_posix()


def _codex_ci_state(report: CodexCheckReport) -> str:
    runtime_present = any(
        surface.name == "runtime" and surface.present for surface in report.surfaces
    )
    if not runtime_present:
        return CI_UNSUPPORTED
    if _codex_ci_workflow_wired(report.repo_root):
        return CI_ENABLED
    return CI_AVAILABLE


def _codex_ci_workflow_wired(repo_root: Path) -> bool:
    workflows_dir = repo_root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return False

    for workflow in _iter_files(workflows_dir):
        if workflow.suffix.lower() not in {".yml", ".yaml"}:
            continue
        try:
            content = workflow.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "ci-check --client codex" in content and "etc-runtime" in content:
            return True
    return False


def _parse_apply_patch(patch: str, cwd: str) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    pending_update_index: int | None = None

    for raw_line in patch.splitlines():
        line = raw_line.rstrip("\n")
        if line.startswith("*** Add File: "):
            changes.append(
                {
                    "path": _normalize_path(line.removeprefix("*** Add File: "), cwd),
                    "change_type": "create",
                }
            )
            pending_update_index = None
        elif line.startswith("*** Delete File: "):
            changes.append(
                {
                    "path": _normalize_path(line.removeprefix("*** Delete File: "), cwd),
                    "change_type": "delete",
                }
            )
            pending_update_index = None
        elif line.startswith("*** Update File: "):
            changes.append(
                {
                    "path": _normalize_path(line.removeprefix("*** Update File: "), cwd),
                    "change_type": "modify",
                }
            )
            pending_update_index = len(changes) - 1
        elif line.startswith("*** Move to: "):
            if pending_update_index is None:
                raise PayloadNormalizationError("apply_patch move missing preceding update file")
            changes[pending_update_index]["change_type"] = "move_from"
            changes.append(
                {
                    "path": _normalize_path(line.removeprefix("*** Move to: "), cwd),
                    "change_type": "move_to",
                }
            )
            pending_update_index = None

    if not changes:
        raise PayloadNormalizationError("apply_patch command contains no file changes")

    return changes


def _discover_project_root(cwd: Path) -> Path:
    """Return the nearest parent containing .git, or cwd when none exists."""
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _normalize_path(path: str, cwd: str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()

    cwd_path = Path(cwd)
    try:
        return candidate.relative_to(cwd_path).as_posix()
    except ValueError:
        return candidate.as_posix()


def _tool_kind(event: str, tool_name: str) -> str:
    if event in {"Stop", "SubagentStop"}:
        return "stop"
    if event in {"SessionStart", "PreCompact", "PostCompact"}:
        return "session"
    if tool_name in {"apply_patch", "Edit", "Write"}:
        return "edit"
    if tool_name in {"Bash", "unified_exec", "exec_command"}:
        return "shell"
    if tool_name in {"Task", "Agent", "spawn_agent"}:
        return "subagent"
    return "unknown"


def _unique(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _parse_timestamp(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field} must be an ISO-8601 timestamp")
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _validate_pass_semantics(payload: dict[str, Any], artifact_name: str) -> list[str]:
    errors: list[str] = []

    if not _is_pass_status(payload.get("status")):
        errors.append("status must be pass")
    errors.extend(_validate_status_entries(payload.get("checks"), "checks"))

    if artifact_name == "readiness.json":
        if payload.get("ready") is not True:
            errors.append("ready must be true")
    elif artifact_name == "reading-ledger.json":
        if payload.get("fresh") is not True:
            errors.append("fresh must be true")
        missing = payload.get("missing")
        if isinstance(missing, list) and missing:
            errors.append("missing must be empty")
    elif artifact_name == "review.json":
        if not _is_pass_status(payload.get("verdict")):
            errors.append("verdict must be pass")
        required_fixes = payload.get("required_fixes")
        if isinstance(required_fixes, list) and required_fixes:
            errors.append("required_fixes must be empty")
        if payload.get("fresh_for_changed_files") is not True:
            errors.append("fresh_for_changed_files must be true")
    elif artifact_name == "completion.json":
        if not _is_pass_status(payload.get("final_status")):
            errors.append("final_status must be pass")
        unresolved = payload.get("unresolved_risks")
        if isinstance(unresolved, list) and unresolved:
            errors.append("unresolved_risks must be empty")
        errors.extend(_validate_status_entries(payload.get("test_evidence"), "test_evidence"))
        errors.extend(
            _validate_status_entries(
                payload.get("acceptance_criteria_results"),
                "acceptance_criteria_results",
            )
        )

    return errors


def _validate_status_entries(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{field} must be a list"]

    errors: list[str] = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            errors.append(f"{field}[{index}] must be a JSON object")
            continue
        if not _is_pass_status(entry.get("status")):
            errors.append(f"{field}[{index}] status must be pass")
    return errors


def _is_pass_status(value: Any) -> bool:
    return isinstance(value, str) and value.lower() in PASS_STATUSES


def _validate_read_entries(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, list):
        return ["read_entries must be a list"]

    for index, entry in enumerate(value):
        prefix = f"read_entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be a JSON object")
            continue
        for field in ("path", "reason", "recorded_at"):
            if field not in entry:
                errors.append(f"{prefix} missing required field: {field}")
        if not any(field in entry for field in ("digest", "mtime")):
            errors.append(f"{prefix} missing deterministic freshness marker")
    return errors


def _cmd_hook_normalize(args: argparse.Namespace) -> int:
    try:
        payload = json.load(sys.stdin)
        normalized = normalize_hook_payload(payload, client=args.client)
    except (json.JSONDecodeError, PayloadNormalizationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    json.dump(normalized, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_path(args: argparse.Namespace) -> int:
    try:
        paths = resolve_install_paths(client=args.client, scope=args.scope)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    path = paths.get(args.kind)
    if path is None:
        print(f"ERROR: unsupported path kind: {args.kind}", file=sys.stderr)
        return 1
    print(path)
    return 0


def _cmd_task_validate(args: argparse.Namespace) -> int:
    if not args.changed_file:
        print(
            "ERROR: --changed-file is required for task artifact freshness validation",
            file=sys.stderr,
        )
        return 1

    result = validate_task_artifact(
        Path.cwd(),
        task_id=args.task_id,
        artifact_name=args.artifact,
        changed_files=args.changed_file,
    )
    if result.ok:
        print(f"OK: {result.path}")
        return 0

    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    if args.client == "codex":
        if args.scope != "project":
            print(
                "ERROR: codex doctor currently supports project scope only",
                file=sys.stderr,
            )
            return 1

        report = validate_codex_project(Path.cwd())
        print(f"client: {args.client}")
        print(f"scope: {args.scope}")
        print(f"project_root: {report.repo_root}")
        print(f"install_root: {report.repo_root / '.codex'}")
        for surface in report.surfaces:
            state = "present" if surface.present else "missing"
            print(f"{surface.name}: {state}")
        print(f"ci_state: {_codex_ci_state(report)}")
        print("unsupported_gaps:")
        for gap in UNSUPPORTED_CODEX_GAPS:
            print(f"- {gap}")
        if report.errors:
            print("errors:")
            for error in report.errors:
                print(f"- {error}")
            return 1
        return 0

    try:
        paths = resolve_install_paths(client=args.client, scope=args.scope)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"client: {args.client}")
    print(f"scope: {args.scope}")
    for key, value in paths.items():
        state = "present" if value.exists() else "missing"
        print(f"{key}: {value} ({state})")
    return 0


def _cmd_ci_check(args: argparse.Namespace) -> int:
    if args.client != "codex":
        print(f"ERROR: unsupported ci-check client: {args.client}", file=sys.stderr)
        return 1

    report = validate_codex_project(Path.cwd())
    if report.ok:
        print("OK: codex ci-check passed")
        return 0

    for error in report.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="etc-runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser("hook-normalize")
    normalize.add_argument("--client", default="codex")
    normalize.set_defaults(func=_cmd_hook_normalize)

    path_parser = subparsers.add_parser("path")
    path_parser.add_argument(
        "kind",
        choices=["config_root", "hooks", "agents", "skills", "runtime", "schemas"],
    )
    path_parser.add_argument("--client", default="codex")
    path_parser.add_argument("--scope", default="project")
    path_parser.set_defaults(func=_cmd_path)

    task = subparsers.add_parser("task")
    task_subparsers = task.add_subparsers(dest="task_command", required=True)
    validate = task_subparsers.add_parser("validate")
    validate.add_argument("--task-id", required=True)
    validate.add_argument("--artifact", required=True)
    validate.add_argument("--changed-file", action="append", default=[])
    validate.set_defaults(func=_cmd_task_validate)

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--client", default="codex")
    doctor.add_argument("--scope", default="project")
    doctor.set_defaults(func=_cmd_doctor)

    ci_check = subparsers.add_parser("ci-check")
    ci_check.add_argument("--client", default="codex")
    ci_check.set_defaults(func=_cmd_ci_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
