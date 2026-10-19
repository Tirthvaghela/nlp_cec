from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.db import now, oid
from app.deps import DB, CurrentUser, Student, Teacher
from app.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.schemas.common import Page
from app.schemas.evaluation import SubmissionReview
from app.schemas.submission import StudentSubmissionItem, SubmissionIn, SubmissionOut, TeacherSubmissionItem
from app.services.access import assessment_questions, deadline_passed, owned_assessment, teacher_submission, visible_assessment
from app.services.evaluation_service import totals
from app.services.review import submission_review
from app.services.serializers import student_brief

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


def _submission_out(s: dict) -> dict:
    return {
        "id": str(s["_id"]),
        "assessment_id": str(s["assessment_id"]),
        "status": s["status"],
        "answers": s.get("answers", []),
        "created_at": s["created_at"],
        "updated_at": s["updated_at"],
        "submitted_at": s.get("submitted_at"),
        "published_at": s.get("published_at"),
    }


def _check_open(db, student: dict, assessment_id: str) -> tuple[dict, list[dict]]:
    a = visible_assessment(db, student, assessment_id)
    if a["status"] != "published":
        raise Forbidden("This assessment is closed and no longer accepts answers.", code="assessment_closed")
    if deadline_passed(a):
        raise Forbidden("The deadline for this assessment has passed.", code="deadline_passed")
    return a, assessment_questions(db, a["_id"])


def _clean_answers(body: SubmissionIn, questions: list[dict]) -> list[dict]:
    valid = {str(q["_id"]) for q in questions}
    unknown = [a.question_id for a in body.answers if a.question_id not in valid]
    if unknown:
        raise Unprocessable("Answers refer to questions that are not part of this assessment.", code="unknown_question")
    by_q = {a.question_id: a.text for a in body.answers}
    # Keep the original text (only trailing whitespace trimmed); order follows the questions.
    return [{"question_id": str(q["_id"]), "text": by_q.get(str(q["_id"]), "").rstrip()} for q in questions]


@router.put("/draft", response_model=SubmissionOut)
def save_draft(body: SubmissionIn, student: Student, db: DB):
    a, questions = _check_open(db, student, body.assessment_id)
    answers = _clean_answers(body, questions)
    ts = now()
    existing = db.submissions.find_one({"assessment_id": a["_id"], "student_id": student["_id"]})
    if existing and existing["status"] != "draft":
        raise Conflict("This assessment has already been submitted.", code="already_submitted")
    try:
        doc = db.submissions.find_one_and_update(
            {"assessment_id": a["_id"], "student_id": student["_id"], "status": "draft"},
            {"$set": {"answers": answers, "updated_at": ts},
             "$setOnInsert": {"created_at": ts, "submitted_at": None, "published_at": None}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        raise Conflict("This assessment has already been submitted.", code="already_submitted") from None
    return _submission_out(doc)


@router.post("/submit", response_model=SubmissionOut)
def submit(body: SubmissionIn, student: Student, db: DB):
    a, questions = _check_open(db, student, body.assessment_id)
    answers = _clean_answers(body, questions)
    if not any(x["text"].strip() for x in answers):
        raise Unprocessable("Write at least one answer before submitting.", code="empty_submission")
    ts = now()
    try:
        doc = db.submissions.find_one_and_update(
            {"assessment_id": a["_id"], "student_id": student["_id"], "status": "draft"},
            {"$set": {"answers": answers, "status": "submitted", "submitted_at": ts, "updated_at": ts},
             "$setOnInsert": {"created_at": ts, "published_at": None}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        # A non-draft submission already exists (unique assessment+student index).
        raise Conflict("This assessment has already been submitted.", code="already_submitted") from None
    return _submission_out(doc)


@router.get("/mine", response_model=list[StudentSubmissionItem])
def my_submissions(student: Student, db: DB):
    items = []
    for s in db.submissions.find({"student_id": student["_id"]}).sort("updated_at", -1):
        a = db.assessments.find_one({"_id": s["assessment_id"]})
        if not a:
            continue
        questions = assessment_questions(db, a["_id"])
        t = totals(db, s, questions) if s["status"] == "published" else None
        items.append({
            "id": str(s["_id"]),
            "assessment_id": str(a["_id"]),
            "assessment_title": a["title"],
            "subject": a["subject"],
            "status": s["status"],
            "submitted_at": s.get("submitted_at"),
            "updated_at": s["updated_at"],
            "published_at": s.get("published_at"),
            # Marks are only revealed once published.
            "total_score": t["final_total"] if t else None,
            "max_total": float(sum(q["max_marks"] for q in questions)),
        })
    return items


@router.get("", response_model=Page[TeacherSubmissionItem])
def list_submissions(
    teacher: Teacher,
    db: DB,
    assessment_id: str,
    status: Literal["draft", "submitted", "evaluated", "published"] | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    a = owned_assessment(db, teacher, assessment_id)
    query: dict = {"assessment_id": a["_id"]}
    if status:
        query["status"] = status
    else:
        query["status"] = {"$ne": "draft"}  # drafts are private work in progress
    total = db.submissions.count_documents(query)
    questions = assessment_questions(db, a["_id"])
    items = []
    for s in db.submissions.find(query).sort([("submitted_at", 1), ("_id", 1)]).skip(skip).limit(limit):
        t = totals(db, s, questions)
        items.append({
            "id": str(s["_id"]),
            "student": student_brief(db.users.find_one({"_id": s["student_id"]})),
            "status": s["status"],
            "submitted_at": s.get("submitted_at"),
            "updated_at": s["updated_at"],
            "question_count": t["question_count"],
            "evaluated_count": t["evaluated_count"],
            "needs_review_count": t["needs_review_count"],
            "ai_total": t["ai_total"],
            "final_total": t["final_total"],
            "max_total": t["max_total"],
            "rubric_outdated": t["rubric_outdated"],
            "source": s.get("source"),
        })
    return {"items": items, "total": total, "skip": skip, "limit": limit}


@router.get("/{submission_id}", response_model=SubmissionReview | SubmissionOut)
def get_submission(submission_id: str, user: CurrentUser, db: DB):
    """Teachers get the full review view; students only their own raw submission
    (marks and feedback are available through /api/results once published)."""
    if user["role"] == "teacher":
        sub, a = teacher_submission(db, user, submission_id)
        if sub["status"] == "draft":
            raise NotFound("Submission not found")
        return submission_review(db, sub, a)
    sub = db.submissions.find_one({"_id": oid(submission_id, "Submission"), "student_id": user["_id"]})
    if not sub:
        raise NotFound("Submission not found")
    return _submission_out(sub)
