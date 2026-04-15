"""Event system — Postgres LISTEN/NOTIFY for event-driven coordination."""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import Enum
from typing import Any
from uuid import UUID

import psycopg


class EventType(str, Enum):
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    PHASE_GATE_REACHED = "phase_gate_reached"
    GUARDRAIL_VIOLATION = "guardrail_violation"
    HUMAN_RESPONSE = "human_response"
    KNOWLEDGE_UPDATED = "knowledge_updated"
    NODE_READY = "node_ready"
    SEM_DECISION = "sem_decision"


def emit_event(
    conn: psycopg.Connection,
    project_id: UUID,
    event_type: EventType,
    actor: str,
    payload: dict[str, Any] | None = None,
) -> UUID:
    """Record an event to the events table. The trigger fires NOTIFY automatically."""
    row = conn.execute(
        """
        INSERT INTO events (project_id, event_type, actor, payload)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (project_id, event_type.value, actor, json.dumps(payload) if payload else None),
    ).fetchone()
    assert row is not None
    return row["id"]


EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    """Listens for Postgres NOTIFY events and dispatches to registered handlers."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._handlers: dict[str, list[EventHandler]] = {}

    def register_handler(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def _dispatch(self, raw_payload: str) -> None:
        try:
            data = json.loads(raw_payload)
        except json.JSONDecodeError:
            return

        event_type = data.get("event_type", "")
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            handler(data)

    def listen_once(self, timeout: float = 5.0) -> None:
        """Listen for a single batch of notifications, then return."""
        with psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute("LISTEN etc_events")
            gen = conn.notifies(timeout=timeout)
            for notify in gen:
                self._dispatch(notify.payload)
                break  # Process one notification then return

    def listen_loop(self, timeout: float = 5.0) -> None:
        """Listen continuously for notifications. Blocking call."""
        with psycopg.connect(self._dsn, autocommit=True) as conn:
            conn.execute("LISTEN etc_events")
            for notify in conn.notifies(timeout=timeout):
                self._dispatch(notify.payload)
