"""User & Auth service. Owner: Backend."""

import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from psycopg import errors
from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, field_validator

from app.auth_deps import DbConn, get_current_user
from app.config import settings
from app.security import (
    create_access_token,
    dummy_hash,
    hash_password,
    needs_rehash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]
# Shape-only check. Full RFC email validation needs a package we have not approved.
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _blank_to_none(value: Any) -> Any:
    value = _strip(value)
    return None if value == "" else value


def _normalize_email(value: str) -> str:
    email = value.lower()
    if len(email) > 254 or not _EMAIL.fullmatch(email):
        raise ValueError("Enter a valid email address")
    return email


Email = Annotated[str, BeforeValidator(_strip), AfterValidator(_normalize_email)]


class RegisterRequest(BaseModel):
    # Extra fields (role, is_active, faculty_id...) are ignored. They are never read.
    full_name: Annotated[str, BeforeValidator(_strip), Field(min_length=2, max_length=120)]
    email: Email
    password: Annotated[str, Field(min_length=8, max_length=128)]
    # A label only. It is never checked against anything and proves nothing.
    matric_no: Annotated[str | None, BeforeValidator(_blank_to_none)] = None
    department_id: uuid.UUID | None = None
    level: Annotated[int, Field(ge=100, le=700)] | None = None

    @field_validator("matric_no")
    @classmethod
    def _matric_length(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 40:
            raise ValueError("matric_no is longer than 40 characters")
        return value


class LoginRequest(BaseModel):
    email: Email
    password: Annotated[str, Field(max_length=128)]


INSERT_USER = """
    INSERT INTO users (full_name, email, password_hash, matric_no, role, department_id, level)
    VALUES (%(full_name)s, %(email)s, %(password_hash)s, %(matric_no)s, 'student',
            %(department_id)s, %(level)s)
    RETURNING id, full_name, email, role, matric_no, department_id, faculty_id, level
    """
USER_BY_EMAIL = """
    SELECT id, full_name, email, role, matric_no, department_id, faculty_id, level,
           is_active, password_hash
    FROM users
    WHERE lower(email) = %(email)s
    LIMIT 1
    """
UPDATE_PASSWORD_HASH = "UPDATE users SET password_hash = %(password_hash)s WHERE id = %(id)s"
DEPARTMENT_EXISTS = "SELECT 1 FROM departments WHERE id = %(id)s AND deleted_at IS NULL"


@router.post("/register", status_code=201)
def register(body: RegisterRequest, conn: DbConn):
    if body.department_id is not None:
        exists = conn.execute(DEPARTMENT_EXISTS, {"id": body.department_id}).fetchone()
        if exists is None:
            raise HTTPException(status_code=422, detail="Unknown department")
    params = {
        "full_name": body.full_name,
        "email": body.email,
        "password_hash": hash_password(body.password),
        "matric_no": body.matric_no,
        "department_id": body.department_id,
        "level": body.level,
    }
    try:
        row = conn.execute(INSERT_USER, params).fetchone()
    except errors.UniqueViolation as error:
        # Does not say which one matched, so the response reveals less about existing accounts.
        raise HTTPException(
            status_code=409,
            detail="An account with this email or matric number already exists",
        ) from error
    return _user(row)


@router.post("/login")
def login(body: LoginRequest, conn: DbConn):
    user = conn.execute(USER_BY_EMAIL, {"email": body.email}).fetchone()
    # An unknown email is still checked against a hash, so response time does not reveal it.
    stored_hash = user["password_hash"] if user else dummy_hash()
    password_ok = verify_password(stored_hash, body.password)
    if user is None or not user["is_active"] or not password_ok:
        # One message for unknown email, wrong password and inactive account.
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if needs_rehash(user["password_hash"]):
        conn.execute(
            UPDATE_PASSWORD_HASH,
            {"id": user["id"], "password_hash": hash_password(body.password)},
        )
    return {
        "access_token": create_access_token(str(user["id"])),
        "token_type": "bearer",
        "expires_in": settings.jwt_expires_minutes * 60,
    }


@router.get("/me")
def me(user: CurrentUser):
    return _user(user)


def _user(row: dict[str, Any]) -> dict[str, Any]:
    # Shape follows the User schema in docs/openapi.yaml. Nothing else leaves this function.
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "role": row["role"],
        "matric_no": row["matric_no"],
        "department_id": row["department_id"],
        "faculty_id": row["faculty_id"],
        "level": row["level"],
    }
