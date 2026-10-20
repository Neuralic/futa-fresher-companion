"""Database access. Use the `get_conn` dependency in route handlers.

Example:
    from fastapi import Depends
    from app.db import get_conn

    @router.get("/faculties")
    def list_faculties(conn=Depends(get_conn)):
        return conn.execute("SELECT id, name FROM faculties WHERE deleted_at IS NULL").fetchall()
"""

import threading
from collections.abc import Iterator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    global _pool
    # Lock so two first requests on a fresh instance cannot each create a pool.
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(
                settings.database_url,
                # Serverless: no idle connection is held between requests (was min_size=1).
                min_size=0,
                # Serverless: each instance uses at most 2 connections; PgBouncer multiplexes them.
                max_size=2,
                # Fail a checkout after 5s when all connections are busy, not the 30s default.
                timeout=5,
                kwargs={
                    "row_factory": dict_row,
                    # PgBouncer in transaction mode cannot reuse server-side prepared statements.
                    "prepare_threshold": None,
                    # Fail a request after 10s when the database is unreachable, not hang.
                    "connect_timeout": 10,
                },
                # Lazy: the pool is opened on the first request, not at import time.
                open=False,
            )
            _pool.open()
    return _pool


def get_conn() -> Iterator:
    with get_pool().connection() as conn:
        yield conn
