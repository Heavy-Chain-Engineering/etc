#!/usr/bin/env python3
"""Validate required-reading proof for edit hooks."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


PASS_STATUSES = {"pass", "passed", "ok", "success", "complete", "completed"}


def main() -> int:
    """Validate the active task's reading requirement for edited files."""
    active_task = Path(sys.argv[1])
    client = sys.argv[2]
    transcript = sys.argv[3]
    task_dir = Path(sys.argv[4])
    cwd = Path(sys.argv[5])
    edited_files = [
        line
        for line in os.environ.get("EDITED_FILES_ENV", "").splitlines()
        if line
    ]

    task = parse_task(active_task)
    required = require_list(task, "requires_reading")
    scopes = require_list(task, "files_in_scope")
    changed_files = scoped_files(edited_files, scopes, cwd)
    if not changed_files or not required:
        return 0

    task_id = str(task.get("id") or active_task.stem.removeprefix("task-"))
    if client == "codex":
        return validate_codex_ledger(
            task_dir,
            task_id,
            active_task,
            required,
            changed_files,
            cwd,
        )
    return validate_claude_transcript(transcript, required, active_task)


def parse_task(path: Path) -> dict[str, object]:
    """Parse the simple task YAML shape used by ETC task files."""
    task: dict[str, object] = {
        "id": path.stem.removeprefix("task-"),
        "status": "",
        "requires_reading": [],
        "files_in_scope": [],
    }
    current_list = ""

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw_line.startswith((" ", "\t")) and stripped.startswith("- ") and current_list:
            values = task[current_list]
            if isinstance(values, list):
                values.append(clean_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = clean_scalar(value)
        if key in {"requires_reading", "files_in_scope"}:
            current_list = key
            continue
        current_list = ""
        if key in task:
            task[key] = value

    return task


def clean_scalar(value: str) -> str:
    """Strip whitespace and common YAML scalar quotes."""
    return value.strip().strip('"').strip("'")


def require_list(task: dict[str, object], key: str) -> list[str]:
    """Return a string list task field."""
    value = task.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def scoped_files(files: list[str], scopes: list[str], cwd: Path) -> list[str]:
    """Return edited files covered by the active task scope."""
    scoped: list[str] = []
    for file_path in files:
        relative = relative_to_cwd(file_path, cwd)
        for scope in scopes:
            prefix = scope.rstrip("/") + "/"
            if relative == scope or relative.startswith(prefix):
                scoped.append(relative)
                break
    return scoped


def relative_to_cwd(file_path: str, cwd: Path) -> str:
    """Return cwd-relative path when possible."""
    path = Path(file_path)
    if not path.is_absolute():
        return file_path
    try:
        return path.relative_to(cwd).as_posix()
    except ValueError:
        return file_path


def validate_codex_ledger(
    task_dir: Path,
    task_id: str,
    active_task: Path,
    required: list[str],
    changed_files: list[str],
    cwd: Path,
) -> int:
    """Validate task-scoped Codex reading-ledger proof."""
    ledger_path = first_existing_ledger(task_dir, task_id, active_task)
    if ledger_path is None:
        return block_missing_ledger(task_id, active_task, task_dir)

    errors = validate_ledger(ledger_path, task_id, required, changed_files, cwd)
    if errors:
        print("BLOCKED: Codex reading-ledger.json is missing required proof:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2
    return 0


def validate_claude_transcript(
    transcript: str,
    required: list[str],
    active_task: Path,
) -> int:
    """Preserve legacy transcript-backed Claude behavior."""
    if not transcript:
        return 0

    missing = transcript_missing(Path(transcript), required)
    if not missing:
        return 0

    print("BLOCKED: Task requires reading these files first:", file=sys.stderr)
    for path in missing:
        print(f"  - {path}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        f"Read the required files before modifying code. The task file is: {active_task}",
        file=sys.stderr,
    )
    return 2


def ledger_candidates(task_dir: Path, task_id: str, active_task: Path) -> list[Path]:
    """Return supported reading-ledger paths for old and new task layouts."""
    names = [task_id, active_task.stem]
    candidates: list[Path] = []
    for name in names:
        candidate = task_dir / name / "reading-ledger.json"
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def first_existing_ledger(
    task_dir: Path,
    task_id: str,
    active_task: Path,
) -> Path | None:
    """Return the first present reading-ledger artifact."""
    for candidate in ledger_candidates(task_dir, task_id, active_task):
        if candidate.is_file():
            return candidate
    return None


def validate_ledger(
    ledger_path: Path,
    task_id: str,
    required: list[str],
    changed_files: list[str],
    cwd: Path,
) -> list[str]:
    """Return validation errors for a reading-ledger artifact."""
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid reading-ledger.json: {exc.msg}"]

    if not isinstance(payload, dict):
        return ["reading-ledger.json root must be a JSON object"]

    errors = validate_ledger_metadata(payload, task_id)
    errors.extend(validate_ledger_reading(payload, required))
    errors.extend(validate_ledger_changes(payload, changed_files, cwd))
    return errors


def validate_ledger_metadata(payload: dict[str, object], task_id: str) -> list[str]:
    """Validate common ledger fields used by the hook."""
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("reading-ledger.json schema_version must be 1")
    if str(payload.get("task_id", "")) != task_id:
        errors.append(f"reading-ledger.json task_id must be {task_id}")
    if payload.get("client") != "codex":
        errors.append("reading-ledger.json client must be codex")
    if not pass_status(payload.get("status")):
        errors.append("reading-ledger.json status must be pass")
    if payload.get("fresh") is not True:
        errors.append("reading-ledger.json fresh must be true")

    missing = payload.get("missing")
    if isinstance(missing, list) and missing:
        errors.append("reading-ledger.json missing must be empty")
    return errors


def validate_ledger_reading(
    payload: dict[str, object],
    required: list[str],
) -> list[str]:
    """Validate required files are covered and recorded."""
    errors: list[str] = []
    ledger_required = payload.get("required_reading")
    if not isinstance(ledger_required, list):
        errors.append("reading-ledger.json required_reading must be a list")
        ledger_required = []
    for required_path in required:
        if required_path not in ledger_required:
            errors.append(f"required reading not covered by ledger: {required_path}")

    read_entries = payload.get("read_entries")
    if not isinstance(read_entries, list):
        errors.append("reading-ledger.json read_entries must be a list")
        read_entries = []

    read_paths = {
        entry.get("path")
        for entry in read_entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    for required_path in required:
        if required_path not in read_paths:
            errors.append(f"required reading not recorded in ledger: {required_path}")
    return errors


def validate_ledger_changes(
    payload: dict[str, object],
    changed_files: list[str],
    cwd: Path,
) -> list[str]:
    """Validate ledger change coverage and freshness."""
    errors: list[str] = []
    declared_changes = payload.get("changed_files")
    if not isinstance(declared_changes, list):
        errors.append("reading-ledger.json changed_files must be a list")
        declared_changes = []
    declared_change_set = {
        changed_file
        for changed_file in declared_changes
        if isinstance(changed_file, str)
    }
    for changed_file in changed_files:
        if changed_file not in declared_change_set:
            errors.append(f"changed file not covered by reading-ledger.json: {changed_file}")

    updated_at = parse_time(payload.get("updated_at"))
    if updated_at is None:
        errors.append("reading-ledger.json updated_at must be an ISO-8601 timestamp")
        return errors

    for changed_file in changed_files:
        changed_path = cwd / changed_file
        if changed_path.exists():
            changed_mtime = datetime.fromtimestamp(changed_path.stat().st_mtime, tz=timezone.utc)
            if changed_mtime > updated_at:
                errors.append(f"reading-ledger.json is stale for {changed_file}")
    return errors


def pass_status(value: object) -> bool:
    """Return whether a status value is passing."""
    return isinstance(value, str) and value.lower() in PASS_STATUSES


def parse_time(value: object) -> datetime | None:
    """Parse ISO-8601 timestamps accepted by task artifacts."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def transcript_missing(transcript_path: Path, required: list[str]) -> list[str]:
    """Return required files not present in the transcript text."""
    if not transcript_path.is_file():
        return required
    content = transcript_path.read_text(encoding="utf-8", errors="ignore")
    return [required_path for required_path in required if required_path not in content]


def block_missing_ledger(task_id: str, active_task: Path, task_dir: Path) -> int:
    """Print the Codex missing-ledger block message."""
    print("BLOCKED: Codex task-scope edit requires reading-ledger.json proof.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Expected one of:", file=sys.stderr)
    for candidate in ledger_candidates(task_dir, task_id, active_task):
        print(f"  - {candidate}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
