from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from app.db import oid
from app.deps import DB, Student, Teacher
from app.errors import AppError, NotFound
from app.schemas.common import ApiModel, Message
from app.schemas.evaluation import PublishOut, ResultDetail, ResultSummary
from app.services.access import assessment_questions, owned_assessment, teacher_submission
from app.services import publication
from app.services.evaluation_service import publish_submission, totals, unpublish_submission
from app.services.serializers import final_score

router = APIRouter(prefix="/api/results", tags=["results"])


class BulkPublishIn(ApiModel):
    submission_ids: list[str] | None = Field(default=None, max_length=500)


@router.post("/submission/{submission_id}/publish", response_model=PublishOut)
def publish_one(submission_id: str, teacher: Teacher, db: DB):
    sub, _ = teacher_submission(db, teacher, submission_id)
    publish_submission(db, sub)
    publication.record(db, sub["_id"], publication.PUBLISHED, teacher["_id"])  # V10: who and when
    return {"published_submissions": 1, "skipped": []}


@router.post("/submission/{submission_id}/unpublish", response_model=Message)
def unpublish_one(submission_id: str, teacher: Teacher, db: DB):
    sub, _ = teacher_submission(db, teacher, submission_id)
    unpublish_submission(db, sub)
    publication.record(db, sub["_id"], publication.UNPUBLISHED, teacher["_id"])
    return {"detail": "Result unpublished. The student can no longer see it."}


@router.post("/assessment/{assessment_id}/publish", response_model=PublishOut)
def publish_assessment_results(assessment_id: str, body: BulkPublishIn, teacher: Teacher, db: DB):
    """Publish every evaluated (or the selected) submission of an assessment."""
    a = owned_assessment(db, teacher, assessment_id)
    query: dict = {"assessment_id": a["_id"], "status": "evaluated"}
    if body.submission_ids is not None:
        query["_id"] = {"$in": [oid(s, "Submission") for s in body.submission_ids]}
    published, skipped = 0, []
    for sub in db.submissions.find(query):
        try:
            publish_submission(db, sub)
            publication.record(db, sub["_id"], publication.PUBLISHED, teacher["_id"])
            published += 1
        except AppError as exc:
            skipped.append({"submission_id": str(sub["_id"]), "reason": exc.detail})
    return {"published_submissions": published, "skipped": skipped}


def _summary(db, sub: dict, a: dict, questions: list[dict]) -> dict:
    t = totals(db, sub, questions)
    total = t["final_total"] or 0.0
    return {
        "submission_id": str(sub["_id"]),
        "assessment_id": str(a["_id"]),
        "assessment_title": a["title"],
        "subject": a["subject"],
        "total_score": total,
        "max_total": t["max_total"],
        "percentage": round(100 * total / t["max_total"], 1) if t["max_total"] else 0.0,
        "submitted_at": sub.get("submitted_at"),
        "published_at": sub.get("published_at"),
    }


@router.get("/mine", response_model=list[ResultSummary])
def my_results(student: Student, db: DB):
    out = []
    for sub in db.submissions.find({"student_id": student["_id"], "status": "published"}).sort("published_at", -1):
        a = db.assessments.find_one({"_id": sub["assessment_id"]})
        if a:
            out.append(_summary(db, sub, a, assessment_questions(db, a["_id"])))
    return out


@router.get("/submission/{submission_id}", response_model=ResultDetail)
def my_result(submission_id: str, student: Student, db: DB):
    """A student's own published result. Unpublished or foreign results are 404."""
    sub = db.submissions.find_one({"_id": oid(submission_id, "Result"), "student_id": student["_id"], "status": "published"})
    if not sub:
        raise NotFound("Result not found")
    a = db.assessments.find_one({"_id": sub["assessment_id"]})
    if not a:
        raise NotFound("Result not found")
    questions = assessment_questions(db, a["_id"])
    answers = {x["question_id"]: x.get("text", "") for x in sub.get("answers", [])}
    evs = {e["question_id"]: e for e in db.evaluations.find({"submission_id": sub["_id"], "published": True})}
    items = []
    for q in questions:
        e = evs.get(q["_id"])
        if not e:
            continue
        r = e["result"]
        items.append({
            "question_id": str(q["_id"]),
            "order": q.get("order", 0),
            "text": q["text"],
            "max_marks": q["max_marks"],
            "answer": answers.get(str(q["_id"]), ""),
            "final_score": final_score(e),
            "ai_score": e["ai_score"],
            "adjusted_by_teacher": e.get("teacher_score") is not None and e["teacher_score"] != e["ai_score"],
            # Only what a student needs: no similarity numbers, thresholds or reference answer.
            "concepts": [
                {"label": c["label"], "description": c["description"], "level": c["level"], "awarded": c["awarded"],
                 "marks": c["marks"], "evidence": c.get("evidence")}
                for c in r["concepts"]
            ],
            "feedback": r["feedback"],
            "teacher_feedback": e.get("teacher_feedback", ""),
        })
    return {**_summary(db, sub, a, questions), "questions": items}
