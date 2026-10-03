"""Database access. Use the `get_conn` dependency in route handlers.

Example:
    from fastapi import Depends
    from app.db import get_conn

    @router.get("/faculties")
    def list_faculties(conn=Depends(get_conn)):
        return conn.execute("SELECT id, name FROM faculties WHERE deleted_at IS NULL").fetchall()
"""

from collections.abc import Iterator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        _pool.open()
    return _pool


def get_conn() -> Iterator:
    with get_pool().connection() as conn:
        yield conn
