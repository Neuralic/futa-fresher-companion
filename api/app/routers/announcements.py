"""Information service (announcements & updates)."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app.caching import fresh_public_cache
from app.db import get_conn
from app.stubs import not_implemented

router = APIRouter(prefix="/announcements", tags=["announcements"])

DbConn = Annotated[Connection, Depends(get_conn)]
Scope = Literal["university", "sug", "faculty", "department"]
# Spec: limit 1-200 (default 50), offset 0 or more.
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


# Time-sensitive: a new or expiring announcement must show up within about 30 seconds.
@router.get("", dependencies=[Depends(fresh_public_cache)])
def list_announcements(
    conn: DbConn,
    scope: Scope | None = None,
    faculty_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    rows = conn.execute(
        """
        SELECT id, title, body, scope, faculty_id, department_id, author_id,
               published_at, expires_at, verification_status, source, verified_by,
               verified_at, updated_at
        FROM announcements
        WHERE deleted_at IS NULL
          AND published_at <= %(now)s
          AND (expires_at IS NULL OR expires_at > %(now)s)
          AND (%(scope)s::announcement_scope IS NULL
               OR scope = %(scope)s::announcement_scope)
          AND (%(faculty_id)s::uuid IS NULL OR faculty_id = %(faculty_id)s::uuid)
          AND (%(department_id)s::uuid IS NULL OR department_id = %(department_id)s::uuid)
        ORDER BY published_at DESC, id DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {
            "now": _now(),
            "scope": scope,
            "faculty_id": faculty_id,
            "department_id": department_id,
            "limit": limit,
            "offset": offset,
        },
    ).fetchall()
    return [_announcement(row) for row in rows]


# Time-sensitive, like the list: an expired announcement must stop showing quickly.
@router.get("/{announcement_id}", dependencies=[Depends(fresh_public_cache)])
def get_announcement(announcement_id: uuid.UUID, conn: DbConn):
    row = conn.execute(
        """
        SELECT id, title, body, scope, faculty_id, department_id, author_id,
               published_at, expires_at, verification_status, source, verified_by,
               verified_at, updated_at
        FROM announcements
        WHERE id = %(id)s
          AND deleted_at IS NULL
          AND published_at <= %(now)s
          AND (expires_at IS NULL OR expires_at > %(now)s)
        """,
        {"id": announcement_id, "now": _now()},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return _announcement(row)


@router.post("", status_code=201)
def create_announcement():
    not_implemented()


def _now() -> datetime:
    # Passed as a parameter so the publish and expiry checks are testable without a clock.
    return datetime.now(timezone.utc)


def _announcement(row: dict) -> dict:
    # Shape follows the Announcement schema in docs/openapi.yaml.
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "scope": row["scope"],
        "faculty_id": row["faculty_id"],
        "department_id": row["department_id"],
        "author_id": row["author_id"],
        "published_at": row["published_at"],
        "expires_at": row["expires_at"],
        "verification": {
            "status": row["verification_status"],
            "source": row["source"],
            "verified_by": row["verified_by"],
            "verified_at": row["verified_at"],
        },
        "updated_at": row["updated_at"],
    }
