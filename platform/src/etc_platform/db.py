"""Database connection management using psycopg3 connection pool."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

if TYPE_CHECKING:
    from collections.abc import Generator

    from psycopg import Connection

_pool: ConnectionPool | None = None


def get_dsn() -> str:
    return os.environ.get(
        "ETC_DATABASE_URL",
        "postgresql://etc:etc_dev@localhost:5433/etc_platform",
    )


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=get_dsn(),
            min_size=2,
            max_size=10,
            kwargs={"row_factory": dict_row},
        )
    return _pool


@contextmanager
def get_conn() -> Generator[Connection[dict], None, None]:
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def apply_schema(conn: Connection[dict]) -> None:
    """Apply the SQL schema files in order."""
    from pathlib import Path

    sql_dir = Path(__file__).parent.parent.parent / "sql"
    for sql_file in sorted(sql_dir.glob("*.sql")):
        conn.execute(sql_file.read_text())
    conn.commit()
