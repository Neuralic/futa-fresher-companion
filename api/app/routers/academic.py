"""Academic service (faculties, departments, lecturers, courses, class reps, timetable)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import Connection

from app.caching import public_cache
from app.db import get_conn
from app.stubs import not_implemented

router = APIRouter(tags=["academic"])

DbConn = Annotated[Connection, Depends(get_conn)]
# Level and semester match the DB CHECKs. Semester 1-2 is the spec's enum [1, 2].
Level = Annotated[int | None, Query(ge=100, le=700)]
Semester = Annotated[int | None, Query(ge=1, le=2)]
# The contract has no limit/offset on these lists, so each one is capped instead.
MAX_LIST_ROWS = 500


# Public and the same for every caller, so it is safe to cache. Do not add to auth or user routes.
@router.get("/faculties", dependencies=[Depends(public_cache)])
def list_faculties(conn: DbConn):
    rows = conn.execute(
        """
        SELECT id, name, short_name, verification_status, source,
               verified_by, verified_at, updated_at
        FROM faculties
        WHERE deleted_at IS NULL
        ORDER BY name
        """
    ).fetchall()
    return [_faculty(row) for row in rows]


def _faculty(row: dict) -> dict:
    # Shape follows the Faculty schema in docs/openapi.yaml.
    return {
        "id": row["id"],
        "name": row["name"],
        "short_name": row["short_name"],
        "verification": {
            "status": row["verification_status"],
            "source": row["source"],
            "verified_by": row["verified_by"],
            "verified_at": row["verified_at"],
        },
        "updated_at": row["updated_at"],
    }


# Department reads are public and the same for every caller, so they are cached like /faculties.
@router.get("/departments", dependencies=[Depends(public_cache)])
def list_departments(conn: DbConn, faculty_id: uuid.UUID | None = None):
    rows = conn.execute(
        """
        SELECT id, faculty_id, name, short_name, hod_name, office_location,
               verification_status, source, verified_by, verified_at, updated_at
        FROM departments
        WHERE deleted_at IS NULL
          AND (%(faculty_id)s::uuid IS NULL OR faculty_id = %(faculty_id)s::uuid)
        ORDER BY name, id
        LIMIT %(limit)s
        """,
        {"faculty_id": faculty_id, "limit": MAX_LIST_ROWS},
    ).fetchall()
    return [_department(row) for row in rows]


@router.get("/departments/{department_id}", dependencies=[Depends(public_cache)])
def get_department(department_id: uuid.UUID, conn: DbConn):
    return _department(_find_department(conn, department_id))


@router.get("/departments/{department_id}/lecturers", dependencies=[Depends(public_cache)])
def list_department_lecturers(department_id: uuid.UUID, conn: DbConn):
    _find_department(conn, department_id)
    rows = conn.execute(
        """
        SELECT id, department_id, full_name, title, rank, email, office_location,
               specialization, verification_status, source, verified_by, verified_at, updated_at
        FROM lecturers
        WHERE department_id = %(department_id)s AND deleted_at IS NULL
        ORDER BY full_name, id
        LIMIT %(limit)s
        """,
        {"department_id": department_id, "limit": MAX_LIST_ROWS},
    ).fetchall()
    return [_lecturer(row) for row in rows]


@router.get("/departments/{department_id}/courses", dependencies=[Depends(public_cache)])
def list_department_courses(
    department_id: uuid.UUID, conn: DbConn, level: Level = None, semester: Semester = None
):
    _find_department(conn, department_id)
    rows = conn.execute(
        """
        SELECT id, department_id, code, title, units, level, semester,
               verification_status, source, verified_by, verified_at, updated_at
        FROM courses
        WHERE department_id = %(department_id)s AND deleted_at IS NULL
          AND (%(level)s::smallint IS NULL OR level = %(level)s::smallint)
          AND (%(semester)s::smallint IS NULL OR semester = %(semester)s::smallint)
        ORDER BY level, semester, code, id
        LIMIT %(limit)s
        """,
        {
            "department_id": department_id,
            "level": level,
            "semester": semester,
            "limit": MAX_LIST_ROWS,
        },
    ).fetchall()
    return [_course(row) for row in rows]


@router.get("/departments/{department_id}/class-reps", dependencies=[Depends(public_cache)])
def list_department_class_reps(department_id: uuid.UUID, conn: DbConn, level: Level = None):
    _find_department(conn, department_id)
    rows = conn.execute(
        """
        SELECT id, department_id, level, full_name, consent_given,
               CASE WHEN consent_given THEN contact END AS contact,
               verification_status, source, verified_by, verified_at, updated_at
        FROM class_reps
        WHERE department_id = %(department_id)s AND deleted_at IS NULL
          AND (%(level)s::smallint IS NULL OR level = %(level)s::smallint)
        ORDER BY level, full_name, id
        LIMIT %(limit)s
        """,
        {"department_id": department_id, "level": level, "limit": MAX_LIST_ROWS},
    ).fetchall()
    return [_class_rep(row) for row in rows]


@router.get("/departments/{department_id}/timetable", dependencies=[Depends(public_cache)])
def get_department_timetable(
    department_id: uuid.UUID, conn: DbConn, level: Level = None, semester: Semester = None
):
    _find_department(conn, department_id)
    rows = conn.execute(
        """
        SELECT te.id, te.department_id, te.level, te.semester, te.course_id,
               te.day_of_week, te.start_time, te.end_time, te.venue_building_id,
               te.venue_note, te.verification_status, te.source, te.verified_by,
               te.verified_at, te.updated_at
        FROM timetable_entries te
        JOIN courses c ON c.id = te.course_id AND c.deleted_at IS NULL
        WHERE te.department_id = %(department_id)s AND te.deleted_at IS NULL
          AND (%(level)s::smallint IS NULL OR te.level = %(level)s::smallint)
          AND (%(semester)s::smallint IS NULL OR te.semester = %(semester)s::smallint)
        ORDER BY te.day_of_week, te.start_time, te.id
        LIMIT %(limit)s
        """,
        {
            "department_id": department_id,
            "level": level,
            "semester": semester,
            "limit": MAX_LIST_ROWS,
        },
    ).fetchall()
    return [_timetable_entry(row) for row in rows]


def _find_department(conn: Connection, department_id: uuid.UUID) -> dict:
    row = conn.execute(
        """
        SELECT id, faculty_id, name, short_name, hod_name, office_location,
               verification_status, source, verified_by, verified_at, updated_at
        FROM departments
        WHERE id = %(id)s AND deleted_at IS NULL
        """,
        {"id": department_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return row


def _verification(row: dict) -> dict:
    return {
        "status": row["verification_status"],
        "source": row["source"],
        "verified_by": row["verified_by"],
        "verified_at": row["verified_at"],
    }


def _department(row: dict) -> dict:
    # Shape follows the Department schema in docs/openapi.yaml.
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


def _lecturer(row: dict) -> dict:
    # Shape follows the Lecturer schema in docs/openapi.yaml.
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


def _course(row: dict) -> dict:
    # Shape follows the Course schema in docs/openapi.yaml.
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


def _class_rep(row: dict) -> dict:
    # Shape follows the ClassRep schema in docs/openapi.yaml.
    rep = {
        "id": row["id"],
        "department_id": row["department_id"],
        "level": row["level"],
        "full_name": row["full_name"],
        "verification": _verification(row),
        "updated_at": row["updated_at"],
    }
    # NDPR: contact is shown only with consent. The SQL already blanks it; this is the second guard.
    if row["consent_given"] and row["contact"] is not None:
        rep["contact"] = row["contact"]
    return rep


def _timetable_entry(row: dict) -> dict:
    # Shape follows the TimetableEntry schema in docs/openapi.yaml. Times are "HH:MM".
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


@router.get("/lecturers")
def search_lecturers(q: str | None = None, limit: int = 50, offset: int = 0):
    not_implemented()


@router.get("/lecturers/{lecturer_id}")
def get_lecturer(lecturer_id: str):
    not_implemented()
