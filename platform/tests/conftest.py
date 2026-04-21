"""Shared test fixtures for ETC Platform tests."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import psycopg
import pytest
from psycopg.rows import dict_row

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(scope="session")
def pg_dsn() -> str:
    """Database DSN for tests. Uses ETC_TEST_DATABASE_URL or defaults to local Docker."""
    return os.environ.get(
        "ETC_TEST_DATABASE_URL",
        "postgresql://etc:etc_dev@localhost:5433/etc_platform_test",
    )


@pytest.fixture(scope="session")
def setup_test_db(pg_dsn: str) -> None:
    """Create the test database and apply schema once per session."""
    # Connect to default db to create test db
    default_dsn = pg_dsn.rsplit("/", 1)[0] + "/etc_platform"
    with psycopg.connect(default_dsn, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS etc_platform_test")
        conn.execute("CREATE DATABASE etc_platform_test")

    # Apply schema to test db (all migration files in order)
    with psycopg.connect(pg_dsn) as conn:
        from pathlib import Path

        sql_dir = Path(__file__).parent.parent / "sql"
        for sql_file in sorted(sql_dir.glob("*.sql")):
            conn.execute(sql_file.read_text())
        conn.commit()


@pytest.fixture
def db(pg_dsn: str, setup_test_db: None) -> Generator[psycopg.Connection, None, None]:
    """Provide a DB connection that rolls back after each test."""
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        # Use savepoint so each test is isolated
        conn.execute("BEGIN")
        yield conn
        conn.execute("ROLLBACK")
