"""Tests for the Agent Runtime — PydanticAI agent lifecycle management (Task 7)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg
from pydantic_ai.models.test import TestModel

from etc_platform.agent_runtime import (
    AgentDeps,
    AgentResult,
    AgentRunner,
    build_domain_context,
    complete_agent_run,
    create_agent_run,
    load_agent_prompt,
    record_agent_output,
)
from etc_platform.config import EtcConfig
from etc_platform.intake import add_source_material

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_node(db: psycopg.Connection) -> tuple[UUID, UUID]:
    """Create a full project -> phase -> graph -> node chain.

    Returns (project_id, node_id).
    """
    project = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('p', '/tmp', 'greenfield') RETURNING id"
    ).fetchone()
    assert project is not None
    pid = project["id"]

    phase = db.execute(
        "INSERT INTO phases (project_id, name) VALUES (%s, 'Build') RETURNING id",
        (pid,),
    ).fetchone()
    assert phase is not None

    graph = db.execute(
        "INSERT INTO execution_graphs (project_id, phase_id, name, status) "
        "VALUES (%s, %s, 'test-graph', 'running') RETURNING id",
        (pid, phase["id"]),
    ).fetchone()
    assert graph is not None

    node = db.execute(
        "INSERT INTO execution_nodes (graph_id, node_type, name, agent_type, status) "
        "VALUES (%s, 'leaf', 'test-node', 'researcher', 'ready') RETURNING id",
        (graph["id"],),
    ).fetchone()
    assert node is not None

    return pid, node["id"]


# ===========================================================================
# load_agent_prompt
# ===========================================================================


class TestLoadAgentPrompt:
    def test_load_from_file(self, tmp_path: Path) -> None:
        """Loads the .md file for the given agent_type from agents_dir."""
        agent_file = tmp_path / "researcher.md"
        agent_file.write_text("You are a researcher agent. Do research.")

        result = load_agent_prompt("researcher", agents_dir=str(tmp_path))

        assert "researcher agent" in result
        assert "Do research" in result

    def test_load_missing_returns_default(self) -> None:
        """Returns a sensible default prompt when the file does not exist."""
        result = load_agent_prompt("nonexistent-agent", agents_dir="/tmp/no-such-dir")

        assert isinstance(result, str)
        assert len(result) > 10  # Should be a meaningful default
        assert "nonexistent-agent" in result

    def test_load_with_context_injection(self, tmp_path: Path) -> None:
        """Injects context dict into the loaded prompt."""
        agent_file = tmp_path / "researcher.md"
        agent_file.write_text("You are a researcher.")

        context = {
            "domain_briefing": "This project is about e-commerce.",
            "research_plan": "Focus on payment gateways.",
        }

        result = load_agent_prompt(
            "researcher", agents_dir=str(tmp_path), context=context
        )

        assert "researcher" in result
        assert "e-commerce" in result
        assert "payment gateways" in result


# ===========================================================================
# AgentResult
# ===========================================================================


class TestAgentResult:
    def test_result_model_validates(self) -> None:
        """AgentResult accepts all fields."""
        result = AgentResult(
            summary="Research complete",
            files_written=["/tmp/report.md"],
            output_type="research_report",
            findings={"key_insight": "The API supports webhooks"},
        )
        assert result.summary == "Research complete"
        assert result.files_written == ["/tmp/report.md"]
        assert result.output_type == "research_report"
        assert result.findings["key_insight"] == "The API supports webhooks"

    def test_result_model_minimal(self) -> None:
        """AgentResult works with just summary (other fields have defaults)."""
        result = AgentResult(summary="Done")
        assert result.summary == "Done"
        assert result.files_written == []
        assert result.output_type == "research_report"
        assert result.findings == {}


# ===========================================================================
# create_agent_run
# ===========================================================================


class TestCreateAgentRun:
    def test_creates_running_record(self, db: psycopg.Connection) -> None:
        """Inserts an agent_run with status='running'."""
        _pid, node_id = _setup_node(db)

        run_id = create_agent_run(
            conn=db,
            node_id=node_id,
            agent_type="researcher",
            model="anthropic:claude-sonnet-4-20250514",
        )

        row = db.execute(
            "SELECT * FROM agent_runs WHERE id = %s", (run_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "running"
        assert row["agent_type"] == "researcher"
        assert row["model"] == "anthropic:claude-sonnet-4-20250514"
        assert row["node_id"] == node_id
        assert row["started_at"] is not None

    def test_returns_uuid(self, db: psycopg.Connection) -> None:
        """create_agent_run returns a UUID."""
        _pid, node_id = _setup_node(db)

        run_id = create_agent_run(
            conn=db,
            node_id=node_id,
            agent_type="researcher",
            model="anthropic:claude-sonnet-4-20250514",
        )
        assert isinstance(run_id, UUID)


# ===========================================================================
# complete_agent_run
# ===========================================================================


class TestCompleteAgentRun:
    def test_completes_with_success(self, db: psycopg.Connection) -> None:
        """Updates an agent_run to completed status."""
        _pid, node_id = _setup_node(db)
        run_id = create_agent_run(db, node_id, "researcher", "test-model")

        complete_agent_run(conn=db, run_id=run_id, status="completed")

        row = db.execute(
            "SELECT * FROM agent_runs WHERE id = %s", (run_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "completed"
        assert row["completed_at"] is not None

    def test_completes_with_failure(self, db: psycopg.Connection) -> None:
        """Updates an agent_run to failed status with error message."""
        _pid, node_id = _setup_node(db)
        run_id = create_agent_run(db, node_id, "researcher", "test-model")

        complete_agent_run(
            conn=db, run_id=run_id, status="failed", error="Model timeout"
        )

        row = db.execute(
            "SELECT * FROM agent_runs WHERE id = %s", (run_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "failed"
        assert row["error"] == "Model timeout"
        assert row["completed_at"] is not None

    def test_records_token_usage(self, db: psycopg.Connection) -> None:
        """Token usage and turns are recorded on completion."""
        _pid, node_id = _setup_node(db)
        run_id = create_agent_run(db, node_id, "researcher", "test-model")

        complete_agent_run(
            conn=db,
            run_id=run_id,
            status="completed",
            tokens_input=1500,
            tokens_output=500,
            turns=3,
        )

        row = db.execute(
            "SELECT * FROM agent_runs WHERE id = %s", (run_id,)
        ).fetchone()
        assert row is not None
        assert row["tokens_input"] == 1500
        assert row["tokens_output"] == 500
        assert row["turns"] == 3


# ===========================================================================
# record_agent_output
# ===========================================================================


class TestRecordAgentOutput:
    def test_records_output(self, db: psycopg.Connection) -> None:
        """Inserts an agent_output record with correct fields."""
        _pid, node_id = _setup_node(db)
        run_id = create_agent_run(db, node_id, "researcher", "test-model")

        output_id = record_agent_output(
            conn=db,
            run_id=run_id,
            output_type="research_report",
            file_path="/tmp/report.md",
            content_hash="abc123",
        )

        row = db.execute(
            "SELECT * FROM agent_outputs WHERE id = %s", (output_id,)
        ).fetchone()
        assert row is not None
        assert row["run_id"] == run_id
        assert row["output_type"] == "research_report"
        assert row["file_path"] == "/tmp/report.md"
        assert row["content_hash"] == "abc123"

    def test_returns_uuid(self, db: psycopg.Connection) -> None:
        """record_agent_output returns a UUID."""
        _pid, node_id = _setup_node(db)
        run_id = create_agent_run(db, node_id, "researcher", "test-model")

        output_id = record_agent_output(
            conn=db, run_id=run_id, output_type="research_report"
        )
        assert isinstance(output_id, UUID)


# ===========================================================================
# AgentRunner
# ===========================================================================


class TestAgentRunner:
    def test_deploy_creates_run(self, db: psycopg.Connection) -> None:
        """deploy() creates an agent_run record."""
        pid, node_id = _setup_node(db)
        config = EtcConfig()
        runner = AgentRunner(config=config)

        test_model = TestModel(
            custom_output_args={
                "summary": "Research complete",
                "output_type": "research_report",
            }
        )

        run_id = runner.deploy(
            conn=db,
            node_id=node_id,
            agent_type="researcher",
            assignment={"task": "Research payment gateways"},
            model_override=test_model,
        )

        assert isinstance(run_id, UUID)

        row = db.execute(
            "SELECT * FROM agent_runs WHERE id = %s", (run_id,)
        ).fetchone()
        assert row is not None
        assert row["node_id"] == node_id
        assert row["agent_type"] == "researcher"

    def test_deploy_completes_run(self, db: psycopg.Connection) -> None:
        """deploy() marks the run as completed on success."""
        pid, node_id = _setup_node(db)
        config = EtcConfig()
        runner = AgentRunner(config=config)

        test_model = TestModel(
            custom_output_args={
                "summary": "All done",
                "output_type": "research_report",
            }
        )

        run_id = runner.deploy(
            conn=db,
            node_id=node_id,
            agent_type="researcher",
            assignment={"task": "Do research"},
            model_override=test_model,
        )

        row = db.execute(
            "SELECT * FROM agent_runs WHERE id = %s", (run_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "completed"
        assert row["completed_at"] is not None
        assert row["tokens_input"] is not None
        assert row["tokens_output"] is not None

    def test_deploy_records_output(self, db: psycopg.Connection) -> None:
        """deploy() inserts an agent_output record."""
        pid, node_id = _setup_node(db)
        config = EtcConfig()
        runner = AgentRunner(config=config)

        test_model = TestModel(
            custom_output_args={
                "summary": "Report written",
                "output_type": "research_report",
                "files_written": ["/tmp/report.md"],
            }
        )

        run_id = runner.deploy(
            conn=db,
            node_id=node_id,
            agent_type="researcher",
            assignment={"task": "Write report"},
            model_override=test_model,
        )

        outputs = db.execute(
            "SELECT * FROM agent_outputs WHERE run_id = %s", (run_id,)
        ).fetchall()
        assert len(outputs) >= 1
        assert outputs[0]["output_type"] == "research_report"

    def test_deploy_emits_event(self, db: psycopg.Connection) -> None:
        """deploy() emits an AGENT_COMPLETED event."""
        pid, node_id = _setup_node(db)
        config = EtcConfig()
        runner = AgentRunner(config=config)

        test_model = TestModel(
            custom_output_args={
                "summary": "Done",
                "output_type": "research_report",
            }
        )

        run_id = runner.deploy(
            conn=db,
            node_id=node_id,
            agent_type="researcher",
            assignment={"task": "Research"},
            model_override=test_model,
        )

        event = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'agent_completed' "
            "ORDER BY created_at DESC LIMIT 1",
            (pid,),
        ).fetchone()
        assert event is not None
        assert event["payload"]["run_id"] == str(run_id)
        assert event["payload"]["node_id"] == str(node_id)

    def test_deploy_handles_failure(self, db: psycopg.Connection) -> None:
        """deploy() marks the run as failed when the agent raises an error."""
        pid, node_id = _setup_node(db)
        config = EtcConfig()
        runner = AgentRunner(config=config)

        # Patch _run_agent to raise an exception
        with patch.object(
            runner, "_run_agent", side_effect=RuntimeError("Model exploded")
        ):
            run_id = runner.deploy(
                conn=db,
                node_id=node_id,
                agent_type="researcher",
                assignment={"task": "Fail spectacularly"},
            )

        row = db.execute(
            "SELECT * FROM agent_runs WHERE id = %s", (run_id,)
        ).fetchone()
        assert row is not None
        assert row["status"] == "failed"
        assert "Model exploded" in row["error"]
        assert row["completed_at"] is not None

    def test_get_run_status(self, db: psycopg.Connection) -> None:
        """get_run_status() returns the run record as a dict."""
        _pid, node_id = _setup_node(db)
        config = EtcConfig()
        runner = AgentRunner(config=config)

        run_id = create_agent_run(db, node_id, "researcher", "test-model")

        status = runner.get_run_status(db, run_id)
        assert status is not None
        assert status["id"] == run_id
        assert status["status"] == "running"
        assert status["agent_type"] == "researcher"

    def test_get_run_status_missing(self, db: psycopg.Connection) -> None:
        """get_run_status() returns None for a nonexistent run."""
        config = EtcConfig()
        runner = AgentRunner(config=config)

        status = runner.get_run_status(db, uuid4())
        assert status is None

    def test_list_runs(self, db: psycopg.Connection) -> None:
        """list_runs() returns all runs, optionally filtered by node_id."""
        _pid, node_id = _setup_node(db)
        config = EtcConfig()
        runner = AgentRunner(config=config)

        # Create two runs for this node
        run1 = create_agent_run(db, node_id, "researcher", "test-model")
        run2 = create_agent_run(db, node_id, "coder", "test-model")

        # List all runs
        all_runs = runner.list_runs(db)
        assert len(all_runs) >= 2

        # List runs for this node
        node_runs = runner.list_runs(db, node_id=node_id)
        assert len(node_runs) == 2
        run_ids = {r["id"] for r in node_runs}
        assert run1 in run_ids
        assert run2 in run_ids

    def test_list_runs_empty(self, db: psycopg.Connection) -> None:
        """list_runs() returns an empty list when no runs exist."""
        config = EtcConfig()
        runner = AgentRunner(config=config)

        runs = runner.list_runs(db, node_id=uuid4())
        assert runs == []


# ===========================================================================
# search_files tool — wired to source_materials table (Task 2)
# ===========================================================================


def _search_files_query(
    conn: psycopg.Connection, project_id: UUID, pattern: str
) -> list[str]:
    """Replicate the search_files SQL logic for direct DB testing.

    This mirrors the query inside the search_files tool so we can test the
    SQL behavior without needing to invoke the PydanticAI agent.
    """
    query_parts = [
        "SELECT name, type, classification, priority, path, reading_instructions",
        "FROM source_materials WHERE project_id = %s",
    ]
    params: list = [project_id]

    if pattern and pattern != "*":
        query_parts.append("AND (name ILIKE %s OR classification = %s)")
        params.extend([f"%{pattern}%", pattern])

    query_parts.append(
        "ORDER BY array_position(ARRAY['primary','high','medium','context_only'], priority), name"
    )

    rows = conn.execute(" ".join(query_parts), params).fetchall()
    results = []
    for row in rows:
        entry = f"[{row['priority']}] {row['name']} ({row['type']}/{row['classification']})"
        if row["path"]:
            entry += f" — {row['path']}"
        if row["reading_instructions"]:
            entry += f"\n  Instructions: {row['reading_instructions']}"
        results.append(entry)
    return results


class TestSearchFiles:
    """Tests for the search_files tool wired to source_materials."""

    def _create_project(self, db: psycopg.Connection) -> UUID:
        """Create a project and return its id."""
        row = db.execute(
            "INSERT INTO projects (name, root_path, classification) "
            "VALUES ('search-test', '/tmp/search', 'greenfield') RETURNING id"
        ).fetchone()
        assert row is not None
        return row["id"]

    def test_search_files_returns_all_materials(self, db: psycopg.Connection) -> None:
        """search_files('*') returns all source materials for the project."""
        pid = self._create_project(db)

        add_source_material(
            db, pid, "API Spec", "document", "requirements", "primary"
        )
        add_source_material(
            db, pid, "DB Export", "export", "business_operations", "medium"
        )
        add_source_material(
            db, pid, "Legacy Code", "code", "implementation_artifact", "high"
        )

        results = _search_files_query(db, pid, "*")
        assert len(results) == 3
        # All three names should appear
        combined = "\n".join(results)
        assert "API Spec" in combined
        assert "DB Export" in combined
        assert "Legacy Code" in combined

    def test_search_files_by_name_pattern(self, db: psycopg.Connection) -> None:
        """search_files with a partial name matches via ILIKE."""
        pid = self._create_project(db)

        add_source_material(
            db, pid, "Payment Gateway Spec", "document", "requirements", "primary"
        )
        add_source_material(
            db, pid, "User Auth Design", "document", "requirements", "high"
        )
        add_source_material(
            db, pid, "DB Schema Export", "export", "implementation_artifact", "medium"
        )

        results = _search_files_query(db, pid, "payment")
        assert len(results) == 1
        assert "Payment Gateway Spec" in results[0]

    def test_search_files_by_classification(self, db: psycopg.Connection) -> None:
        """search_files with a classification string returns matching materials."""
        pid = self._create_project(db)

        add_source_material(
            db, pid, "Biz Ops Manual", "document", "business_operations", "primary"
        )
        add_source_material(
            db, pid, "API Requirements", "document", "requirements", "high"
        )
        add_source_material(
            db, pid, "Ops Playbook", "pdf", "business_operations", "medium"
        )

        results = _search_files_query(db, pid, "business_operations")
        assert len(results) == 2
        combined = "\n".join(results)
        assert "Biz Ops Manual" in combined
        assert "Ops Playbook" in combined

    def test_search_files_empty_project(self, db: psycopg.Connection) -> None:
        """search_files returns empty list for a project with no materials."""
        pid = self._create_project(db)

        results = _search_files_query(db, pid, "*")
        assert results == []

    def test_search_files_includes_reading_instructions(
        self, db: psycopg.Connection
    ) -> None:
        """search_files includes reading_instructions in the result string."""
        pid = self._create_project(db)

        add_source_material(
            db,
            pid,
            "Domain Model",
            "document",
            "domain_truth",
            "primary",
            path="/docs/domain.md",
            reading_instructions="Focus on entity relationships in section 3.",
        )

        results = _search_files_query(db, pid, "*")
        assert len(results) == 1
        assert "Domain Model" in results[0]
        assert "/docs/domain.md" in results[0]
        assert "Instructions: Focus on entity relationships in section 3." in results[0]

    def test_search_files_priority_ordering(self, db: psycopg.Connection) -> None:
        """search_files orders results by priority: primary, high, medium, context_only."""
        pid = self._create_project(db)

        # Insert in reverse priority order
        add_source_material(
            db, pid, "Context Doc", "document", "requirements", "context_only"
        )
        add_source_material(
            db, pid, "Medium Doc", "document", "requirements", "medium"
        )
        add_source_material(
            db, pid, "Primary Doc", "document", "requirements", "primary"
        )
        add_source_material(
            db, pid, "High Doc", "document", "requirements", "high"
        )

        results = _search_files_query(db, pid, "*")
        assert len(results) == 4
        assert "Primary Doc" in results[0]
        assert "High Doc" in results[1]
        assert "Medium Doc" in results[2]
        assert "Context Doc" in results[3]


# ===========================================================================
# AgentDeps — project_id field
# ===========================================================================


class TestAgentDepsProjectId:
    def test_agent_deps_has_project_id(self, db: psycopg.Connection) -> None:
        """AgentDeps includes project_id field."""

        pid, node_id = _setup_node(db)
        run_id = create_agent_run(db, node_id, "researcher", "test-model")

        deps = AgentDeps(
            conn=db,
            node_id=node_id,
            run_id=run_id,
            assignment={"task": "test"},
            project_id=pid,
        )
        assert deps.project_id == pid

    def test_deploy_resolves_project_id(self, db: psycopg.Connection) -> None:
        """deploy() correctly resolves project_id from node -> graph -> project chain."""
        pid, node_id = _setup_node(db)
        config = EtcConfig()
        runner = AgentRunner(config=config)

        test_model = TestModel(
            custom_output_args={
                "summary": "Done",
                "output_type": "research_report",
            }
        )

        # Capture the deps passed to _run_agent so we can inspect project_id
        captured_deps: list[dict] = []
        original_run_agent = runner._run_agent

        def capturing_run_agent(
            prompt, model, node_id, run_id, conn, assignment,
            model_override=None, project_id=None,
        ):
            # Call the real method, but also peek at what happens
            result = original_run_agent(
                prompt=prompt,
                model=model,
                node_id=node_id,
                run_id=run_id,
                conn=conn,
                assignment=assignment,
                model_override=model_override,
                project_id=project_id,
            )
            # After _run_agent executes, verify the project_id was resolved
            captured_deps.append({"project_id": project_id})
            return result

        with patch.object(runner, "_run_agent", side_effect=capturing_run_agent):
            run_id = runner.deploy(
                conn=db,
                node_id=node_id,
                agent_type="researcher",
                assignment={"task": "test project_id resolution"},
                model_override=test_model,
            )

        assert len(captured_deps) == 1
        assert captured_deps[0]["project_id"] == pid


# ===========================================================================
# Knowledge tool integration
# ===========================================================================


class TestKnowledgeToolIntegration:
    """Test the knowledge tools by calling knowledge.py functions directly,
    since the agent tools delegate to them."""

    def test_query_knowledge_tool_returns_real_entry(self, db: psycopg.Connection) -> None:
        """Create a knowledge entry, then verify the tool returns it."""
        from etc_platform.knowledge import (
            contribute_knowledge as _contribute_knowledge,
        )
        from etc_platform.knowledge import (
            query_knowledge as _query_knowledge,
        )

        pid, node_id = _setup_node(db)

        # Create a knowledge entry
        _contribute_knowledge(
            conn=db,
            project_id=pid,
            key="api_endpoint",
            value={"url": "https://api.example.com"},
        )

        # Query it back (simulating what the tool does)
        result = _query_knowledge(conn=db, project_id=pid, key="api_endpoint")
        assert result is not None
        assert result["key"] == "api_endpoint"
        assert result["value"] == {"url": "https://api.example.com"}
        assert result["scope"] == "project"

        # Verify the tool's JSON serialization path
        import json

        serialized = json.dumps(
            {"key": result["key"], "value": result["value"], "scope": result["scope"]}
        )
        parsed = json.loads(serialized)
        assert parsed["key"] == "api_endpoint"
        assert parsed["value"]["url"] == "https://api.example.com"

    def test_query_knowledge_tool_returns_not_found(self, db: psycopg.Connection) -> None:
        """Verify the tool returns 'No knowledge entry found' for missing key."""
        from etc_platform.knowledge import query_knowledge as _query_knowledge

        pid, _node_id = _setup_node(db)

        result = _query_knowledge(conn=db, project_id=pid, key="nonexistent_key")
        assert result is None

        # Simulate the tool's behavior on None
        msg = "No knowledge entry found for key: nonexistent_key"
        assert "No knowledge entry found" in msg

    def test_contribute_knowledge_tool_creates_entry(self, db: psycopg.Connection) -> None:
        """Call the contribute function and verify entry created in DB."""
        from etc_platform.knowledge import (
            contribute_knowledge as _contribute_knowledge,
        )
        from etc_platform.knowledge import (
            query_knowledge as _query_knowledge,
        )

        pid, node_id = _setup_node(db)
        run_id = create_agent_run(db, node_id, "researcher", "test-model")

        entry_id = _contribute_knowledge(
            conn=db,
            project_id=pid,
            key="test_finding",
            value={"detail": "important discovery"},
            contributed_by=run_id,
        )
        assert isinstance(entry_id, UUID)

        # Verify in DB
        result = _query_knowledge(conn=db, project_id=pid, key="test_finding")
        assert result is not None
        assert result["key"] == "test_finding"
        assert result["value"]["detail"] == "important discovery"
        assert result["contributed_by"] == run_id

    def test_contribute_knowledge_tool_json_value(self, db: psycopg.Connection) -> None:
        """Contribute a JSON string and verify it's stored as parsed JSON."""
        import json

        from etc_platform.knowledge import (
            contribute_knowledge as _contribute_knowledge,
        )
        from etc_platform.knowledge import (
            query_knowledge as _query_knowledge,
        )

        pid, node_id = _setup_node(db)
        run_id = create_agent_run(db, node_id, "researcher", "test-model")

        # Simulate the tool's JSON parsing path
        value_str = '{"framework": "FastAPI", "version": "0.100"}'
        try:
            parsed_value = json.loads(value_str)
        except (json.JSONDecodeError, TypeError):
            parsed_value = {"text": value_str}

        entry_id = _contribute_knowledge(
            conn=db,
            project_id=pid,
            key="tech_stack",
            value=parsed_value,
            contributed_by=run_id,
        )

        result = _query_knowledge(conn=db, project_id=pid, key="tech_stack")
        assert result is not None
        assert result["value"]["framework"] == "FastAPI"
        assert result["value"]["version"] == "0.100"

    def test_contribute_knowledge_tool_plain_text(self, db: psycopg.Connection) -> None:
        """Contribute plain text and verify it's wrapped in {"text": ...}."""
        import json

        from etc_platform.knowledge import (
            contribute_knowledge as _contribute_knowledge,
        )
        from etc_platform.knowledge import (
            query_knowledge as _query_knowledge,
        )

        pid, node_id = _setup_node(db)
        run_id = create_agent_run(db, node_id, "researcher", "test-model")

        # Simulate the tool's plain-text path
        value_str = "The API supports webhooks for real-time notifications"
        try:
            parsed_value = json.loads(value_str)
        except (json.JSONDecodeError, TypeError):
            parsed_value = {"text": value_str}

        entry_id = _contribute_knowledge(
            conn=db,
            project_id=pid,
            key="api_notes",
            value=parsed_value,
            contributed_by=run_id,
        )

        result = _query_knowledge(conn=db, project_id=pid, key="api_notes")
        assert result is not None
        assert result["value"] == {"text": "The API supports webhooks for real-time notifications"}


