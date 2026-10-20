"""GET /api/v1/sync with a fake DB connection (no Postgres needed).

SyncFakeDb applies the same rules as the SQL in app/routers/sync.py: the snapshot bound,
the since bound, keyset order, tombstones, the publish time and the consent CASE. The SQL
itself is checked by running it against the database in a read-only transaction.
"""

import pathlib
import re
import uuid
from datetime import datetime, time, timedelta, timezone

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_conn
from app.main import app
from app.routers.sync import COLLECTIONS
from tests.fakedb import FakeCursor

SPEC_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
SCHEMA_FOR = {
    "faculties": "Faculty",
    "departments": "Department",
    "lecturers": "Lecturer",
    "courses": "Course",
    "class_reps": "ClassRep",
    "buildings": "Building",
    "timetable_entries": "TimetableEntry",
    "announcements": "Announcement",
}

# Microseconds on purpose: the keyset must survive the cursor round trip exactly.
CLOCK = datetime.now(timezone.utc).replace(microsecond=123456)
UT = CLOCK - timedelta(hours=3)
ADMIN_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


class SyncFakeDb:
    def __init__(self, clock, **tables):
        self.clock = clock
        self.tables = tables
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append(sql)
        if "now()" in sql:
            return FakeCursor([{"snapshot": self.clock}])
        params = params or {}
        table = re.search(r"FROM (\w+)", sql).group(1)
        snapshot, since = params["snapshot"], params["since"]
        after_ut, after_id = params["after_updated_at"], params["after_id"]
        rows = []
        for row in self.tables.get(table, []):
            if row["updated_at"] > snapshot:
                continue
            if since is None and row["deleted_at"] is not None:
                continue
            if since is not None and row["updated_at"] <= since:
                continue
            if after_ut is not None and (row["updated_at"], row["id"]) <= (after_ut, after_id):
                continue
            if row["deleted_at"] is None and not _visible(table, row, snapshot):
                continue
            rows.append(_as_sql_row(table, row))
        rows.sort(key=lambda row: (row["updated_at"], row["id"]))
        return FakeCursor(rows[: params["limit"]])


def _visible(table, row, snapshot):
    if table == "announcements":
        return row["published_at"] <= snapshot
    if table == "timetable_entries":
        return not row["course_deleted"]
    return True


def _as_sql_row(table, row):
    result = dict(row)
    if table == "class_reps":
        # The SQL CASE: contact is NULL unless consent was given.
        result["contact"] = row["contact"] if row["consent_given"] else None
    return result


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _get(db, params):
    app.dependency_overrides[get_conn] = lambda: db
    return TestClient(app).get("/api/v1/sync", params=params)


def _all_pages(db, limit, **query):
    pages = []
    params = {"limit": limit, **query}
    while True:
        response = _get(db, params)
        assert response.status_code == 200, response.text
        page = response.json()
        pages.append(page)
        if page["next_cursor"] is None:
            return pages
        params = {"limit": limit, "cursor": page["next_cursor"]}


def _base(**fields):
    row = {
        "id": uuid.uuid4(),
        "updated_at": UT,
        "deleted_at": None,
        "verification_status": "verified",
        "source": "Test source",
        "verified_by": None,
        "verified_at": None,
    }
    row.update(fields)
    return row


def faculty(**fields):
    defaults = {"name": "Faculty of Engineering", "short_name": "FOE"}
    return _base(**{**defaults, **fields})


def department(**fields):
    return _base(
        faculty_id=uuid.uuid4(),
        name="Computer Science",
        short_name="CSC",
        hod_name=None,
        office_location=None,
        **fields,
    )


def lecturer(**fields):
    return _base(
        department_id=uuid.uuid4(),
        full_name="Adaeze Okafor",
        title="Dr.",
        rank=None,
        email="a.okafor@futa.edu.ng",
        office_location=None,
        specialization=None,
        **fields,
    )


def course(**fields):
    return _base(
        department_id=uuid.uuid4(),
        code="CSC101",
        title="Intro",
        units=3,
        level=100,
        semester=1,
        **fields,
    )


def class_rep(**fields):
    defaults = {
        "department_id": uuid.uuid4(),
        "level": 100,
        "full_name": "Chidi Eze",
        "consent_given": False,
        "contact": "+2348000000000",
    }
    return _base(**{**defaults, **fields})


def building(**fields):
    return _base(
        name="Main Library",
        type="library",
        description=None,
        lat=7.296,
        lng=5.145,
        **fields,
    )


def timetable(**fields):
    defaults = {
        "department_id": uuid.uuid4(),
        "level": 100,
        "semester": 1,
        "course_id": uuid.uuid4(),
        "day_of_week": 1,
        "start_time": time(8, 0),
        "end_time": time(10, 0),
        "venue_building_id": None,
        "venue_note": None,
        "course_deleted": False,
    }
    return _base(**{**defaults, **fields})


