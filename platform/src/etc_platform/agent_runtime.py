"""Agent Runtime — manages lifecycle of individual agent executions.

Loads agent .md prompt files, deploys agents as PydanticAI calls with tool use,
tracks runs in the agent_runs table, and collects outputs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext

from etc_platform.config import EtcConfig, load_config
from etc_platform.events import EventType, emit_event

if TYPE_CHECKING:
    from uuid import UUID

    import psycopg

logger = logging.getLogger(__name__)


# ===========================================================================
# Domain context builder
# ===========================================================================


def build_domain_context(
    conn: psycopg.Connection,
    project_id: UUID,
    max_tokens: int = 4000,
) -> dict[str, str]:
    """Build domain context for agent prompt injection.

    Queries project classification and source materials to build
    context that is automatically injected into every agent's prompt.

    Returns a dict suitable for passing to load_agent_prompt(context=...).
    """
    context: dict[str, str] = {}

    # 1. Project classification
    project = conn.execute(
        "SELECT name, classification FROM projects WHERE id = %s",
        (project_id,),
    ).fetchone()
    if project is None:
        return context

    context["project_type"] = (
        f"Project: {project['name']}\nClassification: {project['classification']}"
    )

    # 2. Domain briefing from primary + high priority materials
    from etc_platform.intake import list_source_materials

    materials = list_source_materials(conn, project_id)

    briefing_parts: list[str] = []
    for mat in materials:
        if mat["priority"] == "primary":
            entry = f"[PRIMARY] {mat['name']} ({mat['type']}/{mat['classification']})"
            if mat.get("reading_instructions"):
                entry += f"\n  Instructions: {mat['reading_instructions']}"
            briefing_parts.append(entry)
        elif mat["priority"] == "high":
            entry = f"[HIGH] {mat['name']} ({mat['type']}/{mat['classification']})"
            if mat.get("reading_instructions"):
                entry += f"\n  Instructions: {mat['reading_instructions']}"
            briefing_parts.append(entry)
        elif mat["priority"] == "medium":
            briefing_parts.append(
                f"[MEDIUM] {mat['name']} ({mat['type']}/{mat['classification']})"
            )
        # context_only materials are excluded

    if briefing_parts:
        context["domain_briefing"] = "\n".join(briefing_parts)

    # 3. Anti-pattern catalog for re-engineering projects
    if project["classification"] == "re-engineering":
        context["anti_pattern_catalog"] = (
            "WARNING — RE-ENGINEERING PROJECT\n"
            "The following patterns from the legacy system are ANTI-PATTERNS.\n"
            "Do NOT reproduce them. Design new solutions instead.\n\n"
            "Anti-patterns to avoid:\n"
            "- Boolean flag sets (is_*, has_*, can_*, should_*) — use state machines or enums\n"
            "- Hardcoded enum lists — use configurable, data-driven values\n"
            "- Legacy field mappings (old_field -> new_field) — redesign the data model\n"
            "- Platform-specific patterns from the source system — question every inherited structure"
        )

    return context


# ===========================================================================
# Agent prompt loading
# ===========================================================================


def load_agent_prompt(
    agent_type: str,
    agents_dir: str = "~/.claude/agents",
    context: dict[str, str] | None = None,
) -> str:
    """Load agent .md prompt file and inject context.

    Args:
        agent_type: The type of agent (e.g. 'researcher', 'coder').
        agents_dir: Directory containing agent .md files.
        context: Optional dict of context to inject (domain_briefing, research_plan, etc.).

    Returns:
        The system prompt string for the agent.
    """
    agents_path = Path(agents_dir).expanduser()
    prompt_file = agents_path / f"{agent_type}.md"

    if prompt_file.exists():
        prompt = prompt_file.read_text()
    else:
        logger.info(
            "Agent prompt file not found: %s — using default prompt", prompt_file
        )
        prompt = (
            f"You are a {agent_type} agent for the ETC Platform.\n"
            f"Complete the assigned task thoroughly and report your findings.\n"
            f"Use the tools available to read, write, and search files as needed."
        )

    if context:
        context_parts: list[str] = ["\n\n=== Context ===\n"]
        for key, value in context.items():
            label = key.replace("_", " ").title()
            context_parts.append(f"### {label}\n{value}\n")
        prompt += "\n".join(context_parts)

    return prompt


# ===========================================================================
# Agent result model — structured output from PydanticAI
# ===========================================================================


class AgentResult(BaseModel):
    """Structured output from an agent run."""

    summary: str
    files_written: list[str] = []
    output_type: str = "research_report"
    findings: dict[str, Any] = {}


# ===========================================================================
# Agent run dependencies
# ===========================================================================


class AgentDeps:
    """Dependencies injected into agent tool calls via RunContext."""

    def __init__(
        self,
        conn: psycopg.Connection,
        node_id: UUID,
        run_id: UUID,
        assignment: dict[str, Any],
        project_id: UUID | None = None,
    ) -> None:
        self.conn = conn
        self.node_id = node_id
        self.run_id = run_id
        self.assignment = assignment
        self.project_id = project_id


# ===========================================================================
# Database operations
# ===========================================================================


def create_agent_run(
    conn: psycopg.Connection,
    node_id: UUID,
    agent_type: str,
    model: str,
    system_prompt_hash: str | None = None,
) -> UUID:
    """Insert a new agent_run record with status='running'. Returns the run ID."""
    row = conn.execute(
        """
        INSERT INTO agent_runs (node_id, agent_type, system_prompt_hash, model, status)
        VALUES (%s, %s, %s, %s, 'running')
        RETURNING id
        """,
        (node_id, agent_type, system_prompt_hash, model),
    ).fetchone()
    assert row is not None
    return row["id"]


def complete_agent_run(
    conn: psycopg.Connection,
    run_id: UUID,
    status: str,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
    turns: int | None = None,
    error: str | None = None,
) -> None:
    """Update the agent_run record with completion data."""
    now = datetime.now(UTC)
    conn.execute(
        """
        UPDATE agent_runs
        SET status = %s,
            tokens_input = %s,
            tokens_output = %s,
            turns = %s,
            error = %s,
            completed_at = %s
        WHERE id = %s
        """,
        (status, tokens_input, tokens_output, turns, error, now, run_id),
    )


def record_agent_output(
    conn: psycopg.Connection,
    run_id: UUID,
    output_type: str,
    file_path: str | None = None,
    content_hash: str | None = None,
) -> UUID:
    """Insert an agent_output record. Returns the output ID."""
    row = conn.execute(
        """
        INSERT INTO agent_outputs (run_id, output_type, file_path, content_hash)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (run_id, output_type, file_path, content_hash),
    ).fetchone()
    assert row is not None
    return row["id"]


