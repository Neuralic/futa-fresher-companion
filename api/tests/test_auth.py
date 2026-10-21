"""Register, login and me, with a fake DB connection (no Postgres needed).

Argon2 runs for real here, so each test that hashes takes a fraction of a second.
"""

import base64
import json
import logging
import pathlib
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import yaml
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from psycopg import errors

from app import security
from app.config import settings
from app.db import get_conn
from app.main import app
from app.routers import auth as auth_router
from app.security import create_access_token, dummy_hash, hash_password, verify_password
from tests.fakedb import FakeCursor

SPEC_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
USER_PROPERTIES = set(SPEC["components"]["schemas"]["User"]["properties"])
PASSWORD = "correct horse battery"
WEBSITE = "http://localhost:5173"


class AuthFakeDb:
    """Applies the auth SQL rules: unique email (lower) and matric, departments, hash update."""

    def __init__(self, users=(), departments=()):
        self.users = list(users)
        self.departments = set(departments)
        self.queries = []

    def execute(self, sql, params=None):
        params = params or {}
        self.queries.append(sql)
        text = sql.lstrip()
        if text.startswith("INSERT INTO users"):
            return self._insert(params)
        if text.startswith("UPDATE users"):
            for user in self.users:
                if user["id"] == params["id"]:
                    user["password_hash"] = params["password_hash"]
            return FakeCursor([])
        if "FROM departments" in sql:
            return FakeCursor([{"?column?": 1}] if params["id"] in self.departments else [])
        if "lower(email)" in sql:
            matches = [u for u in self.users if u["email"] == params["email"]]
        else:
            matches = [u for u in self.users if u["id"] == params["id"]]
        return FakeCursor([_row(u, with_hash="password_hash" in sql) for u in matches[:1]])

    def _insert(self, params):
        if any(u["email"] == params["email"] for u in self.users):
            raise errors.UniqueViolation("duplicate key value violates unique constraint")
        matric = params["matric_no"]
        if matric is not None and any(u["matric_no"] == matric for u in self.users):
            raise errors.UniqueViolation("duplicate key value violates unique constraint")
        user = {
            "id": uuid.uuid4(),
            "full_name": params["full_name"],
            "email": params["email"],
            "password_hash": params["password_hash"],
            "matric_no": matric,
            "role": "student",
            "department_id": params["department_id"],
            "faculty_id": None,
            "level": params["level"],
            "is_active": True,
        }
        self.users.append(user)
        return FakeCursor([_row(user, with_hash=False)])


def _row(user, with_hash):
    row = {k: v for k, v in user.items() if k != "password_hash" or with_hash}
    return dict(row)


def make_user(email="ada@example.com", password=PASSWORD, **fields):
    user = {
        "id": uuid.uuid4(),
        "full_name": "Ada Obi",
        "email": email,
        "password_hash": hash_password(password),
        "matric_no": None,
        "role": "student",
        "department_id": None,
        "faculty_id": None,
        "level": None,
        "is_active": True,
    }
    user.update(fields)
    return user


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client(db):
    app.dependency_overrides[get_conn] = lambda: db
    return TestClient(app)


def _register(db, **body):
    payload = {"full_name": "Ada Obi", "email": "ada@example.com", "password": PASSWORD}
    payload.update(body)
    return _client(db).post("/api/v1/auth/register", json=payload)


def _login(db, email="ada@example.com", password=PASSWORD):
    return _client(db).post("/api/v1/auth/login", json={"email": email, "password": password})


def _me(db, token=None, headers=None):
    headers = dict(headers or {})
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return _client(db).get("/api/v1/auth/me", headers=headers)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


# ------------------------------------------------------------------ register


def test_register_stores_an_argon2_hash_never_the_password():
    db = AuthFakeDb()

    response = _register(db)

    stored = db.users[0]["password_hash"]
    assert response.status_code == 201
    assert stored.startswith("$argon2id$")
    assert stored != PASSWORD
    assert verify_password(stored, PASSWORD)
    assert PASSWORD not in response.text


def test_register_ignores_role_and_scope_in_the_body():
    db = AuthFakeDb()

    response = _register(db, role="super_admin", is_active=False, faculty_id=str(uuid.uuid4()))

    assert response.status_code == 201
    assert response.json()["role"] == "student"
    assert db.users[0]["role"] == "student"
    assert db.users[0]["is_active"] is True
    assert db.users[0]["faculty_id"] is None


def test_register_returns_the_user_shape_and_nothing_else():
    db = AuthFakeDb()

    body = _register(db).json()

    assert set(body) == USER_PROPERTIES
    assert "password_hash" not in body and "password" not in body


def test_email_is_trimmed_and_lowercased():
    db = AuthFakeDb()

    _register(db, email="  Ada@Example.COM ")

    assert db.users[0]["email"] == "ada@example.com"


