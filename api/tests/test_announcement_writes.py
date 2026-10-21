"""POST /announcements (admin only), with a fake DB connection (no Postgres needed)."""

import pathlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from fastapi.testclient import TestClient
from psycopg import errors

from app.db import get_conn
from app.main import app
from app.security import create_access_token
from tests.fakedb import FakeCursor, FakeDb

SPEC_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
ANNOUNCEMENT_PROPERTIES = set(SPEC["components"]["schemas"]["Announcement"]["properties"])

FACULTY_ENG = uuid.UUID("11111111-1111-1111-1111-111111111111")
FACULTY_SCI = uuid.UUID("22222222-2222-2222-2222-222222222222")
DEPT_CSC = uuid.UUID("33333333-3333-3333-3333-333333333333")
DEPT_BIO = uuid.UUID("44444444-4444-4444-4444-444444444444")
NOW = datetime.now(timezone.utc)


class WriteFakeDb(FakeDb):
    """FakeDb for reads. The announcement insert is recorded and stored, with a server time."""

    def __init__(self, **tables):
        super().__init__(**tables)
        self.inserts = []

    def execute(self, sql, params=None):
        if sql.lstrip().startswith("INSERT INTO announcements"):
            self.queries.append(sql)
            return self._insert(params or {})
        return super().execute(sql, params)

    def _insert(self, params):
        self.inserts.append(params)
        if params["department_id"] is not None and not any(
            d["id"] == params["department_id"] for d in self.tables.get("departments", [])
        ):
            raise errors.ForeignKeyViolation("insert violates foreign key constraint")
        if params["faculty_id"] is not None and not any(
            f["id"] == params["faculty_id"] for f in self.tables.get("faculties", [])
        ):
            raise errors.ForeignKeyViolation("insert violates foreign key constraint")
        row = {
            "id": uuid.uuid4(),
            "title": params["title"],
            "body": params["body"],
            "scope": params["scope"],
            "faculty_id": params["faculty_id"],
            "department_id": params["department_id"],
            "author_id": params["author_id"],
            # The SQL uses now(). The fake plays the server clock.
            "published_at": datetime.now(timezone.utc),
            "expires_at": params["expires_at"],
            "verification_status": "unverified",
            "source": None,
            "verified_by": None,
            "verified_at": None,
            "updated_at": datetime.now(timezone.utc),
            "deleted_at": None,
        }
        self.tables.setdefault("announcements", []).append(row)
        return FakeCursor([row])


def user(role, **fields):
    row = {
        "id": uuid.uuid4(),
        "full_name": "Test Person",
        "email": f"{role}-{uuid.uuid4().hex[:6]}@example.com",
        "role": role,
        "matric_no": None,
        "department_id": None,
        "faculty_id": None,
        "level": None,
        "is_active": True,
        "deleted_at": None,
    }
    row.update(fields)
    return row


def _auth(row):
    return {"Authorization": f"Bearer {create_access_token(str(row['id']))}"}


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _post(db, row, body):
    app.dependency_overrides[get_conn] = lambda: db
    headers = _auth(row) if row is not None else {}
    return TestClient(app).post("/api/v1/announcements", json=body, headers=headers)


def _body(**fields):
    body = {"title": "Registration opens", "body": "Register on the portal.", "scope": "university"}
    body.update(fields)
    return body


def _db(*users, **tables):
    return WriteFakeDb(users=list(users), **tables)


# ----------------------------------------------------------------- who may post


def test_without_a_token_is_401():
    response = _post(_db(), None, _body())

    assert response.status_code == 401


@pytest.mark.parametrize("role", ["student", "class_rep"])
def test_non_admin_roles_get_403(role):
    caller = user(role)

    response = _post(_db(caller), caller, _body(scope="department", department_id=str(DEPT_CSC)))

    assert response.status_code == 403
    assert response.json() == {"detail": "Admins only"}


def test_super_admin_creates_a_university_announcement_with_201():
    admin = user("super_admin")
    db = _db(admin)

    response = _post(db, admin, _body())

    assert response.status_code == 201
    body = response.json()
    assert set(body) == ANNOUNCEMENT_PROPERTIES
    assert body["author_id"] == str(admin["id"])
    assert body["scope"] == "university"
    assert body["verification"]["status"] == "unverified"


def test_the_role_is_read_from_the_database_on_every_request():
    admin = user("department_admin", department_id=DEPT_CSC)
    db = _db(admin, departments=[{"id": DEPT_CSC, "faculty_id": FACULTY_ENG, "deleted_at": None}])
    assert (
        _post(db, admin, _body(scope="department", department_id=str(DEPT_CSC))).status_code == 201
    )

    admin["role"] = "student"

    response = _post(db, admin, _body(scope="department", department_id=str(DEPT_CSC)))
    assert response.status_code == 403


# ----------------------------------------------------------------- scope rules


def test_department_admin_can_post_only_for_their_own_department():
    admin = user("department_admin", department_id=DEPT_CSC)
    db = _db(admin, departments=[{"id": DEPT_CSC, "faculty_id": FACULTY_ENG, "deleted_at": None}])

    own = _post(db, admin, _body(scope="department", department_id=str(DEPT_CSC)))
    other = _post(db, admin, _body(scope="department", department_id=str(DEPT_BIO)))
    university = _post(db, admin, _body(scope="university"))

    assert own.status_code == 201
    assert other.status_code == 403
    assert university.status_code == 403


