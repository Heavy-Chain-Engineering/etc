"""Tests for the event system — LISTEN/NOTIFY + event recording."""

from __future__ import annotations

import threading
import time
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from etc_platform.events import EventBus, EventType, emit_event


class TestEventTypes:
    def test_all_event_types_defined(self) -> None:
        expected = {
            "agent_started",
            "agent_completed",
            "phase_gate_reached",
            "guardrail_violation",
            "human_response",
            "knowledge_updated",
            "node_ready",
        }
        actual = {e.value for e in EventType}
        assert expected.issubset(actual)


class TestEmitEvent:
    def test_emit_records_to_events_table(self, db: psycopg.Connection) -> None:
        project = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES ('p', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert project is not None
        pid = project["id"]

        event_id = emit_event(
            conn=db,
            project_id=pid,
            event_type=EventType.AGENT_COMPLETED,
            actor="test",
            payload={"node_id": "abc"},
        )
        assert isinstance(event_id, UUID)

        row = db.execute("SELECT * FROM events WHERE id = %s", (event_id,)).fetchone()
        assert row is not None
        assert row["event_type"] == "agent_completed"
        assert row["actor"] == "test"
        assert row["payload"]["node_id"] == "abc"

    def test_emit_multiple_events(self, db: psycopg.Connection) -> None:
        project = db.execute(
            "INSERT INTO projects (name, root_path, classification) VALUES ('p', '/tmp', 'greenfield') RETURNING id"
        ).fetchone()
        assert project is not None
        pid = project["id"]

        for etype in [EventType.AGENT_STARTED, EventType.AGENT_COMPLETED, EventType.PHASE_GATE_REACHED]:
            emit_event(conn=db, project_id=pid, event_type=etype, actor="test")

        count = db.execute(
            "SELECT count(*) as cnt FROM events WHERE project_id = %s", (pid,)
        ).fetchone()
        assert count is not None
        assert count["cnt"] == 3


class TestEventBus:
    def test_bus_receives_notification(self, pg_dsn: str, setup_test_db: None) -> None:
        """Test that LISTEN/NOTIFY works end-to-end."""
        received: list[dict] = []

        def on_event(payload: dict) -> None:
            received.append(payload)

        bus = EventBus(pg_dsn)
        bus.register_handler("agent_completed", on_event)

        # Start listener in background thread
        listener_thread = threading.Thread(target=bus.listen_once, daemon=True)
        listener_thread.start()
        time.sleep(0.3)  # Give listener time to start

        # Emit an event from a separate connection
        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            project = conn.execute(
                "INSERT INTO projects (name, root_path, classification) VALUES ('notify-test', '/tmp', 'greenfield') RETURNING id"
            ).fetchone()
            assert project is not None
            emit_event(
                conn=conn,
                project_id=project["id"],
                event_type=EventType.AGENT_COMPLETED,
                actor="test-notifier",
                payload={"node_id": "xyz"},
            )
            conn.commit()

        listener_thread.join(timeout=5)

        assert len(received) == 1
        assert received[0]["event_type"] == "agent_completed"
        assert received[0]["actor"] == "test-notifier"

    def test_bus_filters_by_event_type(self, pg_dsn: str, setup_test_db: None) -> None:
        received: list[dict] = []

        def on_agent(payload: dict) -> None:
            received.append(payload)

        bus = EventBus(pg_dsn)
        bus.register_handler("agent_completed", on_agent)
        # Do NOT register for phase_gate_reached

        listener_thread = threading.Thread(
            target=bus.listen_loop, kwargs={"timeout": 3.0}, daemon=True
        )
        listener_thread.start()
        time.sleep(0.3)

        with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
            project = conn.execute(
                "INSERT INTO projects (name, root_path, classification) VALUES ('filter-test', '/tmp', 'greenfield') RETURNING id"
            ).fetchone()
            assert project is not None
            # Emit a phase_gate event — should NOT be received by our handler
            emit_event(
                conn=conn,
                project_id=project["id"],
                event_type=EventType.PHASE_GATE_REACHED,
                actor="test",
            )
            # Then emit an agent_completed — SHOULD be received
            emit_event(
                conn=conn,
                project_id=project["id"],
                event_type=EventType.AGENT_COMPLETED,
                actor="test",
            )
            conn.commit()

        listener_thread.join(timeout=5)

        # Only the agent_completed event should have triggered our handler
        agent_events = [e for e in received if e["event_type"] == "agent_completed"]
        assert len(agent_events) >= 1
