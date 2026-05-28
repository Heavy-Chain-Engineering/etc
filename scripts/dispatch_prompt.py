"""dispatch_prompt.py — mechanized per-dispatch prompt assembler (Ftmp-19e49f7c).

<!-- forward-only: dispatch assembly mechanized from F-2026-05-23 release tag onward -->

Replaces the hand-authored prose in ``skills/build/SKILL.md`` Step 6a with a
deterministic CLI that materializes the eight required sections from
``standards/process/subagent-dispatch.md``. The conductor invokes it
from the install dir (default ``~/.claude/scripts/``; resolves to
``$CLAUDE_CONFIG_DIR/scripts/`` if set)::

    python3 <install-dir>/scripts/dispatch_prompt.py assemble \\
        --feature-path <path> --task-id <id>

and reads the assembled prompt from stdout. Token-budget warnings (per
BR-010) go to stderr; stdout content is unaffected.

Composes on:
    - F022 stdlib-only helper convention (no new pyproject deps; PyYAML
      was already a dep).
    - F024 conditional-emission idiom — sections appear only when their
      input data is present (wiring contract, task intent).
    - F025 CLI shape — one subcommand, argparse, structured stderr.

Public API:

- ``assemble_dispatch_prompt(*, feature_path, task_id) -> str``
- ``maybe_emit_token_warning(prompt) -> bool``
- ``main(argv) -> int``

Forward-only per spec BR-013: applies to dispatches authored from the
F-2026-05-23 release tag onward. Pre-tag features that get re-built keep
the legacy prose path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

# ── Module constants ────────────────────────────────────────────────────

#: Token-budget warning threshold (per BR-010 / EC-008). Strict > 1000.
_TOKEN_BUDGET_LIMIT = 1000

#: stdlib heuristic for token count: 4 chars per token (per BR-010).
_CHARS_PER_TOKEN = 4

#: User-flow sentence prefix sentinels (per BR-009). Both must appear in the
#: same AC string, before the next ``.`` or newline that follows ``As ``.
_USER_FLOW_PREFIX = "As "
_USER_FLOW_NAV_MARKER = ", navigate from"

#: Wiring-contract clause body. Lifted verbatim from
#: ``skills/build/SKILL.md`` line 1110 (the blockquote body). The single
#: ``<path>`` placeholder is substituted by the parent wiring file path
#: identified in ``files_in_scope``; when no parent file is present
#: (EC-006), the literal deferred placeholder is substituted instead.
_WIRING_CONTRACT_CLAUSE = (
    "Your task creates a user-facing surface (route/modal/tab/sidebar entry/"
    "wizard step) per the User-flow sentence in your AC. The surface is NOT "
    "done until it is wired into the parent navigation graph in the SAME "
    "commit as the new surface. Your `files_in_scope` includes the parent "
    "wiring file at `<path>` for this purpose. Before reporting success, "
    "run `grep -rn \"<your-route-or-component-name>\" <project>/frontend/src` "
    "(or the equivalent for your stack) and confirm at least one parent "
    "surface references it via `<Link>`, `<Tab>`, sidebar-config entry, or "
    "equivalent. If the parent file does not contain a working reference "
    "after your edits, do not report success. See "
    "`standards/process/user-flow-completeness.md` (Dispatch-time Wiring "
    "Contract section) for the full rule."
)

#: Deferred-path placeholder per EC-006 / SKILL.md lines 1115-1118.
_WIRING_DEFERRED_PATH = (
    "(deferred — no parent file in scope; escalate if you "
    "discover the surface needs to be wired)"
)

#: Report-back format. Lifted verbatim from
#: ``standards/process/subagent-dispatch.md`` §Required dispatch sections
#: item 8 lines 43-46. Angle-bracket placeholders are PRESERVED — the
#: subagent reads them as instructions for what to surface.
_REPORT_BACK_BODY = (
    "Report back with: (a) <pytest/verify output>; "
    "(b) <key artifact path or diff>;\n"
    "(c) <one architectural decision you made beyond the spec>; "
    "(d) <any gaps>."
)


# ── Errors ──────────────────────────────────────────────────────────────


class DispatchAssemblyError(RuntimeError):
    """Raised when the assembler cannot produce a valid dispatch prompt.

    The CLI maps these to stderr + exit 1; tests assert on the message
    substring per the spec EC-001..EC-005 contracts.
    """


# ── Public API ──────────────────────────────────────────────────────────


def assemble_dispatch_prompt(*, feature_path: Path, task_id: str) -> str:
    """Assemble the per-dispatch prompt for ``task_id`` under ``feature_path``.

    Implements the eight required sections from
    ``standards/process/subagent-dispatch.md``. Section 2 (task intent) and
    the wiring-contract appendix are conditional per BR-003 / BR-009.

    Args:
        feature_path: Feature directory containing ``spec.md`` +
            ``state.yaml`` + ``tasks/``.
        task_id: Task identifier (the leading numeric prefix of the task
            YAML filename, e.g. ``"001"``).

    Returns:
        The assembled prompt as a single string with section headings.

    Raises:
        DispatchAssemblyError: When required inputs are missing or
            malformed (EC-001 through EC-005).
    """
    if not feature_path.is_dir():
        raise DispatchAssemblyError(
            f"feature-path {feature_path} does not exist"
        )

    spec_paragraph = _extract_summary_paragraph(feature_path)
    state_data = _load_state_yaml(feature_path)
    feature_id = _resolve_feature_id(feature_path, state_data)
    task_yaml_path, task_data = _load_task_yaml(feature_path, task_id)
    _validate_task_yaml(task_yaml_path, task_data)

    sections: list[str] = []
    sections.append(_render_feature_intent(feature_id, spec_paragraph))

    task_intent = _coerce_str(task_data.get("intent"))
    if task_intent:
        sections.append(f"**Task intent:** {task_intent}")

    sections.append(f"**Task YAML:** {task_yaml_path}")
    sections.append(_render_required_reading(task_data))
    sections.append(_render_files_in_scope(task_data))
    sections.append(_render_acceptance_criteria(task_data))
    sections.append(
        _render_cross_task_awareness(state_data, task_id, feature_path)
    )
    sections.append(_REPORT_BACK_BODY)

    wiring_section = _maybe_render_wiring_contract(task_data)
    if wiring_section is not None:
        sections.append(wiring_section)

    return "\n\n".join(sections) + "\n"


def maybe_emit_token_warning(prompt: str) -> bool:
    """Emit the BR-010 warning to stderr when ``len(prompt) // 4 > 1000``.

    EC-008: strict greater-than. Exactly 1000 tokens does NOT warn.

    Returns ``True`` iff the warning was emitted.
    """
    approx_tokens = len(prompt) // _CHARS_PER_TOKEN
    if approx_tokens <= _TOKEN_BUDGET_LIMIT:
        return False
    print(
        f"WARNING: assembled dispatch prompt ~{approx_tokens} tokens "
        f"exceeds 1000-token target. AC list may be substantial; verify "
        f"content is task-specific and not duplicating system-overlay or "
        f"role-manifest content.",
        file=sys.stderr,
    )
    return True


# ── Internals: spec.md extraction (BR-002, EC-001, EC-002) ──────────────


def _extract_summary_paragraph(feature_path: Path) -> str:
    """Return the first paragraph of ``spec.md``'s first ``## Summary`` section.

    "First paragraph" = the contiguous non-blank lines after the heading,
    terminated by the first blank line OR the next ``#`` heading OR EOF.
    """
    spec_path = feature_path / "spec.md"
    if not spec_path.is_file():
        raise DispatchAssemblyError(
            f"{spec_path} does not exist; feature lacks a spec"
        )
    lines = spec_path.read_text().splitlines()
    summary_index = _find_summary_heading(lines)
    if summary_index is None:
        raise DispatchAssemblyError(
            f"{spec_path} missing required ## Summary section"
        )
    paragraph_lines = _collect_first_paragraph(lines, summary_index + 1)
    if not paragraph_lines:
        raise DispatchAssemblyError(
            f"{spec_path} Summary section is empty"
        )
    return " ".join(paragraph_lines).strip()


def _find_summary_heading(lines: list[str]) -> int | None:
    """Return the index of the first ``## Summary`` heading, or ``None``."""
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped == "## Summary":
            return index
    return None