def test_duplicate_email_in_another_case_is_409():
    db = AuthFakeDb()
    _register(db, email="ada@example.com")

    response = _register(db, email="ADA@example.com")

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_duplicate_matric_number_is_409():
    db = AuthFakeDb()
    _register(db, email="a@example.com", matric_no="FUTA/2026/001")

    response = _register(db, email="b@example.com", matric_no="FUTA/2026/001")

    assert response.status_code == 409


def test_blank_matric_number_is_stored_as_none():
    db = AuthFakeDb()

    _register(db, matric_no="   ")

    assert db.users[0]["matric_no"] is None


@pytest.mark.parametrize("password", ["Sh0rt", "x" * 129])
def test_password_outside_8_to_128_characters_is_422(password):
    db = AuthFakeDb()

    response = _register(db, password=password)

    assert response.status_code == 422
    assert password not in response.text
    assert db.users == []


def test_password_of_exactly_8_and_128_characters_is_accepted():
    db = AuthFakeDb()

    assert _register(db, email="a@example.com", password="a" * 8).status_code == 201
    assert _register(db, email="b@example.com", password="b" * 128).status_code == 201


@pytest.mark.parametrize("email", ["not-an-email", "a@b", " "])
def test_bad_email_is_422(email):
    response = _register(AuthFakeDb(), email=email)

    assert response.status_code == 422


def test_unknown_department_is_422():
    response = _register(AuthFakeDb(), department_id=str(uuid.uuid4()))

    assert response.status_code == 422


def test_register_422_body_does_not_echo_the_password_or_email():
    response = _register(
        AuthFakeDb(), password="Sh0rt", email="secret.person@example.com", full_name="A"
    )

    assert response.status_code == 422
    assert "Sh0rt" not in response.text
    assert "secret.person@example.com" not in response.text


# ------------------------------------------------------------------ login


def test_login_returns_a_bearer_token_and_its_lifetime():
    db = AuthFakeDb([make_user()])

    response = _login(db)

    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.jwt_expires_minutes * 60
    claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == str(db.users[0]["id"])
    assert "role" not in claims and "scope" not in claims


def test_wrong_password_unknown_email_and_inactive_account_give_identical_401s():
    db = AuthFakeDb([make_user(), make_user("off@example.com", is_active=False)])

    wrong = _login(db, password="not the password")
    unknown = _login(db, email="nobody@example.com")
    inactive = _login(db, email="off@example.com")

    assert wrong.status_code == unknown.status_code == inactive.status_code == 401
    assert (
        wrong.json() == unknown.json() == inactive.json() == {"detail": "Invalid email or password"}
    )


def test_login_email_is_normalised_like_registration():
    db = AuthFakeDb([make_user()])

    assert _login(db, email="  ADA@example.com ").status_code == 200


def test_unknown_email_is_still_checked_against_the_dummy_hash(monkeypatch):
    seen = []
    real = auth_router.verify_password

    def spy(stored_hash, password):
        seen.append(stored_hash)
        return real(stored_hash, password)

    monkeypatch.setattr(auth_router, "verify_password", spy)

    response = _login(AuthFakeDb(), email="nobody@example.com")

    assert response.status_code == 401
    assert seen == [dummy_hash()]


def test_known_email_is_checked_against_its_own_hash(monkeypatch):
    seen = []
    real = auth_router.verify_password
    monkeypatch.setattr(
        auth_router,
        "verify_password",
        lambda stored, password: seen.append(stored) or real(stored, password),
    )
    user = make_user()

    _login(AuthFakeDb([user]))

    assert seen == [user["password_hash"]]


def test_login_upgrades_an_old_hash_when_parameters_have_changed():
    old_hasher = PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    user = make_user(password_hash=old_hasher.hash(PASSWORD))
    old = user["password_hash"]
    db = AuthFakeDb([user])

    assert _login(db).status_code == 200

    upgraded = db.users[0]["password_hash"]
    assert upgraded != old
    assert not security.needs_rehash(upgraded)
    assert verify_password(upgraded, PASSWORD)


def test_failed_login_does_not_rehash():
    old_hasher = PasswordHasher(time_cost=1, memory_cost=8 * 1024, parallelism=1)
    stored = old_hasher.hash(PASSWORD)
    db = AuthFakeDb([make_user(password_hash=stored)])

    _login(db, password="wrong")

    assert db.users[0]["password_hash"] == stored
    assert not any(q.lstrip().startswith("UPDATE users") for q in db.queries)


def test_failed_login_logs_neither_password_nor_email(caplog):
    caplog.set_level(logging.DEBUG)

    _login(AuthFakeDb([make_user()]), email="ada@example.com", password="wrong-password-123")

    assert "wrong-password-123" not in caplog.text
    assert "ada@example.com" not in caplog.text


