"""Department read endpoints with a fake DB connection (no Postgres needed)."""

import pathlib
import re
import uuid
from datetime import datetime, time, timezone

import pytest
import yaml
from fastapi.testclient import TestClient

from app.db import get_conn
from app.main import app
from app.routers.academic import MAX_LIST_ROWS, TIMETABLE_MAX_ROWS

SPEC_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]

FACULTY_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CSC_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
EEE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
ADMIN_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
LECTURER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
COURSE_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
REP_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
ENTRY_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")
NOW = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
MISSING_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeDb:
    """Holds rows for the department tables.

    A query goes to the table named after its first FROM. Soft-deleted rows are dropped.
    Each named param filters the rows with the same column name (None means no filter).
    Rows are sorted by the ORDER BY columns and cut by LIMIT. The SQL text is checked
    separately in the tests, so a missing clause still fails.
    """

    def __init__(self, **tables):
        self.tables = tables
        self.queries = []
        self.params = []

    def execute(self, sql, params=None):
        params = params or {}
        self.queries.append(sql)
        self.params.append(params)
        table = re.search(r"FROM (\w+)", sql).group(1)
        rows = [row for row in self.tables.get(table, []) if row["deleted_at"] is None]
        for name, value in params.items():
            if name != "limit" and value is not None:
                rows = [row for row in rows if row.get(name) == value]
        order = re.search(r"ORDER BY ([^\n]+)", sql)
        if order:
            keys = [column.strip().split(".")[-1] for column in order.group(1).split(",")]
            rows = sorted(rows, key=lambda row: tuple(row[key] for key in keys))
        if params.get("limit") is not None:
            rows = rows[: params["limit"]]
        return FakeCursor(rows)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _get(path, **tables):
    db = FakeDb(**tables)
    app.dependency_overrides[get_conn] = lambda: db
    return TestClient(app).get(path), db


def _verification_fields(**overrides):
    fields = {
        "verification_status": "verified",
        "source": "FUTA prospectus 2026",
        "verified_by": ADMIN_ID,
        "verified_at": NOW,
        "updated_at": NOW,
        "deleted_at": None,
    }
    fields.update(overrides)
    return fields


def _department(**overrides):
    row = {
        "id": CSC_ID,
        "faculty_id": FACULTY_ID,
        "name": "Computer Science",
        "short_name": "CSC",
        "hod_name": "Dr. A. Bello",
        "office_location": "Block C, Room 4",
    }
    row.update(_verification_fields())
    row.update(overrides)
    return row


def _lecturer(**overrides):
    row = {
        "id": LECTURER_ID,
        "department_id": CSC_ID,
        "full_name": "Adaeze Okafor",
        "title": "Dr.",
        "rank": "Senior Lecturer",
        "email": "a.okafor@futa.edu.ng",
        "office_location": "Block C, Room 9",
        "specialization": "Databases",
    }
    row.update(_verification_fields())
    row.update(overrides)
    return row


def _course(**overrides):
    row = {
        "id": COURSE_ID,
        "department_id": CSC_ID,
        "code": "CSC101",
        "title": "Introduction to Computing",
        "units": 3,
        "level": 100,
        "semester": 1,
    }
    row.update(_verification_fields())
    row.update(overrides)
    return row


def _class_rep(**overrides):
    row = {
        "id": REP_ID,
        "department_id": CSC_ID,
        "level": 100,
        "full_name": "Chidi Eze",
        "consent_given": False,
        "contact": "+2348000000000",
    }
    row.update(_verification_fields())
    row.update(overrides)
    return row


def _entry(**overrides):
    row = {
        "id": ENTRY_ID,
        "department_id": CSC_ID,
        "level": 100,
        "semester": 1,
        "course_id": COURSE_ID,
        "day_of_week": 1,
        "start_time": time(8, 0),
        "end_time": time(10, 0),
        "venue_building_id": None,
        "venue_note": "Lecture Theatre 2",
    }
    row.update(_verification_fields())
    row.update(overrides)
    return row


# ----------------------------------------------------------------- /departments


