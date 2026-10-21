"""Password hashing and access tokens. No request or database code here."""

import functools
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import settings

# HS256 only. The decoder pins this, so a token cannot choose its own algorithm.
ALGORITHM = "HS256"
# Memory 19 MiB and time cost 2, as set for a small serverless instance. Measure on the target.
_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


@functools.cache
def dummy_hash() -> str:
    """Checked when the email is unknown, so an unknown email takes about as long as a known one."""
    return _hasher.hash("futa-dummy-password-that-matches-nothing")


def create_access_token(user_id: str) -> str:
    # The role and scopes are not in the token. Each request reads them from the database.
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Return the claims of a valid, unexpired HS256 token. Raises InvalidTokenError otherwise."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
        options={"require": ["exp", "iat", "sub"]},
    )
