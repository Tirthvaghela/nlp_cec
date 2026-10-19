"""Password hashing (bcrypt) and JWT access tokens."""

from __future__ import annotations

from datetime import timedelta

import bcrypt
import jwt

from app.config import get_settings
from app.db import now

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; passwords are capped at 72 bytes by validation.
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, session_version: int = 0) -> tuple[str, int]:
    """``sv`` is the user's session version at issue time (security audit F5/V9). Incrementing the stored version
    (password change, "sign out everywhere") revokes every token issued before - checked on every request."""
    s = get_settings()
    issued = now()
    payload = {"sub": user_id, "sv": int(session_version), "iat": issued,
               "exp": issued + timedelta(minutes=s.jwt_expire_minutes), "type": "access"}
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM), s.jwt_expire_minutes * 60


def decode_access_token(token: str) -> tuple[str, int] | None:
    """Return (user id, session version) from a valid token, else None. The role is *not* taken from
    the token: it is always re-read from the database on every request. Tokens issued before session versions
    existed carry no ``sv`` and count as version 0 (they stay valid until the first revocation event)."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access" or not payload.get("sub"):
        return None
    sv = payload.get("sv", 0)
    if not isinstance(sv, int) or isinstance(sv, bool):
        return None
    return payload["sub"], sv
