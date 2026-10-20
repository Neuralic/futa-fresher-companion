"""Bulk sync for the offline PWA cache (one request instead of many).

Read docs/DECISIONS.md section 8 before changing paging. In short:
- Collections come in a fixed order. Inside one, rows are ordered by (updated_at, id).
- The first page takes a snapshot time. Later pages read only rows changed up to it.
- The cursor is HMAC-signed and expires after 24 hours. It holds the snapshot, the since
  bound and the position of the last row sent, so a page can be resumed exactly.
"""

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app.config import settings
from app.db import get_conn

router = APIRouter(prefix="/sync", tags=["sync"])

DbConn = Annotated[Connection, Depends(get_conn)]
COLLECTIONS = (
    "faculties",
    "departments",
    "lecturers",
    "courses",
    "class_reps",
    "buildings",
    "timetable_entries",
    "announcements",
)
# The last page reports the snapshot minus this, so clients re-fetch recent changes.
OVERLAP = timedelta(seconds=60)
CURSOR_TTL = timedelta(hours=24)
CURSOR_VERSION = 1


@dataclass(frozen=True)
class _Position:
    """Where a page starts: a collection index, and the last row sent in it (if any)."""

    collection: int
    updated_at: datetime | None = None
    id: uuid.UUID | None = None


@dataclass(frozen=True)
class _Sync:
    """What a later page needs: the snapshot, the since bound, and the position."""

    snapshot: datetime
    since: datetime | None
    position: _Position


@router.get("")
def sync(
    conn: DbConn,
    since: datetime | None = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
):
    if cursor is not None:
        # A cursor takes precedence over since. It already carries the since bound.
        state = _decode_cursor(cursor)
    else:
        if since is not None and since.tzinfo is None:
            raise HTTPException(
                status_code=422,
                detail="since needs a time zone, for example 2026-10-20T10:00:00Z",
            )
        state = _Sync(snapshot=_database_now(conn), since=since, position=_Position(0))

    rows, next_position = _read_page(conn, state, limit)

    collections: dict[str, list[dict[str, Any]]] = {name: [] for name in COLLECTIONS}
    deleted: dict[str, list[uuid.UUID]] = {name: [] for name in COLLECTIONS}
    for index, row in rows:
        name = COLLECTIONS[index]
        if row["deleted_at"] is not None:
            deleted[name].append(row["id"])  # tombstone: the id only
        else:
            collections[name].append(_SHAPE[name](row))

    return {
        "server_time": state.snapshot - OVERLAP,
        # Only the first page of a full sync: no since and no cursor.
        "full": state.since is None and cursor is None,
        "next_cursor": (
            _encode_cursor(replace(state, position=next_position))
            if next_position is not None
            else None
        ),
        **collections,
        "deleted": deleted,
    }


def _database_now(conn: Connection) -> datetime:
    # now() is the transaction start time, the same clock the updated_at triggers use.
    return conn.execute("SELECT now() AS snapshot").fetchone()["snapshot"]


def _read_page(
    conn: Connection, state: _Sync, limit: int
) -> tuple[list[tuple[int, dict[str, Any]]], _Position | None]:
    """Up to `limit` rows in collection order, plus where the next page starts (or None)."""
    rows: list[tuple[int, dict[str, Any]]] = []
    start = state.position
    for index in range(start.collection, len(COLLECTIONS)):
        # One extra row, read past the limit, tells us whether another page exists.
        budget = limit + 1 - len(rows)
        if budget <= 0:
            break
        after = start if index == start.collection else _Position(index)
        params = {
            "snapshot": state.snapshot,
            "since": state.since,
            "after_updated_at": after.updated_at,
            "after_id": after.id,
            "limit": budget,
        }
        for row in conn.execute(_SQL[COLLECTIONS[index]], params).fetchall():
            rows.append((index, row))

    if len(rows) <= limit:
        return rows, None
    rows = rows[:limit]
    index, last = rows[-1]
    return rows, _Position(index, last["updated_at"], last["id"])


