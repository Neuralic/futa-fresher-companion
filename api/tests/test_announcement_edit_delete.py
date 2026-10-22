"""PATCH and DELETE /announcements/{id} (admin only), with a fake DB connection."""

import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import get_conn
from app.main import app
from app.security import create_access_token
from tests.fakedb import FakeCursor
from tests.test_announcement_writes import (
    ANNOUNCEMENT_PROPERTIES,
    DEPT_BIO,
    DEPT_CSC,
    FACULTY_ENG,
    FACULTY_SCI,
    NOW,
    WriteFakeDb,
    user,
)
from tests.test_sync import SyncFakeDb

OLD = datetime.now(timezone.utc) - timedelta(days=2)
FUTURE = datetime.now(timezone.utc) + timedelta(days=30)
LATER = datetime.now(timezone.utc) + timedelta(days=60)


class EditFakeDb(WriteFakeDb):
    """Adds the two UPDATE statements. It plays the updated_at trigger like the database does."""

    def __init__(self, **tables):
        super().__init__(**tables)
        self.updates = []

    def execute(self, sql, params=None):
        if sql.lstrip().startswith("UPDATE announcements"):
            self.queries.append(sql)
            self.updates.append(sql)
            return self._update(sql, params or {})
        return super().execute(sql, params)

    def _update(self, sql, params):
        live = [
            row
            for row in self.tables.get("announcements", [])
            if row["id"] == params["id"] and row["deleted_at"] is None
        ]
        if not live:
            return FakeCursor([])
        row = live[0]
        if "SET deleted_at = now()" in sql:
            row["deleted_at"] = datetime.now(timezone.utc)
        else:
            set_list = _set_list(sql)
            for column, name in re.findall(r"(\w+) = %\((\w+)\)s", set_list):
                row[column] = params[name]
        row["updated_at"] = datetime.now(timezone.utc)  # the BEFORE UPDATE trigger
        return FakeCursor([row])


def stored(**fields):
    row = {
        "id": uuid.uuid4(),
        "title": "Registration opens",
        "body": "Register on the portal.",
        "scope": "university",
        "faculty_id": None,
        "department_id": None,
        "author_id": uuid.uuid4(),
        "published_at": OLD,
        "expires_at": FUTURE,
        "verification_status": "verified",
        "source": "Registry",
        "verified_by": None,
        "verified_at": None,
        "updated_at": OLD,
        "deleted_at": None,
    }
    row.update(fields)
    return row


def _set_list(sql):
    return re.search(r"SET (.*?) WHERE", sql, re.DOTALL).group(1).strip()


DEPARTMENTS = [
    {"id": DEPT_CSC, "faculty_id": FACULTY_ENG, "deleted_at": None},
    {"id": DEPT_BIO, "faculty_id": FACULTY_SCI, "deleted_at": None},
]


def _db(*users, announcements=()):
    return EditFakeDb(
        users=list(users),
        departments=[dict(d) for d in DEPARTMENTS],
        announcements=list(announcements),
    )


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _call(method, db, caller, announcement_id, **kwargs):
    app.dependency_overrides[get_conn] = lambda: db
    headers = {}
    if caller is not None:
        headers = {"Authorization": f"Bearer {create_access_token(str(caller['id']))}"}
    return TestClient(app).request(
        method, f"/api/v1/announcements/{announcement_id}", headers=headers, **kwargs
    )


def _patch(db, caller, announcement_id, body):
    return _call("PATCH", db, caller, announcement_id, json=body)


def _delete(db, caller, announcement_id):
    return _call("DELETE", db, caller, announcement_id)


