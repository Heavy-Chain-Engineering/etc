#!/usr/bin/env python3
"""Normalize hook payloads for shell hooks.

The hooks support both legacy Claude payloads and Codex command-hook payloads.
Codex edit hooks can arrive as ``apply_patch`` commands, so file-based checks
must iterate the extracted edited files instead of reading one raw
``tool_input.file_path`` value.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCHEMA_VERSION = 1


class HookPayloadError(ValueError):
    """Raised when hook stdin cannot be normalized."""


def main() -> int:
    """Print the requested normalized payload field."""
    mode = sys.argv[1] if len(sys.argv) > 1 else "json"
    try:
        payload = json.load(sys.stdin)
        normalized = normalize_payload(payload)
    except (json.JSONDecodeError, HookPayloadError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if mode == "json":
        print(json.dumps(normalized.as_dict(), indent=2))
        return 0
    if mode == "files":
        print_lines(normalized.edited_files)
        return 0
    if mode == "commands":
        print_lines(normalized.commands)
        return 0
    if mode == "cwd":
        print(normalized.cwd)
        return 0
    if mode == "client":
        print(normalized.client)
        return 0
    if mode == "transcript":
        print(normalized.transcript_path)
        return 0

    print(f"ERROR: unsupported mode: {mode}", file=sys.stderr)
    return 1


class NormalizedPayload:
    """Small value object for normalized hook fields."""

    def __init__(
        self,
        *,
        client: str,
        event: str,
        tool_name: str,
        tool_kind: str,
        cwd: str,
        edited_files: list[str],
        commands: list[str],
        transcript_path: str,
    ) -> None:
        self.client = client
        self.event = event
        self.tool_name = tool_name
        self.tool_kind = tool_kind
        self.cwd = cwd
        self.edited_files = edited_files
        self.commands = commands
        self.transcript_path = transcript_path

    def as_dict(self) -> dict[str, object]:
        """Return the stable JSON representation."""
        return {
            "schema_version": SCHEMA_VERSION,
            "client": self.client,
            "event": self.event,
            "tool_name": self.tool_name,
            "tool_kind": self.tool_kind,
            "cwd": self.cwd,
            "edited_files": self.edited_files,
            "commands": self.commands,
            "transcript_path": self.transcript_path,
            "raw_payload_available": True,
        }


def normalize_payload(payload: object) -> NormalizedPayload:
    """Normalize raw or already-normalized hook JSON."""
    if not isinstance(payload, dict):
        raise HookPayloadError("hook payload must be a JSON object")

    event = string_value(payload, "hook_event_name") or string_value(payload, "event")
    tool_name = string_value(payload, "tool_name")
    cwd = string_value(payload, "cwd") or os.getcwd()
    client = detect_client(payload, tool_name)
    tool_kind = string_value(payload, "tool_kind") or tool_kind_for(event, tool_name)
    transcript_path = string_value(payload, "transcript_path")

    edited_files = string_list(payload.get("edited_files"))
    commands = string_list(payload.get("commands"))

    tool_input = payload.get("tool_input")
    if tool_input is not None and not isinstance(tool_input, dict):
        raise HookPayloadError("tool_input must be a JSON object when present")

    if isinstance(tool_input, dict):
        if not commands:
            command = tool_input.get("command")
            if isinstance(command, str) and command:
                commands = [command]
        if not edited_files:
            edited_files = edited_files_from_tool_input(tool_name, tool_input, cwd)

    return NormalizedPayload(
        client=client,
        event=event or "unknown",
        tool_name=tool_name,
        tool_kind=tool_kind,
        cwd=cwd,
        edited_files=unique_strings(edited_files),
        commands=unique_strings(commands),
        transcript_path=transcript_path,
    )


def edited_files_from_tool_input(
    tool_name: str,
    tool_input: dict[object, object],
    cwd: str,
) -> list[str]:
    """Extract edited files from a raw hook ``tool_input`` object."""
    if tool_name == "apply_patch":
        command = tool_input.get("command")
        if not isinstance(command, str) or not command.strip():
            raise HookPayloadError("apply_patch payload missing tool_input.command")
        return parse_apply_patch(command, cwd)

    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and file_path:
        return [normalize_path(file_path, cwd)]
    return []


def parse_apply_patch(patch: str, cwd: str) -> list[str]:
    """Extract changed paths from an ``apply_patch`` command string."""
    edited_files: list[str] = []
    saw_update = False

    for raw_line in patch.splitlines():
        line = raw_line.rstrip("\n")
        if line.startswith("*** Add File: "):
            edited_files.append(normalize_path(line.removeprefix("*** Add File: "), cwd))
            saw_update = False
        elif line.startswith("*** Delete File: "):
            edited_files.append(normalize_path(line.removeprefix("*** Delete File: "), cwd))
            saw_update = False
        elif line.startswith("*** Update File: "):
            edited_files.append(normalize_path(line.removeprefix("*** Update File: "), cwd))
            saw_update = True
        elif line.startswith("*** Move to: "):
            if not saw_update:
                raise HookPayloadError("apply_patch move missing preceding update file")
            edited_files.append(normalize_path(line.removeprefix("*** Move to: "), cwd))
            saw_update = False

    if not edited_files:
        raise HookPayloadError("apply_patch command contains no file changes")
    return edited_files


def normalize_path(path: str, cwd: str) -> str:
    """Return project-relative paths when possible."""
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()

    cwd_path = Path(cwd)
    try:
        return candidate.relative_to(cwd_path).as_posix()
    except ValueError:
        return candidate.as_posix()


def detect_client(payload: dict[object, object], tool_name: str) -> str:
    """Infer client while preserving explicit payload values."""
    client = payload.get("client")
    if isinstance(client, str) and client:
        return client
    if tool_name == "apply_patch" or "edited_files" in payload or "commands" in payload:
        return "codex"
    return "claude"


def tool_kind_for(event: str, tool_name: str) -> str:
    """Map raw hook metadata into broad tool categories."""
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


def string_value(payload: dict[object, object], key: str) -> str:
    """Return a string field or an empty string."""
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def string_list(value: object) -> list[str]:
    """Return a list containing only non-empty strings."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def unique_strings(values: list[str]) -> list[str]:
    """Preserve order while removing duplicate strings."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def print_lines(values: list[str]) -> None:
    """Print one value per line for shell ``while read`` loops."""
    for value in values:
        print(value)


if __name__ == "__main__":
    sys.exit(main())
