"""Announcement read endpoints with a fake DB connection (no Postgres needed)."""

import pathlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from fastapi.testclient import TestClient

from app.db import get_conn
from app.main import app
from tests.fakedb import FakeDb

SPEC_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]

ANN_1 = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-000000000001")
ANN_2 = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-000000000002")
ANN_3 = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-000000000003")
FACULTY_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEPT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ADMIN_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
MISSING_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
PUBLISHED = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)


def _ago(days):
    return datetime.now(timezone.utc) - timedelta(days=days)


def _ahead(days):
    return datetime.now(timezone.utc) + timedelta(days=days)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _get(path, **tables):
    db = FakeDb(**tables)
    app.dependency_overrides[get_conn] = lambda: db
    return TestClient(app).get(path), db


def _announcement(**overrides):
    row = {
        "id": ANN_1,
        "title": "Registration opens",
        "body": "Register on the portal.",
        "scope": "university",
        "faculty_id": None,
        "department_id": None,
        "author_id": ADMIN_ID,
        "published_at": PUBLISHED,
        "expires_at": None,
        "verification_status": "verified",
        "source": "Registrar notice",
        "verified_by": ADMIN_ID,
        "verified_at": PUBLISHED,
        "updated_at": PUBLISHED,
        "deleted_at": None,
    }
    row.update(overrides)
    return row


# ------------------------------------------------------------ GET /announcements


def test_list_empty():
    response, _ = _get("/api/v1/announcements")

    assert response.status_code == 200
    assert response.json() == []


def test_announcement_contract_shape():
    response, _ = _get("/api/v1/announcements", announcements=[_announcement()])

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(ANN_1),
            "title": "Registration opens",
            "body": "Register on the portal.",
            "scope": "university",
            "faculty_id": None,
            "department_id": None,
            "author_id": str(ADMIN_ID),
            "published_at": "2026-01-05T09:00:00+00:00",
            "expires_at": None,
            "verification": {
                "status": "verified",
                "source": "Registrar notice",
                "verified_by": str(ADMIN_ID),
                "verified_at": "2026-01-05T09:00:00+00:00",
            },
            "updated_at": "2026-01-05T09:00:00+00:00",
        }
    ]


def test_announcement_keys_match_openapi():
    response, _ = _get("/api/v1/announcements", announcements=[_announcement()])
    announcement = response.json()[0]
    schema = SCHEMAS["Announcement"]

    assert set(announcement) == set(schema["properties"])
    assert set(schema["required"]) <= set(announcement)
    assert set(announcement["verification"]) == set(SCHEMAS["Verification"]["properties"])


def test_list_excludes_soft_deleted():
    response, db = _get(
        "/api/v1/announcements",
        announcements=[_announcement(), _announcement(id=ANN_2, deleted_at=PUBLISHED)],
    )

    assert [a["id"] for a in response.json()] == [str(ANN_1)]
    assert "WHERE deleted_at IS NULL" in db.queries[0]


def test_list_excludes_unpublished_and_expired_announcements():
    table = [
        _announcement(id=ANN_1, published_at=PUBLISHED, expires_at=None),
        _announcement(id=ANN_2, published_at=_ahead(1)),  # not published yet
        _announcement(id=ANN_3, published_at=PUBLISHED, expires_at=_ago(1)),  # expired
    ]

    response, db = _get("/api/v1/announcements", announcements=table)

    assert [a["id"] for a in response.json()] == [str(ANN_1)]
    assert "published_at <= %(now)s" in db.queries[0]
    assert "expires_at > %(now)s" in db.queries[0]


def test_list_still_shows_announcements_that_expire_later():
    table = [_announcement(published_at=PUBLISHED, expires_at=_ahead(7))]

    response, _ = _get("/api/v1/announcements", announcements=table)

    assert len(response.json()) == 1


def test_list_shows_unverified_announcements_with_their_status():
    # The spec does not filter on verification. Unverified rows are shown with their status.
    table = [_announcement(verification_status="unverified", verified_by=None, verified_at=None)]

    response, _ = _get("/api/v1/announcements", announcements=table)

    assert response.json()[0]["verification"]["status"] == "unverified"


