"""Pilot enrollment allowlist (security audit F2). Teachers only.

In PILOT_MODE a student can register only with an enrolled e-mail, and can see or submit to assessments only while
the enrollment is active. Revoking an enrollment immediately removes the student's access to assessments (their own
already-published results stay visible to them).

An enrollment is an ACCESS CONTROL. It is not evidence of informed consent or of ethics approval: those are recorded
and verified outside the application (docs/REAL_STUDENT_EVALUATION_PROTOCOL.md).

Audit history (V6, corrected in sprint 5 / A7): the ``enrollments`` document holds the CURRENT state and is mutable
(re-enrolling overwrites ``enrolled_by`` and clears ``revoked_at``). The API appends an event to ``enrollment_events``
(action, e-mail, actor, time) for each change it makes: "enrolled", "revoked" and - since sprint 5 - "registered"
(routers/auth.py). Limits:
* nothing here is one transaction (MongoDB transactions need a replica set, and the pilot's database topology is not
  decided). Each change is THREE separate writes: the ``enrollments`` document, the student's ``users.pilot_enrolled``
  flag and the event. Events are written last, so an event is never written for a change that did not happen; a
  failure at any step fails the request with a server error.
  Sprint 7 (fix for sprint 6 finding S6-1): assessment access needs BOTH the flag and an active enrollment
  (services/access.py ``pilot_access_ok``), and ``revoke`` clears the flag first and can be repeated to finish an
  interrupted revocation (see ``revoke``). So no partial failure of enroll, register or revoke can grant access that
  the list does not show. A partial failure can still leave the list showing a participant as active whose access is
  already gone (fail closed) until the revoke is repeated;
* the application only inserts events, but nothing stops someone with direct database access from editing or deleting
  them: the log is not tamper-proof;
* events made before the log existed (and registrations before sprint 5) do not exist and are not back-filled.
Policy questions - global vs per-study enrollment, who may manage it, what withdrawal means for existing
submissions - are faculty decisions and are NOT decided here (PILOT_READINESS.md, decision register).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from pydantic import EmailStr, Field, field_validator

from app.db import now
from app.deps import DB, Teacher
from app.errors import Conflict, NotFound
from app.schemas.common import ApiModel, Message

router = APIRouter(prefix="/api/enrollments", tags=["enrollments"])


class EnrollmentIn(ApiModel):
    emails: Annotated[list[EmailStr], Field(min_length=1, max_length=500)]

    @field_validator("emails")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return sorted({e.strip().lower() for e in v})


@router.post("", response_model=Message, status_code=201)
def enroll(body: EnrollmentIn, teacher: Teacher, db: DB):
    ts = now()
    for email in body.emails:
        db.enrollments.update_one(
            {"email": email},
            {"$set": {"revoked_at": None, "updated_at": ts, "enrolled_by": teacher["_id"]},
             "$setOnInsert": {"email": email, "created_at": ts}},
            upsert=True,
        )
        # Re-enrolling an existing account restores its access.
        db.users.update_one({"email": email, "role": "student"}, {"$set": {"pilot_enrolled": True}})
        db.enrollment_events.insert_one({"action": "enrolled", "email": email, "by": teacher["_id"], "at": ts})
    return {"detail": f"{len(body.emails)} e-mail(s) enrolled."}


@router.get("")
def list_enrollments(_: Teacher, db: DB):
    return [{"email": e["email"], "active": e.get("revoked_at") is None, "registered": e.get("user_id") is not None}
            for e in db.enrollments.find().sort("email", 1)]


@router.delete("/{email}", response_model=Message)
def revoke(email: str, teacher: Teacher, db: DB):
    """Withdraw access (sprint 7, S6-1). Ordered so that every partial failure fails CLOSED, and idempotent so that
    repeating the request finishes an interrupted revocation:
    1. the account's access flag is cleared FIRST (access also needs an active enrollment, services/access.py);
    2. the enrollment is marked revoked (``revoked_at`` = this revocation's time);
    3. the "revoked" event is written with that same time, unless one already exists for this revocation.
    A failure at any step returns a server error; access is already gone once step 1 succeeded. Repeating the DELETE
    redoes step 1 and completes whatever is missing, without duplicating the event. 404 only for an e-mail that was
    never enrolled."""
    email = email.strip().lower()
    if not db.enrollments.find_one({"email": email}, {"_id": 1}):
        raise NotFound("No enrollment for this e-mail")
    db.users.update_one({"email": email, "role": "student"}, {"$set": {"pilot_enrolled": False}})  # 1. access off
    ts = now()
    r = db.enrollments.update_one({"email": email, "revoked_at": None},
                                  {"$set": {"revoked_at": ts, "revoked_by": teacher["_id"]}})  # 2.
    if r.modified_count:
        db.enrollment_events.insert_one({"action": "revoked", "email": email, "by": teacher["_id"], "at": ts})  # 3.
        return {"detail": "Enrollment revoked; the student can no longer open or submit assessments."}
    # Already revoked, possibly by an earlier request that failed before writing its event: complete it.
    enrollment = db.enrollments.find_one({"email": email})
    revoked_at = enrollment.get("revoked_at")
    if revoked_at is None:  # re-enrolled concurrently: do not touch the new enrollment's state
        raise Conflict("The enrollment was changed by another request; check the list and try again.",
                       code="enrollment_changed")
    if not db.enrollment_events.find_one({"action": "revoked", "email": email, "at": {"$gte": revoked_at}}):
        db.enrollment_events.insert_one({"action": "revoked", "email": email, "by": enrollment.get("revoked_by"),
                                         "at": revoked_at, "completed_by": teacher["_id"], "completed_at": now()})
        return {"detail": "An interrupted revocation was completed; the student can no longer open or submit "
                          "assessments."}
    return {"detail": "This enrollment was already revoked; the student's access remains removed."}
