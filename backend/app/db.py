"""MongoDB connection and index management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from app.config import get_settings
from app.errors import NotFound

log = logging.getLogger(__name__)

_client: MongoClient | None = None
_db: Database | None = None


def get_db() -> Database:
    global _client, _db
    if _db is None:
        s = get_settings()
        _client = MongoClient(s.mongodb_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
        _db = _client[s.mongodb_db]
    return _db


def set_db(db: Database | None) -> None:
    """Override the database (tests)."""
    global _db
    _db = db


def ensure_indexes(db: Database) -> None:
    db.users.create_index([("email", ASCENDING)], unique=True, name="uniq_email")
    db.assessments.create_index([("teacher_id", ASCENDING), ("created_at", DESCENDING)], name="by_teacher")
    db.assessments.create_index([("status", ASCENDING)], name="by_status")
    db.questions.create_index([("assessment_id", ASCENDING), ("order", ASCENDING)], name="by_assessment_order")
    # One submission per student per assessment (drafts are updated in place).
    db.submissions.create_index([("assessment_id", ASCENDING), ("student_id", ASCENDING)], unique=True,
                                name="uniq_student_assessment")
    db.submissions.create_index([("student_id", ASCENDING), ("updated_at", DESCENDING)], name="by_student")
    # One *current* evaluation per answer; older versions live in evaluation_history.
    db.evaluations.create_index([("submission_id", ASCENDING), ("question_id", ASCENDING)], unique=True,
                                name="uniq_submission_question")
    db.evaluations.create_index([("assessment_id", ASCENDING)], name="by_assessment")
    db.evaluation_history.create_index([("submission_id", ASCENDING), ("question_id", ASCENDING), ("version", ASCENDING)],
                                       name="history_lookup")
    db.enrollments.create_index([("email", ASCENDING)], unique=True, name="uniq_enrollment_email")


def now() -> datetime:
    return datetime.now(timezone.utc)


def oid(value: str | ObjectId, what: str = "Resource") -> ObjectId:
    """Parse an ObjectId from a path parameter; invalid ids are reported as not found."""
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise NotFound(f"{what} not found") from None


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