def test_faculty_admin_can_post_for_their_faculty_and_its_departments_only():
    admin = user("faculty_admin", faculty_id=FACULTY_ENG)
    db = _db(
        admin,
        faculties=[{"id": FACULTY_ENG}, {"id": FACULTY_SCI}],
        departments=[
            {"id": DEPT_CSC, "faculty_id": FACULTY_ENG, "deleted_at": None},
            {"id": DEPT_BIO, "faculty_id": FACULTY_SCI, "deleted_at": None},
        ],
    )

    own_faculty = _post(db, admin, _body(scope="faculty", faculty_id=str(FACULTY_ENG)))
    other_faculty = _post(db, admin, _body(scope="faculty", faculty_id=str(FACULTY_SCI)))
    own_dept = _post(db, admin, _body(scope="department", department_id=str(DEPT_CSC)))
    other_dept = _post(db, admin, _body(scope="department", department_id=str(DEPT_BIO)))

    assert own_faculty.status_code == 201
    assert other_faculty.status_code == 403
    assert own_dept.status_code == 201
    assert other_dept.status_code == 403


def test_sug_may_post_only_sug_scope():
    sug = user("sug")
    db = _db(sug)

    assert _post(db, sug, _body(scope="sug")).status_code == 201
    assert _post(db, sug, _body(scope="university")).status_code == 403


def test_only_super_admin_may_post_university_scope():
    faculty_admin = user("faculty_admin", faculty_id=FACULTY_ENG)

    response = _post(_db(faculty_admin), faculty_admin, _body(scope="university"))

    assert response.status_code == 403


def test_a_client_supplied_scope_id_that_does_not_match_is_dropped():
    admin = user("super_admin")
    db = _db(admin, faculties=[{"id": FACULTY_ENG}])

    response = _post(
        db, admin, _body(scope="faculty", faculty_id=str(FACULTY_ENG), department_id=str(DEPT_BIO))
    )

    assert response.status_code == 201
    assert response.json()["department_id"] is None


# ----------------------------------------------------------------- what the server sets


def test_client_published_at_is_ignored_and_the_server_sets_it():
    admin = user("super_admin")
    db = _db(admin)

    response = _post(db, admin, _body(published_at="2001-01-01T00:00:00Z"))

    published = datetime.fromisoformat(response.json()["published_at"])
    assert abs(datetime.now(timezone.utc) - published) < timedelta(minutes=1)
    assert all("published_at" not in params for params in db.inserts)


def test_the_insert_uses_now_for_published_at():
    admin = user("super_admin")
    db = _db(admin)

    _post(db, admin, _body())

    insert = next(q for q in db.queries if q.lstrip().startswith("INSERT INTO announcements"))
    assert "now()" in insert


def test_author_is_the_signed_in_admin_not_a_client_value():
    admin = user("super_admin")
    db = _db(admin)

    response = _post(db, admin, _body(author_id=str(uuid.uuid4())))

    assert response.json()["author_id"] == str(admin["id"])


def test_soft_deleted_announcement_is_hidden_from_the_public_list():
    admin = user("super_admin")
    db = _db(admin)
    created = _post(db, admin, _body()).json()
    app.dependency_overrides[get_conn] = lambda: db
    listed = TestClient(app).get("/api/v1/announcements").json()
    assert [a["id"] for a in listed] == [created["id"]]

    # Soft delete: the row stays, with deleted_at set. The public list must stop showing it.
    for row in db.tables["announcements"]:
        row["deleted_at"] = datetime.now(timezone.utc)

    listed_after = TestClient(app).get("/api/v1/announcements").json()
    assert listed_after == []


# ----------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "fields",
    [
        {"body": "x" * 4001},
        {"title": "x" * 201},
        {"title": "ab"},
        {"body": "   "},
        {"scope": "faculty"},
        {"scope": "department"},
        {"scope": "moon"},
        {"expires_at": (NOW - timedelta(days=1)).isoformat()},
        {"expires_at": "2099-01-01T00:00:00"},
    ],
    ids=[
        "body too long",
        "title too long",
        "title too short",
        "blank body",
        "faculty scope without faculty_id",
        "department scope without department_id",
        "unknown scope",
        "expiry in the past",
        "expiry without a time zone",
    ],
)
def test_bad_announcement_input_is_422(fields):
    admin = user("super_admin")
    db = _db(admin)

    response = _post(db, admin, _body(**fields))

    assert response.status_code == 422
    assert db.inserts == []


def test_body_of_exactly_4000_characters_is_accepted():
    admin = user("super_admin")

    response = _post(_db(admin), admin, _body(body="x" * 4000))

    assert response.status_code == 201


def test_unknown_department_is_422_not_500():
    admin = user("super_admin")
    db = _db(admin)

    response = _post(db, admin, _body(scope="department", department_id=str(DEPT_BIO)))

    assert response.status_code == 422
    assert response.json() == {"detail": "Unknown faculty or department"}


def test_validation_errors_do_not_echo_the_text_back():
    admin = user("super_admin")

    response = _post(_db(admin), admin, _body(body="   ", title="secret-title-value-x"))

    assert response.status_code == 422
    assert "secret-title-value-x" not in response.text