# ===========================================================================
# PydanticAI agent tools (stubs for MVP)
# ===========================================================================


def _register_tools(agent: Agent[AgentDeps, AgentResult]) -> None:
    """Register tool stubs on the agent. These will be fleshed out later."""

    @agent.tool
    def read_file(ctx: RunContext[AgentDeps], path: str) -> str:
        """Read the contents of a file."""
        logger.info("Tool read_file called: %s", path)
        target = Path(path).expanduser()
        if target.exists():
            return target.read_text()
        return f"File not found: {path}"

    @agent.tool
    def write_file(ctx: RunContext[AgentDeps], path: str, content: str) -> str:
        """Write content to a file."""
        logger.info("Tool write_file called: %s", path)
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Written {len(content)} bytes to {path}"

    @agent.tool
    def search_files(ctx: RunContext[AgentDeps], pattern: str) -> list[str]:
        """Search source materials for the project. Use '*' to list all materials."""
        logger.info("Tool search_files called: %s", pattern)
        query_parts = [
            "SELECT name, type, classification, priority, path, reading_instructions",
            "FROM source_materials WHERE project_id = %s",
        ]
        params: list = [ctx.deps.project_id]

        if pattern and pattern != "*":
            query_parts.append("AND (name ILIKE %s OR classification = %s)")
            params.extend([f"%{pattern}%", pattern])

        query_parts.append(
            "ORDER BY array_position(ARRAY['primary','high','medium','context_only'], priority), name"
        )

        rows = ctx.deps.conn.execute(" ".join(query_parts), params).fetchall()
        results = []
        for row in rows:
            entry = f"[{row['priority']}] {row['name']} ({row['type']}/{row['classification']})"
            if row["path"]:
                entry += f" — {row['path']}"
            if row["reading_instructions"]:
                entry += f"\n  Instructions: {row['reading_instructions']}"
            results.append(entry)
        return results

    @agent.tool
    def query_knowledge(ctx: RunContext[AgentDeps], key: str) -> str:
        """Query a knowledge entry from the shared knowledge store."""
        logger.info("Tool query_knowledge called: %s", key)
        from etc_platform.knowledge import query_knowledge as _query_knowledge

        result = _query_knowledge(
            conn=ctx.deps.conn,
            project_id=ctx.deps.project_id,
            key=key,
        )
        if result is None:
            return f"No knowledge entry found for key: {key}"
        return json.dumps(
            {"key": result["key"], "value": result["value"], "scope": result["scope"]}
        )

    @agent.tool
    def contribute_knowledge(ctx: RunContext[AgentDeps], key: str, value: str) -> str:
        """Contribute a knowledge entry to the shared knowledge store."""
        logger.info("Tool contribute_knowledge called: key=%s", key)
        from etc_platform.knowledge import (
            contribute_knowledge as _contribute_knowledge,
        )

        # Try to parse as JSON, fall back to text wrapper
        try:
            parsed_value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            parsed_value = {"text": value}
        entry_id = _contribute_knowledge(
            conn=ctx.deps.conn,
            project_id=ctx.deps.project_id,
            key=key,
            value=parsed_value,
            contributed_by=ctx.deps.run_id,
        )
        return f"Knowledge entry recorded: {key} (id={entry_id})"


