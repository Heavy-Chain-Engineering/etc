"""Tests for scripts/telemetry.py — SQLite WAL telemetry sink.

Covers AC-018 and BR-014, edge case 8 (concurrent-write contention),
and security consideration 6 (schema enforcement at write time):

  - WAL mode is set after connect()
  - Schema is created if missing on connect()
  - record() validates event payloads against the schema and rejects
    bad input (controlled event_type enum, required fields, types).
  - record() retries on `sqlite3.OperationalError` containing
    "database is locked" or "busy" up to 3 attempts with exponential
    backoff (~0.05s / 0.1s / 0.2s); on exhaustion, the event is
    appended to .etc_sdlc/telemetry-overflow.jsonl as JSONL and
    record() returns False.
  - On schema-rejection, no row is written and no overflow row is
    appended (validation errors raise; only operational lock failure
    routes to the overflow file).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Make scripts/ importable without packaging it.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import telemetry  # noqa: E402  (import after sys.path manipulation)


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Return a fresh DB path under a tmp .etc_sdlc/ tree."""
    project_root = tmp_path / "project"
    (project_root / ".etc_sdlc").mkdir(parents=True)
    return project_root / ".etc_sdlc" / "telemetry.db"


def _make_event(**overrides: Any) -> dict[str, Any]:
    """Build a minimally valid event; callers override fields under test."""
    base: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "feature_id": "F001",
        "event_type": "spec_started",
        "timestamp": "2026-04-27T12:00:00+00:00",
        "payload": {"note": "hello"},
        "schema_version": 1,
    }
    base.update(overrides)
    return base


# ── connect() ──────────────────────────────────────────────────────────