# ------------------------------------------------------------------ me and tokens


def test_me_with_a_valid_token_returns_the_user_shape():
    user = make_user(matric_no="FUTA/1")
    db = AuthFakeDb([user])

    response = _me(db, create_access_token(str(user["id"])))

    assert response.status_code == 200
    assert set(response.json()) == USER_PROPERTIES
    assert "password_hash" not in response.text


def test_role_comes_from_the_database_not_the_token():
    user = make_user()
    db = AuthFakeDb([user])
    token = create_access_token(str(user["id"]))
    assert jwt.decode(token, settings.jwt_secret, algorithms=["HS256"]).get("role") is None

    user["role"] = "department_admin"

    assert _me(db, token).json()["role"] == "department_admin"


def test_deactivating_a_user_locks_out_their_existing_token():
    user = make_user()
    db = AuthFakeDb([user])
    token = create_access_token(str(user["id"]))
    assert _me(db, token).status_code == 200

    user["is_active"] = False

    response = _me(db, token)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_expired_token_is_401():
    user = make_user()
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(user["id"]), "iat": past - timedelta(minutes=5), "exp": past},
        settings.jwt_secret,
        algorithm="HS256",
    )

    response = _me(AuthFakeDb([user]), token)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_tampered_signature_is_401():
    user = make_user()
    token = create_access_token(str(user["id"]))
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")

    assert _me(AuthFakeDb([user]), tampered).status_code == 401


def test_token_signed_with_another_secret_is_401():
    user = make_user()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": str(user["id"]), "iat": now, "exp": now + timedelta(minutes=5)},
        "not-the-real-secret",
        algorithm="HS256",
    )

    assert _me(AuthFakeDb([user]), token).status_code == 401


def test_alg_none_token_is_401():
    user = make_user()
    now = int(datetime.now(timezone.utc).timestamp())
    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"sub": str(user["id"]), "iat": now, "exp": now + 300}).encode())
    token = f"{header}.{payload}."

    response = _me(AuthFakeDb([user]), token)

    assert response.status_code == 401


def test_token_missing_required_claims_is_401():
    user = make_user()
    now = datetime.now(timezone.utc)
    no_exp = jwt.encode(
        {"sub": str(user["id"]), "iat": now}, settings.jwt_secret, algorithm="HS256"
    )

    assert _me(AuthFakeDb([user]), no_exp).status_code == 401


def test_token_for_an_unknown_user_is_401():
    token = create_access_token(str(uuid.uuid4()))

    assert _me(AuthFakeDb([make_user()]), token).status_code == 401


def test_token_with_a_malformed_subject_is_401_not_500():
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": "not-a-uuid", "iat": now, "exp": now + timedelta(minutes=5)},
        settings.jwt_secret,
        algorithm="HS256",
    )

    assert _me(AuthFakeDb([make_user()]), token).status_code == 401


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}],
    ids=["missing", "wrong scheme", "empty token"],
)
def test_missing_or_wrong_authorization_is_401(headers):
    response = _me(AuthFakeDb([make_user()]), headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


# ------------------------------------------------------------------ headers and CORS


def test_every_auth_response_is_no_store():
    db = AuthFakeDb([make_user()])
    token = create_access_token(str(db.users[0]["id"]))
    responses = [
        _register(db, email="new@example.com"),
        _login(db),
        _login(db, password="wrong"),
        _me(db, token),
        _me(db),
        _register(db, password="short"),
    ]

    assert [r.headers.get("cache-control") for r in responses] == ["no-store"] * len(responses)


def test_website_origin_may_send_the_authorization_header():
    response = TestClient(app).options(
        "/api/v1/auth/me",
        headers={
            "Origin": WEBSITE,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.headers.get("access-control-allow-origin") == WEBSITE
    assert "authorization" in response.headers.get("access-control-allow-headers", "").lower()


def test_password_hash_never_appears_in_any_response():
    user = make_user()
    db = AuthFakeDb([user])
    token = create_access_token(str(user["id"]))
    bodies = [
        _register(db, email="new@example.com").text,
        _login(db).text,
        _me(db, token).text,
    ]

    for body in bodies:
        assert "password_hash" not in body
        assert "$argon2" not in body
        assert user["password_hash"] not in body


@pytest.mark.parametrize(
    "fields",
    [{"matric_no": "M" * 41}, {"level": 99}, {"level": 701}],
    ids=["matric too long", "level below 100", "level above 700"],
)
def test_bad_matric_or_level_is_422(fields):
    db = AuthFakeDb()

    assert _register(db, **fields).status_code == 422
    assert db.users == []


def test_null_level_and_matric_are_accepted():
    db = AuthFakeDb()

    response = _register(db, matric_no=None, level=None)

    assert response.status_code == 201
    assert response.json()["level"] is None