def test_list_departments_empty():
    response, _ = _get("/api/v1/departments")

    assert response.status_code == 200
    assert response.json() == []


def test_department_contract_shape():
    response, _ = _get("/api/v1/departments", departments=[_department()])

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(CSC_ID),
            "faculty_id": str(FACULTY_ID),
            "name": "Computer Science",
            "short_name": "CSC",
            "hod_name": "Dr. A. Bello",
            "office_location": "Block C, Room 4",
            "verification": {
                "status": "verified",
                "source": "FUTA prospectus 2026",
                "verified_by": str(ADMIN_ID),
                "verified_at": "2026-01-05T09:00:00+00:00",
            },
            "updated_at": "2026-01-05T09:00:00+00:00",
        }
    ]


def test_department_keys_match_openapi():
    response, _ = _get("/api/v1/departments", departments=[_department()])
    department = response.json()[0]
    schema = SCHEMAS["Department"]

    assert set(department) == set(schema["properties"])
    assert set(schema["required"]) <= set(department)
    assert set(department["verification"]) == set(SCHEMAS["Verification"]["properties"])


def test_list_departments_filters_by_faculty():
    other_faculty = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    table = [
        _department(),
        _department(id=EEE_ID, faculty_id=other_faculty, name="Electrical Engineering"),
    ]

    response, _ = _get(f"/api/v1/departments?faculty_id={FACULTY_ID}", departments=table)

    assert [d["id"] for d in response.json()] == [str(CSC_ID)]


def test_list_departments_excludes_soft_deleted_and_sorts_by_name():
    table = [
        _department(id=EEE_ID, name="Electrical Engineering"),
        _department(),
        _department(id=ADMIN_ID, name="Archived Studies", deleted_at=NOW),
    ]

    response, db = _get("/api/v1/departments", departments=table)

    assert [d["name"] for d in response.json()] == [
        "Computer Science",
        "Electrical Engineering",
    ]
    assert "WHERE deleted_at IS NULL" in db.queries[0]
    assert "ORDER BY name, id" in db.queries[0]


def test_departments_with_same_name_are_ordered_by_id():
    # Names are unique per faculty only, so two faculties can share one.
    table = [
        _department(id=EEE_ID, name="General Studies"),
        _department(id=CSC_ID, name="General Studies"),
    ]

    response, _ = _get("/api/v1/departments", departments=table)

    assert [d["id"] for d in response.json()] == [str(CSC_ID), str(EEE_ID)]


def test_get_department_returns_one():
    response, _ = _get(f"/api/v1/departments/{CSC_ID}", departments=[_department()])

    assert response.status_code == 200
    assert response.json()["id"] == str(CSC_ID)


def test_get_department_unknown_id_returns_404_in_error_shape():
    response, _ = _get(f"/api/v1/departments/{MISSING_ID}", departments=[_department()])

    assert response.status_code == 404
    assert response.json() == {"detail": "Department not found"}


def test_get_department_soft_deleted_returns_404():
    table = [_department(deleted_at=NOW)]

    response, _ = _get(f"/api/v1/departments/{CSC_ID}", departments=table)

    assert response.status_code == 404


# ------------------------------------------------------------- sub-lists


def test_lecturers_contract_shape_and_keys():
    response, _ = _get(
        f"/api/v1/departments/{CSC_ID}/lecturers",
        departments=[_department()],
        lecturers=[_lecturer()],
    )
    lecturer = response.json()[0]
    schema = SCHEMAS["Lecturer"]

    assert response.status_code == 200
    assert set(lecturer) == set(schema["properties"])
    assert set(schema["required"]) <= set(lecturer)
    assert lecturer["email"] == "a.okafor@futa.edu.ng"
    assert lecturer["verification"]["status"] == "verified"


def test_lecturers_excludes_soft_deleted_and_sorts_by_name():
    response, db = _get(
        f"/api/v1/departments/{CSC_ID}/lecturers",
        departments=[_department()],
        lecturers=[
            _lecturer(id=EEE_ID, full_name="Yusuf Musa"),
            _lecturer(),
            _lecturer(id=ADMIN_ID, full_name="Old Name", deleted_at=NOW),
        ],
    )

    assert [lec["full_name"] for lec in response.json()] == [
        "Adaeze Okafor",
        "Yusuf Musa",
    ]
    assert "deleted_at IS NULL" in db.queries[1]
    assert "ORDER BY full_name, id" in db.queries[1]


