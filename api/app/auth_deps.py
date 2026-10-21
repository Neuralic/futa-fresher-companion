"""Who is calling. Reusable by any route that needs a signed-in user (admin routes too)."""

import uuid
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request
from psycopg import Connection

from app.db import get_conn
from app.security import decode_access_token

DbConn = Annotated[Connection, Depends(get_conn)]

# Read on every request, so a role change or deactivation applies at once.
USER_BY_ID = """
    SELECT id, full_name, email, role, matric_no, department_id, faculty_id, level, is_active
    FROM users
    WHERE id = %(id)s
    """


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(request: Request, conn: DbConn) -> dict[str, Any]:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Not authenticated")

    try:
        claims = decode_access_token(token)
        user_id = uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        # The same message for expired, tampered, wrong-algorithm and malformed tokens.
        raise _unauthorized("Invalid or expired token") from error

    user = conn.execute(USER_BY_ID, {"id": user_id}).fetchone()
    if user is None or not user["is_active"]:
        raise _unauthorized("Invalid or expired token")
    return user