def _collect_first_paragraph(lines: list[str], start: int) -> list[str]:
    """Collect contiguous non-blank lines after ``start`` until blank/heading."""
    collected: list[str] = []
    for raw in lines[start:]:
        stripped = raw.strip()
        if not stripped:
            if collected:
                break
            continue
        if stripped.startswith("#"):
            break
        collected.append(stripped)
    return collected


# ── Internals: state.yaml + feature_id (BR-002, EC-005) ─────────────────


def _load_state_yaml(feature_path: Path) -> dict[str, Any]:
    """Load ``state.yaml`` from ``feature_path``; raise on absent file (EC-005)."""
    state_path = feature_path / "state.yaml"
    if not state_path.is_file():
        raise DispatchAssemblyError(
            f"{state_path} does not exist; feature has not been "
            f"allocated via /spec"
        )
    loaded = yaml.safe_load(state_path.read_text())
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _resolve_feature_id(
    feature_path: Path, state_data: dict[str, Any]
) -> str:
    """Resolve the feature ID per BR-002 priority order.

    1. ``state.yaml`` ``build.feature``
    2. ``state.yaml`` top-level ``feature_id``
    3. Feature directory basename
    """
    build = state_data.get("build")
    if isinstance(build, dict):
        candidate = build.get("feature")
        if isinstance(candidate, str) and candidate:
            return candidate

    top_level = state_data.get("feature_id")
    if isinstance(top_level, str) and top_level:
        return top_level

    return feature_path.name


