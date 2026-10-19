"""Analytics computed from real stored data only (no simulated activity)."""

from __future__ import annotations

import statistics

from fastapi import APIRouter

from app.deps import DB, Student, Teacher
from app.services.access import assessment_questions, owned_assessment
from app.services.evaluation_service import totals
from app.services.serializers import final_score

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

BINS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]


@router.get("/overview")
def teacher_overview(teacher: Teacher, db: DB):
    assessments = list(db.assessments.find({"teacher_id": teacher["_id"]}))
    ids = [a["_id"] for a in assessments]
    counts = {"draft": 0, "submitted": 0, "evaluated": 0, "published": 0}
    for row in db.submissions.aggregate([{"$match": {"assessment_id": {"$in": ids}}},
                                         {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        counts[row["_id"]] = row["n"]
    needs_review = db.evaluations.count_documents(
        {"assessment_id": {"$in": ids}, "result.needs_review": True, "status": "ai_suggested", "published": False}
    )
    pct = []
    for sub in db.submissions.find({"assessment_id": {"$in": ids}, "status": "published"}):
        t = totals(db, sub)
        if t["final_total"] is not None and t["max_total"]:
            pct.append(100 * t["final_total"] / t["max_total"])
    return {
        "assessments_total": len(assessments),
        "assessments_by_status": {s: sum(1 for a in assessments if a["status"] == s) for s in ("draft", "published", "closed")},
        "submissions_awaiting_evaluation": counts["submitted"],
        "submissions_awaiting_publication": counts["evaluated"],
        "results_published": counts["published"],
        "answers_flagged_for_review": needs_review,
        "average_published_percentage": round(statistics.mean(pct), 1) if pct else None,
    }


@router.get("/assessment/{assessment_id}")
def assessment_analytics(assessment_id: str, teacher: Teacher, db: DB):
    """Class-level and question-level statistics for evaluated submissions.

    Scores are the *final* marks (teacher-adjusted where available, otherwise the
    AI suggestion). ``basis`` tells the UI how many of them are still unpublished."""
    a = owned_assessment(db, teacher, assessment_id)
    questions = assessment_questions(db, a["_id"])
    subs = list(db.submissions.find({"assessment_id": a["_id"], "status": {"$in": ["evaluated", "published"]}}))
    status_counts = {"draft": 0, "submitted": 0, "evaluated": 0, "published": 0}
    for row in db.submissions.aggregate([{"$match": {"assessment_id": a["_id"]}},
                                         {"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        status_counts[row["_id"]] = row["n"]

    percentages = []
    for s in subs:
        t = totals(db, s, questions)
        if t["final_total"] is not None and t["max_total"]:
            percentages.append(round(100 * t["final_total"] / t["max_total"], 1))
    distribution = [
        {"range": f"{lo}-{min(hi, 100)}%", "count": sum(1 for p in percentages if lo <= p < hi)} for lo, hi in BINS
    ]

    evs_by_q: dict = {}
    reviewed = adjusted = 0
    abs_adjust = []
    for e in db.evaluations.find({"assessment_id": a["_id"], "submission_id": {"$in": [s["_id"] for s in subs]}}):
        evs_by_q.setdefault(e["question_id"], []).append(e)
        if e.get("status") == "reviewed":
            reviewed += 1
        if e.get("teacher_score") is not None and e["teacher_score"] != e["ai_score"]:
            adjusted += 1
            abs_adjust.append(abs(e["teacher_score"] - e["ai_score"]))

    q_stats = []
    for q in questions:
        evs = evs_by_q.get(q["_id"], [])
        scores = [final_score(e) for e in evs]
        concepts = []
        for item in q.get("rubric", []):
            levels = {"matched": 0, "partial": 0, "missing": 0}
            for e in evs:
                for c in e["result"]["concepts"]:
                    if c["id"] == item["id"]:
                        levels[c["level"]] += 1
            n = sum(levels.values())
            concepts.append({"id": item["id"], "label": item["label"], **levels,
                             "missing_rate": round(levels["missing"] / n, 3) if n else None})
        q_stats.append({
            "question_id": str(q["_id"]),
            "order": q.get("order", 0),
            "text": q["text"],
            "max_marks": q["max_marks"],
            "n": len(scores),
            "average_score": round(statistics.mean(scores), 2) if scores else None,
            "average_percentage": round(100 * statistics.mean(scores) / q["max_marks"], 1) if scores else None,
            "concepts": concepts,
        })

    return {
        "assessment": {"id": str(a["_id"]), "title": a["title"], "subject": a["subject"], "status": a["status"]},
        "submission_status": status_counts,
        "basis": {"evaluated": len(subs), "published": sum(1 for s in subs if s["status"] == "published")},
        "average_percentage": round(statistics.mean(percentages), 1) if percentages else None,
        "median_percentage": round(statistics.median(percentages), 1) if percentages else None,
        "highest_percentage": max(percentages) if percentages else None,
        "lowest_percentage": min(percentages) if percentages else None,
        "distribution": distribution,
        "questions": q_stats,
        "review": {
            "evaluations": sum(len(v) for v in evs_by_q.values()),
            "reviewed": reviewed,
            "adjusted": adjusted,
            "mean_absolute_adjustment": round(statistics.mean(abs_adjust), 2) if abs_adjust else None,
            "flagged_for_review": sum(1 for v in evs_by_q.values() for e in v if e["result"].get("needs_review")),
        },
    }


@router.get("/student")
def student_progress(student: Student, db: DB):
    """A student's own published results over time and their most frequently missed concepts."""
    history = []
    missed: dict[str, int] = {}
    for sub in db.submissions.find({"student_id": student["_id"], "status": "published"}).sort("published_at", 1):
        a = db.assessments.find_one({"_id": sub["assessment_id"]})
        if not a:
            continue
        t = totals(db, sub)
        if t["final_total"] is None:
            continue
        history.append({
            "submission_id": str(sub["_id"]),
            "assessment_title": a["title"],
            "subject": a["subject"],
            "published_at": sub.get("published_at"),
            "score": t["final_total"],
            "max_total": t["max_total"],
            "percentage": round(100 * t["final_total"] / t["max_total"], 1) if t["max_total"] else 0.0,
        })
        for e in db.evaluations.find({"submission_id": sub["_id"], "published": True}):
            for c in e["result"]["concepts"]:
                if c["level"] == "missing":
                    missed[c["label"]] = missed.get(c["label"], 0) + 1
    pct = [h["percentage"] for h in history]
    return {
        "results": history,
        "average_percentage": round(statistics.mean(pct), 1) if pct else None,
        "best_percentage": max(pct) if pct else None,
        "most_missed_concepts": [{"label": k, "count": v} for k, v in sorted(missed.items(), key=lambda kv: -kv[1])[:5]],
    }
