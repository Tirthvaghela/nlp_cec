"""Ownership and visibility checks shared by the routers.

Every lookup is scoped to the current user so that ids belonging to someone else
behave exactly like ids that do not exist (404, not 403) - this avoids leaking
which records exist.
"""

from __future__ import annotations

from bson import ObjectId
from pymongo.database import Database

from app.config import get_settings
from app.db import now, oid
from app.errors import NotFound


def owned_assessment(db: Database, teacher: dict, assessment_id: str | ObjectId) -> dict:
    doc = db.assessments.find_one({"_id": oid(assessment_id, "Assessment"), "teacher_id": teacher["_id"]})
    if not doc:
        raise NotFound("Assessment not found")
    return doc


def owned_question(db: Database, teacher: dict, question_id: str | ObjectId) -> tuple[dict, dict]:
    q = db.questions.find_one({"_id": oid(question_id, "Question")})
    if not q:
        raise NotFound("Question not found")
    a = db.assessments.find_one({"_id": q["assessment_id"], "teacher_id": teacher["_id"]})
    if not a:
        raise NotFound("Question not found")
    return q, a


def pilot_access_ok(db: Database, student: dict) -> bool:
    """PILOT_MODE (security audit F2, sprint 7 / S6-1): a student may use assessments only while BOTH the account's
    ``pilot_enrolled`` flag is true AND an active enrollment for the account's e-mail exists (not revoked and, if it
    is linked to an account, linked to this one). Either record alone is not enough, so a revocation that stopped
    half-way, or a missing or inconsistent record, fails closed. Outside PILOT_MODE nothing changes."""
    if not get_settings().pilot_mode:
        return True
    if student.get("pilot_enrolled") is not True:
        return False
    enrollment = db.enrollments.find_one({"email": student.get("email"), "revoked_at": None}, {"user_id": 1})
    return enrollment is not None and enrollment.get("user_id") in (None, student["_id"])


def student_can_see(assessment: dict, student: dict, *, pilot_ok: bool) -> bool:
    """``pilot_ok`` is ``pilot_access_ok(db, student)``, computed once per request by the caller. Every student
    assessment path (list, detail, draft, submit) goes through this function."""
    if assessment.get("status") not in ("published", "closed"):
        return False
    if not pilot_ok:
        return False
    assigned = assessment.get("assigned_student_ids") or []
    return not assigned or student["_id"] in assigned


def visible_assessment(db: Database, student: dict, assessment_id: str | ObjectId) -> dict:
    a = db.assessments.find_one({"_id": oid(assessment_id, "Assessment")})
    if not a or not student_can_see(a, student, pilot_ok=pilot_access_ok(db, student)):
        raise NotFound("Assessment not found")
    return a


def teacher_submission(db: Database, teacher: dict, submission_id: str | ObjectId) -> tuple[dict, dict]:
    sub = db.submissions.find_one({"_id": oid(submission_id, "Submission")})
    if not sub:
        raise NotFound("Submission not found")
    a = db.assessments.find_one({"_id": sub["assessment_id"], "teacher_id": teacher["_id"]})
    if not a:
        raise NotFound("Submission not found")
    return sub, a


def deadline_passed(assessment: dict) -> bool:
    dl = assessment.get("deadline")
    if dl is None:
        return False
    if dl.tzinfo is None:
        from datetime import timezone

        dl = dl.replace(tzinfo=timezone.utc)
    return now() > dl


def assessment_questions(db: Database, assessment_id: ObjectId) -> list[dict]:
    return list(db.questions.find({"assessment_id": assessment_id}).sort([("order", 1), ("created_at", 1)]))