# ── Internals: task YAML (BR-003..BR-009, EC-003, EC-004) ───────────────


def _load_task_yaml(
    feature_path: Path, task_id: str
) -> tuple[Path, dict[str, Any]]:
    """Find + parse the unique ``<task_id>*.yaml`` under ``tasks/``."""
    tasks_dir = feature_path / "tasks"
    if not tasks_dir.is_dir():
        raise DispatchAssemblyError(
            f"no task YAML matching id {task_id} under {tasks_dir}"
        )
    matches = sorted(tasks_dir.glob(f"{task_id}*.yaml"))
    if len(matches) == 0:
        raise DispatchAssemblyError(
            f"no task YAML matching id {task_id} under {tasks_dir}"
        )
    if len(matches) > 1:
        raise DispatchAssemblyError(
            f"ambiguous task-id {task_id} matched {len(matches)} task YAMLs"
        )
    task_yaml_path = matches[0]
    try:
        loaded = yaml.safe_load(task_yaml_path.read_text())
    except yaml.YAMLError as exc:
        raise DispatchAssemblyError(
            f"failed to parse {task_yaml_path}: {exc}"
        ) from exc
    if not isinstance(loaded, dict):
        raise DispatchAssemblyError(
            f"failed to parse {task_yaml_path}: top-level structure is not a mapping"
        )
    return task_yaml_path, loaded


def _validate_task_yaml(task_path: Path, task_data: dict[str, Any]) -> None:
    """Validate the task YAML has the required ``acceptance_criteria`` field."""
    if "acceptance_criteria" not in task_data:
        raise DispatchAssemblyError(
            f"{task_path} missing required field acceptance_criteria"
        )


# ── Internals: section renderers ────────────────────────────────────────


def _render_feature_intent(feature_id: str, paragraph: str) -> str:
    """Render section 1 — feature intent prefix + lifted Summary paragraph."""
    return f"**Feature intent ({feature_id}):** {paragraph}"


def _render_required_reading(task_data: dict[str, Any]) -> str:
    """Render section 4 — required reading list (BR-004, EC-007)."""
    entries = task_data.get("requires_reading") or []
    heading = "**Required reading (in order):**"
    if not entries:
        return f"{heading}\n(none)"
    rendered: list[str] = []
    for index, entry in enumerate(entries, start=1):
        rendered.append(_render_reading_entry(index, entry))
    body = "\n".join(rendered)
    return f"{heading}\n{body}"


def _render_reading_entry(index: int, entry: Any) -> str:
    """Render one ``<N>. <path> — <commentary>`` line.

    The YAML's authored shape may be a bare string (no commentary) or a
    structured map ``{path: <p>, why: <c>}``. The bare-string form is the
    convention in this repo today; the map form is reserved for a future
    schema migration. Both render predictably.
    """
    if isinstance(entry, dict):
        path = entry.get("path") or entry.get("file") or ""
        commentary = entry.get("why") or entry.get("commentary") or ""
        if commentary:
            return f"{index}. {path} — {commentary}"
        return f"{index}. {path}"
    return f"{index}. {entry}"