def test_list_sorted_newest_first_with_id_tiebreak():
    recent = _ago(1)
    table = [
        _announcement(id=ANN_1, published_at=_ago(3)),
        _announcement(id=ANN_2, published_at=recent),
        _announcement(id=ANN_3, published_at=recent),
    ]

    response, db = _get("/api/v1/announcements", announcements=table)

    # Same publish time: the higher id comes first, so the order is stable.
    assert [a["id"] for a in response.json()] == [str(ANN_3), str(ANN_2), str(ANN_1)]
    assert "ORDER BY published_at DESC, id DESC" in db.queries[0]


def test_list_filters_by_scope_faculty_and_department():
    table = [
        _announcement(id=ANN_1, scope="university"),
        _announcement(id=ANN_2, scope="faculty", faculty_id=FACULTY_ID),
        _announcement(id=ANN_3, scope="department", department_id=DEPT_ID),
    ]

    by_scope, _ = _get("/api/v1/announcements?scope=faculty", announcements=table)
    by_faculty, _ = _get(f"/api/v1/announcements?faculty_id={FACULTY_ID}", announcements=table)
    by_department, _ = _get(f"/api/v1/announcements?department_id={DEPT_ID}", announcements=table)

    assert [a["id"] for a in by_scope.json()] == [str(ANN_2)]
    assert [a["id"] for a in by_faculty.json()] == [str(ANN_2)]
    assert [a["id"] for a in by_department.json()] == [str(ANN_3)]


def test_list_pages_with_limit_and_offset():
    table = [_announcement(id=uuid.uuid4(), published_at=_ago(n)) for n in range(1, 6)]

    response, db = _get("/api/v1/announcements?limit=2&offset=1", announcements=table)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert db.params[0]["limit"] == 2
    assert db.params[0]["offset"] == 1


def test_list_defaults_to_50_and_offset_0():
    _, db = _get("/api/v1/announcements")

    assert db.params[0]["limit"] == 50
    assert db.params[0]["offset"] == 0


def test_list_passes_current_time_as_aware_datetime():
    _, db = _get("/api/v1/announcements")

    assert db.params[0]["now"].tzinfo is not None


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=201",
        "offset=-1",
        "scope=bogus",
        "faculty_id=not-a-uuid",
        "department_id=not-a-uuid",
    ],
)
def test_bad_query_params_are_422_not_500(query):
    response, _ = _get(f"/api/v1/announcements?{query}")

    assert response.status_code == 422


# ------------------------------------------------------ GET /announcements/{id}


def test_detail_returns_one_in_contract_shape():
    response, _ = _get(f"/api/v1/announcements/{ANN_1}", announcements=[_announcement()])

    assert response.status_code == 200
    assert response.json() == _get_list_item()


def _get_list_item():
    response, _ = _get("/api/v1/announcements", announcements=[_announcement()])
    return response.json()[0]


def test_detail_soft_deleted_is_404():
    response, _ = _get(
        f"/api/v1/announcements/{ANN_1}", announcements=[_announcement(deleted_at=PUBLISHED)]
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "row",
    [
        _announcement(published_at=_ahead(1)),
        _announcement(published_at=PUBLISHED, expires_at=_ago(1)),
    ],
    ids=["unpublished", "expired"],
)
def test_detail_unpublished_or_expired_is_404(row):
    response, _ = _get(f"/api/v1/announcements/{ANN_1}", announcements=[row])

    assert response.status_code == 404


def test_detail_unknown_id_returns_404_in_error_shape():
    response, _ = _get(f"/api/v1/announcements/{MISSING_ID}", announcements=[_announcement()])

    assert response.status_code == 404
    assert response.json() == {"detail": "Announcement not found"}


def test_detail_bad_id_format_is_422_not_500():
    response, _ = _get("/api/v1/announcements/not-a-uuid", announcements=[_announcement()])

    assert response.status_code == 422


# ----------------------------------------------------------------- caching


@pytest.mark.parametrize(
    "path",
    ["/api/v1/announcements", f"/api/v1/announcements/{ANN_1}"],
)
def test_announcement_reads_use_fresh_cache(path):
    response, _ = _get(path, announcements=[_announcement()])

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == (
        "public, max-age=0, s-maxage=30, stale-while-revalidate=60"
    )
