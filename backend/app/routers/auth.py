from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.config import get_settings
from app.db import now
from app.deps import DB, CurrentUser, Teacher
from app.errors import Conflict, Forbidden, TooManyRequests, Unauthorized
from app.ratelimit import (
    INVITE_GLOBAL_LIMIT, INVITE_GLOBAL_WINDOW, INVITE_IP_LIMIT, INVITE_IP_WINDOW, LOGIN_MAX_FAILURES, LOGIN_WINDOW,
    PWCHANGE_MAX_FAILURES, PWCHANGE_WINDOW, limiter,
)
from app.schemas.auth import (
    LoginIn, PasswordChange, ProfileUpdate, RegisterIn, SessionRenewedOut, StudentBrief, TokenOut, UserOut,
)
from app.schemas.common import Message
from app.security import create_access_token, hash_password, verify_password
from app.services.serializers import student_brief, user_out

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])

# Used to spend the same time on unknown e-mails as on wrong passwords.
_DUMMY_HASH = hash_password("timing-equaliser-123")


def _token_response(user: dict) -> dict:
    token, expires = create_access_token(str(user["_id"]), user.get("session_version", 0))
    return {"access_token": token, "token_type": "bearer", "expires_in": expires, "user": user_out(user)}


def client_ip(request: Request) -> str:
    # The address the ASGI server reports. The pilot launcher (scripts/run_server.py) turns uvicorn's proxy-header
    # rewriting OFF unless TRUSTED_PROXIES lists the real proxies, so X-Forwarded-For from anyone else is ignored (V1).
    return request.client.host if request.client else "unknown"


def _check_invite(body: RegisterIn, request: Request) -> None:
    """Wrong teacher invite codes are throttled per IP and globally; codes are never logged."""
    code = get_settings().teacher_invite_code
    if body.role != "teacher" or not code:
        return
    ip_key, global_key = f"invite-fail:ip:{client_ip(request)}", "invite-fail:global"
    # Atomic reservation on both counters (V3): parallel guesses cannot all pass the check before one is recorded.
    taken, wait = limiter.reserve_all([(ip_key, INVITE_IP_LIMIT, INVITE_IP_WINDOW),
                                       (global_key, INVITE_GLOBAL_LIMIT, INVITE_GLOBAL_WINDOW)])
    if taken is None:
        log.warning("Teacher registration throttled after repeated wrong invite codes")
        raise TooManyRequests("Too many attempts with a wrong teacher invite code. Try again later.", wait)
    if not body.invite_code or not hmac.compare_digest(body.invite_code.encode(), code.encode()):
        raise Forbidden("A valid teacher invite code is required to register as a teacher.", code="invite_required")
    for key, token in taken:  # correct code: the attempt does not count as a failure
        limiter.release(key, token)


