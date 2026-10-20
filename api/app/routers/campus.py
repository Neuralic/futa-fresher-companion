"""Campus service (buildings, map, routing). Owners: Backend + Maps/GIS."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app.caching import public_cache
from app.db import get_conn
from app.stubs import not_implemented

router = APIRouter(prefix="/campus", tags=["campus"])

DbConn = Annotated[Connection, Depends(get_conn)]
BuildingType = Literal[
    "faculty",
    "department",
    "lecture_hall",
    "hostel",
    "admin",
    "library",
    "sports",
    "food",
    "health",
    "worship",
    "gate",
    "other",
]
# Spec: limit 1-200 (default 50), offset 0 or more.
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
# Hard cap on search text, so a long string cannot make the name search expensive.
SearchText = Annotated[str | None, Query(max_length=100)]


# Buildings change rarely and are the same for every caller, so they are cached like /faculties.
@router.get("/buildings", dependencies=[Depends(public_cache)])
def list_buildings(
    conn: DbConn,
    q: SearchText = None,
    type: BuildingType | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    rows = conn.execute(
        """
        SELECT id, name, type, description, verification_status, source, verified_by,
               verified_at, updated_at,
               ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng
        FROM buildings
        WHERE deleted_at IS NULL
          AND (%(name_like)s::text IS NULL OR name ILIKE %(name_like)s::text)
          AND (%(type)s::building_type IS NULL OR type = %(type)s::building_type)
        ORDER BY name, id
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {
            "name_like": _search_pattern(q),
            "type": type,
            "limit": limit,
            "offset": offset,
        },
    ).fetchall()
    return [_building(row) for row in rows]


@router.get("/buildings/{building_id}", dependencies=[Depends(public_cache)])
def get_building(building_id: uuid.UUID, conn: DbConn):
    row = conn.execute(
        """
        SELECT id, name, type, description, verification_status, source, verified_by,
               verified_at, updated_at,
               ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng
        FROM buildings
        WHERE id = %(id)s AND deleted_at IS NULL
        """,
        {"id": building_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Building not found")
    return _building(row)


@router.get("/route")
def get_route(from_lat: float, from_lng: float, to_building_id: str):
    not_implemented()


def _search_pattern(text: str | None) -> str | None:
    """Turn user text into a LIKE pattern that matches it literally, wildcards included."""
    text = (text or "").strip()
    if not text:
        return None
    # Backslash is PostgreSQL's default LIKE escape character.
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _building(row: dict) -> dict:
    # Shape follows the Building schema in docs/openapi.yaml. Coordinates come from the
    # PostGIS geography column (WGS84, stored as lng/lat), read back as plain numbers.
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "description": row["description"],
        "lat": row["lat"],
        "lng": row["lng"],
        "verification": {
            "status": row["verification_status"],
            "source": row["source"],
            "verified_by": row["verified_by"],
            "verified_at": row["verified_at"],
        },
        "updated_at": row["updated_at"],
    }