# ----------------------------------------------------------------- who may call


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_without_a_token_is_401(method):
    row = stored()

    response = _call(method, _db(announcements=[row]), None, row["id"], json={"title": "New title"})

    assert response.status_code == 401


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
@pytest.mark.parametrize("role", ["student", "class_rep"])
@pytest.mark.parametrize("exists", [True, False], ids=["existing id", "unknown id"])
def test_non_admin_roles_get_403_and_learn_nothing_about_the_id(method, role, exists):
    caller = user(role)
    row = stored()
    target = row["id"] if exists else uuid.uuid4()

    response = _call(
        method, _db(caller, announcements=[row]), caller, target, json={"title": "New title"}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Admins only"}


# Each case: the caller, and the stored row the caller must NOT be able to change.
OUT_OF_SCOPE = {
    "department_admin, another department": (
        ("department_admin", {"department_id": DEPT_CSC}),
        {"scope": "department", "department_id": DEPT_BIO},
    ),
    "department_admin, university": (
        ("department_admin", {"department_id": DEPT_CSC}),
        {"scope": "university"},
    ),
    "department_admin, their faculty": (
        ("department_admin", {"department_id": DEPT_CSC}),
        {"scope": "faculty", "faculty_id": FACULTY_ENG},
    ),
    "department_admin, sug": (
        ("department_admin", {"department_id": DEPT_CSC}),
        {"scope": "sug"},
    ),
    "faculty_admin, another faculty": (
        ("faculty_admin", {"faculty_id": FACULTY_ENG}),
        {"scope": "faculty", "faculty_id": FACULTY_SCI},
    ),
    "faculty_admin, department of another faculty": (
        ("faculty_admin", {"faculty_id": FACULTY_ENG}),
        {"scope": "department", "department_id": DEPT_BIO},
    ),
    "faculty_admin, university": (
        ("faculty_admin", {"faculty_id": FACULTY_ENG}),
        {"scope": "university"},
    ),
    "faculty_admin, sug": (
        ("faculty_admin", {"faculty_id": FACULTY_ENG}),
        {"scope": "sug"},
    ),
    "sug, university": (("sug", {}), {"scope": "university"}),
    "sug, faculty": (("sug", {}), {"scope": "faculty", "faculty_id": FACULTY_ENG}),
    "sug, department": (("sug", {}), {"scope": "department", "department_id": DEPT_CSC}),
}

IN_SCOPE = {
    "department_admin, own department": (
        ("department_admin", {"department_id": DEPT_CSC}),
        {"scope": "department", "department_id": DEPT_CSC},
    ),
    "faculty_admin, own faculty": (
        ("faculty_admin", {"faculty_id": FACULTY_ENG}),
        {"scope": "faculty", "faculty_id": FACULTY_ENG},
    ),
    "faculty_admin, department in their faculty": (
        ("faculty_admin", {"faculty_id": FACULTY_ENG}),
        {"scope": "department", "department_id": DEPT_CSC},
    ),
    "sug, sug": (("sug", {}), {"scope": "sug"}),
    "super_admin, university": (("super_admin", {}), {"scope": "university"}),
    "super_admin, any department": (
        ("super_admin", {}),
        {"scope": "department", "department_id": DEPT_BIO},
    ),
}


@pytest.mark.parametrize("case", list(OUT_OF_SCOPE), ids=list(OUT_OF_SCOPE))
def test_patch_outside_the_callers_scope_is_403_and_changes_nothing(case):
    (role, fields), target = OUT_OF_SCOPE[case]
    caller = user(role, **fields)
    row = stored(**target)
    db = _db(caller, announcements=[row])

    response = _patch(db, caller, row["id"], {"title": "Hijacked title"})

    assert response.status_code == 403
    assert db.updates == []
    assert row["title"] == "Registration opens"


@pytest.mark.parametrize("case", list(OUT_OF_SCOPE), ids=list(OUT_OF_SCOPE))
def test_delete_outside_the_callers_scope_is_403_and_changes_nothing(case):
    (role, fields), target = OUT_OF_SCOPE[case]
    caller = user(role, **fields)
    row = stored(**target)
    db = _db(caller, announcements=[row])

    response = _delete(db, caller, row["id"])

    assert response.status_code == 403
    assert db.updates == []
    assert row["deleted_at"] is None


@pytest.mark.parametrize("case", list(IN_SCOPE), ids=list(IN_SCOPE))
def test_each_admin_role_can_edit_and_delete_inside_its_scope(case):
    (role, fields), target = IN_SCOPE[case]
    caller = user(role, **fields)
    row = stored(**target)
    db = _db(caller, announcements=[row])

    patched = _patch(db, caller, row["id"], {"title": "Updated title"})
    deleted = _delete(db, caller, row["id"])

    assert patched.status_code == 200
    assert patched.json()["title"] == "Updated title"
    assert deleted.status_code == 204


def test_the_scope_comes_from_the_stored_row_not_the_request():
    caller = user("department_admin", department_id=DEPT_CSC)
    row = stored(scope="department", department_id=DEPT_BIO)
    db = _db(caller, announcements=[row])

    response = _patch(
        db,
        caller,
        row["id"],
        {"title": "Hijacked title", "scope": "department", "department_id": str(DEPT_CSC)},
    )

    assert response.status_code == 403
    assert row["department_id"] == DEPT_BIO


def test_the_role_is_read_from_the_database_on_every_request():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])
    assert _patch(db, admin, row["id"], {"title": "First edit"}).status_code == 200

    admin["role"] = "student"

    assert _patch(db, admin, row["id"], {"title": "Second edit"}).status_code == 403
    assert _delete(db, admin, row["id"]).status_code == 403