def announcement(**fields):
    defaults = {
        "title": "Registration",
        "body": "Register on the portal.",
        "scope": "university",
        "faculty_id": None,
        "department_id": None,
        "author_id": ADMIN_ID,
        "published_at": UT,
        "expires_at": None,
    }
    return _base(**{**defaults, **fields})


def _ids_in_order(pages):
    seen = {name: [] for name in COLLECTIONS}
    for page in pages:
        for name in COLLECTIONS:
            seen[name] += [row["id"] for row in page[name]]
            seen[name] += page["deleted"][name]
    return seen


# ------------------------------------------------------------- basics


def test_empty_database():
    db = SyncFakeDb(CLOCK)

    response = _get(db, {})

    body = response.json()
    assert response.status_code == 200
    assert body["full"] is True
    assert body["next_cursor"] is None
    assert all(body[name] == [] for name in COLLECTIONS)
    assert body["deleted"] == {name: [] for name in COLLECTIONS}
    assert body["server_time"] == (CLOCK - timedelta(seconds=60)).isoformat()


def test_contract_shape_and_key_match_openapi():
    db = SyncFakeDb(
        CLOCK,
        faculties=[faculty()],
        departments=[department()],
        lecturers=[lecturer()],
        courses=[course()],
        class_reps=[class_rep(consent_given=True)],
        buildings=[building()],
        timetable_entries=[timetable()],
        announcements=[announcement()],
    )

    body = _get(db, {}).json()

    assert set(body) == set(SCHEMAS["SyncResponse"]["properties"])
    assert set(body["deleted"]) == set(COLLECTIONS)
    for name in COLLECTIONS:
        (item,) = body[name]
        assert set(item) == set(SCHEMAS[SCHEMA_FOR[name]]["properties"]), name
        assert set(SCHEMAS[SCHEMA_FOR[name]]["required"]) <= set(item), name
        assert set(item["verification"]) == set(SCHEMAS["Verification"]["properties"])


def test_response_contains_no_user_or_admin_collections():
    db = SyncFakeDb(CLOCK, faculties=[faculty()])

    body = _get(db, {}).json()

    assert not {"users", "user", "admins", "password_hash", "email"} & set(body)


# ------------------------------------------------------------- paging


def test_multi_page_sync_with_shared_timestamps_skips_and_repeats_nothing():
    # Every row has the same updated_at, so only the id decides the order.
    db = SyncFakeDb(
        CLOCK,
        faculties=[faculty() for _ in range(4)],
        departments=[department() for _ in range(3)],
        buildings=[building() for _ in range(3)],
        announcements=[announcement() for _ in range(2)],
    )
    expected = {
        name: sorted(str(row["id"]) for row in db.tables[name])
        for name in ("faculties", "departments", "buildings", "announcements")
    }

    pages = _all_pages(db, limit=3)

    assert len(pages) > 1
    seen = _ids_in_order(pages)
    for name, ids in expected.items():
        assert seen[name] == ids, name
    assert sum(len(v) for v in seen.values()) == 12
    assert all("OFFSET" not in sql for sql in db.queries)


def test_full_is_true_only_on_the_first_page():
    db = SyncFakeDb(CLOCK, faculties=[faculty() for _ in range(5)])

    pages = _all_pages(db, limit=2)

    assert [page["full"] for page in pages] == [True, False, False]


def test_server_time_on_the_last_page_is_snapshot_minus_60_seconds():
    db = SyncFakeDb(CLOCK, faculties=[faculty() for _ in range(3)])

    pages = _all_pages(db, limit=2)

    expected = (CLOCK - timedelta(seconds=60)).isoformat()
    assert pages[-1]["server_time"] == expected
    assert all(page["server_time"] == expected for page in pages)


def test_limit_counts_rows_across_collections_and_tombstones():
    db = SyncFakeDb(
        CLOCK,
        faculties=[faculty(), faculty()],
        buildings=[building(), building(deleted_at=UT)],
        announcements=[announcement()],
    )

    pages = _all_pages(db, limit=2, since=(CLOCK - timedelta(hours=6)).isoformat())

    for page in pages:
        counted = sum(len(page[name]) for name in COLLECTIONS)
        counted += sum(len(ids) for ids in page["deleted"].values())
        assert counted <= 2
    # Five rows in all (two faculties, a live building, a tombstone, an announcement).
    assert len(pages) == 3


def test_default_limit_is_500():
    db = SyncFakeDb(CLOCK, faculties=[faculty() for _ in range(501)])

    first = _get(db, {}).json()

    assert len(first["faculties"]) == 500
    assert first["next_cursor"] is not None


# ------------------------------------------------------------- deltas