def _pilot_enrollment(body: RegisterIn, db) -> dict | None:
    """In PILOT_MODE a student account can only be created for an e-mail a teacher has enrolled (security audit F2).
    Enrollment is an access control only: it is not evidence of consent or of ethics approval."""
    if body.role != "student" or not get_settings().pilot_mode:
        return None
    enrollment = db.enrollments.find_one({"email": body.email, "revoked_at": None})
    if not enrollment:
        raise Forbidden("Registration is limited to enrolled pilot participants. Ask your teacher to enroll this e-mail.",
                        code="enrollment_required")
    return enrollment


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, db: DB):
    _check_invite(body, request)
    enrollment = _pilot_enrollment(body, db)
    ts = now()
    user = {
        "name": body.name,
        "email": body.email,
        "password_hash": hash_password(body.password),
        "role": body.role,
        "created_at": ts,
        "updated_at": ts,
    }
    if enrollment:
        user["pilot_enrolled"] = True
    try:
        user["_id"] = db.users.insert_one(user).inserted_id
    except DuplicateKeyError:
        raise Conflict("An account with this email already exists.", code="email_taken") from None
    if enrollment:
        db.enrollments.update_one({"_id": enrollment["_id"]}, {"$set": {"user_id": user["_id"], "used_at": ts}})
        # Sprint 5 (A7): registration changes the enrollment too, so it is logged like enroll/revoke (actor = the
        # student who registered). Separate write, not atomic with the update above (enrollments.py docstring).
        db.enrollment_events.insert_one({"action": "registered", "email": body.email, "by": user["_id"], "at": ts})
    log.info("Registered %s account %s", body.role, user["_id"])
    return _token_response(user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DB):
    # Per-account cooldown: checked BEFORE the password, so guessing stops even when the next guess would be right.
    # The slot is reserved atomically BEFORE the slow bcrypt check (V3): at most LOGIN_MAX_FAILURES attempts per
    # account can be in flight or recorded per window, however many requests arrive in parallel.
    key = f"login-fail:{body.email}"
    token, wait = limiter.reserve(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW)
    if token is None:
        raise TooManyRequests("Too many failed sign-in attempts for this account. Try again later.", wait)
    user = db.users.find_one({"email": body.email})
    ok = verify_password(body.password, user["password_hash"] if user else _DUMMY_HASH)
    if not user or not ok:
        # the reservation stays: it is the recorded failure (unknown e-mails count too - no account enumeration)
        raise Unauthorized("Incorrect email or password.", code="invalid_credentials")
    limiter.clear(key)
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user_out(user)


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: CurrentUser, db: DB):
    db.users.update_one({"_id": user["_id"]}, {"$set": {"name": body.name, "updated_at": now()}})
    return user_out(db.users.find_one({"_id": user["_id"]}))


def _revoke_sessions(db, user: dict) -> tuple[str, int]:
    """Increment the session version (revokes every existing token) and issue one for the current device."""
    new = db.users.find_one_and_update({"_id": user["_id"]}, {"$inc": {"session_version": 1}, "$set": {"updated_at": now()}},
                                       return_document=ReturnDocument.AFTER)
    return create_access_token(str(user["_id"]), new["session_version"])


@router.post("/logout-all", response_model=SessionRenewedOut)
def logout_all(user: CurrentUser, db: DB):
    """Sign out every other device (for example after a lost laptop): all earlier tokens stop working."""
    token, expires = _revoke_sessions(db, user)
    return {"detail": "All other sessions were signed out.", "access_token": token, "expires_in": expires}


@router.post("/change-password", response_model=SessionRenewedOut)
def change_password(body: PasswordChange, user: CurrentUser, db: DB):
    # V5: someone holding a stolen token must not be able to guess the current password without limit.
    key = f"pwchange-fail:{user['_id']}"
    token, wait = limiter.reserve(key, PWCHANGE_MAX_FAILURES, PWCHANGE_WINDOW)
    if token is None:
        raise TooManyRequests("Too many failed password-change attempts. Try again later.", wait)
    if not verify_password(body.current_password, user["password_hash"]):
        raise Forbidden("Current password is incorrect.", code="wrong_password")  # reservation kept = failure
    limiter.clear(key)
    if body.current_password == body.new_password:
        raise Conflict("The new password must be different from the current one.")
    db.users.update_one({"_id": user["_id"]},
                        {"$set": {"password_hash": hash_password(body.new_password), "updated_at": now()}})
    # F5/V9: a password change revokes every existing session (including any stolen token); this device continues
    # with the fresh token returned here.
    token, expires = _revoke_sessions(db, user)
    return {"detail": "Password updated. Other sessions were signed out.", "access_token": token, "expires_in": expires}


@users_router.get("/students", response_model=list[StudentBrief])
def list_students(_: Teacher, db: DB):
    """Registered students (name and e-mail only) so a teacher can assign assessments.

    V11 least privilege: in PILOT_MODE only actively enrolled participants are listed - nobody else can take part, so
    no teacher needs their e-mail. Restricting further (per teacher/class) needs an assignment model that does not
    exist yet (decision register, PILOT_READINESS.md)."""
    query: dict = {"role": "student"}
    if get_settings().pilot_mode:
        query["pilot_enrolled"] = True
    return [student_brief(u) for u in db.users.find(query, {"name": 1, "email": 1}).sort("name", 1)]
