"""Bridge between the NLP engine and the database.

Versioning: there is exactly one *current* evaluation per (submission, question).
Re-evaluating archives the current document into ``evaluation_history`` and
creates a new one with ``version + 1``. Each evaluation stores the rubric
version, a fingerprint of the rubric and of the engine configuration, the
engine version and the model name, so the AI score can be reproduced.
"""

from __future__ import annotations

import logging

from pymongo.database import Database

from app.config import get_settings
from app.db import now
from app.errors import Conflict, Unprocessable
from app.nlp import EvaluationConfig, QuestionSpec, RubricError, evaluate_answer
from app.nlp.similarity import get_backend
from app.services.access import assessment_questions
from app.services.serializers import final_score

log = logging.getLogger(__name__)


def question_spec(q: dict) -> QuestionSpec:
    return QuestionSpec.from_dict(
        {
            "id": str(q["_id"]),
            "text": q["text"],
            "max_marks": q["max_marks"],
            "reference_answer": q.get("reference_answer", ""),
            "rubric": q.get("rubric", []),
            "settings": {k: v for k, v in (q.get("settings") or {}).items() if v is not None},
        }
    )


def run_engine(q: dict, answer: str) -> dict:
    backend = get_backend()
    try:
        result = evaluate_answer(question_spec(q), answer, EvaluationConfig.for_backend(backend.name), backend)
    except RubricError as exc:
        raise Unprocessable(str(exc), code="rubric_invalid") from exc
    return result.to_dict()


def evaluate_submission(db: Database, submission: dict, *, allow_unpublish: bool = False, reason: str = "re-evaluated") -> int:
    """(Re-)evaluate every question of a submission. Returns the number of evaluations written."""
    if submission["status"] == "draft":
        raise Conflict("This submission is still a draft and cannot be evaluated yet.")
    if submission["status"] == "published" and not allow_unpublish:
        raise Conflict("Results for this submission are published. Re-evaluating will unpublish them; confirm to continue.",
                       code="published")
    questions = assessment_questions(db, submission["assessment_id"])
    answers = {a["question_id"]: a.get("text", "") for a in submission.get("answers", [])}
    ts = now()
    written = 0
    for q in questions:
        result = run_engine(q, answers.get(str(q["_id"]), ""))
        key = {"submission_id": submission["_id"], "question_id": q["_id"]}
        existing = db.evaluations.find_one(key)
        version = 1
        if existing:
            archived = {k: v for k, v in existing.items() if k != "_id"}
            archived.update({"evaluation_id": existing["_id"], "archived_at": ts, "archive_reason": reason})
            db.evaluation_history.insert_one(archived)
            version = existing["version"] + 1
        meta = result["metadata"]
        doc = {
            **key,
            "assessment_id": submission["assessment_id"],
            "student_id": submission["student_id"],
            "version": version,
            "rubric_version": q.get("rubric_version", 1),
            "rubric_fingerprint": meta["rubric_fingerprint"],
            "config_fingerprint": meta["config_fingerprint"],
            "engine_version": meta["engine_version"],
            "backend": meta["backend"],
            "model_name": meta["model_name"],
            "ai_score": result["suggested_score"],
            "max_marks": q["max_marks"],
            "teacher_score": None,
            "adjustment_reason": "",
            "teacher_feedback": "",
            "status": "ai_suggested",
            "published": False,
            "evaluated_at": ts,
            "reviewed_at": None,
            "published_at": None,
            "result": result,
        }
        if existing:
            db.evaluations.replace_one({"_id": existing["_id"]}, doc)
        else:
            db.evaluations.insert_one(doc)
        written += 1
    # Evaluations for questions that were deleted are archived away.
    q_ids = [q["_id"] for q in questions]
    for stale in db.evaluations.find({"submission_id": submission["_id"], "question_id": {"$nin": q_ids}}):
        db.evaluation_history.insert_one({**{k: v for k, v in stale.items() if k != "_id"}, "evaluation_id": stale["_id"],
                                          "archived_at": ts, "archive_reason": "question removed"})
        db.evaluations.delete_one({"_id": stale["_id"]})
    db.submissions.update_one(
        {"_id": submission["_id"]},
        {"$set": {"status": "evaluated", "evaluated_at": ts, "updated_at": ts, "published_at": None}},
    )
    return written


