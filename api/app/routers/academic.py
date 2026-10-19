"""Academic service (faculties, departments, lecturers, courses, class reps, timetable)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from psycopg import Connection

from app.db import get_conn
from app.stubs import not_implemented

router = APIRouter(tags=["academic"])

DbConn = Annotated[Connection, Depends(get_conn)]


@router.get("/faculties")
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


@router.get("/departments")
def list_departments(faculty_id: str | None = None):
    not_implemented()


@router.get("/departments/{department_id}")
def get_department(department_id: str):
    not_implemented()


@router.get("/departments/{department_id}/lecturers")
def list_department_lecturers(department_id: str):
    not_implemented()


@router.get("/departments/{department_id}/courses")
def list_department_courses(
    department_id: str, level: int | None = None, semester: int | None = None
):
    not_implemented()


@router.get("/departments/{department_id}/class-reps")
def list_department_class_reps(department_id: str, level: int | None = None):
    not_implemented()


@router.get("/departments/{department_id}/timetable")
def get_department_timetable(
    department_id: str, level: int | None = None, semester: int | None = None
):
    not_implemented()


@router.get("/lecturers")
def search_lecturers(q: str | None = None, limit: int = 50, offset: int = 0):
    not_implemented()


@router.get("/lecturers/{lecturer_id}")
def get_lecturer(lecturer_id: str):
    not_implemented()