def _render_files_in_scope(task_data: dict[str, Any]) -> str:
    """Render section 5 — files_in_scope, one per line (BR-005)."""
    entries = task_data.get("files_in_scope") or []
    body = "\n".join(f"- {path}" for path in entries) if entries else "(none)"
    return f"**Files in scope:**\n{body}"


def _render_acceptance_criteria(task_data: dict[str, Any]) -> str:
    """Render section 6 — verbatim AC list, numbered (BR-006)."""
    acs = task_data.get("acceptance_criteria") or []
    heading = f"**Acceptance criteria ({len(acs)} ACs):**"
    if not acs:
        return f"{heading}\n(none)"
    rendered = "\n".join(
        f"{index}. {ac}" for index, ac in enumerate(acs, start=1)
    )
    return f"{heading}\n{rendered}"


def _render_cross_task_awareness(
    state_data: dict[str, Any],
    task_id: str,
    feature_path: Path,
) -> str:
    """Render section 7 — wave-plan-derived sibling enumeration (BR-007)."""
    heading = "**Cross-task awareness:**"
    wave_plan = _extract_wave_plan(state_data)
    if wave_plan is None:
        return (
            f"{heading}\n"
            "(wave plan not yet computed; assume serial execution within feature)"
        )

    sibling_ids = _siblings_in_same_wave(wave_plan, task_id)
    if not sibling_ids:
        return (
            f"{heading}\n"
            "(no sibling tasks in this wave)"
        )

    sibling_titles = _read_sibling_titles(feature_path, sibling_ids)
    lines = [
        f"- task {sid}: {title}"
        for sid, title in sibling_titles
    ]
    return f"{heading}\n" + "\n".join(lines)


