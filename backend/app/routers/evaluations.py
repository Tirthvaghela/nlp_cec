from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from app.db import now, oid
from app.deps import DB, Teacher
from app.errors import Conflict, NotFound, Unprocessable
from app.schemas.evaluation import BatchEvaluateOut, EvaluationOut, HistoryItem, ReviewIn, SubmissionReview
from app.services.access import owned_assessment, teacher_submission
from app.services import publication
from app.services.evaluation_service import evaluate_submission
from app.services.review import submission_review
from app.services.serializers import evaluation_out, final_score

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.post("/submission/{submission_id}", response_model=SubmissionReview)
def evaluate_one(submission_id: str, teacher: Teacher, db: DB, allow_unpublish: bool = False):
    """Run the NLP engine on every answer of a submission. Re-running creates a new
    evaluation version (the previous one is archived) and resets teacher adjustments."""
    sub, a = teacher_submission(db, teacher, submission_id)
    if sub["status"] == "draft":
        raise NotFound("Submission not found")
    was_published = sub["status"] == "published"
    evaluate_submission(db, sub, allow_unpublish=allow_unpublish,
                        reason="re-evaluated by teacher" if sub["status"] != "submitted" else "initial")
    if was_published:  # V10: re-evaluation unpublished it - record who
        publication.record(db, sub["_id"], publication.UNPUBLISHED_FOR_REEVALUATION, teacher["_id"])
    return submission_review(db, db.submissions.find_one({"_id": sub["_id"]}), a)


@router.post("/assessment/{assessment_id}", response_model=BatchEvaluateOut)
def evaluate_assessment(
    assessment_id: str,
    teacher: Teacher,
    db: DB,
    scope: Literal["pending", "outdated"] = Query("pending", description="pending = submitted but not yet evaluated; "
                                                  "outdated = also re-evaluate unpublished results whose rubric changed"),
):
    a = owned_assessment(db, teacher, assessment_id)
    statuses = ["submitted"] if scope == "pending" else ["submitted", "evaluated"]
    done = skipped = created = 0
    questions = {q["_id"]: q.get("rubric_version", 1) for q in db.questions.find({"assessment_id": a["_id"]})}
    for sub in db.submissions.find({"assessment_id": a["_id"], "status": {"$in": statuses}}):
        if sub["status"] == "evaluated":
            evs = list(db.evaluations.find({"submission_id": sub["_id"]}, {"question_id": 1, "rubric_version": 1}))
            outdated = len(evs) != len(questions) or any(questions.get(e["question_id"]) != e["rubric_version"] for e in evs)
            if not outdated:
                skipped += 1
                continue
        created += evaluate_submission(db, sub, reason="rubric changed" if sub["status"] == "evaluated" else "initial")
        done += 1
    return {"evaluated_submissions": done, "skipped_submissions": skipped, "evaluations_created": created}


@router.get("/submission/{submission_id}", response_model=SubmissionReview)
def review_view(submission_id: str, teacher: Teacher, db: DB):
    sub, a = teacher_submission(db, teacher, submission_id)
    if sub["status"] == "draft":
        raise NotFound("Submission not found")
    return submission_review(db, sub, a)


def _owned_evaluation(db, teacher: dict, evaluation_id: str) -> tuple[dict, dict]:
    e = db.evaluations.find_one({"_id": oid(evaluation_id, "Evaluation")})
    if not e or not db.assessments.find_one({"_id": e["assessment_id"], "teacher_id": teacher["_id"]}, {"_id": 1}):
        raise NotFound("Evaluation not found")
    return e, db.questions.find_one({"_id": e["question_id"]})


@router.patch("/{evaluation_id}", response_model=EvaluationOut)
def review(evaluation_id: str, body: ReviewIn, teacher: Teacher, db: DB):
    """Teacher review: set a final score (or None to accept the AI suggestion), a reason
    for the adjustment and feedback for the student. The AI score is never overwritten."""
    e, q = _owned_evaluation(db, teacher, evaluation_id)
    if e.get("published"):
        raise Conflict("This result is already published. Unpublish it before editing.", code="published")
    explicit = "teacher_score" in body.model_fields_set or body.accept_ai_score
    if body.mark_reviewed and not explicit:
        raise Unprocessable("A review must state a decision: give your mark (teacher_score) or accept the AI score "
                            "(accept_ai_score). An empty review is not recorded as reviewed.", code="review_decision_required")
    if body.accept_ai_score and body.teacher_score is not None:
        raise Unprocessable("Either accept the AI score or give your own mark, not both.", code="review_conflict")
    if body.teacher_score is not None:
        if body.teacher_score > e["max_marks"]:
            raise Unprocessable(f"Score cannot exceed the maximum of {e['max_marks']:g} marks.", code="score_out_of_range")
        if abs(body.teacher_score * 4 - round(body.teacher_score * 4)) > 1e-9:
            raise Unprocessable("Scores must be in steps of 0.25 marks.", code="score_step")
    if body.teacher_score is not None and body.teacher_score != e["ai_score"] and not body.adjustment_reason:
        raise Unprocessable("Please give a short reason when changing the AI-suggested score.", code="reason_required")
    ts = now()
    changes = {
        "teacher_score": body.teacher_score,
        "adjustment_reason": body.adjustment_reason,
        "teacher_feedback": body.teacher_feedback,
        "status": "reviewed" if body.mark_reviewed else "ai_suggested",
        "reviewed_at": ts if body.mark_reviewed else None,
        "reviewed_by": teacher["_id"],
    }
    # Append-only audit trail: a later review overwrites the current fields, so every review is also logged
    # (re-evaluation archives the whole document, log included, into evaluation_history).
    entry = {k: changes[k] for k in ("teacher_score", "adjustment_reason", "status", "reviewed_by")}
    decision = "unreviewed" if not body.mark_reviewed else ("accepted_ai_score" if body.teacher_score is None else "teacher_mark")
    entry.update({"ai_score": e["ai_score"], "at": ts, "decision": decision})
    db.evaluations.update_one({"_id": e["_id"]}, {"$set": changes, "$push": {"review_log": entry}})
    e.update(changes)
    count = db.evaluation_history.count_documents({"submission_id": e["submission_id"], "question_id": e["question_id"]})
    return evaluation_out(e, q, count)


@router.get("/{evaluation_id}/history", response_model=list[HistoryItem])
def history(evaluation_id: str, teacher: Teacher, db: DB):
    e, _ = _owned_evaluation(db, teacher, evaluation_id)
    rows = db.evaluation_history.find({"submission_id": e["submission_id"], "question_id": e["question_id"]}).sort("version", -1)
    return [
        {
            "version": h["version"], "rubric_version": h["rubric_version"], "engine_version": h["engine_version"],
            "config_fingerprint": h["config_fingerprint"], "ai_score": h["ai_score"], "teacher_score": h.get("teacher_score"),
            "final_score": final_score(h), "evaluated_at": h["evaluated_at"], "archived_at": h["archived_at"],
            "archive_reason": h.get("archive_reason", ""),
        }
        for h in rows
    ]
