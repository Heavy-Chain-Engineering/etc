"""Tests for Phase Engine — SDLC state machine with Definition of Done gates."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from etc_platform.phases import PhaseEngine

if TYPE_CHECKING:
    from uuid import UUID

    import psycopg


def _create_project(db: psycopg.Connection) -> UUID:
    """Helper: insert a project and return its id."""
    row = db.execute(
        "INSERT INTO projects (name, root_path, classification) "
        "VALUES ('p', '/tmp', 'greenfield') RETURNING id"
    ).fetchone()
    assert row is not None
    return row["id"]


def _seed_phases(db: psycopg.Connection, project_id: UUID) -> None:
    """Helper: insert all 8 phases for a project in order, all 'pending'."""
    for name in PhaseEngine.PHASE_ORDER:
        db.execute(
            "INSERT INTO phases (project_id, name, status) VALUES (%s, %s, 'pending')",
            (project_id, name),
        )


class TestPhaseEngine:
    def test_phase_order(self) -> None:
        """PHASE_ORDER has exactly 8 phases in the correct SDLC order."""
        assert PhaseEngine.PHASE_ORDER == [
            "Bootstrap",
            "Spec",
            "Design",
            "Decompose",
            "Build",
            "Verify",
            "Ship",
            "Evaluate",
        ]

    def test_get_current_phase_returns_first_pending(self, db: psycopg.Connection) -> None:
        """When no phase is active, get_current_phase returns the first pending phase."""
        pid = _create_project(db)
        _seed_phases(db, pid)

        current = PhaseEngine.get_current_phase(db, pid)
        assert current is not None
        assert current["name"] == "Bootstrap"
        assert current["status"] == "pending"

    def test_activate_phase(self, db: psycopg.Connection) -> None:
        """activate_phase sets status='active' and records entered_at."""
        pid = _create_project(db)
        _seed_phases(db, pid)

        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        row = db.execute(
            "SELECT * FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "active"
        assert row["entered_at"] is not None

    def test_add_dod_item(self, db: psycopg.Connection) -> None:
        """add_dod_item appends a structured DoD item to the phase's dod_items JSONB."""
        pid = _create_project(db)
        _seed_phases(db, pid)

        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        phase_id = phase["id"]

        PhaseEngine.add_dod_item(db, phase_id, "PRD written", "agent_verified")

        row = db.execute("SELECT dod_items FROM phases WHERE id = %s", (phase_id,)).fetchone()
        assert row is not None
        items = row["dod_items"]
        assert len(items) == 1
        assert items[0]["text"] == "PRD written"
        assert items[0]["check_type"] == "agent_verified"
        assert items[0]["checked"] is False
        assert items[0]["checked_at"] is None
        assert items[0]["checked_by"] is None

    def test_check_dod_item(self, db: psycopg.Connection) -> None:
        """check_dod_item marks a specific DoD item as checked with timestamp and actor."""
        pid = _create_project(db)
        _seed_phases(db, pid)

        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        phase_id = phase["id"]

        PhaseEngine.add_dod_item(db, phase_id, "PRD written", "agent_verified")
        PhaseEngine.add_dod_item(db, phase_id, "Stakeholder sign-off", "human_confirmed")

        PhaseEngine.check_dod_item(db, phase_id, 0, "spec_agent")

        row = db.execute("SELECT dod_items FROM phases WHERE id = %s", (phase_id,)).fetchone()
        assert row is not None
        items = row["dod_items"]
        assert items[0]["checked"] is True
        assert items[0]["checked_at"] is not None
        assert items[0]["checked_by"] == "spec_agent"
        # Second item should be untouched
        assert items[1]["checked"] is False

    def test_evaluate_dod_not_passed(self, db: psycopg.Connection) -> None:
        """evaluate_dod returns passed=False when not all items are checked."""
        pid = _create_project(db)
        _seed_phases(db, pid)

        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        phase_id = phase["id"]

        PhaseEngine.add_dod_item(db, phase_id, "PRD written", "agent_verified")
        PhaseEngine.add_dod_item(db, phase_id, "Stakeholder sign-off", "human_confirmed")
        PhaseEngine.check_dod_item(db, phase_id, 0, "spec_agent")

        result = PhaseEngine.evaluate_dod(db, phase_id)
        assert result["phase_id"] == phase_id
        assert result["total"] == 2
        assert result["checked"] == 1
        assert result["passed"] is False

    def test_evaluate_dod_all_passed(self, db: psycopg.Connection) -> None:
        """evaluate_dod returns passed=True when all items are checked."""
        pid = _create_project(db)
        _seed_phases(db, pid)

        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        phase_id = phase["id"]

        PhaseEngine.add_dod_item(db, phase_id, "PRD written", "agent_verified")
        PhaseEngine.add_dod_item(db, phase_id, "Stakeholder sign-off", "human_confirmed")
        PhaseEngine.check_dod_item(db, phase_id, 0, "spec_agent")
        PhaseEngine.check_dod_item(db, phase_id, 1, "human_reviewer")

        result = PhaseEngine.evaluate_dod(db, phase_id)
        assert result["total"] == 2
        assert result["checked"] == 2
        assert result["passed"] is True

    def test_advance_phase_blocks_on_incomplete_dod(self, db: psycopg.Connection) -> None:
        """advance_phase raises ValueError when DoD is not fully passed."""
        pid = _create_project(db)
        _seed_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        PhaseEngine.add_dod_item(db, phase["id"], "PRD written", "agent_verified")

        with pytest.raises(ValueError, match="DoD not met"):
            PhaseEngine.advance_phase(db, pid, reason="Moving on", approved_by="sem")

    def test_advance_phase_succeeds(self, db: psycopg.Connection) -> None:
        """advance_phase completes current phase, activates next, returns new phase name."""
        pid = _create_project(db)
        _seed_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        PhaseEngine.add_dod_item(db, phase["id"], "PRD written", "agent_verified")
        PhaseEngine.check_dod_item(db, phase["id"], 0, "spec_agent")

        new_phase = PhaseEngine.advance_phase(db, pid, reason="Bootstrap done", approved_by="sem")
        assert new_phase == "Spec"

        # Verify Bootstrap is completed
        bootstrap = db.execute(
            "SELECT * FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert bootstrap is not None
        assert bootstrap["status"] == "completed"
        assert bootstrap["completed_at"] is not None

        # Verify Spec is active
        spec = db.execute(
            "SELECT * FROM phases WHERE project_id = %s AND name = 'Spec'",
            (pid,),
        ).fetchone()
        assert spec is not None
        assert spec["status"] == "active"
        assert spec["entered_at"] is not None

    def test_advance_records_transition(self, db: psycopg.Connection) -> None:
        """advance_phase inserts a record into the phase_transitions table."""
        pid = _create_project(db)
        _seed_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        PhaseEngine.add_dod_item(db, phase["id"], "Done", "automatic")
        PhaseEngine.check_dod_item(db, phase["id"], 0, "system")

        PhaseEngine.advance_phase(db, pid, reason="Bootstrap done", approved_by="sem")

        transitions = db.execute(
            "SELECT * FROM phase_transitions WHERE project_id = %s", (pid,)
        ).fetchall()
        assert len(transitions) == 1
        t = transitions[0]
        assert t["from_phase"] == "Bootstrap"
        assert t["to_phase"] == "Spec"
        assert t["reason"] == "Bootstrap done"
        assert t["approved_by"] == "sem"
        assert t["transitioned_at"] is not None

    def test_advance_emits_event(self, db: psycopg.Connection) -> None:
        """advance_phase emits a PHASE_GATE_REACHED event."""
        pid = _create_project(db)
        _seed_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Bootstrap")

        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Bootstrap'",
            (pid,),
        ).fetchone()
        assert phase is not None
        PhaseEngine.add_dod_item(db, phase["id"], "Done", "automatic")
        PhaseEngine.check_dod_item(db, phase["id"], 0, "system")

        PhaseEngine.advance_phase(db, pid, reason="Bootstrap done", approved_by="sem")

        events = db.execute(
            "SELECT * FROM events WHERE project_id = %s AND event_type = 'phase_gate_reached'",
            (pid,),
        ).fetchall()
        assert len(events) == 1
        event = events[0]
        assert event["actor"] == "phase_engine"
        assert event["payload"]["from_phase"] == "Bootstrap"
        assert event["payload"]["to_phase"] == "Spec"

    def test_advance_from_last_phase_raises(self, db: psycopg.Connection) -> None:
        """advance_phase raises ValueError when already on the last phase (Evaluate)."""
        pid = _create_project(db)
        _seed_phases(db, pid)
        PhaseEngine.activate_phase(db, pid, "Evaluate")

        phase = db.execute(
            "SELECT id FROM phases WHERE project_id = %s AND name = 'Evaluate'",
            (pid,),
        ).fetchone()
        assert phase is not None
        PhaseEngine.add_dod_item(db, phase["id"], "Done", "automatic")
        PhaseEngine.check_dod_item(db, phase["id"], 0, "system")

        with pytest.raises(ValueError, match="last phase"):
            PhaseEngine.advance_phase(db, pid, reason="Trying to go past Evaluate", approved_by="sem")