# ----------------------------------------------------------------- 404


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_unknown_id_is_404(method):
    admin = user("super_admin")

    response = _call(method, _db(admin), admin, uuid.uuid4(), json={"title": "New title"})

    assert response.status_code == 404


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_already_deleted_announcement_is_404(method):
    admin = user("super_admin")
    row = stored(deleted_at=OLD)

    response = _call(
        method, _db(admin, announcements=[row]), admin, row["id"], json={"title": "New title"}
    )

    assert response.status_code == 404


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_a_403_is_only_given_for_a_row_that_exists(method):
    caller = user("sug")
    missing = _call(method, _db(caller), caller, uuid.uuid4(), json={"title": "New title"})
    row = stored()
    existing = _call(
        method, _db(caller, announcements=[row]), caller, row["id"], json={"title": "New title"}
    )

    assert missing.status_code == 404
    assert existing.status_code == 403


def test_deleting_twice_is_404_the_second_time():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])

    assert _delete(db, admin, row["id"]).status_code == 204
    assert _delete(db, admin, row["id"]).status_code == 404


def test_the_id_must_be_a_uuid():
    admin = user("super_admin")

    response = _call("DELETE", _db(admin), admin, "not-a-uuid")

    assert response.status_code == 422


# ----------------------------------------------------------------- 422


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"scope": "sug"},
        {"faculty_id": str(FACULTY_ENG), "published_at": "2001-01-01T00:00:00Z"},
        {"title": "ab"},
        {"title": "x" * 201},
        {"title": "   "},
        {"title": None},
        {"title": 123},
        {"body": ""},
        {"body": "   "},
        {"body": "x" * 4001},
        {"body": None},
        {"expires_at": (NOW - timedelta(days=1)).isoformat()},
        {"expires_at": "2099-01-01T00:00:00"},
        {"expires_at": "not a date"},
    ],
    ids=[
        "empty body",
        "only an ignored field (scope)",
        "only ignored fields (faculty_id, published_at)",
        "title too short",
        "title too long",
        "blank title",
        "null title",
        "title not a string",
        "empty body text",
        "blank body text",
        "body too long",
        "null body text",
        "expiry in the past",
        "expiry without a time zone",
        "expiry not a date",
    ],
)
def test_bad_patch_input_is_422_and_changes_nothing(fields):
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])

    response = _patch(db, admin, row["id"], fields)

    assert response.status_code == 422
    assert db.updates == []


def test_a_patch_with_no_json_body_at_all_is_422():
    admin = user("super_admin")
    row = stored()

    response = _call("PATCH", _db(admin, announcements=[row]), admin, row["id"])

    assert response.status_code == 422


def test_validation_errors_do_not_echo_the_text_back():
    admin = user("super_admin")
    row = stored()

    response = _patch(_db(admin, announcements=[row]), admin, row["id"], {"title": "x" * 201})

    assert response.status_code == 422
    assert "xxxxxxxxxx" not in response.text


def test_limits_are_inclusive():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])

    response = _patch(db, admin, row["id"], {"title": "x" * 200, "body": "y" * 4000})

    assert response.status_code == 200
    short = _patch(db, admin, row["id"], {"title": "abc", "body": "z"})
    assert short.status_code == 200


# ----------------------------------------------------------------- PATCH result


def test_patch_changes_only_the_fields_that_were_sent():
    admin = user("super_admin")
    row = stored()
    before = dict(row)
    db = _db(admin, announcements=[row])

    response = _patch(db, admin, row["id"], {"title": "Registration is open"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == ANNOUNCEMENT_PROPERTIES
    assert body["title"] == "Registration is open"
    assert body["body"] == before["body"]
    assert datetime.fromisoformat(body["expires_at"]) == before["expires_at"]
    unchanged = ("body", "expires_at", "scope", "faculty_id", "department_id", "published_at")
    assert all(row[column] == before[column] for column in unchanged)


def test_the_update_statement_sets_only_the_sent_columns():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])

    _patch(db, admin, row["id"], {"body": "New body text"})

    (sql,) = db.updates
    set_list = _set_list(sql)
    assert set_list == "body = %(body)s"
    assert "deleted_at IS NULL" in sql
    assert "RETURNING" in sql


def test_patch_with_all_three_fields_in_a_fixed_column_order():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])

    body = {"expires_at": LATER.isoformat(), "body": "New body", "title": "New title"}
    response = _patch(db, admin, row["id"], body)

    assert response.status_code == 200
    (sql,) = db.updates
    assert _set_list(sql).split(", ") == [
        "title = %(title)s",
        "body = %(body)s",
        "expires_at = %(expires_at)s::timestamptz",
    ]


