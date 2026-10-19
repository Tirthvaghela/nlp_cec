"""Build the teacher's review view of a submission."""

from __future__ import annotations

from pymongo.database import Database

from app.services.access import assessment_questions
from app.services.evaluation_service import totals
from app.services.serializers import evaluation_out, student_brief


def submission_review(db: Database, sub: dict, assessment: dict) -> dict:
    questions = assessment_questions(db, assessment["_id"])
    answers = {a["question_id"]: a.get("text", "") for a in sub.get("answers", [])}
    evs = {e["question_id"]: e for e in db.evaluations.find({"submission_id": sub["_id"]})}
    history = {
        row["_id"]: row["n"]
        for row in db.evaluation_history.aggregate(
            [{"$match": {"submission_id": sub["_id"]}}, {"$group": {"_id": "$question_id", "n": {"$sum": 1}}}]
        )
    }
    t = totals(db, sub, questions)
    student = db.users.find_one({"_id": sub["student_id"]})
    return {
        "id": str(sub["_id"]),
        "assessment_id": str(assessment["_id"]),
        "assessment_title": assessment["title"],
        "subject": assessment["subject"],
        "student": student_brief(student),
        "status": sub["status"],
        "submitted_at": sub.get("submitted_at"),
        "published_at": sub.get("published_at"),
        "ai_total": t["ai_total"],
        "final_total": t["final_total"],
        "max_total": t["max_total"],
        "source": sub.get("source"),
        "questions": [
            {
                "question_id": str(q["_id"]),
                "order": q.get("order", 0),
                "text": q["text"],
                "max_marks": q["max_marks"],
                "reference_answer": q.get("reference_answer", ""),
                "rubric_levels": q.get("rubric_levels") or {},
                "rubric_version": q.get("rubric_version", 1),
                "answer": answers.get(str(q["_id"]), ""),
                "evaluation": evaluation_out(evs[q["_id"]], q, history.get(q["_id"], 0)) if q["_id"] in evs else None,
            }
            for q in questions
        ],
    }
