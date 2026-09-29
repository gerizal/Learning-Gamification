"""psycopg (v3) connection pool. DATABASE_URL env var."""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DEFAULT_DATABASE_URL = "postgresql://localhost:5432/playclass"

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                _pool = ConnectionPool(
                    conninfo=database_url(),
                    min_size=1,
                    max_size=10,
                    kwargs={"row_factory": dict_row, "connect_timeout": 3},
                    open=False,
                    timeout=5,
                )
                # wait=False: the app must still start (and /api/health answer) when the DB is down.
                _pool.open(wait=False)
    return _pool


def close_pool() -> None:
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """Yield a pooled connection inside a transaction (commit on success, rollback on error)."""
    with get_pool().connection() as conn:
        yield conn


def ping() -> bool:
    try:
        with connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False
