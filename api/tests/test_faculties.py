"""GET /api/v1/faculties with a fake DB connection (no Postgres needed)."""

import pathlib
import uuid
from datetime import datetime, timezone

import pytest
import yaml
from fastapi.testclient import TestClient

from app.db import get_conn
from app.main import app

SPEC_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))

FOE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
FOS_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ADMIN_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
NOW = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConn:
    """Holds the rows a `faculties` table would hold.

    The filter and sort are applied in Python here. The SQL text is checked separately,
    so a missing `deleted_at IS NULL` or `ORDER BY` in the query still fails a test.
    """

    def __init__(self, table):
        self.table = table
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append(sql)
        live = [row for row in self.table if row["deleted_at"] is None]
        return FakeCursor(sorted(live, key=lambda row: row["name"]))


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _get_faculties(table):
    conn = FakeConn(table)
    app.dependency_overrides[get_conn] = lambda: conn
    response = TestClient(app).get("/api/v1/faculties")
    return response, conn


def _row(**overrides):
    row = {
        "id": FOE_ID,
        "name": "Faculty of Engineering",
        "short_name": "FOE",
        "verification_status": "verified",
        "source": "FUTA prospectus 2026",
        "verified_by": ADMIN_ID,
        "verified_at": NOW,
        "updated_at": NOW,
        "deleted_at": None,
    }
    row.update(overrides)
    return row


def test_empty_list():
    response, _ = _get_faculties([])

    assert response.status_code == 200
    assert response.json() == []


def test_returns_faculty_in_contract_shape():
    response, _ = _get_faculties([_row()])

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(FOE_ID),
            "name": "Faculty of Engineering",
            "short_name": "FOE",
            "verification": {
                "status": "verified",
                "source": "FUTA prospectus 2026",
                "verified_by": str(ADMIN_ID),
                "verified_at": "2026-01-05T09:00:00+00:00",
            },
            "updated_at": "2026-01-05T09:00:00+00:00",
        }
    ]


def test_shape_matches_openapi_schema():
    response, _ = _get_faculties([_row()])
    faculty = response.json()[0]
    schemas = SPEC["components"]["schemas"]

    assert set(faculty) == set(schemas["Faculty"]["properties"])
    assert set(faculty["verification"]) == set(schemas["Verification"]["properties"])


def test_response_is_publicly_cacheable():
    response, _ = _get_faculties([_row()])

    assert response.headers["Cache-Control"] == (
        "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    )


def test_health_is_not_cacheable():
    response = TestClient(app).get("/api/v1/health")

    assert "Cache-Control" not in response.headers


def test_deleted_rows_are_excluded_and_results_sorted_by_name():
    table = [
        _row(id=FOS_ID, name="Faculty of Science", short_name="FOS"),
        _row(id=FOE_ID, name="Faculty of Engineering"),
        _row(id=ADMIN_ID, name="Faculty of Arts", deleted_at=NOW),
    ]

    response, conn = _get_faculties(table)

    assert [f["name"] for f in response.json()] == [
        "Faculty of Engineering",
        "Faculty of Science",
    ]
    assert "WHERE deleted_at IS NULL" in conn.queries[0]
    assert "ORDER BY name" in conn.queries[0]
