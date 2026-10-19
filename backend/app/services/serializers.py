"""Convert MongoDB documents to API response dictionaries."""

from __future__ import annotations

from pymongo.database import Database


def user_out(u: dict) -> dict:
    return {"id": str(u["_id"]), "name": u["name"], "email": u["email"], "role": u["role"], "created_at": u["created_at"]}


def student_brief(u: dict | None) -> dict:
    if not u:
        return {"id": "", "name": "Deleted user", "email": ""}
    return {"id": str(u["_id"]), "name": u["name"], "email": u["email"]}


def question_out(q: dict) -> dict:
    return {
        "id": str(q["_id"]),
        "assessment_id": str(q["assessment_id"]),
        "order": q.get("order", 0),
        "text": q["text"],
        "max_marks": q["max_marks"],
        "reference_answer": q.get("reference_answer", ""),
        "rubric": q.get("rubric", []),
        "rubric_levels": q.get("rubric_levels") or {},
        "settings": q.get("settings") or {},
        "rubric_version": q.get("rubric_version", 1),
        "created_at": q["created_at"],
        "updated_at": q["updated_at"],
    }


def submission_counts(db: Database, assessment_id) -> dict:
    counts = {"draft": 0, "submitted": 0, "evaluated": 0, "published": 0}
    for row in db.submissions.aggregate([{"$match": {"assessment_id": assessment_id}},
                                         {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        counts[row["_id"]] = row["n"]
    return counts


def assessment_out(db: Database, a: dict, questions: list[dict] | None = None) -> dict:
    if questions is None:
        questions = list(db.questions.find({"assessment_id": a["_id"]}, {"max_marks": 1}))
    return {
        "id": str(a["_id"]),
        "title": a["title"],
        "subject": a["subject"],
        "instructions": a.get("instructions", ""),
        "status": a["status"],
        "deadline": a.get("deadline"),
        "assigned_student_ids": [str(s) for s in a.get("assigned_student_ids", [])],
        "question_count": len(questions),
        "total_marks": float(sum(q["max_marks"] for q in questions)),
        "created_at": a["created_at"],
        "updated_at": a["updated_at"],
        "published_at": a.get("published_at"),
        "submission_counts": submission_counts(db, a["_id"]),
    }


def evaluation_out(e: dict, question: dict | None, history_count: int = 0) -> dict:
    current_version = (question or {}).get("rubric_version", e["rubric_version"])
    return {
        "id": str(e["_id"]),
        "submission_id": str(e["submission_id"]),
        "question_id": str(e["question_id"]),
        "version": e["version"],
        "rubric_version": e["rubric_version"],
        "rubric_outdated": current_version != e["rubric_version"],
        "engine_version": e["engine_version"],
        "backend": e["backend"],
        "model_name": e["model_name"],
        "config_fingerprint": e["config_fingerprint"],
        "rubric_fingerprint": e["rubric_fingerprint"],
        "ai_score": e["ai_score"],
        "max_marks": e["max_marks"],
        "teacher_score": e.get("teacher_score"),
        "final_score": final_score(e),
        "adjustment_reason": e.get("adjustment_reason", ""),
        "teacher_feedback": e.get("teacher_feedback", ""),
        "status": e.get("status", "ai_suggested"),
        "published": e.get("published", False),
        "evaluated_at": e["evaluated_at"],
        "reviewed_at": e.get("reviewed_at"),
        "published_at": e.get("published_at"),
        "history_count": history_count,
        "result": e["result"],
    }


def final_score(e: dict) -> float:
    ts = e.get("teacher_score")
    return float(ts if ts is not None else e["ai_score"])