# ===========================================================================
# AgentRunner
# ===========================================================================


class AgentRunner:
    """Manages the lifecycle of individual agent executions.

    Creates PydanticAI agents with structured output, runs them against
    the configured model, tracks runs in the agent_runs table, and collects outputs.
    """

    def __init__(self, config: EtcConfig | None = None) -> None:
        self.config = config or load_config()

    def deploy(
        self,
        conn: psycopg.Connection,
        node_id: UUID,
        agent_type: str,
        assignment: dict[str, Any],
        model_override: Any | None = None,
    ) -> UUID:
        """Deploy an agent for a given execution node.

        Steps:
            1. Create agent_run record (status='running')
            2. Load agent prompt
            3. Create PydanticAI agent with structured output
            4. Run the agent (via run_sync)
            5. Record output(s)
            6. Complete agent_run (status='completed' or 'failed')
            7. Emit AGENT_COMPLETED event

        Args:
            conn: Database connection.
            node_id: The execution node to run the agent for.
            agent_type: Type of agent (e.g. 'researcher', 'coder').
            assignment: The task assignment dict from the execution node.
            model_override: Optional model override (e.g. TestModel for testing).

        Returns:
            The run_id UUID.
        """
        model = self.config.default_model

        # Resolve project_id from the execution node chain
        proj_row = conn.execute(
            """
            SELECT eg.project_id
            FROM execution_nodes en
            JOIN execution_graphs eg ON en.graph_id = eg.id
            WHERE en.id = %s
            """,
            (node_id,),
        ).fetchone()
        project_id = proj_row["project_id"] if proj_row else None

        # Build domain context and inject into prompt
        domain_context: dict[str, str] = {}
        if project_id is not None:
            domain_context = build_domain_context(conn, project_id)
        prompt = load_agent_prompt(
            agent_type,
            agents_dir=self.config.agents_dir,
            context=domain_context if domain_context else None,
        )
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        # 1. Create the run record
        run_id = create_agent_run(
            conn=conn,
            node_id=node_id,
            agent_type=agent_type,
            model=model,
            system_prompt_hash=prompt_hash,
        )

        try:
            # 2-4. Build and run the agent
            result, usage = self._run_agent(
                prompt=prompt,
                model=model,
                node_id=node_id,
                run_id=run_id,
                conn=conn,
                assignment=assignment,
                model_override=model_override,
                project_id=project_id,
            )

            # 5. Record output
            content_hash = hashlib.sha256(
                result.summary.encode()
            ).hexdigest()[:16]
            record_agent_output(
                conn=conn,
                run_id=run_id,
                output_type=result.output_type,
                file_path=result.files_written[0] if result.files_written else None,
                content_hash=content_hash,
            )

            # 6. Complete the run
            complete_agent_run(
                conn=conn,
                run_id=run_id,
                status="completed",
                tokens_input=usage.get("input_tokens"),
                tokens_output=usage.get("output_tokens"),
                turns=usage.get("requests"),
            )

            # 7. Emit completion event
            self._emit_completed(conn, node_id, run_id, agent_type)

        except Exception as exc:
            logger.error("Agent run %s failed: %s", run_id, exc)
            complete_agent_run(
                conn=conn,
                run_id=run_id,
                status="failed",
                error=str(exc),
            )

        return run_id

    def _run_agent(
        self,
        prompt: str,
        model: str,
        node_id: UUID,
        run_id: UUID,
        conn: psycopg.Connection,
        assignment: dict[str, Any],
        model_override: Any | None = None,
        project_id: UUID | None = None,
    ) -> tuple[AgentResult, dict[str, int]]:
        """Build a PydanticAI agent, run it, and return (result, usage_dict).

        This is extracted as a method so it can be patched in failure tests.
        """
        agent: Agent[AgentDeps, AgentResult] = Agent(
            model,
            deps_type=AgentDeps,
            output_type=AgentResult,
            system_prompt=prompt,
            defer_model_check=True,
        )
        _register_tools(agent)

        deps = AgentDeps(
            conn=conn,
            node_id=node_id,
            run_id=run_id,
            assignment=assignment,
            project_id=project_id,
        )

        # Build the user prompt from the assignment
        user_prompt = self._build_user_prompt(assignment)

        if model_override is not None:
            with agent.override(model=model_override):
                run_result = agent.run_sync(user_prompt, deps=deps)
        else:
            run_result = agent.run_sync(user_prompt, deps=deps)

        usage = run_result.usage()
        usage_dict = {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "requests": usage.requests,
        }

        return run_result.output, usage_dict

    def _build_user_prompt(self, assignment: dict[str, Any]) -> str:
        """Build a user prompt from the assignment dict."""
        parts: list[str] = ["=== Assignment ===\n"]
        for key, value in assignment.items():
            parts.append(f"{key}: {value}")
        return "\n".join(parts)

    def _emit_completed(
        self,
        conn: psycopg.Connection,
        node_id: UUID,
        run_id: UUID,
        agent_type: str,
    ) -> None:
        """Emit an AGENT_COMPLETED event.

        Looks up the project_id from the node's graph.
        """
        # Resolve project_id from the execution node chain
        row = conn.execute(
            """
            SELECT eg.project_id
            FROM execution_nodes en
            JOIN execution_graphs eg ON en.graph_id = eg.id
            WHERE en.id = %s
            """,
            (node_id,),
        ).fetchone()
        assert row is not None, f"Could not find project for node {node_id}"

        emit_event(
            conn=conn,
            project_id=row["project_id"],
            event_type=EventType.AGENT_COMPLETED,
            actor=agent_type,
            payload={
                "run_id": str(run_id),
                "node_id": str(node_id),
                "agent_type": agent_type,
            },
        )

    def get_run_status(self, conn: psycopg.Connection, run_id: UUID) -> dict | None:
        """Get the status of an agent run."""
        row = conn.execute(
            "SELECT * FROM agent_runs WHERE id = %s", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_runs(
        self, conn: psycopg.Connection, node_id: UUID | None = None
    ) -> list[dict]:
        """List agent runs, optionally filtered by node."""
        if node_id is not None:
            rows = conn.execute(
                "SELECT * FROM agent_runs WHERE node_id = %s ORDER BY started_at",
                (node_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_runs ORDER BY started_at"
            ).fetchall()
        return [dict(r) for r in rows]