def test_lecturers_of_another_department_are_not_listed():
    other_dept = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    response, _ = _get(
        f"/api/v1/departments/{CSC_ID}/lecturers",
        departments=[_department()],
        lecturers=[_lecturer(department_id=other_dept)],
    )

    assert response.json() == []


def test_courses_filter_by_level_and_semester_and_sort():
    table = [
        _course(id=EEE_ID, code="CSC201", level=200, semester=1),
        _course(code="CSC102", level=100, semester=2),
        _course(id=ADMIN_ID, code="CSC101", level=100, semester=1),
        _course(id=REP_ID, code="CSC999", level=100, semester=1, deleted_at=NOW),
    ]

    everything, _ = _get(
        f"/api/v1/departments/{CSC_ID}/courses", departments=[_department()], courses=table
    )
    first_year_first_sem, _ = _get(
        f"/api/v1/departments/{CSC_ID}/courses?level=100&semester=1",
        departments=[_department()],
        courses=table,
    )

    assert [c["code"] for c in everything.json()] == ["CSC101", "CSC102", "CSC201"]
    assert [c["code"] for c in first_year_first_sem.json()] == ["CSC101"]
    assert set(everything.json()[0]) == set(SCHEMAS["Course"]["properties"])


def test_courses_reject_semester_outside_enum():
    response, _ = _get(
        f"/api/v1/departments/{CSC_ID}/courses?semester=3", departments=[_department()]
    )

    assert response.status_code == 422


def test_class_reps_show_contact_only_with_consent():
    response, _ = _get(
        f"/api/v1/departments/{CSC_ID}/class-reps",
        departments=[_department()],
        class_reps=[
            _class_rep(consent_given=False),
            _class_rep(id=EEE_ID, full_name="Ada Obi", consent_given=True),
        ],
    )
    by_name = {rep["full_name"]: rep for rep in response.json()}

    assert "contact" not in by_name["Chidi Eze"]
    assert by_name["Ada Obi"]["contact"] == "+2348000000000"


def test_class_rep_keys_match_openapi():
    response, _ = _get(
        f"/api/v1/departments/{CSC_ID}/class-reps",
        departments=[_department()],
        class_reps=[_class_rep(consent_given=True)],
    )
    rep = response.json()[0]
    schema = SCHEMAS["ClassRep"]

    assert set(rep) <= set(schema["properties"])
    assert set(schema["required"]) <= set(rep)


def test_timetable_formats_times_and_sorts_by_day_then_start():
    table = [
        _entry(id=EEE_ID, day_of_week=2, start_time=time(8, 0), end_time=time(9, 0)),
        _entry(day_of_week=1, start_time=time(14, 0), end_time=time(16, 0)),
        _entry(id=ADMIN_ID, day_of_week=1, start_time=time(8, 0), end_time=time(10, 0)),
    ]

    response, db = _get(
        f"/api/v1/departments/{CSC_ID}/timetable",
        departments=[_department()],
        timetable_entries=table,
    )
    entries = response.json()

    assert [(e["day_of_week"], e["start_time"]) for e in entries] == [
        (1, "08:00"),
        (1, "14:00"),
        (2, "08:00"),
    ]
    assert entries[0]["end_time"] == "10:00"
    assert set(entries[0]) == set(SCHEMAS["TimetableEntry"]["properties"])
    assert "ORDER BY te.day_of_week, te.start_time, te.id" in db.queries[1]


def test_timetable_excludes_entries_whose_course_is_deleted():
    # The course join must also filter soft-deleted courses, or their entries would leak.
    _, db = _get(
        f"/api/v1/departments/{CSC_ID}/timetable",
        departments=[_department()],
        timetable_entries=[_entry()],
    )

    assert "JOIN courses c ON c.id = te.course_id AND c.deleted_at IS NULL" in db.queries[1]
    assert "te.deleted_at IS NULL" in db.queries[1]