class TestConnect:
    def test_should_set_wal_journal_mode_when_connection_is_opened(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            mode_row = conn.execute("PRAGMA journal_mode").fetchone()
        finally:
            conn.close()
        assert mode_row is not None
        # SQLite returns the mode as a single string column, lower-cased.
        assert str(mode_row[0]).lower() == "wal"

    def test_should_create_events_table_when_schema_is_missing(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='events'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None, "events table must exist after connect()"

    def test_should_have_required_columns_when_schema_is_created(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            cols = {
                row[1]: row
                for row in conn.execute("PRAGMA table_info(events)").fetchall()
            }
        finally:
            conn.close()
        expected = {
            "event_id",
            "feature_id",
            "event_type",
            "timestamp",
            "payload",
            "schema_version",
        }
        assert expected.issubset(cols.keys()), (
            f"missing columns: {expected - cols.keys()}"
        )
        # event_id is PRIMARY KEY (PRAGMA table_info pk column = index 5)
        assert cols["event_id"][5] == 1, "event_id must be PRIMARY KEY"
        # NOT NULL columns: event_type, timestamp, payload, schema_version
        for col_name in ("event_type", "timestamp", "payload", "schema_version"):
            assert cols[col_name][3] == 1, f"{col_name} must be NOT NULL"
        # feature_id is nullable
        assert cols["feature_id"][3] == 0, "feature_id must be NULLable"

    def test_should_be_idempotent_when_called_twice_on_same_path(
        self, db_path: Path
    ) -> None:
        conn1 = telemetry.connect(db_path)
        conn1.close()
        # Second call must not raise (CREATE TABLE IF NOT EXISTS).
        conn2 = telemetry.connect(db_path)
        try:
            row = conn2.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='events'"
            ).fetchone()
        finally:
            conn2.close()
        assert row is not None


# ── record() — happy path & schema enforcement ─────────────────────────


class TestRecordHappyPath:
    def test_should_return_true_when_valid_event_is_recorded(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            ok = telemetry.record(conn, _make_event())
            assert ok is True
            count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            assert count == 1
        finally:
            conn.close()

    def test_should_serialize_payload_as_json_when_event_is_recorded(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            event = _make_event(payload={"k": "v", "n": 3})
            telemetry.record(conn, event)
            row = conn.execute(
                "SELECT payload FROM events WHERE event_id = ?",
                (event["event_id"],),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert json.loads(row[0]) == {"k": "v", "n": 3}

    def test_should_accept_null_feature_id_when_event_has_no_feature(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            event = _make_event(feature_id=None)
            ok = telemetry.record(conn, event)
            assert ok is True
            row = conn.execute(
                "SELECT feature_id FROM events WHERE event_id = ?",
                (event["event_id"],),
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] is None


class TestRecordSchemaRejection:
    def test_should_raise_when_event_type_is_not_in_enum(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            event = _make_event(event_type="not_a_real_event")
            with pytest.raises(telemetry.TelemetrySchemaError):
                telemetry.record(conn, event)
            count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        finally:
            conn.close()
        assert count == 0

    def test_should_raise_when_required_field_is_missing(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            event = _make_event()
            del event["timestamp"]
            with pytest.raises(telemetry.TelemetrySchemaError):
                telemetry.record(conn, event)
        finally:
            conn.close()

    def test_should_raise_when_schema_version_is_not_an_integer(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            event = _make_event(schema_version="one")
            with pytest.raises(telemetry.TelemetrySchemaError):
                telemetry.record(conn, event)
        finally:
            conn.close()

    def test_should_raise_when_payload_is_not_a_dict(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            event = _make_event(payload="not-a-dict")
            with pytest.raises(telemetry.TelemetrySchemaError):
                telemetry.record(conn, event)
        finally:
            conn.close()


# ── record() — retry / overflow ────────────────────────────────────────


class _FakeBusyConnection:
    """Test double that simulates a SQLITE_BUSY condition on every execute().

    Mirrors only the surface telemetry.record() needs:
      - .execute() raising sqlite3.OperationalError("database is locked")
      - .commit() (never reached in the lock case)

    Uses sqlite3.OperationalError so the production code's exception
    filtering (matching real SQLITE_BUSY) is exercised.
    """

    def __init__(self, message: str = "database is locked") -> None:
        self._message = message
        self.execute_call_count = 0

    def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        self.execute_call_count += 1
        raise sqlite3.OperationalError(self._message)

    def commit(self) -> None:  # pragma: no cover - never reached under lock
        return None


@pytest.fixture()
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Capture backoff durations without actually sleeping.

    Prevents the retry test from waiting ~0.35s of real wall time and
    surfaces the backoff schedule for assertion.
    """
    sleeps: list[float] = []

    def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(telemetry.time, "sleep", _fake_sleep)
    return sleeps


class TestRecordRetryAndOverflow:
    def test_should_retry_three_times_when_database_is_locked(
        self,
        db_path: Path,
        no_sleep: list[float],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Route overflow under the same .etc_sdlc/ as db_path.
        monkeypatch.chdir(db_path.parent.parent)
        fake = _FakeBusyConnection()

        result = telemetry.record(fake, _make_event())

        assert result is False
        assert fake.execute_call_count == 3, (
            "record() must attempt the insert 3 times before giving up"
        )

    def test_should_use_exponential_backoff_when_retrying(
        self,
        db_path: Path,
        no_sleep: list[float],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(db_path.parent.parent)
        fake = _FakeBusyConnection()

        telemetry.record(fake, _make_event())

        # 3 attempts → 2 sleeps between them (after attempt 1 and 2).
        # Schedule per spec: 0.05, 0.10, 0.20 (last sleep may or may not
        # fire depending on the implementation; require the doubling
        # pattern of the first two).
        assert len(no_sleep) >= 2
        assert no_sleep[0] == pytest.approx(0.05, rel=0.01)
        assert no_sleep[1] == pytest.approx(0.10, rel=0.01)

    def test_should_route_event_to_overflow_jsonl_when_retries_are_exhausted(
        self,
        db_path: Path,
        no_sleep: list[float],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project_root = db_path.parent.parent
        monkeypatch.chdir(project_root)
        fake = _FakeBusyConnection()
        event = _make_event()

        result = telemetry.record(fake, event)

        assert result is False
        overflow_path = project_root / ".etc_sdlc" / "telemetry-overflow.jsonl"
        assert overflow_path.exists(), "overflow JSONL file must be written"
        lines = overflow_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        recorded = json.loads(lines[0])
        assert recorded["event_id"] == event["event_id"]
        assert recorded["event_type"] == event["event_type"]

    def test_should_append_when_overflow_jsonl_already_has_rows(
        self,
        db_path: Path,
        no_sleep: list[float],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project_root = db_path.parent.parent
        monkeypatch.chdir(project_root)
        overflow_path = project_root / ".etc_sdlc" / "telemetry-overflow.jsonl"
        overflow_path.write_text(
            json.dumps({"event_id": "pre-existing"}) + "\n",
            encoding="utf-8",
        )

        fake = _FakeBusyConnection()
        telemetry.record(fake, _make_event())

        lines = overflow_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2, "must append, not overwrite"
        assert json.loads(lines[0])["event_id"] == "pre-existing"

    def test_should_treat_busy_message_as_retryable(
        self,
        db_path: Path,
        no_sleep: list[float],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Spec calls out both "database is locked" and "busy".
        monkeypatch.chdir(db_path.parent.parent)
        fake = _FakeBusyConnection(message="database is busy")

        result = telemetry.record(fake, _make_event())

        assert result is False
        assert fake.execute_call_count == 3

    def test_should_not_retry_when_operational_error_is_unrelated(
        self,
        db_path: Path,
        no_sleep: list[float],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Non-busy OperationalError must propagate without retry / overflow.
        monkeypatch.chdir(db_path.parent.parent)
        fake = _FakeBusyConnection(message="disk I/O error")

        with pytest.raises(sqlite3.OperationalError):
            telemetry.record(fake, _make_event())

        assert fake.execute_call_count == 1, (
            "non-busy OperationalError must not be retried"
        )
        overflow_path = (
            db_path.parent.parent / ".etc_sdlc" / "telemetry-overflow.jsonl"
        )
        assert not overflow_path.exists(), (
            "non-busy errors must not write to overflow"
        )


# ── Event-type enum ────────────────────────────────────────────────────


class TestEventTypeEnum:
    @pytest.mark.parametrize(
        "event_type",
        [
            "spec_started",
            "spec_completed",
            "build_phase_entered",
            "build_phase_completed",
            "hotfix_completed",
            "agent_invoked",
            "token_count_recorded",
        ],
    )
    def test_should_accept_event_type_when_in_controlled_enum(
        self, db_path: Path, event_type: str
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            ok = telemetry.record(conn, _make_event(event_type=event_type))
        finally:
            conn.close()
        assert ok is True


# ── aggregate() ────────────────────────────────────────────────────────


def _seed_events(
    conn: sqlite3.Connection, events: list[dict[str, Any]]
) -> None:
    """Insert a list of pre-shaped events via record() for aggregate() tests."""
    for event in events:
        telemetry.record(conn, event)


class TestAggregateNoFilter:
    def test_should_return_zero_counts_when_database_is_empty(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            result = telemetry.aggregate(conn)
        finally:
            conn.close()
        assert result == {
            "by_event_type": {},
            "by_feature_id": {},
            "total_events": 0,
        }

    def test_should_count_all_events_when_no_filter_is_given(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            _seed_events(
                conn,
                [
                    _make_event(event_type="spec_started", feature_id="F001"),
                    _make_event(event_type="spec_completed", feature_id="F001"),
                    _make_event(event_type="spec_started", feature_id="F002"),
                ],
            )
            result = telemetry.aggregate(conn)
        finally:
            conn.close()
        assert result["total_events"] == 3
        assert result["by_event_type"] == {
            "spec_started": 2,
            "spec_completed": 1,
        }
        assert result["by_feature_id"] == {"F001": 2, "F002": 1}

    def test_should_treat_none_filter_as_no_filter(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            _seed_events(conn, [_make_event(feature_id="F001")])
            via_none = telemetry.aggregate(conn, None)
            via_default = telemetry.aggregate(conn)
        finally:
            conn.close()
        assert via_none == via_default

    def test_should_treat_empty_filter_as_no_filter(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            _seed_events(conn, [_make_event(feature_id="F001")])
            via_empty = telemetry.aggregate(conn, {})
            via_default = telemetry.aggregate(conn)
        finally:
            conn.close()
        assert via_empty == via_default

    def test_should_bucket_null_feature_id_under_sentinel_key(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            _seed_events(
                conn,
                [
                    _make_event(feature_id=None),
                    _make_event(feature_id=None),
                    _make_event(feature_id="F001"),
                ],
            )
            result = telemetry.aggregate(conn)
        finally:
            conn.close()
        # Null feature_id rows must be reported, not silently dropped.
        # The sentinel key is None so callers can distinguish project-level
        # events from feature-scoped ones.
        assert result["by_feature_id"][None] == 2
        assert result["by_feature_id"]["F001"] == 1
        assert result["total_events"] == 3


class TestAggregateFeatureIdFilter:
    def test_should_filter_to_single_feature_when_feature_id_is_given(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            _seed_events(
                conn,
                [
                    _make_event(event_type="spec_started", feature_id="F001"),
                    _make_event(event_type="spec_completed", feature_id="F001"),
                    _make_event(event_type="spec_started", feature_id="F002"),
                ],
            )
            result = telemetry.aggregate(conn, {"feature_id": "F001"})
        finally:
            conn.close()
        assert result["total_events"] == 2
        assert result["by_event_type"] == {
            "spec_started": 1,
            "spec_completed": 1,
        }
        assert result["by_feature_id"] == {"F001": 2}

    def test_should_return_zero_counts_when_feature_id_has_no_events(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            _seed_events(conn, [_make_event(feature_id="F001")])
            result = telemetry.aggregate(conn, {"feature_id": "F999"})
        finally:
            conn.close()
        assert result == {
            "by_event_type": {},
            "by_feature_id": {},
            "total_events": 0,
        }


class TestAggregateEventTypeFilter:
    def test_should_filter_to_single_event_type_when_event_type_is_given(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            _seed_events(
                conn,
                [
                    _make_event(event_type="spec_started", feature_id="F001"),
                    _make_event(event_type="spec_completed", feature_id="F001"),
                    _make_event(event_type="spec_started", feature_id="F002"),
                ],
            )
            result = telemetry.aggregate(
                conn, {"event_type": "spec_started"}
            )
        finally:
            conn.close()
        assert result["total_events"] == 2
        assert result["by_event_type"] == {"spec_started": 2}
        assert result["by_feature_id"] == {"F001": 1, "F002": 1}


class TestAggregateSinceFilter:
    def test_should_include_events_at_or_after_since_timestamp(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            _seed_events(
                conn,
                [
                    _make_event(timestamp="2026-04-01T00:00:00+00:00"),
                    _make_event(timestamp="2026-04-15T00:00:00+00:00"),
                    _make_event(timestamp="2026-04-30T00:00:00+00:00"),
                ],
            )
            result = telemetry.aggregate(
                conn, {"since": "2026-04-15T00:00:00+00:00"}
            )
        finally:
            conn.close()
        # since is inclusive: the 2026-04-15 row counts, the 2026-04-01 row does not.
        assert result["total_events"] == 2

    def test_should_exclude_events_strictly_before_since_timestamp(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            _seed_events(
                conn,
                [
                    _make_event(timestamp="2026-01-01T00:00:00+00:00"),
                    _make_event(timestamp="2026-02-01T00:00:00+00:00"),
                ],
            )
            result = telemetry.aggregate(
                conn, {"since": "2026-12-31T00:00:00+00:00"}
            )
        finally:
            conn.close()
        assert result["total_events"] == 0


class TestAggregateCombinedFilters:
    def test_should_combine_filters_with_and_semantics(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            _seed_events(
                conn,
                [
                    _make_event(
                        event_type="spec_started",
                        feature_id="F001",
                        timestamp="2026-04-01T00:00:00+00:00",
                    ),
                    _make_event(
                        event_type="spec_started",
                        feature_id="F001",
                        timestamp="2026-04-20T00:00:00+00:00",
                    ),
                    _make_event(
                        event_type="spec_completed",
                        feature_id="F001",
                        timestamp="2026-04-20T00:00:00+00:00",
                    ),
                    _make_event(
                        event_type="spec_started",
                        feature_id="F002",
                        timestamp="2026-04-20T00:00:00+00:00",
                    ),
                ],
            )
            result = telemetry.aggregate(
                conn,
                {
                    "feature_id": "F001",
                    "event_type": "spec_started",
                    "since": "2026-04-15T00:00:00+00:00",
                },
            )
        finally:
            conn.close()
        # Only the second seeded event matches all three filters.
        assert result["total_events"] == 1
        assert result["by_event_type"] == {"spec_started": 1}
        assert result["by_feature_id"] == {"F001": 1}


class TestAggregateInvalidFilter:
    def test_should_raise_when_filter_contains_unknown_key(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            with pytest.raises(ValueError, match="unknown filter key"):
                telemetry.aggregate(conn, {"not_a_real_key": "x"})
        finally:
            conn.close()

    def test_should_name_offending_key_in_error_message(
        self, db_path: Path
    ) -> None:
        conn = telemetry.connect(db_path)
        try:
            with pytest.raises(ValueError) as exc_info:
                telemetry.aggregate(conn, {"bogus": "x"})
        finally:
            conn.close()
        assert "bogus" in str(exc_info.value)
