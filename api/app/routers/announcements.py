"""Information service (announcements & updates)."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection, errors
from pydantic import BaseModel, BeforeValidator, Field, model_validator

from app.auth_deps import AdminUser
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


# Contract-first stubs: PATCH and DELETE are in docs/openapi.yaml, built in a follow-up PR.
@router.patch("/{announcement_id}")
def update_announcement(announcement_id: uuid.UUID):
    not_implemented()


@router.delete("/{announcement_id}", status_code=204)
def delete_announcement(announcement_id: uuid.UUID):
    not_implemented()


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class AnnouncementCreate(BaseModel):
    # published_at is not a field here: the server sets it to now(), and a client value is ignored.
    title: Annotated[str, BeforeValidator(_strip), Field(min_length=3, max_length=200)]
    body: Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=4000)]
    scope: Scope
    faculty_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _check_scope_and_expiry(self):
        # Keep only the id that matches the scope, so a row never carries both.
        if self.scope == "faculty":
            if self.faculty_id is None:
                raise ValueError("faculty_id is needed for scope faculty")
            self.department_id = None
        elif self.scope == "department":
            if self.department_id is None:
                raise ValueError("department_id is needed for scope department")
            self.faculty_id = None
        else:
            self.faculty_id = None
            self.department_id = None
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                raise ValueError("expires_at needs a time zone")
            if self.expires_at <= datetime.now(timezone.utc):
                raise ValueError("expires_at must be in the future")
        return self


DEPARTMENT_FACULTY = "SELECT faculty_id FROM departments WHERE id = %(id)s AND deleted_at IS NULL"
INSERT_ANNOUNCEMENT = """
    INSERT INTO announcements
        (title, body, scope, faculty_id, department_id, author_id, published_at, expires_at)
    VALUES (%(title)s, %(body)s, %(scope)s::announcement_scope, %(faculty_id)s::uuid,
            %(department_id)s::uuid, %(author_id)s::uuid, now(), %(expires_at)s::timestamptz)
    RETURNING id, title, body, scope, faculty_id, department_id, author_id, published_at,
              expires_at, verification_status, source, verified_by, verified_at, updated_at
    """


@router.post("", status_code=201)
def create_announcement(body: AnnouncementCreate, admin: AdminUser, conn: DbConn):
    if not _may_publish(conn, admin, body):
        raise HTTPException(status_code=403, detail="You cannot publish for this scope")
    try:
        row = conn.execute(
            INSERT_ANNOUNCEMENT,
            {
                "title": body.title,
                "body": body.body,
                "scope": body.scope,
                "faculty_id": body.faculty_id,
                "department_id": body.department_id,
                "author_id": admin["id"],
                "expires_at": body.expires_at,
            },
        ).fetchone()
    except errors.ForeignKeyViolation as error:
        raise HTTPException(status_code=422, detail="Unknown faculty or department") from error
    return _announcement(row)


def _may_publish(conn: Connection, admin: dict[str, Any], body: AnnouncementCreate) -> bool:
    """Each admin role publishes only inside its own scope. The database role is the source."""
    role = admin["role"]
    if role == "super_admin":
        return True
    if role == "sug":
        return body.scope == "sug"
    if role == "faculty_admin":
        if body.scope == "faculty":
            return body.faculty_id == admin["faculty_id"]
        if body.scope == "department":
            row = conn.execute(DEPARTMENT_FACULTY, {"id": body.department_id}).fetchone()
            return row is not None and row["faculty_id"] == admin["faculty_id"]
        return False
    if role == "department_admin":
        return body.scope == "department" and body.department_id == admin["department_id"]
    return False


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
