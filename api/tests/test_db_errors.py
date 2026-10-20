"""Database trouble becomes a clean 503 with no internal details in the body."""

import logging

import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

from app.db import get_conn
from app.main import app

# What a real failure might say: host names and SQL must never reach the client.
LEAKY_MESSAGE = "could not connect to host db.internal.futa.local port 5432: SELECT * FROM users"


class FailingConn:
    def __init__(self, error):
        self.error = error

    def execute(self, sql, params=None):
        raise self.error


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "error",
    [PoolTimeout("couldn't get a connection after 5.00 sec"), OperationalError(LEAKY_MESSAGE)],
)
def test_database_failure_returns_503_without_internal_details(error, caplog):
    conn = FailingConn(error)
    app.dependency_overrides[get_conn] = lambda: conn

    with caplog.at_level(logging.ERROR, logger="app.main"):
        response = TestClient(app).get("/api/v1/faculties")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json() == {"detail": "Service temporarily unavailable"}
    assert "db.internal" not in response.text
    assert "SELECT" not in response.text
    # The real error is still logged server-side.
    assert any(record.exc_info and record.exc_info[1] is error for record in caplog.records)


def test_health_still_ok_when_database_is_down():
    app.dependency_overrides[get_conn] = lambda: FailingConn(PoolTimeout("down"))

    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