def totals(db: Database, submission: dict, questions: list[dict] | None = None) -> dict:
    """AI and final totals; None when not every question has been evaluated."""
    if questions is None:
        questions = assessment_questions(db, submission["assessment_id"])
    max_total = float(sum(q["max_marks"] for q in questions))
    evs = {e["question_id"]: e for e in db.evaluations.find({"submission_id": submission["_id"]})}
    complete = bool(questions) and all(q["_id"] in evs for q in questions)
    ai = sum(evs[q["_id"]]["ai_score"] for q in questions if q["_id"] in evs)
    final = sum(final_score(evs[q["_id"]]) for q in questions if q["_id"] in evs)
    needs_review = sum(1 for e in evs.values() if e["result"].get("needs_review") and e.get("status") != "reviewed")
    outdated = any(
        q["_id"] in evs and evs[q["_id"]]["rubric_version"] != q.get("rubric_version", 1) for q in questions
    )
    return {
        "max_total": max_total,
        "ai_total": round(ai, 2) if complete else None,
        "final_total": round(final, 2) if complete else None,
        "evaluated_count": sum(1 for q in questions if q["_id"] in evs),
        "question_count": len(questions),
        "needs_review_count": needs_review,
        "rubric_outdated": outdated,
        "complete": complete,
    }


def publish_submission(db: Database, submission: dict) -> None:
    if submission["status"] not in ("evaluated", "published"):
        raise Conflict("Only evaluated submissions can be published.")
    t = totals(db, submission)
    if not t["complete"]:
        raise Conflict("Every question must be evaluated before results can be published.")
    if t["rubric_outdated"]:
        raise Conflict("A rubric changed after this submission was evaluated. Re-evaluate it before publishing.",
                       code="rubric_outdated")
    if get_settings().require_review_before_publish:
        unreviewed = db.evaluations.count_documents({"submission_id": submission["_id"], "status": {"$ne": "reviewed"}})
        if unreviewed:
            raise Conflict(f"{unreviewed} question(s) have not been reviewed by the teacher yet. Every AI suggestion must be "
                           "accepted or adjusted before publishing (pilot setting).", code="review_required")
    if get_settings().pilot_mode:
        # Security audit F11/F12: scoring is unchanged, but a suggestion made by the TF-IDF fallback (not the frozen
        # embedding engine) cannot simply be accepted - the teacher must enter their own mark with a reason.
        fallback = db.evaluations.count_documents({
            "submission_id": submission["_id"], "backend": {"$ne": "embedding"},
            "$or": [{"teacher_score": None}, {"adjustment_reason": {"$in": ["", None]}}],
        })
        if fallback:
            raise Conflict(f"{fallback} question(s) were scored by the fallback method, not the pilot engine. Enter your "
                           "own mark with a reason for each before publishing (pilot setting).",
                           code="fallback_requires_teacher_mark")
    ts = now()
    db.evaluations.update_many({"submission_id": submission["_id"]}, {"$set": {"published": True, "published_at": ts}})
    db.submissions.update_one({"_id": submission["_id"]},
                              {"$set": {"status": "published", "published_at": ts, "updated_at": ts}})


def unpublish_submission(db: Database, submission: dict) -> None:
    if submission["status"] != "published":
        raise Conflict("This result is not published.")
    ts = now()
    db.evaluations.update_many({"submission_id": submission["_id"]}, {"$set": {"published": False, "published_at": None}})
    db.submissions.update_one({"_id": submission["_id"]},
                              {"$set": {"status": "evaluated", "published_at": None, "updated_at": ts}})
