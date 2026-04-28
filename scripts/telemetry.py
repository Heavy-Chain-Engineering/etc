"""telemetry.py — SQLite WAL telemetry sink for the etc harness.

Backs the cost / activity layer of `/metrics`. Per BR-014, all data lives
under the project working tree (`.etc_sdlc/telemetry.db`). Per security
consideration 6, every row is validated against the v1 schema at write
time; rejection raises rather than corrupting the table. Per edge case 8,
write contention is tolerated via short exponential-backoff retries on
`SQLITE_BUSY`; on retry exhaustion the event is appended as JSONL to
`.etc_sdlc/telemetry-overflow.jsonl` for later replay.

Public surface:
    connect(db_path) -> sqlite3.Connection
    record(conn, event) -> bool
    aggregate(conn, filter) -> dict[str, int]
    TelemetrySchemaError  (raised on schema-rejection)

stdlib only — no third-party dependencies (per spec "Technical Constraints").
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Final, Protocol

# ── Schema constants ───────────────────────────────────────────────────

SCHEMA_VERSION: Final[int] = 1

ALLOWED_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "spec_started",
        "spec_completed",
        "build_phase_entered",
        "build_phase_completed",
        "hotfix_completed",
        "agent_invoked",
        "token_count_recorded",
    }
)

REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "event_id",
    "event_type",
    "timestamp",
    "payload",
    "schema_version",
)

# ── Retry / overflow constants ─────────────────────────────────────────

MAX_WRITE_ATTEMPTS: Final[int] = 3
BACKOFF_BASE_SECONDS: Final[float] = 0.05
BACKOFF_FACTOR: Final[float] = 2.0
RETRYABLE_ERROR_FRAGMENTS: Final[tuple[str, ...]] = (
    "database is locked",
    "busy",
)
OVERFLOW_FILENAME: Final[str] = "telemetry-overflow.jsonl"
OVERFLOW_DIR: Final[str] = ".etc_sdlc"

# ── Aggregate filter constants ─────────────────────────────────────────

ALLOWED_FILTER_KEYS: Final[frozenset[str]] = frozenset(
    {"feature_id", "event_type", "since"}
)

# ── Schema DDL ─────────────────────────────────────────────────────────

_CREATE_EVENTS_TABLE: Final[str] = """
CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    feature_id      TEXT,
    event_type      TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    payload         TEXT NOT NULL,
    schema_version  INTEGER NOT NULL
)
"""

_INSERT_EVENT: Final[str] = (
    "INSERT INTO events "
    "(event_id, feature_id, event_type, timestamp, payload, schema_version) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


# ── Errors ─────────────────────────────────────────────────────────────


class TelemetrySchemaError(ValueError):
    """Raised when an event payload fails schema validation.

    Schema rejection is a programming/contract violation — never silently
    routed to the overflow file (that path is reserved for transient
    contention). Caller should surface or log and discard.
    """


# ── Connection protocol (for typing the retry loop's input) ────────────


class _Executable(Protocol):
    """Subset of sqlite3.Connection used by record(): execute() + commit()."""

    def execute(self, sql: str, parameters: tuple[Any, ...] = ..., /) -> Any: ...

    def commit(self) -> None: ...


# ── Public API ─────────────────────────────────────────────────────────


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the telemetry DB in WAL mode and ensure the schema exists.

    Creates parent directories as needed so callers don't have to
    pre-create `.etc_sdlc/`. Returns an open `sqlite3.Connection`; the
    caller is responsible for closing it.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # PRAGMA journal_mode returns the new mode as a row; we don't need
    # the value, but the statement must be executed (not just prepared).
    conn.execute("PRAGMA journal_mode=WAL").fetchone()
    conn.execute(_CREATE_EVENTS_TABLE)
    conn.commit()
    return conn


def record(conn: _Executable, event: dict[str, Any]) -> bool:
    """Validate and persist a telemetry event.

    Returns True on successful insert. On retry exhaustion against
    SQLITE_BUSY-style contention, appends the event as JSONL to
    `.etc_sdlc/telemetry-overflow.jsonl` (relative to CWD) and returns
    False — the caller may treat this as a soft failure.

    Raises:
        TelemetrySchemaError: event fails schema validation. No row
            is written and no overflow line is appended.
        sqlite3.OperationalError: a non-retryable operational error
            (e.g. "disk I/O error") propagates unchanged.
    """
    _validate_event(event)
    row = _event_to_row(event)
    return _insert_with_retry(conn, row, event)


def aggregate(
    conn: sqlite3.Connection,
    filter: dict[str, str] | None = None,  # noqa: A002 — public-API name per spec
) -> dict[str, Any]:
    """Aggregate event counts from the telemetry events table.

    Returns a dict with three keys:
        - "by_event_type":  {event_type -> count}
        - "by_feature_id":  {feature_id (or None) -> count}
        - "total_events":   int — total matching rows

    `filter` is an optional dict whose keys may include:
        - "feature_id": exact match against the events.feature_id column
        - "event_type": exact match against the events.event_type column
        - "since":      ISO-8601 timestamp; rows with timestamp >= since

    Combining filters is logical AND. `None` and `{}` both mean "no
    filter" (aggregate over all events). Any other key in `filter`
    raises ValueError naming the offending key — silent acceptance of
    typos would defeat the controlled-surface contract.
    """
    where_clause, params = _build_filter_clause(filter)
    return {
        "by_event_type": _count_grouped_by(conn, "event_type", where_clause, params),
        "by_feature_id": _count_grouped_by(conn, "feature_id", where_clause, params),
        "total_events": _count_total(conn, where_clause, params),
    }


# ── Internals ──────────────────────────────────────────────────────────


def _validate_event(event: dict[str, Any]) -> None:
    """Enforce the v1 schema at write time.

    Raises TelemetrySchemaError with a message naming the offending
    field. Validation is intentionally strict — the DB never accepts
    rows that violate the contract (security consideration 6).
    """
    if not isinstance(event, dict):
        msg = f"event must be a dict, got {type(event).__name__}"
        raise TelemetrySchemaError(msg)

    for field in REQUIRED_FIELDS:
        if field not in event:
            msg = f"event missing required field: {field!r}"
            raise TelemetrySchemaError(msg)

    event_type = event["event_type"]
    if event_type not in ALLOWED_EVENT_TYPES:
        allowed = ", ".join(sorted(ALLOWED_EVENT_TYPES))
        msg = (
            f"event_type {event_type!r} is not in the controlled enum. "
            f"Allowed: {allowed}"
        )
        raise TelemetrySchemaError(msg)

    if not isinstance(event["event_id"], str) or not event["event_id"]:
        msg = "event_id must be a non-empty string (UUID)"
        raise TelemetrySchemaError(msg)

    if not isinstance(event["timestamp"], str) or not event["timestamp"]:
        msg = "timestamp must be a non-empty ISO-8601 string"
        raise TelemetrySchemaError(msg)

    if not isinstance(event["payload"], dict):
        msg = (
            f"payload must be a dict (will be JSON-serialized), "
            f"got {type(event['payload']).__name__}"
        )
        raise TelemetrySchemaError(msg)

    # bool is a subclass of int — reject it explicitly.
    if not isinstance(event["schema_version"], int) or isinstance(
        event["schema_version"], bool
    ):
        msg = (
            f"schema_version must be int, "
            f"got {type(event['schema_version']).__name__}"
        )
        raise TelemetrySchemaError(msg)

    feature_id = event.get("feature_id")
    if feature_id is not None and not isinstance(feature_id, str):
        msg = (
            f"feature_id must be str or None, got {type(feature_id).__name__}"
        )
        raise TelemetrySchemaError(msg)


def _event_to_row(event: dict[str, Any]) -> tuple[Any, ...]:
    """Project a validated event dict to the SQL insert parameter tuple."""
    return (
        event["event_id"],
        event.get("feature_id"),
        event["event_type"],
        event["timestamp"],
        json.dumps(event["payload"], sort_keys=True),
        event["schema_version"],
    )


def _is_retryable_operational_error(exc: sqlite3.OperationalError) -> bool:
    """True iff the message indicates SQLITE_BUSY-style contention.

    Per spec, both "database is locked" and "busy" are retryable;
    everything else (e.g. disk I/O errors, malformed schema) propagates
    so the caller can investigate.
    """
    message = str(exc).lower()
    return any(fragment in message for fragment in RETRYABLE_ERROR_FRAGMENTS)


def _insert_with_retry(
    conn: _Executable,
    row: tuple[Any, ...],
    event: dict[str, Any],
) -> bool:
    """Run the INSERT with exponential-backoff retry on SQLITE_BUSY.

    Returns True on insert success, False after retry exhaustion (with
    the event written to the overflow JSONL). Non-retryable
    OperationalErrors propagate.
    """
    for attempt in range(1, MAX_WRITE_ATTEMPTS + 1):
        try:
            conn.execute(_INSERT_EVENT, row)
            conn.commit()
        except sqlite3.OperationalError as exc:
            if not _is_retryable_operational_error(exc):
                raise
            if attempt < MAX_WRITE_ATTEMPTS:
                time.sleep(_backoff_for_attempt(attempt))
                continue
            # Retries exhausted — route to overflow.
            _append_to_overflow(event)
            return False
        else:
            return True
    # Defensive: loop above always returns or raises.
    return False  # pragma: no cover


def _backoff_for_attempt(attempt: int) -> float:
    """Backoff schedule: 0.05, 0.10, 0.20 seconds (per spec)."""
    return BACKOFF_BASE_SECONDS * (BACKOFF_FACTOR ** (attempt - 1))


def _append_to_overflow(event: dict[str, Any]) -> None:
    """Append a JSON-serialized event line to the overflow JSONL.

    Path is resolved relative to the current working directory so that
    each project's harness writes to its own `.etc_sdlc/`. The directory
    is created if missing.
    """
    overflow_dir = Path.cwd() / OVERFLOW_DIR
    overflow_dir.mkdir(parents=True, exist_ok=True)
    overflow_path = overflow_dir / OVERFLOW_FILENAME
    line = json.dumps(event, sort_keys=True)
    with overflow_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _build_filter_clause(
    filter: dict[str, str] | None,  # noqa: A002 — mirrors public param name
) -> tuple[str, tuple[Any, ...]]:
    """Translate a filter dict into a parameterized SQL WHERE clause.

    Returns ("", ()) when the filter is None or empty. Validates that
    every supplied key is in ALLOWED_FILTER_KEYS — unknown keys are a
    contract violation, not silently dropped.
    """
    if not filter:
        return "", ()

    unknown = set(filter) - ALLOWED_FILTER_KEYS
    if unknown:
        offending = sorted(unknown)[0]
        allowed = ", ".join(sorted(ALLOWED_FILTER_KEYS))
        msg = (
            f"unknown filter key {offending!r}; "
            f"allowed keys: {allowed}"
        )
        raise ValueError(msg)

    conditions: list[str] = []
    params: list[Any] = []
    if "feature_id" in filter:
        conditions.append("feature_id = ?")
        params.append(filter["feature_id"])
    if "event_type" in filter:
        conditions.append("event_type = ?")
        params.append(filter["event_type"])
    if "since" in filter:
        # ISO-8601 timestamps sort lexicographically when normalized,
        # which matches our write contract (UTC, fixed offset).
        conditions.append("timestamp >= ?")
        params.append(filter["since"])

    if not conditions:
        return "", ()
    return " WHERE " + " AND ".join(conditions), tuple(params)


def _count_grouped_by(
    conn: sqlite3.Connection,
    column: str,
    where_clause: str,
    params: tuple[Any, ...],
) -> dict[Any, int]:
    """Run `SELECT col, COUNT(*) FROM events {where} GROUP BY col`.

    `column` is constrained to a known set of literals at the only call
    sites (`event_type`, `feature_id`) so f-string interpolation is
    safe — never user input.
    """
    sql = (
        f"SELECT {column}, COUNT(*) FROM events"
        f"{where_clause} GROUP BY {column}"
    )
    return {row[0]: row[1] for row in conn.execute(sql, params).fetchall()}


def _count_total(
    conn: sqlite3.Connection,
    where_clause: str,
    params: tuple[Any, ...],
) -> int:
    """Run `SELECT COUNT(*) FROM events {where}` and return the scalar."""
    sql = f"SELECT COUNT(*) FROM events{where_clause}"
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row is not None else 0
