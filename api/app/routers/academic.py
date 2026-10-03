"""Academic service (faculties, departments, lecturers, courses, class reps, timetable)."""

from fastapi import APIRouter

from app.stubs import not_implemented

router = APIRouter(tags=["academic"])


@router.get("/faculties")
def list_faculties():
    not_implemented()


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