def _extract_wave_plan(state_data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Pull the wave_plan list from state.yaml (build.wave_plan convention)."""
    build = state_data.get("build")
    if not isinstance(build, dict):
        return None
    plan = build.get("wave_plan")
    if not isinstance(plan, list) or not plan:
        return None
    return plan


def _siblings_in_same_wave(
    wave_plan: list[dict[str, Any]], task_id: str
) -> list[str]:
    """Return the other task IDs in the wave that contains ``task_id``."""
    for entry in wave_plan:
        if not isinstance(entry, dict):
            continue
        tasks = entry.get("tasks") or []
        if task_id in tasks:
            return [t for t in tasks if t != task_id and isinstance(t, str)]
    return []


def _read_sibling_titles(
    feature_path: Path, sibling_ids: list[str]
) -> list[tuple[str, str]]:
    """Resolve ``(task_id, title)`` for each sibling via YAML lookup."""
    tasks_dir = feature_path / "tasks"
    out: list[tuple[str, str]] = []
    for sid in sibling_ids:
        title = _read_one_title(tasks_dir, sid)
        out.append((sid, title))
    return out


def _read_one_title(tasks_dir: Path, task_id: str) -> str:
    """Best-effort title lookup for a sibling task; returns ``"(no title)"`` on miss."""
    if not tasks_dir.is_dir():
        return "(no title)"
    matches = sorted(tasks_dir.glob(f"{task_id}*.yaml"))
    if not matches:
        return "(no title)"
    try:
        loaded = yaml.safe_load(matches[0].read_text())
    except yaml.YAMLError:
        return "(no title)"
    if not isinstance(loaded, dict):
        return "(no title)"
    title = loaded.get("title")
    if isinstance(title, str) and title:
        return title
    return "(no title)"


# ── Internals: wiring-contract (BR-009, EC-006) ─────────────────────────


def _maybe_render_wiring_contract(task_data: dict[str, Any]) -> str | None:
    """Return the wiring-contract section when a User-flow AC is present.

    Returns ``None`` when no AC contains the User-flow sentence prefix
    (AC-005). When the AC exists but no parent wiring file is in
    ``files_in_scope`` (EC-006), substitutes the deferred placeholder.
    """
    acs = task_data.get("acceptance_criteria") or []
    if not _has_user_flow_ac(acs):
        return None

    files = task_data.get("files_in_scope") or []
    parent_path = _identify_parent_wiring_file(files)
    path_to_render = parent_path if parent_path else _WIRING_DEFERRED_PATH
    clause = _WIRING_CONTRACT_CLAUSE.replace("<path>", path_to_render)
    return (
        "## Wiring contract (user-facing surface)\n\n"
        f"> {clause}"
    )


def _has_user_flow_ac(acs: list[Any]) -> bool:
    """Detect the literal ``As ... , navigate from`` pattern in any AC.

    Per BR-009: the literal prefix ``As `` must appear, and the
    ``, navigate from`` marker must appear AFTER it within the same AC
    string, before the next ``.`` or newline that closes the ``As ...``
    sentence.
    """
    for ac in acs:
        if not isinstance(ac, str):
            continue
        if _matches_user_flow_sentence(ac):
            return True
    return False


def _matches_user_flow_sentence(ac: str) -> bool:
    """True iff ``ac`` contains the User-flow sentence shape."""
    prefix_idx = ac.find(_USER_FLOW_PREFIX)
    if prefix_idx < 0:
        return False
    # Window from the prefix to the next sentence terminator (``.`` or ``\n``).
    tail = ac[prefix_idx:]
    terminator_dot = tail.find(".")
    terminator_nl = tail.find("\n")
    candidates = [t for t in (terminator_dot, terminator_nl) if t >= 0]
    end = min(candidates) if candidates else len(tail)
    window = tail[:end]
    return _USER_FLOW_NAV_MARKER in window


def _identify_parent_wiring_file(files: list[Any]) -> str | None:
    """Pick the parent wiring file from ``files_in_scope`` (per BR-009).

    Heuristic per /build Step 6a.5/6a.6: the parent-wire entry is the
    last item added to ``files_in_scope`` and is conventionally a
    sidebar/nav/router config file (e.g. ``SidebarConfig.ts``,
    ``router.tsx``, ``nav.ts``, ``Sidebar.tsx``, ``Header.tsx``).
    When more than one file is present, we prefer the entry that
    matches the parent-wire vocabulary; otherwise fall back to the last
    entry (Step 6a.5 append order). When only one file is present, we
    treat that as the TARGET (not the parent) — no parent wired.
    """
    str_files = [f for f in files if isinstance(f, str)]
    if len(str_files) < 2:
        return None
    parent_markers = (
        "sidebar",
        "nav",
        "router",
        "route",
        "tab",
        "menu",
        "header",
        "shell",
        "layout",
    )
    for path in str_files:
        lowered = path.lower()
        if any(marker in lowered for marker in parent_markers):
            return path
    # Fallback: last entry per /build Step 6a.5 append order.
    return str_files[-1]


# ── Helpers ─────────────────────────────────────────────────────────────


def _coerce_str(value: Any) -> str:
    """Return ``value`` stripped if str-like; else empty string."""
    if isinstance(value, str):
        return value.strip()
    return ""


# ── CLI ─────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Dispatches the ``assemble`` subcommand.

    Returns a process exit code:
        0 — success (prompt printed to stdout; optional warning to stderr).
        1 — operational error (missing path, malformed YAML, etc.).
        2 — argparse usage error (handled by argparse via SystemExit).
    """
    parser = argparse.ArgumentParser(
        prog="dispatch_prompt.py",
        description=(
            "Assemble the per-dispatch prompt (layer 3 of the four-layer "
            "subagent context model) from a feature directory + task ID."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    assemble = sub.add_parser(
        "assemble",
        help="Assemble the dispatch prompt for one task.",
    )
    assemble.add_argument(
        "--feature-path",
        required=True,
        help="Path to the feature directory (contains spec.md, state.yaml, tasks/).",
    )
    assemble.add_argument(
        "--task-id",
        required=True,
        help="Task identifier (the leading numeric prefix of the task YAML).",
    )

    args = parser.parse_args(argv)

    if args.command == "assemble":
        return _cmd_assemble(args.feature_path, args.task_id)

    # argparse with required=True should never let us reach here.
    parser.print_help(sys.stderr)  # pragma: no cover
    return 1  # pragma: no cover


def _cmd_assemble(feature_path_arg: str, task_id: str) -> int:
    """Execute the ``assemble`` subcommand; emit prompt + optional warning."""
    feature_path = Path(feature_path_arg)
    try:
        prompt = assemble_dispatch_prompt(
            feature_path=feature_path, task_id=task_id
        )
    except DispatchAssemblyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    sys.stdout.write(prompt)
    maybe_emit_token_warning(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