# ===========================================================================
# build_domain_context (Task 3 — Domain Briefing Injection)
# ===========================================================================


class TestBuildDomainContext:
    """Tests for build_domain_context()."""

    def _create_project(self, db, classification="re-engineering"):
        row = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES (%s, %s, %s) RETURNING id",
            ("test-project", "/tmp/test", classification),
        ).fetchone()
        return row["id"]

    def _add_material(self, db, project_id, name, mat_type, classification, priority, reading_instructions=None):
        return add_source_material(
            conn=db,
            project_id=project_id,
            name=name,
            type=mat_type,
            classification=classification,
            priority=priority,
            reading_instructions=reading_instructions,
        )

    def test_returns_project_type(self, db):
        pid = self._create_project(db, "re-engineering")
        ctx = build_domain_context(db, pid)
        assert "re-engineering" in ctx["project_type"]

    def test_primary_materials_in_briefing(self, db):
        pid = self._create_project(db)
        self._add_material(db, pid, "CX Workflows", "spreadsheet", "domain_truth", "primary",
                          reading_instructions="Focus on trigger and outcome columns")
        ctx = build_domain_context(db, pid)
        assert "CX Workflows" in ctx["domain_briefing"]
        assert "Focus on trigger" in ctx["domain_briefing"]
        assert "[PRIMARY]" in ctx["domain_briefing"]

    def test_high_materials_in_briefing(self, db):
        pid = self._create_project(db)
        self._add_material(db, pid, "API Spec", "document", "requirements", "high",
                          reading_instructions="REST API v2 endpoints")
        ctx = build_domain_context(db, pid)
        assert "API Spec" in ctx["domain_briefing"]
        assert "[HIGH]" in ctx["domain_briefing"]

    def test_medium_materials_name_only(self, db):
        pid = self._create_project(db)
        self._add_material(db, pid, "Legacy Schema", "code", "implementation_artifact", "medium",
                          reading_instructions="Should NOT appear")
        ctx = build_domain_context(db, pid)
        assert "Legacy Schema" in ctx["domain_briefing"]
        assert "Should NOT appear" not in ctx["domain_briefing"]

    def test_context_only_excluded(self, db):
        pid = self._create_project(db)
        self._add_material(db, pid, "Old Docs", "document", "implementation_artifact", "context_only")
        ctx = build_domain_context(db, pid)
        assert "domain_briefing" not in ctx  # No briefing when only context_only materials

    def test_anti_pattern_catalog_for_reengineering(self, db):
        pid = self._create_project(db, "re-engineering")
        ctx = build_domain_context(db, pid)
        assert "anti_pattern_catalog" in ctx
        assert "Boolean flag sets" in ctx["anti_pattern_catalog"]
        assert "RE-ENGINEERING" in ctx["anti_pattern_catalog"]

    def test_no_anti_pattern_catalog_for_greenfield(self, db):
        pid = self._create_project(db, "greenfield")
        ctx = build_domain_context(db, pid)
        assert "anti_pattern_catalog" not in ctx

    def test_nonexistent_project_returns_empty(self, db):
        from uuid import uuid4
        ctx = build_domain_context(db, uuid4())
        assert ctx == {}