def test_scope_ids_and_published_at_can_never_change():
    admin = user("super_admin")
    row = stored(scope="faculty", faculty_id=FACULTY_ENG)
    before = dict(row)
    db = _db(admin, announcements=[row])

    response = _patch(
        db,
        admin,
        row["id"],
        {
            "title": "Still the engineering faculty",
            "scope": "university",
            "faculty_id": str(FACULTY_SCI),
            "department_id": str(DEPT_BIO),
            "published_at": "2001-01-01T00:00:00Z",
            "author_id": str(uuid.uuid4()),
            "id": str(uuid.uuid4()),
            "deleted_at": "2001-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 200
    for column in ("scope", "faculty_id", "department_id", "published_at", "author_id", "id"):
        assert row[column] == before[column]
    assert row["deleted_at"] is None
    (sql,) = db.updates
    set_list = _set_list(sql)
    assert set_list == "title = %(title)s"


def test_title_and_body_are_trimmed():
    admin = user("super_admin")
    row = stored()

    response = _patch(
        _db(admin, announcements=[row]),
        admin,
        row["id"],
        {"title": "  Padded title  ", "body": "\n Padded body \n"},
    )

    assert response.json()["title"] == "Padded title"
    assert response.json()["body"] == "Padded body"


def test_expiry_can_be_changed_to_a_later_time():
    admin = user("super_admin")
    row = stored()

    response = _patch(
        _db(admin, announcements=[row]), admin, row["id"], {"expires_at": LATER.isoformat()}
    )

    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()["expires_at"]) == LATER


def test_null_expiry_removes_the_expiry():
    admin = user("super_admin")
    row = stored(expires_at=FUTURE)
    db = _db(admin, announcements=[row])

    response = _patch(db, admin, row["id"], {"expires_at": None})

    assert response.status_code == 200
    assert response.json()["expires_at"] is None
    assert row["expires_at"] is None
    assert row["title"] == "Registration opens"


def test_leaving_expires_at_out_keeps_the_expiry():
    admin = user("super_admin")
    row = stored(expires_at=FUTURE)

    response = _patch(_db(admin, announcements=[row]), admin, row["id"], {"title": "New title"})

    assert datetime.fromisoformat(response.json()["expires_at"]) == FUTURE


def test_an_already_expired_announcement_can_still_be_edited_to_a_new_future_expiry():
    admin = user("super_admin")
    row = stored(expires_at=OLD + timedelta(hours=1))

    response = _patch(
        _db(admin, announcements=[row]), admin, row["id"], {"expires_at": FUTURE.isoformat()}
    )

    assert response.status_code == 200


def test_patch_moves_updated_at_forward():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])

    response = _patch(db, admin, row["id"], {"title": "New title"})

    assert datetime.fromisoformat(response.json()["updated_at"]) > OLD


# ----------------------------------------------------------------- DELETE result


def test_delete_returns_204_with_an_empty_body_and_soft_deletes():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])

    response = _delete(db, admin, row["id"])

    assert response.status_code == 204
    assert response.content == b""
    assert row["deleted_at"] is not None
    assert row in db.tables["announcements"]  # soft delete: the row is kept
    (sql,) = db.updates
    assert "SET deleted_at = now()" in sql
    assert "DELETE FROM" not in " ".join(db.queries)


def test_a_deleted_announcement_is_gone_from_the_public_list_and_get():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])
    app.dependency_overrides[get_conn] = lambda: db
    public = TestClient(app)
    assert [a["id"] for a in public.get("/api/v1/announcements").json()] == [str(row["id"])]

    _delete(db, admin, row["id"])

    assert public.get("/api/v1/announcements").json() == []
    assert public.get(f"/api/v1/announcements/{row['id']}").status_code == 404


def test_the_public_list_shows_an_edit():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])
    _patch(db, admin, row["id"], {"title": "Edited title"})
    app.dependency_overrides[get_conn] = lambda: db

    listed = TestClient(app).get("/api/v1/announcements").json()

    assert [a["title"] for a in listed] == ["Edited title"]


# ----------------------------------------------------------------- /sync


def _sync(rows, since):
    sync_db = SyncFakeDb(datetime.now(timezone.utc) + timedelta(seconds=5), announcements=rows)
    app.dependency_overrides[get_conn] = lambda: sync_db
    response = TestClient(app).get("/api/v1/sync", params={"since": since.isoformat()})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_deleted_announcement_is_a_tombstone_in_sync():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])
    since = OLD + timedelta(hours=1)
    assert [a["id"] for a in _sync(db.tables["announcements"], since)["announcements"]] == []

    _delete(db, admin, row["id"])

    synced = _sync(db.tables["announcements"], since)
    assert synced["deleted"]["announcements"] == [str(row["id"])]
    assert synced["announcements"] == []


def test_an_edited_announcement_arrives_in_sync_with_the_new_text():
    admin = user("super_admin")
    row = stored()
    db = _db(admin, announcements=[row])
    since = OLD + timedelta(hours=1)

    _patch(db, admin, row["id"], {"title": "Edited title"})

    synced = _sync(db.tables["announcements"], since)
    assert [a["title"] for a in synced["announcements"]] == ["Edited title"]
    assert synced["deleted"]["announcements"] == []