def _encode_cursor(state: _Sync) -> str:
    position = state.position
    payload = {
        "v": CURSOR_VERSION,
        "snapshot": state.snapshot.isoformat(),
        "since": state.since.isoformat() if state.since is not None else None,
        "collection": position.collection,
        "updated_at": position.updated_at.isoformat() if position.updated_at else None,
        "id": str(position.id) if position.id is not None else None,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def _decode_cursor(token: str) -> _Sync:
    body, separator, signature = token.partition(".")
    # Check the signature before reading anything in the cursor.
    if not separator or not hmac.compare_digest(
        signature.encode("utf-8"), _sign(body).encode("ascii")
    ):
        raise _bad_cursor()
    try:
        payload = json.loads(_unb64(body))
        if payload["v"] != CURSOR_VERSION:
            raise ValueError("unknown cursor version")
        snapshot = _parse_time(payload["snapshot"])
        since = _parse_time(payload["since"]) if payload["since"] is not None else None
        collection = payload["collection"]
        if type(collection) is not int or not 0 <= collection < len(COLLECTIONS):
            raise ValueError("bad collection")
        updated_at = _parse_time(payload["updated_at"]) if payload["updated_at"] else None
        row_id = uuid.UUID(payload["id"]) if payload["id"] is not None else None
        if (updated_at is None) != (row_id is None):
            raise ValueError("half a position")
    except (KeyError, TypeError, ValueError) as error:
        raise _bad_cursor() from error

    if snapshot < datetime.now(timezone.utc) - CURSOR_TTL:
        raise HTTPException(
            status_code=422,
            detail="Cursor expired. Start again from your last saved since value.",
        )
    return _Sync(snapshot, since, _Position(collection, updated_at, row_id))


def _bad_cursor() -> HTTPException:
    return HTTPException(status_code=422, detail="Invalid cursor")


def _sign(body: str) -> str:
    digest = hmac.new(
        settings.sync_cursor_secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
    ).digest()
    return _b64(digest)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("time must be a string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("time needs a time zone")
    return parsed


# One query per collection. Each one applies the same rules:
# - updated_at <= snapshot, so a page never reads rows changed after the first page.
# - since: only rows changed after it. Without since (a full sync), live rows only.
# - keyset: rows after the position in (updated_at, id) order. No OFFSET.
# - soft-deleted rows come back only so they can be sent as tombstones.
_SQL: dict[str, str] = {
    "faculties": """
        SELECT id, name, short_name, verification_status, source, verified_by, verified_at,
               updated_at, deleted_at
        FROM faculties
        WHERE updated_at <= %(snapshot)s::timestamptz
          AND (%(since)s::timestamptz IS NULL OR updated_at > %(since)s::timestamptz)
          AND (deleted_at IS NULL OR %(since)s::timestamptz IS NOT NULL)
          AND (%(after_updated_at)s::timestamptz IS NULL
               OR (updated_at, id) > (%(after_updated_at)s::timestamptz, %(after_id)s::uuid))
        ORDER BY updated_at, id
        LIMIT %(limit)s
        """,
    "departments": """
        SELECT id, faculty_id, name, short_name, hod_name, office_location,
               verification_status, source, verified_by, verified_at, updated_at, deleted_at
        FROM departments
        WHERE updated_at <= %(snapshot)s::timestamptz
          AND (%(since)s::timestamptz IS NULL OR updated_at > %(since)s::timestamptz)
          AND (deleted_at IS NULL OR %(since)s::timestamptz IS NOT NULL)
          AND (%(after_updated_at)s::timestamptz IS NULL
               OR (updated_at, id) > (%(after_updated_at)s::timestamptz, %(after_id)s::uuid))
        ORDER BY updated_at, id
        LIMIT %(limit)s
        """,
    "lecturers": """
        SELECT id, department_id, full_name, title, rank, email, office_location,
               specialization, verification_status, source, verified_by, verified_at,
               updated_at, deleted_at
        FROM lecturers
        WHERE updated_at <= %(snapshot)s::timestamptz
          AND (%(since)s::timestamptz IS NULL OR updated_at > %(since)s::timestamptz)
          AND (deleted_at IS NULL OR %(since)s::timestamptz IS NOT NULL)
          AND (%(after_updated_at)s::timestamptz IS NULL
               OR (updated_at, id) > (%(after_updated_at)s::timestamptz, %(after_id)s::uuid))
        ORDER BY updated_at, id
        LIMIT %(limit)s
        """,
    "courses": """
        SELECT id, department_id, code, title, units, level, semester,
               verification_status, source, verified_by, verified_at, updated_at, deleted_at
        FROM courses
        WHERE updated_at <= %(snapshot)s::timestamptz
          AND (%(since)s::timestamptz IS NULL OR updated_at > %(since)s::timestamptz)
          AND (deleted_at IS NULL OR %(since)s::timestamptz IS NOT NULL)
          AND (%(after_updated_at)s::timestamptz IS NULL
               OR (updated_at, id) > (%(after_updated_at)s::timestamptz, %(after_id)s::uuid))
        ORDER BY updated_at, id
        LIMIT %(limit)s
        """,
    # Contact is blanked in SQL unless consent_given. The Python shape checks it again.
    "class_reps": """
        SELECT id, department_id, level, full_name, consent_given,
               CASE WHEN consent_given THEN contact END AS contact,
               verification_status, source, verified_by, verified_at, updated_at, deleted_at
        FROM class_reps
        WHERE updated_at <= %(snapshot)s::timestamptz
          AND (%(since)s::timestamptz IS NULL OR updated_at > %(since)s::timestamptz)
          AND (deleted_at IS NULL OR %(since)s::timestamptz IS NOT NULL)
          AND (%(after_updated_at)s::timestamptz IS NULL
               OR (updated_at, id) > (%(after_updated_at)s::timestamptz, %(after_id)s::uuid))
        ORDER BY updated_at, id
        LIMIT %(limit)s
        """,
    "buildings": """
        SELECT id, name, type, description, verification_status, source, verified_by,
               verified_at, updated_at, deleted_at,
               ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng
        FROM buildings
        WHERE updated_at <= %(snapshot)s::timestamptz
          AND (%(since)s::timestamptz IS NULL OR updated_at > %(since)s::timestamptz)
          AND (deleted_at IS NULL OR %(since)s::timestamptz IS NOT NULL)
          AND (%(after_updated_at)s::timestamptz IS NULL
               OR (updated_at, id) > (%(after_updated_at)s::timestamptz, %(after_id)s::uuid))
        ORDER BY updated_at, id
        LIMIT %(limit)s
        """,
    # A timetable entry is hidden while its course is soft-deleted, as on the public read.
    "timetable_entries": """
        SELECT te.id, te.department_id, te.level, te.semester, te.course_id,
               te.day_of_week, te.start_time, te.end_time, te.venue_building_id,
               te.venue_note, te.verification_status, te.source, te.verified_by,
               te.verified_at, te.updated_at, te.deleted_at
        FROM timetable_entries te
        JOIN courses c ON c.id = te.course_id
        WHERE te.updated_at <= %(snapshot)s::timestamptz
          AND (%(since)s::timestamptz IS NULL OR te.updated_at > %(since)s::timestamptz)
          AND (te.deleted_at IS NULL OR %(since)s::timestamptz IS NOT NULL)
          AND (te.deleted_at IS NOT NULL OR c.deleted_at IS NULL)
          AND (%(after_updated_at)s::timestamptz IS NULL
               OR (te.updated_at, te.id)
                  > (%(after_updated_at)s::timestamptz, %(after_id)s::uuid))
        ORDER BY te.updated_at, te.id
        LIMIT %(limit)s
        """,
    # Publish time is checked here. Expiry is not: clients hide expired rows locally.
    "announcements": """
        SELECT id, title, body, scope, faculty_id, department_id, author_id,
               published_at, expires_at, verification_status, source, verified_by,
               verified_at, updated_at, deleted_at
        FROM announcements
        WHERE updated_at <= %(snapshot)s::timestamptz
          AND (%(since)s::timestamptz IS NULL OR updated_at > %(since)s::timestamptz)
          AND (deleted_at IS NULL OR %(since)s::timestamptz IS NOT NULL)
          AND (deleted_at IS NOT NULL OR published_at <= %(snapshot)s::timestamptz)
          AND (%(after_updated_at)s::timestamptz IS NULL
               OR (updated_at, id) > (%(after_updated_at)s::timestamptz, %(after_id)s::uuid))
        ORDER BY updated_at, id
        LIMIT %(limit)s
        """,
}


# The shapes below follow the schemas in docs/openapi.yaml. They match the public reads in
# the other routers. api/tests/test_sync.py checks the keys against the spec.
def _verification(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": row["verification_status"],
        "source": row["source"],
        "verified_by": row["verified_by"],
        "verified_at": row["verified_at"],
    }


def _faculty(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "short_name": row["short_name"],
        "verification": _verification(row),
        "updated_at": row["updated_at"],
    }


def _department(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "faculty_id": row["faculty_id"],
        "name": row["name"],
        "short_name": row["short_name"],
        "hod_name": row["hod_name"],
        "office_location": row["office_location"],
        "verification": _verification(row),
        "updated_at": row["updated_at"],
    }


def _lecturer(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "department_id": row["department_id"],
        "full_name": row["full_name"],
        "title": row["title"],
        "rank": row["rank"],
        "email": row["email"],
        "office_location": row["office_location"],
        "specialization": row["specialization"],
        "verification": _verification(row),
        "updated_at": row["updated_at"],
    }


def _course(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "department_id": row["department_id"],
        "code": row["code"],
        "title": row["title"],
        "units": row["units"],
        "level": row["level"],
        "semester": row["semester"],
        "verification": _verification(row),
        "updated_at": row["updated_at"],
    }


def _class_rep(row: dict[str, Any]) -> dict[str, Any]:
    rep = {
        "id": row["id"],
        "department_id": row["department_id"],
        "level": row["level"],
        "full_name": row["full_name"],
        "verification": _verification(row),
        "updated_at": row["updated_at"],
    }
    # NDPR: contact only with consent. The SQL already blanks it; this is the second check.
    if row["consent_given"] and row["contact"] is not None:
        rep["contact"] = row["contact"]
    return rep


def _building(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "description": row["description"],
        "lat": row["lat"],
        "lng": row["lng"],
        "verification": _verification(row),
        "updated_at": row["updated_at"],
    }


def _timetable_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "department_id": row["department_id"],
        "level": row["level"],
        "semester": row["semester"],
        "course_id": row["course_id"],
        "day_of_week": row["day_of_week"],
        "start_time": row["start_time"].strftime("%H:%M"),
        "end_time": row["end_time"].strftime("%H:%M"),
        "venue_building_id": row["venue_building_id"],
        "venue_note": row["venue_note"],
        "verification": _verification(row),
        "updated_at": row["updated_at"],
    }


def _announcement(row: dict[str, Any]) -> dict[str, Any]:
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
        "verification": _verification(row),
        "updated_at": row["updated_at"],
    }


_SHAPE = {
    "faculties": _faculty,
    "departments": _department,
    "lecturers": _lecturer,
    "courses": _course,
    "class_reps": _class_rep,
    "buildings": _building,
    "timetable_entries": _timetable_entry,
    "announcements": _announcement,
}
