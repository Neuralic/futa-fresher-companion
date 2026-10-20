"""Campus building reads with a fake DB connection (no Postgres needed)."""

import pathlib
import uuid
from datetime import datetime, timezone

import pytest
import yaml
from fastapi.testclient import TestClient

from app.db import get_conn
from app.main import app
from tests.fakedb import FakeDb

SPEC_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]

BLDG_1 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-000000000001")
BLDG_2 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-000000000002")
BLDG_3 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-000000000003")
ADMIN_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
MISSING_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
NOW = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _get(path, **tables):
    db = FakeDb(**tables)
    app.dependency_overrides[get_conn] = lambda: db
    return TestClient(app).get(path), db


def _building(**overrides):
    row = {
        "id": BLDG_1,
        "name": "Main Library",
        "type": "library",
        "description": "Central library",
        "lat": 7.2960,
        "lng": 5.1450,
        "verification_status": "verified",
        "source": "Campus survey 2026",
        "verified_by": ADMIN_ID,
        "verified_at": NOW,
        "updated_at": NOW,
        "deleted_at": None,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------- GET /campus/buildings


def test_list_empty():
    response, _ = _get("/api/v1/campus/buildings")

    assert response.status_code == 200
    assert response.json() == []


def test_building_contract_shape():
    response, _ = _get("/api/v1/campus/buildings", buildings=[_building()])

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(BLDG_1),
            "name": "Main Library",
            "type": "library",
            "description": "Central library",
            "lat": 7.296,
            "lng": 5.145,
            "verification": {
                "status": "verified",
                "source": "Campus survey 2026",
                "verified_by": str(ADMIN_ID),
                "verified_at": "2026-01-05T09:00:00+00:00",
            },
            "updated_at": "2026-01-05T09:00:00+00:00",
        }
    ]


def test_building_keys_match_openapi():
    response, _ = _get("/api/v1/campus/buildings", buildings=[_building()])
    building = response.json()[0]
    schema = SCHEMAS["Building"]

    assert set(building) == set(schema["properties"])
    assert set(schema["required"]) <= set(building)
    assert set(building["verification"]) == set(SCHEMAS["Verification"]["properties"])


def test_list_excludes_soft_deleted():
    response, db = _get(
        "/api/v1/campus/buildings",
        buildings=[_building(), _building(id=BLDG_2, name="Old Hall", deleted_at=NOW)],
    )

    assert [b["id"] for b in response.json()] == [str(BLDG_1)]
    assert "WHERE deleted_at IS NULL" in db.queries[0]


def test_list_sorted_by_name_then_id():
    table = [
        _building(id=BLDG_3, name="Senate Building"),
        _building(id=BLDG_2, name="Main Library"),
        _building(id=BLDG_1, name="Main Library"),
    ]

    response, db = _get("/api/v1/campus/buildings", buildings=table)

    assert [b["id"] for b in response.json()] == [str(BLDG_1), str(BLDG_2), str(BLDG_3)]
    assert "ORDER BY name, id" in db.queries[0]


def test_type_filter():
    table = [_building(), _building(id=BLDG_2, name="Gate A", type="gate")]

    response, _ = _get("/api/v1/campus/buildings?type=gate", buildings=table)

    assert [b["name"] for b in response.json()] == ["Gate A"]


def test_name_search_is_case_insensitive():
    response, _ = _get(
        "/api/v1/campus/buildings?q=LIBRARY",
        buildings=[_building(), _building(id=BLDG_2, name="Gate A", type="gate")],
    )

    assert [b["name"] for b in response.json()] == ["Main Library"]


def test_search_treats_underscore_and_percent_literally():
    table = [
        _building(id=BLDG_1, name="Lecture_Hall 1", type="lecture_hall"),
        _building(id=BLDG_2, name="Hostel A", type="hostel"),
        _building(id=BLDG_3, name="Block 50% Lab", type="other"),
    ]

    underscore, _ = _get("/api/v1/campus/buildings?q=_", buildings=table)
    percent, _ = _get("/api/v1/campus/buildings?q=%25", buildings=table)
    backslash, _ = _get("/api/v1/campus/buildings?q=%5C", buildings=table)

    # "_" must not act as "any one character": only names that contain a real underscore.
    assert [b["name"] for b in underscore.json()] == ["Lecture_Hall 1"]
    # "%" must not act as "any text": only names that contain a real percent sign.
    assert [b["name"] for b in percent.json()] == ["Block 50% Lab"]
    assert backslash.json() == []


def test_search_text_is_capped_at_100_characters():
    accepted, _ = _get("/api/v1/campus/buildings?q=" + "a" * 100)
    rejected, _ = _get("/api/v1/campus/buildings?q=" + "a" * 101)

    assert accepted.status_code == 200
    assert rejected.status_code == 422


def test_search_query_is_bound_as_a_parameter_not_sql_text():
    _, db = _get("/api/v1/campus/buildings?q=x%27%3BDROP%20TABLE%20buildings%3B--")

    assert "DROP" not in db.queries[0]
    assert db.params[0]["name_like"] == "%x';DROP TABLE buildings;--%"


def test_list_passes_limit_and_offset():
    table = [_building(id=uuid.uuid4(), name=f"Building {n}") for n in range(5)]

    response, db = _get("/api/v1/campus/buildings?limit=2&offset=1", buildings=table)

    assert len(response.json()) == 2
    assert db.params[0]["limit"] == 2
    assert db.params[0]["offset"] == 1


def test_list_defaults_to_50_and_offset_0():
    _, db = _get("/api/v1/campus/buildings")

    assert db.params[0]["limit"] == 50
    assert db.params[0]["offset"] == 0


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=201", "offset=-1", "type=bogus"],
)
def test_bad_list_params_are_422_not_500(query):
    response, _ = _get(f"/api/v1/campus/buildings?{query}")

    assert response.status_code == 422


# ------------------------------------------------------ GET /campus/buildings/{id}


def test_detail_returns_one_in_contract_shape():
    response, _ = _get(f"/api/v1/campus/buildings/{BLDG_1}", buildings=[_building()])

    assert response.status_code == 200
    assert response.json()["id"] == str(BLDG_1)
    assert set(response.json()) == set(SCHEMAS["Building"]["properties"])


def test_detail_soft_deleted_is_404():
    response, _ = _get(f"/api/v1/campus/buildings/{BLDG_1}", buildings=[_building(deleted_at=NOW)])

    assert response.status_code == 404


def test_detail_unknown_id_returns_404_in_error_shape():
    response, _ = _get(f"/api/v1/campus/buildings/{MISSING_ID}", buildings=[_building()])

    assert response.status_code == 404
    assert response.json() == {"detail": "Building not found"}


def test_detail_bad_id_format_is_422_not_500():
    response, _ = _get("/api/v1/campus/buildings/not-a-uuid", buildings=[_building()])

    assert response.status_code == 422


# ----------------------------------------------------------------- caching


@pytest.mark.parametrize(
    "path",
    ["/api/v1/campus/buildings", f"/api/v1/campus/buildings/{BLDG_1}"],
)
def test_building_reads_use_public_cache(path):
    response, _ = _get(path, buildings=[_building()])

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == (
        "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
    )


# ------------------------------------------------------------------- route


def test_route_is_still_not_implemented():
    # Stays a stub until pgRouting and campus path data exist. Update this test when it is built.
    response = TestClient(app).get(
        "/api/v1/campus/route?from_lat=7.3&from_lng=5.14&to_building_id=" + str(BLDG_1)
    )

    assert response.status_code == 501
