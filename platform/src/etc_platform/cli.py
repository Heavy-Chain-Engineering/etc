"""ETC Platform CLI — Typer-based command interface."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from etc_platform import __version__

app = typer.Typer(
    name="etc",
    help="ETC Orchestration Platform — AI agent SDLC orchestration",
)
console = Console()

# ---------------------------------------------------------------------------
# Phase subcommand group
# ---------------------------------------------------------------------------
phase_app = typer.Typer(help="Phase management commands")
app.add_typer(phase_app, name="phase")

# ---------------------------------------------------------------------------
# DoD subcommand group
# ---------------------------------------------------------------------------
dod_app = typer.Typer(help="Definition of Done management")
app.add_typer(dod_app, name="dod")

# ---------------------------------------------------------------------------
# Knowledge subcommand group
# ---------------------------------------------------------------------------
knowledge_app = typer.Typer(help="Knowledge graph management")
app.add_typer(knowledge_app, name="knowledge")

# ---------------------------------------------------------------------------
# Guardrails subcommand group
# ---------------------------------------------------------------------------
guardrails_app = typer.Typer(help="Guardrail management")
app.add_typer(guardrails_app, name="guardrails")

# ---------------------------------------------------------------------------
# Topology subcommand group
# ---------------------------------------------------------------------------
topology_app = typer.Typer(help="Topology management")
app.add_typer(topology_app, name="topology")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_active_project(conn: Any) -> dict[str, Any] | None:
    """Return the most recently created active project, or None."""
    return conn.execute(
        "SELECT * FROM projects WHERE status = 'active' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()


def _require_active_project(conn: Any) -> dict[str, Any]:
    """Return active project or print error and exit."""
    project = _get_active_project(conn)
    if project is None:
        console.print("[yellow]No active project found. Run 'etc init' to create one.[/yellow]")
        raise typer.Exit(0)
    return project


# ---------------------------------------------------------------------------
# Root callback
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
) -> None:
    if version:
        console.print(f"etc-platform {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None and not version:
        console.print(ctx.get_help())
        raise typer.Exit()


# ---------------------------------------------------------------------------
# etc status  (enhanced)
# ---------------------------------------------------------------------------


@app.command()
def status() -> None:
    """Show current project status, phase, and active agents."""
    from etc_platform.db import get_conn
    from etc_platform.phases import PhaseEngine

    with get_conn() as conn:
        result = conn.execute(
            "SELECT id, name, classification, status FROM projects WHERE status = 'active'"
        ).fetchall()

        if not result:
            console.print("[yellow]No active projects. Run 'etc init' to create one.[/yellow]")
            return

        table = Table(title="Active Projects")
        table.add_column("Name", style="bold")
        table.add_column("Classification")
        table.add_column("Status")
        table.add_column("Phase")
        table.add_column("DoD Progress")
        table.add_column("Events")
        table.add_column("ID", style="dim")

        for row in result:
            project_id = row["id"]

            # Get current phase info
            current_phase = PhaseEngine.get_current_phase(conn, project_id)
            phase_name = current_phase["name"] if current_phase else "-"
            phase_status = current_phase["status"] if current_phase else "-"

            # Get DoD progress
            dod_display = "-"
            if current_phase:
                dod_result = PhaseEngine.evaluate_dod(conn, current_phase["id"])
                if dod_result["total"] > 0:
                    dod_display = f"{dod_result['checked']}/{dod_result['total']}"
                else:
                    dod_display = "0 items"

            # Get event count
            event_row = conn.execute(
                "SELECT count(*) as cnt FROM events WHERE project_id = %s",
                (project_id,),
            ).fetchone()
            event_count = str(event_row["cnt"]) if event_row else "0"

            phase_display = f"{phase_name} ({phase_status})"

            table.add_row(
                row["name"],
                row["classification"],
                row["status"],
                phase_display,
                dod_display,
                event_count,
                str(row["id"])[:8],
            )

    console.print(table)


# ---------------------------------------------------------------------------
# etc init
# ---------------------------------------------------------------------------


@app.command()
def init(
    name: str = typer.Argument(..., help="Project name"),
    project_type: str = typer.Option(
        ...,
        "--type",
        "-t",
        help="Project classification",
        prompt="Project type (greenfield/brownfield/re-engineering/lift-and-shift/consolidation)",
    ),
    root_path: str = typer.Option(".", "--path", "-p", help="Project root path"),
    intake: bool = typer.Option(False, "--intake", help="Run interactive source material intake"),
) -> None:
    """Initialize a new project with classification and source material triage."""
    import click

    valid_types = {"greenfield", "brownfield", "re-engineering", "lift-and-shift", "consolidation"}
    if project_type not in valid_types:
        console.print(f"[red]Invalid type '{project_type}'. Must be one of: {valid_types}[/red]")
        raise typer.Exit(1)

    from etc_platform.db import get_conn
    from etc_platform.intake import VALID_CLASSIFICATIONS, VALID_TYPES

    phases = ["Bootstrap", "Spec", "Design", "Decompose", "Build", "Verify", "Ship", "Evaluate"]

    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO projects (name, root_path, classification)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (name, root_path, project_type),
        ).fetchone()
        assert row is not None
        project_id = row["id"]

        for phase_name in phases:
            conn.execute(
                """
                INSERT INTO phases (project_id, name, dod_items)
                VALUES (%s, %s, %s)
                """,
                (project_id, phase_name, "[]"),
            )

        if intake:
            console.print("\n[bold]Source Material Intake[/bold]\n")
            materials: list[dict[str, str | None]] = []

            while True:
                if not typer.confirm("Add a source material?", default=bool(not materials)):
                    break

                mat_name = typer.prompt("  Name")
                mat_type = typer.prompt(
                    "  Type",
                    type=click.Choice(sorted(VALID_TYPES)),
                )
                mat_class = typer.prompt(
                    "  Classification",
                    type=click.Choice(sorted(VALID_CLASSIFICATIONS)),
                )
                mat_priority = typer.prompt(
                    "  Priority",
                    type=click.Choice(["primary", "high", "medium", "context_only"]),
                )
                mat_path = typer.prompt("  File path (optional)", default="")
                mat_instructions = typer.prompt("  Reading instructions (optional)", default="")

                materials.append({
                    "name": mat_name,
                    "type": mat_type,
                    "classification": mat_class,
                    "priority": mat_priority,
                    "path": mat_path or None,
                    "reading_instructions": mat_instructions or None,
                })

                console.print(f"  [green]Added: {mat_name}[/green]\n")

            if materials:
                from etc_platform.intake import (
                    batch_add_materials,
                    generate_domain_briefing_skeleton,
                    triage_summary,
                )

                batch_add_materials(conn, project_id, materials)

                # Show triage summary
                summary = triage_summary(conn, project_id)
                console.print(f"\n[bold]Triage Summary:[/bold]\n{summary}")

                # Offer domain briefing generation
                if typer.confirm("\nGenerate domain briefing skeleton?", default=True):
                    briefing = generate_domain_briefing_skeleton(conn, project_id)
                    console.print(f"\n[dim]{briefing}[/dim]")

        conn.commit()

    console.print(f"[green]Project '{name}' created ({project_type})[/green]")
    console.print(f"  ID: {project_id}")
    console.print(f"  Phases: {len(phases)} initialized (Bootstrap → Evaluate)")


# ---------------------------------------------------------------------------
# etc phase status
# ---------------------------------------------------------------------------


@phase_app.command("status")
def phase_status() -> None:
    """Show current phase name, status, and DoD progress."""
    from etc_platform.db import get_conn
    from etc_platform.phases import PhaseEngine

    with get_conn() as conn:
        project = _get_active_project(conn)
        if project is None:
            console.print("[yellow]No active project found. Run 'etc init' to create one.[/yellow]")
            return

        current = PhaseEngine.get_current_phase(conn, project["id"])
        if current is None:
            console.print("[yellow]No phases found for the active project.[/yellow]")
            return

        dod_result = PhaseEngine.evaluate_dod(conn, current["id"])

        panel_content = (
            f"[bold]Phase:[/bold] {current['name']}\n"
            f"[bold]Status:[/bold] {current['status']}\n"
            f"[bold]DoD Progress:[/bold] {dod_result['checked']}/{dod_result['total']} items checked\n"
            f"[bold]DoD Passed:[/bold] {'Yes' if dod_result['passed'] else 'No'}"
        )
        console.print(Panel(panel_content, title=f"Phase Status — {project['name']}"))


# ---------------------------------------------------------------------------
# etc phase approve
# ---------------------------------------------------------------------------


@phase_app.command("approve")
def phase_approve(
    reason: str = typer.Option(..., "--reason", "-r", help="Reason for phase transition"),
    approved_by: str = typer.Option("cli_user", "--by", help="Who approved the transition"),
) -> None:
    """Approve transition to the next phase (requires DoD to pass)."""
    from etc_platform.db import get_conn
    from etc_platform.phases import PhaseEngine

    with get_conn() as conn:
        project = _require_active_project(conn)

        try:
            next_phase = PhaseEngine.advance_phase(
                conn, project["id"], reason=reason, approved_by=approved_by
            )
            conn.commit()
        except ValueError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(1) from None

        console.print(
            f"[green]Phase advanced to '{next_phase}' for project '{project['name']}'[/green]"
        )


# ---------------------------------------------------------------------------
# etc phase list
# ---------------------------------------------------------------------------


@phase_app.command("list")
def phase_list() -> None:
    """Show all phases for the active project with their statuses."""
    from etc_platform.db import get_conn
    from etc_platform.phases import PhaseEngine

    with get_conn() as conn:
        project = _require_active_project(conn)

        phases = conn.execute(
            "SELECT * FROM phases WHERE project_id = %s",
            (project["id"],),
        ).fetchall()

    # Sort by PHASE_ORDER
    order_map = {name: i for i, name in enumerate(PhaseEngine.PHASE_ORDER)}
    phases.sort(key=lambda p: order_map.get(p["name"], 999))

    table = Table(title=f"Phases — {project['name']}")
    table.add_column("#", style="dim")
    table.add_column("Phase", style="bold")
    table.add_column("Status")
    table.add_column("DoD Items")
    table.add_column("Entered At")

    for i, phase in enumerate(phases):
        items = phase["dod_items"] if phase["dod_items"] else []
        dod_count = str(len(items))
        entered = str(phase["entered_at"])[:19] if phase["entered_at"] else "-"

        status_style = ""
        if phase["status"] == "active":
            status_style = "[green]"
        elif phase["status"] == "completed":
            status_style = "[dim]"

        status_display = f"{status_style}{phase['status']}"
        if status_style:
            status_display += status_style.replace("[", "[/")

        table.add_row(str(i), phase["name"], status_display, dod_count, entered)

    console.print(table)


# ---------------------------------------------------------------------------
# etc dod status
# ---------------------------------------------------------------------------


@dod_app.command("status")
def dod_status() -> None:
    """Show DoD checklist for the current phase."""
    from etc_platform.db import get_conn
    from etc_platform.phases import PhaseEngine

    with get_conn() as conn:
        project = _require_active_project(conn)
        current = PhaseEngine.get_current_phase(conn, project["id"])
        if current is None:
            console.print("[yellow]No current phase found.[/yellow]")
            return

        items = current["dod_items"] if current["dod_items"] else []

    if not items:
        console.print(f"[yellow]No DoD items defined for phase '{current['name']}'.[/yellow]")
        return

    table = Table(title=f"Definition of Done — {current['name']}")
    table.add_column("#", style="dim")
    table.add_column("Item")
    table.add_column("Status")
    table.add_column("Type")
    table.add_column("Checked By")

    for i, item in enumerate(items):
        check_mark = "[green]✓[/green]" if item.get("checked") else "○"
        checked_by = item.get("checked_by") or "-"
        table.add_row(str(i), item["text"], check_mark, item["check_type"], checked_by)

    console.print(table)


# ---------------------------------------------------------------------------
# etc dod check <index>
# ---------------------------------------------------------------------------


@dod_app.command("check")
def dod_check(
    index: int = typer.Argument(..., help="Index of the DoD item to check"),
    checked_by: str = typer.Option("cli_user", "--by", help="Who is checking this item"),
) -> None:
    """Mark a DoD item as checked by index."""
    from etc_platform.db import get_conn
    from etc_platform.phases import PhaseEngine

    with get_conn() as conn:
        project = _require_active_project(conn)
        current = PhaseEngine.get_current_phase(conn, project["id"])
        if current is None:
            console.print("[red]No current phase found.[/red]")
            raise typer.Exit(1)

        items = current["dod_items"] if current["dod_items"] else []
        if index < 0 or index >= len(items):
            console.print(f"[red]Invalid index {index}. Phase has {len(items)} DoD items (0-{len(items) - 1}).[/red]")
            raise typer.Exit(1)

        PhaseEngine.check_dod_item(conn, current["id"], index, checked_by)
        conn.commit()

    console.print(f"[green]DoD item {index} checked by '{checked_by}' ✓[/green]")


# ---------------------------------------------------------------------------
# etc dod add
# ---------------------------------------------------------------------------

VALID_CHECK_TYPES = ["automatic", "agent_verified", "human_confirmed", "guardrail_verified"]


@dod_app.command("add")
def dod_add(
    text: str = typer.Option(..., "--text", "-t", help="Description of the DoD item"),
    check_type: str = typer.Option(
        ...,
        "--type",
        "-c",
        help=f"Check type: {', '.join(VALID_CHECK_TYPES)}",
    ),
) -> None:
    """Add a DoD item to the current phase."""
    from etc_platform.db import get_conn
    from etc_platform.phases import PhaseEngine

    if check_type not in VALID_CHECK_TYPES:
        console.print(
            f"[red]Invalid check type '{check_type}'. "
            f"Must be one of: {', '.join(VALID_CHECK_TYPES)}[/red]"
        )
        raise typer.Exit(1)

    with get_conn() as conn:
        project = _require_active_project(conn)
        current = PhaseEngine.get_current_phase(conn, project["id"])
        if current is None:
            console.print("[red]No current phase found.[/red]")
            raise typer.Exit(1)

        PhaseEngine.add_dod_item(conn, current["id"], text, check_type)
        conn.commit()

    console.print(f"[green]DoD item added to phase '{current['name']}': {text} ({check_type})[/green]")


# ---------------------------------------------------------------------------
# etc history
# ---------------------------------------------------------------------------


@app.command()
def history(
    phase: str = typer.Option(None, "--phase", help="Filter by phase name"),
    limit: int = typer.Option(20, "--limit", help="Number of events to show"),
) -> None:
    """Show project event history and SEM decision log."""
    from etc_platform.db import get_conn

    with get_conn() as conn:
        project = _get_active_project(conn)
        if project is None:
            console.print("[yellow]No active project found. Run 'etc init' to create one.[/yellow]")
            return

        project_id = project["id"]

        # Build the query with optional phase filter
        if phase:
            # When filtering by phase, match events with phase_id in payload
            rows = conn.execute(
                """
                SELECT e.* FROM events e
                WHERE e.project_id = %s
                  AND (
                    e.payload->>'phase_id' IN (
                        SELECT id::text FROM phases
                        WHERE project_id = %s AND name = %s
                    )
                    OR e.payload->>'action' LIKE %s
                  )
                ORDER BY e.created_at DESC
                LIMIT %s
                """,
                (project_id, project_id, phase, f"%{phase}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE project_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (project_id, limit),
            ).fetchall()

    if not rows:
        console.print("[yellow]No events found.[/yellow]")
        return

    table = Table(title=f"Event History -- {project['name']}")
    table.add_column("Time", style="dim")
    table.add_column("Type", style="bold")
    table.add_column("Actor")
    table.add_column("Details")

    for row in rows:
        timestamp = str(row["created_at"])[:19] if row["created_at"] else "-"
        event_type = row["event_type"]
        actor = row.get("actor", "-") or "-"
        payload = row.get("payload") or {}

        # Format details based on event type
        if event_type == "sem_decision":
            decision_type = payload.get("decision_type", "?")
            reasoning = payload.get("reasoning", "")
            # Truncate reasoning to 60 chars
            if len(reasoning) > 60:
                reasoning = reasoning[:57] + "..."
            details = f"[bold]{decision_type}[/bold]: {reasoning}"
        else:
            # For other events, show a brief payload summary
            details_parts = []
            for key in ("action", "node_id", "agent_type", "question", "rule_name"):
                if key in payload:
                    val = str(payload[key])
                    if len(val) > 30:
                        val = val[:27] + "..."
                    details_parts.append(f"{key}={val}")
            details = ", ".join(details_parts) if details_parts else "-"

        table.add_row(timestamp, event_type, actor, details)

    console.print(table)


# ---------------------------------------------------------------------------
# etc run
# ---------------------------------------------------------------------------


@app.command()
def run(
    auto: bool = typer.Option(False, "--auto", help="Autonomous mode: loop until phase gate or blocker"),
) -> None:
    """Run next action or enter autonomous mode."""
    from etc_platform.db import get_conn
    from etc_platform.run_engine import RunEngine

    with get_conn() as conn:
        project = _require_active_project(conn)
        engine = RunEngine(project["id"])

        if auto:
            console.print(
                f"[bold]Starting autonomous run for '{project['name']}'...[/bold]"
            )
            cycle = 0
            while True:
                cycle += 1
                result = engine.run_once(conn)
                conn.commit()

                deployed_count = len(result["deployed"])
                completed_count = len(result["completed_graphs"])
                console.print(
                    f"  Cycle {cycle}: {result['actions_taken']} actions "
                    f"({deployed_count} deployed, {completed_count} graphs completed)"
                )

                # Stop conditions
                if result["actions_taken"] == 0:
                    console.print("[yellow]No more pending actions. Stopping.[/yellow]")
                    break

                # Check for phase gate
                status = result["status"]
                if status.get("dod", {}).get("passed", False):
                    phase_name = status.get("phase", {}).get("name", "?")
                    console.print(
                        f"[green]Phase gate reached: '{phase_name}' DoD is met. "
                        f"Run 'etc phase approve' to advance.[/green]"
                    )
                    break
        else:
            result = engine.run_once(conn)
            conn.commit()

            deployed_count = len(result["deployed"])
            completed_count = len(result["completed_graphs"])

            if result["actions_taken"] == 0:
                console.print("[yellow]No pending actions.[/yellow]")
            else:
                console.print(
                    f"[green]Completed: {result['actions_taken']} actions "
                    f"({deployed_count} deployed, {completed_count} graphs completed)[/green]"
                )

            # Show current status summary
            status = result["status"]
            phase = status.get("phase", {})
            dod = status.get("dod", {})
            if phase:
                console.print(
                    f"  Phase: {phase.get('name', '?')} ({phase.get('status', '?')})"
                )
            if dod:
                console.print(
                    f"  DoD: {dod.get('checked', 0)}/{dod.get('total', 0)} items"
                )

            node_counts = status.get("node_counts", {})
            if node_counts:
                parts = [f"{s}: {c}" for s, c in sorted(node_counts.items())]
                console.print(f"  Nodes: {', '.join(parts)}")


# ---------------------------------------------------------------------------
# etc agents
# ---------------------------------------------------------------------------


@app.command()
def agents() -> None:
    """Show running/completed/failed agent runs."""
    from etc_platform.db import get_conn

    with get_conn() as conn:
        project = _require_active_project(conn)

        rows = conn.execute(
            """
            SELECT ar.id, ar.agent_type, ar.model, ar.status,
                   ar.tokens_input, ar.tokens_output, ar.turns,
                   ar.started_at, ar.completed_at, ar.error,
                   en.name AS node_name
            FROM agent_runs ar
            JOIN execution_nodes en ON ar.node_id = en.id
            JOIN execution_graphs eg ON en.graph_id = eg.id
            WHERE eg.project_id = %s
            ORDER BY ar.started_at DESC
            """,
            (project["id"],),
        ).fetchall()

    if not rows:
        console.print("[yellow]No agent runs found for this project.[/yellow]")
        return

    table = Table(title=f"Agent Runs -- {project['name']}")
    table.add_column("Agent", style="bold")
    table.add_column("Node")
    table.add_column("Status")
    table.add_column("Model", style="dim")
    table.add_column("Tokens (in/out)")
    table.add_column("Turns")
    table.add_column("Started")
    table.add_column("Error", style="red")
    table.add_column("ID", style="dim")

    for row in rows:
        tokens = "-"
        if row["tokens_input"] is not None:
            tokens = f"{row['tokens_input']}/{row['tokens_output'] or 0}"

        turns = str(row["turns"]) if row["turns"] is not None else "-"
        started = str(row["started_at"])[:19] if row["started_at"] else "-"
        error = (row["error"] or "")[:40]

        status_display = row["status"]
        if row["status"] == "completed":
            status_display = f"[green]{row['status']}[/green]"
        elif row["status"] == "failed":
            status_display = f"[red]{row['status']}[/red]"
        elif row["status"] == "running":
            status_display = f"[yellow]{row['status']}[/yellow]"

        table.add_row(
            row["agent_type"],
            row["node_name"],
            status_display,
            row["model"],
            tokens,
            turns,
            started,
            error,
            str(row["id"])[:8],
        )

    console.print(table)


# ---------------------------------------------------------------------------
# etc knowledge list
# ---------------------------------------------------------------------------


@knowledge_app.command("list")
def knowledge_list() -> None:
    """Show all knowledge entries for the active project."""
    from etc_platform.db import get_conn
    from etc_platform.knowledge import list_knowledge

    with get_conn() as conn:
        project = _require_active_project(conn)
        entries = list_knowledge(conn, project["id"])

    if not entries:
        console.print("[yellow]No knowledge entries found for this project.[/yellow]")
        return

    table = Table(title=f"Knowledge Entries — {project['name']}")
    table.add_column("Key", style="bold")
    table.add_column("Scope")
    table.add_column("Value")
    table.add_column("Contributed By", style="dim")

    for entry in entries:
        value_str = str(entry["value"])
        if len(value_str) > 50:
            value_str = value_str[:50] + "..."
        contributed = str(entry["contributed_by"])[:8] if entry["contributed_by"] else "-"
        table.add_row(entry["key"], entry["scope"], value_str, contributed)

    console.print(table)


# ---------------------------------------------------------------------------
# etc knowledge conflicts
# ---------------------------------------------------------------------------


@knowledge_app.command("conflicts")
def knowledge_conflicts() -> None:
    """Show unresolved knowledge conflicts between agents."""
    from etc_platform.db import get_conn
    from etc_platform.knowledge import detect_conflicts

    with get_conn() as conn:
        project = _require_active_project(conn)
        conflicts = detect_conflicts(conn, project["id"])

    if not conflicts:
        console.print("[green]No unresolved conflicts.[/green]")
        return

    console.print(f"[bold]Knowledge Conflicts — {project['name']}[/bold]\n")
    for conflict in conflicts:
        conflict_table = Table(
            title=f"Key: {conflict['key']} ({conflict['contributor_count']} contributors)",
            show_header=True,
        )
        conflict_table.add_column("Entry ID", style="dim")
        conflict_table.add_column("Scope")
        conflict_table.add_column("Value")
        conflict_table.add_column("Contributed By", style="dim")

        for entry in conflict["entries"]:
            value_str = str(entry["value"])
            if len(value_str) > 60:
                value_str = value_str[:60] + "..."
            contributed = str(entry["contributed_by"])[:8] if entry["contributed_by"] else "-"
            conflict_table.add_row(
                str(entry["id"])[:8],
                entry["scope"],
                value_str,
                contributed,
            )

        console.print(Panel(conflict_table))


# ---------------------------------------------------------------------------
# etc knowledge resolve
# ---------------------------------------------------------------------------


@knowledge_app.command("resolve")
def knowledge_resolve(
    key: str = typer.Argument(..., help="The knowledge key to resolve"),
    winner_id: str = typer.Argument(..., help="UUID of the winning entry"),
) -> None:
    """Resolve a knowledge conflict by choosing the winning entry."""
    from etc_platform.db import get_conn
    from etc_platform.events import EventType, emit_event
    from etc_platform.knowledge import detect_conflicts, resolve_conflict

    # Parse winner_id as UUID
    try:
        winner_uuid = UUID(winner_id)
    except ValueError:
        console.print(f"[red]Invalid UUID: {winner_id}[/red]")
        raise typer.Exit(1) from None

    with get_conn() as conn:
        project = _require_active_project(conn)

        # Find the conflict for this key
        conflicts = detect_conflicts(conn, project["id"])
        target_conflict = None
        for conflict in conflicts:
            if conflict["key"] == key:
                target_conflict = conflict
                break

        if target_conflict is None:
            console.print(f"[yellow]No conflict found for key '{key}'.[/yellow]")
            raise typer.Exit(1)

        # Find the losing entries (all entries for this key that are not the winner)
        losing_ids = [
            entry["id"]
            for entry in target_conflict["entries"]
            if entry["id"] != winner_uuid
        ]

        if not losing_ids:
            console.print(f"[yellow]Winner ID not found among conflicting entries for '{key}'.[/yellow]")
            raise typer.Exit(1)

        resolve_conflict(conn, winner_uuid, losing_ids)

        # Emit an audit event
        emit_event(
            conn,
            project["id"],
            event_type=EventType.HUMAN_RESPONSE,
            actor="cli_user",
            payload={
                "action": "knowledge_conflict_resolved",
                "key": key,
                "winner_id": str(winner_uuid),
                "losing_ids": [str(lid) for lid in losing_ids],
            },
        )

        conn.commit()

    console.print(
        f"[green]Conflict resolved for '{key}'. "
        f"Winner: {str(winner_uuid)[:8]}, "
        f"{len(losing_ids)} losing entry/entries superseded.[/green]"
    )


# ---------------------------------------------------------------------------
# etc guardrails status
# ---------------------------------------------------------------------------


@guardrails_app.command("status")
def guardrails_status(
    failed_only: bool = typer.Option(False, "--failed", "-f", help="Show only failed checks"),
) -> None:
    """Show guardrail check results for the active project."""
    from etc_platform.db import get_conn
    from etc_platform.guardrails import list_guardrail_checks

    with get_conn() as conn:
        project = _require_active_project(conn)
        checks = list_guardrail_checks(conn, project["id"], failed_only=failed_only)

    if not checks:
        console.print("[yellow]No guardrail checks found for this project.[/yellow]")
        return

    table = Table(title=f"Guardrail Checks — {project['name']}")
    table.add_column("ID", style="dim")
    table.add_column("Rule", style="bold")
    table.add_column("Passed")
    table.add_column("Severity")
    table.add_column("Agent")
    table.add_column("Node")
    table.add_column("Output Type")
    table.add_column("Override")
    table.add_column("Checked At")

    for check in checks:
        passed_display = "[green]Yes[/green]" if check["passed"] else "[red]No[/red]"

        override_display = "-"
        if check["overridden_by"]:
            override_display = f"{check['overridden_by']}: {check['override_reason'] or ''}"

        checked_at = str(check["checked_at"])[:19] if check["checked_at"] else "-"

        table.add_row(
            str(check["id"])[:8],
            check["rule_name"],
            passed_display,
            check["severity"],
            check["agent_type"],
            check["node_name"],
            check["output_type"],
            override_display,
            checked_at,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# etc guardrails override
# ---------------------------------------------------------------------------


@guardrails_app.command("override")
def guardrails_override(
    check_id: str = typer.Argument(..., help="UUID of the guardrail check to override"),
    reason: str = typer.Option(..., "--reason", "-r", help="Justification for the override"),
    by: str = typer.Option("cli_user", "--by", help="Who is performing the override"),
) -> None:
    """Override a failed guardrail check with justification."""
    from etc_platform.db import get_conn
    from etc_platform.guardrails import override_guardrail_check

    try:
        parsed_id = UUID(check_id)
    except ValueError:
        console.print(f"[red]Invalid UUID: {check_id}[/red]")
        raise typer.Exit(1) from None

    with get_conn() as conn:
        result = override_guardrail_check(conn, parsed_id, reason=reason, overridden_by=by)
        if result:
            conn.commit()
            console.print(
                f"[green]Guardrail check {check_id[:8]} overridden by '{by}'.[/green]\n"
                f"  Reason: {reason}"
            )
        else:
            console.print(
                f"[yellow]Could not override check {check_id[:8]}. "
                f"It may not exist or may already be passing.[/yellow]"
            )
            raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Topology helpers
# ---------------------------------------------------------------------------


def _get_pending_topology_event(conn: Any, project_id: UUID) -> dict[str, Any] | None:
    """Return the most recent topology_designed event that is awaiting approval, or None."""
    row = conn.execute(
        """
        SELECT * FROM events
        WHERE project_id = %s
          AND event_type = 'phase_gate_reached'
          AND payload->>'action' = 'topology_designed'
          AND payload->>'awaiting_approval' = 'true'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (project_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


# ---------------------------------------------------------------------------
# etc topology show
# ---------------------------------------------------------------------------


@topology_app.command("show")
def topology_show() -> None:
    """Display the proposed topology awaiting approval."""
    from etc_platform.db import get_conn

    with get_conn() as conn:
        project = _get_active_project(conn)
        if project is None:
            console.print("[yellow]No active project found. Run 'etc init' to create one.[/yellow]")
            return

        event = _get_pending_topology_event(conn, project["id"])
        if event is None:
            console.print("[yellow]No pending topology found awaiting approval.[/yellow]")
            return

        payload = event["payload"]
        plan = payload["plan"]

    # Render using Rich Tree
    layers = plan.get("layers", [])
    estimated = plan.get("estimated_agents", 0)
    strategy = plan.get("reduce_strategy", "unknown")
    reasoning = plan.get("reasoning", "")

    header = f"Topology: {len(layers)} layers, {estimated} estimated agents"
    tree = Tree(f"[bold]{header}[/bold]")
    tree.add(f"Strategy: {strategy}")
    if reasoning:
        tree.add(f"Reasoning: {reasoning}")

    for layer_idx, layer in enumerate(layers):
        layer_label = f"Layer {layer_idx}: {layer['name']} ({layer.get('dimension', '')})"
        layer_branch = tree.add(f"[bold cyan]{layer_label}[/bold cyan]")

        nodes = layer.get("nodes", [])
        for node in nodes:
            dep_note = f" (depends on Layer {layer_idx - 1})" if layer_idx > 0 else ""
            layer_branch.add(f"{node['name']} [{node['agent_type']}]{dep_note}")

    console.print(tree)


# ---------------------------------------------------------------------------
# etc topology approve
# ---------------------------------------------------------------------------


@topology_app.command("approve")
def topology_approve() -> None:
    """Approve the proposed topology and create the execution graph."""
    from etc_platform.db import get_conn
    from etc_platform.events import EventType, emit_event
    from etc_platform.phases import PhaseEngine
    from etc_platform.topology import TopologyPlan, generate_graph

    with get_conn() as conn:
        project = _get_active_project(conn)
        if project is None:
            console.print("[yellow]No active project found. Run 'etc init' to create one.[/yellow]")
            return

        event = _get_pending_topology_event(conn, project["id"])
        if event is None:
            console.print("[yellow]No pending topology found awaiting approval.[/yellow]")
            return

        # Parse plan from the event payload
        plan = TopologyPlan(**event["payload"]["plan"])

        # Get the current phase
        current_phase = PhaseEngine.get_current_phase(conn, project["id"])
        if current_phase is None:
            console.print("[red]No current phase found.[/red]")
            raise typer.Exit(1)

        phase_id = current_phase["id"]

        # Generate the execution graph
        graph_id = generate_graph(conn, project["id"], phase_id, plan)

        # Count nodes created
        node_row = conn.execute(
            "SELECT count(*) as cnt FROM execution_nodes WHERE graph_id = %s",
            (graph_id,),
        ).fetchone()
        node_count = node_row["cnt"] if node_row else 0

        # Emit approval event
        emit_event(
            conn,
            project["id"],
            event_type=EventType.HUMAN_RESPONSE,
            actor="cli_user",
            payload={
                "action": "topology_approved",
                "graph_id": str(graph_id),
                "node_count": node_count,
            },
        )

        conn.commit()

    console.print(
        f"[green]Topology approved.[/green]\n"
        f"  Graph ID: {graph_id}\n"
        f"  Nodes created: {node_count}"
    )


# ---------------------------------------------------------------------------
# etc topology reject
# ---------------------------------------------------------------------------


@topology_app.command("reject")
def topology_reject(
    reason: str = typer.Argument(..., help="Reason for rejecting the topology"),
) -> None:
    """Reject the proposed topology with feedback."""
    from etc_platform.db import get_conn
    from etc_platform.events import EventType, emit_event

    with get_conn() as conn:
        project = _get_active_project(conn)
        if project is None:
            console.print("[yellow]No active project found. Run 'etc init' to create one.[/yellow]")
            return

        event = _get_pending_topology_event(conn, project["id"])
        if event is None:
            console.print("[yellow]No pending topology found awaiting approval.[/yellow]")
            return

        # Emit rejection event
        emit_event(
            conn,
            project["id"],
            event_type=EventType.HUMAN_RESPONSE,
            actor="cli_user",
            payload={
                "action": "topology_rejected",
                "reason": reason,
            },
        )

        conn.commit()

    console.print(
        f"[yellow]Topology rejected.[/yellow]\n"
        f"  Reason: {reason}\n"
        f"  The SEM will re-generate the topology with your feedback."
    )


if __name__ == "__main__":
    app()