def test_timetable_soft_deleted_entry_is_excluded():
    response, _ = _get(
        f"/api/v1/departments/{CSC_ID}/timetable",
        departments=[_department()],
        timetable_entries=[_entry(deleted_at=NOW)],
    )

    assert response.json() == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/departments/{id}/lecturers",
        "/api/v1/departments/{id}/courses",
        "/api/v1/departments/{id}/class-reps",
        "/api/v1/departments/{id}/timetable",
    ],
)
def test_sub_lists_return_404_for_unknown_department(path):
    response, _ = _get(path.format(id=MISSING_ID), departments=[_department()])

    assert response.status_code == 404
    assert response.json() == {"detail": "Department not found"}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/departments/not-a-uuid",
        "/api/v1/departments/not-a-uuid/lecturers",
        "/api/v1/departments/not-a-uuid/courses",
        "/api/v1/departments/not-a-uuid/class-reps",
        "/api/v1/departments/not-a-uuid/timetable",
        "/api/v1/departments?faculty_id=not-a-uuid",
    ],
)
def test_bad_id_format_is_422_not_500(path):
    response, _ = _get(path, departments=[_department()])

    assert response.status_code == 422


def test_lists_are_capped_at_max_rows():
    lecturers = [
        _lecturer(id=uuid.uuid4(), full_name=f"Lecturer {n:04d}") for n in range(MAX_LIST_ROWS + 1)
    ]

    response, _ = _get(
        f"/api/v1/departments/{CSC_ID}/lecturers",
        departments=[_department()],
        lecturers=lecturers,
    )

    assert len(response.json()) == MAX_LIST_ROWS


def test_timetable_is_capped_at_its_own_higher_limit():
    entries = [
        _entry(id=uuid.uuid4(), start_time=time(8, 0), end_time=time(9, 0))
        for _ in range(TIMETABLE_MAX_ROWS + 1)
    ]

    response, db = _get(
        f"/api/v1/departments/{CSC_ID}/timetable",
        departments=[_department()],
        timetable_entries=entries,
    )

    assert db.params[1]["limit"] == 2000
    assert len(response.json()) == TIMETABLE_MAX_ROWS


def test_timetable_returns_more_than_the_general_list_cap():
    # A department can have more timetable rows than the 500-row cap used for other lists.
    entries = [
        _entry(id=uuid.uuid4(), start_time=time(8, 0), end_time=time(9, 0))
        for _ in range(MAX_LIST_ROWS + 100)
    ]

    response, _ = _get(
        f"/api/v1/departments/{CSC_ID}/timetable",
        departments=[_department()],
        timetable_entries=entries,
    )

    assert len(response.json()) == MAX_LIST_ROWS + 100


def test_other_lists_keep_the_general_cap():
    paths = [
        f"/api/v1/departments/{CSC_ID}/lecturers",
        f"/api/v1/departments/{CSC_ID}/courses",
        f"/api/v1/departments/{CSC_ID}/class-reps",
        "/api/v1/departments",
    ]

    for path in paths:
        _, db = _get(path, departments=[_department()])

        assert db.params[-1]["limit"] == MAX_LIST_ROWS, path


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/departments",
        f"/api/v1/departments/{CSC_ID}",
        f"/api/v1/departments/{CSC_ID}/lecturers",
        f"/api/v1/departments/{CSC_ID}/courses",
        f"/api/v1/departments/{CSC_ID}/timetable",
    ],
)
def test_department_reads_are_publicly_cacheable(path):
    response, _ = _get(
        path,
        departments=[_department()],
        lecturers=[],
        courses=[],
        timetable_entries=[],
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == (
        "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    )


def test_class_reps_use_short_cache_because_they_carry_contact_details():
    response, _ = _get(
        f"/api/v1/departments/{CSC_ID}/class-reps",
        departments=[_department()],
        class_reps=[],
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == ("public, max-age=0, s-maxage=30, must-revalidate")