def test_since_is_strict_and_returns_only_newer_rows():
    since = CLOCK - timedelta(hours=2)
    db = SyncFakeDb(
        CLOCK,
        faculties=[
            faculty(id=uuid.UUID(int=1), updated_at=since),
            faculty(id=uuid.UUID(int=2), updated_at=since + timedelta(minutes=1)),
        ],
    )

    body = _get(db, {"since": since.isoformat()}).json()

    assert body["full"] is False
    assert [row["id"] for row in body["faculties"]] == [str(uuid.UUID(int=2))]


def test_tombstones_are_ids_only_in_a_delta_and_absent_from_a_full_sync():
    gone = uuid.uuid4()
    db = SyncFakeDb(
        CLOCK,
        faculties=[faculty(id=gone, deleted_at=UT, name="Old name")],
    )

    delta = _get(db, {"since": (CLOCK - timedelta(hours=6)).isoformat()}).json()
    full = _get(db, {}).json()

    assert delta["deleted"]["faculties"] == [str(gone)]
    assert delta["faculties"] == []
    assert full["deleted"]["faculties"] == []
    assert full["faculties"] == []


def test_unpublished_announcements_are_excluded_and_expired_ones_are_not():
    future = announcement(published_at=CLOCK + timedelta(days=1))
    live = announcement(published_at=UT)
    expired = announcement(published_at=UT, expires_at=CLOCK - timedelta(days=1))
    db = SyncFakeDb(CLOCK, announcements=[future, live, expired])

    body = _get(db, {}).json()

    returned = {row["id"] for row in body["announcements"]}
    assert returned == {str(live["id"]), str(expired["id"])}


def test_class_rep_contact_is_hidden_without_consent():
    without = class_rep(consent_given=False)
    with_consent = class_rep(consent_given=True)
    db = SyncFakeDb(CLOCK, class_reps=[without, with_consent])

    rows = {row["id"]: row for row in _get(db, {}).json()["class_reps"]}

    assert "contact" not in rows[str(without["id"])]
    assert rows[str(with_consent["id"])]["contact"] == "+2348000000000"


def test_timetable_entries_of_a_deleted_course_are_hidden():
    db = SyncFakeDb(
        CLOCK,
        timetable_entries=[timetable(course_deleted=True), timetable(course_deleted=False)],
    )

    body = _get(db, {}).json()

    assert len(body["timetable_entries"]) == 1


def test_timetable_times_are_formatted_as_hh_mm():
    db = SyncFakeDb(CLOCK, timetable_entries=[timetable()])

    (entry,) = _get(db, {}).json()["timetable_entries"]

    assert entry["start_time"] == "08:00"
    assert entry["end_time"] == "10:00"


# ------------------------------------------------------------- cursor safety


def _first_cursor(db):
    response = _get(db, {"limit": 1})
    assert response.json()["next_cursor"] is not None
    return response.json()["next_cursor"]


@pytest.mark.parametrize(
    "tamper",
    [
        lambda token: token.replace(token[5], "A" if token[5] != "A" else "B", 1),
        lambda token: token[:-1] + ("A" if token[-1] != "A" else "B"),
        lambda token: token.replace(".", "", 1),
        lambda token: "not-a-cursor",
        lambda token: "é" * 20,
    ],
    ids=["body changed", "signature changed", "separator removed", "garbage", "non-ascii"],
)
def test_tampered_cursor_returns_422(tamper):
    db = SyncFakeDb(CLOCK, faculties=[faculty() for _ in range(3)])
    cursor = _first_cursor(db)

    response = _get(db, {"limit": 1, "cursor": tamper(cursor)})

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid cursor"}


def test_cursor_signed_with_another_secret_returns_422(monkeypatch):
    db = SyncFakeDb(CLOCK, faculties=[faculty() for _ in range(3)])
    monkeypatch.setattr(settings, "sync_cursor_secret", "someone-elses-secret")
    forged = _first_cursor(db)
    monkeypatch.undo()

    response = _get(db, {"limit": 1, "cursor": forged})

    assert response.status_code == 422


def test_expired_cursor_returns_422():
    old = CLOCK - timedelta(hours=25)
    db = SyncFakeDb(old, faculties=[faculty(updated_at=old - timedelta(hours=1)) for _ in range(3)])
    cursor = _first_cursor(db)

    response = _get(db, {"limit": 1, "cursor": cursor})

    assert response.status_code == 422
    assert "expired" in response.json()["detail"]


def test_cursor_takes_precedence_over_since():
    db = SyncFakeDb(CLOCK, faculties=[faculty() for _ in range(3)])
    cursor = _first_cursor(db)

    body = _get(db, {"limit": 1, "cursor": cursor, "since": CLOCK.isoformat()}).json()

    assert body["full"] is False
    assert len(body["faculties"]) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"since": "2026-10-20T10:00:00"},
        {"since": "not a date"},
        {"limit": "0"},
        {"limit": "1001"},
    ],
)
def test_bad_since_or_limit_returns_422(params):
    db = SyncFakeDb(CLOCK, faculties=[faculty()])

    response = _get(db, params)

    assert response.status_code == 422
