"""Phase Engine — SDLC state machine with Definition of Done evaluation and gated transitions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import psycopg

from etc_platform.events import EventType, emit_event

VALID_CHECK_TYPES: set[str] = {
    "automatic",
    "agent_verified",
    "human_confirmed",
    "guardrail_verified",
}


class PhaseEngine:
    """Manages SDLC phase lifecycle: activation, DoD tracking, and gated transitions."""

    PHASE_ORDER: list[str] = [
        "Bootstrap",
        "Spec",
        "Design",
        "Decompose",
        "Build",
        "Verify",
        "Ship",
        "Evaluate",
    ]

    @staticmethod
    def get_current_phase(conn: psycopg.Connection, project_id: UUID) -> dict[str, Any] | None:
        """Return the currently active phase, or the first pending phase if none is active."""
        # First, look for an active phase
        row = conn.execute(
            "SELECT * FROM phases WHERE project_id = %s AND status = 'active' LIMIT 1",
            (project_id,),
        ).fetchone()
        if row is not None:
            return dict(row)

        # No active phase — find the first pending one in PHASE_ORDER
        for phase_name in PhaseEngine.PHASE_ORDER:
            row = conn.execute(
                "SELECT * FROM phases WHERE project_id = %s AND name = %s AND status = 'pending'",
                (project_id, phase_name),
            ).fetchone()
            if row is not None:
                return dict(row)

        return None

    @staticmethod
    def activate_phase(conn: psycopg.Connection, project_id: UUID, phase_name: str) -> None:
        """Set a phase to 'active' status and record entered_at timestamp."""
        now = datetime.now(timezone.utc)
        conn.execute(
            "UPDATE phases SET status = 'active', entered_at = %s "
            "WHERE project_id = %s AND name = %s",
            (now, project_id, phase_name),
        )

    @staticmethod
    def add_dod_item(
        conn: psycopg.Connection,
        phase_id: UUID,
        text: str,
        check_type: str,
    ) -> None:
        """Append a DoD item to the phase's dod_items JSONB array."""
        if check_type not in VALID_CHECK_TYPES:
            raise ValueError(
                f"Invalid check_type: {check_type!r}. Must be one of {sorted(VALID_CHECK_TYPES)}"
            )

        item = {
            "text": text,
            "check_type": check_type,
            "checked": False,
            "checked_at": None,
            "checked_by": None,
        }

        conn.execute(
            "UPDATE phases SET dod_items = dod_items || %s::jsonb WHERE id = %s",
            (json.dumps([item]), phase_id),
        )

    @staticmethod
    def check_dod_item(
        conn: psycopg.Connection,
        phase_id: UUID,
        item_index: int,
        checked_by: str,
    ) -> None:
        """Mark a specific DoD item as checked (by index)."""
        now = datetime.now(timezone.utc).isoformat()

        # Update the specific item in the JSONB array using jsonb_set calls
        conn.execute(
            """
            UPDATE phases
            SET dod_items = jsonb_set(
                jsonb_set(
                    jsonb_set(
                        dod_items,
                        ARRAY[%s::text, 'checked'],
                        'true'::jsonb
                    ),
                    ARRAY[%s::text, 'checked_at'],
                    %s::jsonb
                ),
                ARRAY[%s::text, 'checked_by'],
                %s::jsonb
            )
            WHERE id = %s
            """,
            (
                str(item_index),
                str(item_index),
                json.dumps(now),
                str(item_index),
                json.dumps(checked_by),
                phase_id,
            ),
        )

    @staticmethod
    def evaluate_dod(conn: psycopg.Connection, phase_id: UUID) -> dict[str, Any]:
        """Evaluate whether all DoD items are checked.

        Returns:
            {"phase_id": UUID, "total": N, "checked": M, "passed": bool}
        """
        row = conn.execute(
            "SELECT dod_items FROM phases WHERE id = %s", (phase_id,)
        ).fetchone()
        assert row is not None

        items = row["dod_items"]
        total = len(items)
        checked = sum(1 for item in items if item.get("checked") is True)

        return {
            "phase_id": phase_id,
            "total": total,
            "checked": checked,
            "passed": total > 0 and checked == total,
        }

    @staticmethod
    def advance_phase(
        conn: psycopg.Connection,
        project_id: UUID,
        reason: str,
        approved_by: str,
    ) -> str:
        """Advance from the current phase to the next one, if DoD is met.

        Raises ValueError if:
        - DoD is not fully passed
        - Already on the last phase (Evaluate)

        Returns the name of the newly activated phase.
        """
        current = PhaseEngine.get_current_phase(conn, project_id)
        assert current is not None, "No current phase found for project"

        current_name = current["name"]
        current_index = PhaseEngine.PHASE_ORDER.index(current_name)

        # Check if we're on the last phase
        if current_index >= len(PhaseEngine.PHASE_ORDER) - 1:
            raise ValueError(
                f"Cannot advance past the last phase: {current_name!r}"
            )

        # Evaluate DoD
        dod_result = PhaseEngine.evaluate_dod(conn, current["id"])
        if not dod_result["passed"]:
            raise ValueError(
                f"DoD not met for phase {current_name!r}: "
                f"{dod_result['checked']}/{dod_result['total']} items checked"
            )

        next_name = PhaseEngine.PHASE_ORDER[current_index + 1]

        # Complete current phase
        now = datetime.now(timezone.utc)
        conn.execute(
            "UPDATE phases SET status = 'completed', completed_at = %s "
            "WHERE project_id = %s AND name = %s",
            (now, project_id, current_name),
        )

        # Activate next phase
        PhaseEngine.activate_phase(conn, project_id, next_name)

        # Record transition
        conn.execute(
            """
            INSERT INTO phase_transitions (project_id, from_phase, to_phase, reason, approved_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (project_id, current_name, next_name, reason, approved_by),
        )

        # Emit event
        emit_event(
            conn=conn,
            project_id=project_id,
            event_type=EventType.PHASE_GATE_REACHED,
            actor="phase_engine",
            payload={
                "from_phase": current_name,
                "to_phase": next_name,
                "reason": reason,
                "approved_by": approved_by,
            },
        )

        return next_name
