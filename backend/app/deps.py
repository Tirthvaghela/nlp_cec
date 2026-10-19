"""Request dependencies: current user and role guards."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.database import Database

from app.db import get_db, oid
from app.errors import Forbidden, NotFound, Unauthorized
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def db_dep() -> Database:
    return get_db()


DB = Annotated[Database, Depends(db_dep)]


def current_user(db: DB, creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Not authenticated")
    decoded = decode_access_token(creds.credentials)
    if not decoded:
        raise Unauthorized("Invalid or expired token")
    user_id, session_version = decoded
    try:
        user = db.users.find_one({"_id": oid(user_id)})
    except NotFound:
        user = None
    if not user:
        raise Unauthorized("User no longer exists")
    if session_version != user.get("session_version", 0):
        # Revoked by a password change or "sign out everywhere" (security audit F5/V9).
        raise Unauthorized("This session has ended. Please sign in again.", code="session_revoked")
    return user


def require_teacher(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "teacher":
        raise Forbidden("Teacher access required")
    return user


def require_student(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "student":
        raise Forbidden("Student access required")
    return user


CurrentUser = Annotated[dict, Depends(current_user)]
Teacher = Annotated[dict, Depends(require_teacher)]
Student = Annotated[dict, Depends(require_student)]
