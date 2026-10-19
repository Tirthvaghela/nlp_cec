from __future__ import annotations

from fastapi import APIRouter

from app.db import now, oid
from app.deps import DB, CurrentUser, Teacher
from app.errors import Conflict, Unprocessable
from app.nlp.rubric import RubricError, prepare_question
from app.schemas.assessment import (
    AssessmentDetail,
    AssessmentIn,
    AssessmentOut,
    AssessmentUpdate,
    StudentAssessmentDetail,
    StudentAssessmentOut,
)
from app.schemas.common import Message
from app.services.access import (
    assessment_questions,
    deadline_passed,
    owned_assessment,
    pilot_access_ok,
    student_can_see,
    visible_assessment,
)
from app.services.evaluation_service import question_spec
from app.services.serializers import assessment_out, question_out

router = APIRouter(prefix="/api/assessments", tags=["assessments"])


def _student_ids(db, ids: list[str]) -> list:
    parsed = []
    for s in dict.fromkeys(ids):
        _id = oid(s, "Student")
        if not db.users.find_one({"_id": _id, "role": "student"}, {"_id": 1}):
            raise Unprocessable(f"Unknown student id: {s}", code="unknown_student")
        parsed.append(_id)
    return parsed


def _student_view(db, a: dict, student: dict, detail: bool = False) -> dict:
    questions = assessment_questions(db, a["_id"])
    sub = db.submissions.find_one({"assessment_id": a["_id"], "student_id": student["_id"]})
    passed = deadline_passed(a)
    if sub:
        my_status = sub["status"]
    elif passed or a["status"] == "closed":
        my_status = "missed"
    else:
        my_status = "not_started"
    teacher = db.users.find_one({"_id": a["teacher_id"]}, {"name": 1})
    out = {
        "id": str(a["_id"]),
        "title": a["title"],
        "subject": a["subject"],
        "instructions": a.get("instructions", ""),
        "status": a["status"],
        "deadline": a.get("deadline"),
        "deadline_passed": passed,
        "question_count": len(questions),
        "total_marks": float(sum(q["max_marks"] for q in questions)),
        "teacher_name": teacher["name"] if teacher else "",
        "my_status": my_status,
        "submission_id": str(sub["_id"]) if sub else None,
        "submitted_at": sub.get("submitted_at") if sub else None,
    }
    if detail:
        # Reference answers, rubrics and thresholds are never sent to students.
        out["questions"] = [
            {"id": str(q["_id"]), "order": q.get("order", 0), "text": q["text"], "max_marks": q["max_marks"]}
            for q in questions
        ]
        out["answers"] = [{"question_id": x["question_id"], "text": x.get("text", "")} for x in (sub or {}).get("answers", [])]
        out["can_edit"] = a["status"] == "published" and not passed and (sub is None or sub["status"] == "draft")
    return out


@router.get("", response_model=list[AssessmentOut] | list[StudentAssessmentOut])
def list_assessments(user: CurrentUser, db: DB):
    """Teachers see their own assessments; students see published assessments assigned to them."""
    if user["role"] == "teacher":
        docs = db.assessments.find({"teacher_id": user["_id"]}).sort("created_at", -1)
        return [assessment_out(db, a) for a in docs]
    docs = db.assessments.find({"status": {"$in": ["published", "closed"]}}).sort("created_at", -1)
    pilot_ok = pilot_access_ok(db, user)
    return [_student_view(db, a, user) for a in docs if student_can_see(a, user, pilot_ok=pilot_ok)]


@router.post("", response_model=AssessmentOut, status_code=201)
def create_assessment(body: AssessmentIn, teacher: Teacher, db: DB):
    ts = now()
    doc = {
        "teacher_id": teacher["_id"],
        "title": body.title,
        "subject": body.subject,
        "instructions": body.instructions,
        "status": "draft",
        "deadline": body.deadline,
        "assigned_student_ids": _student_ids(db, body.assigned_student_ids),
        "created_at": ts,
        "updated_at": ts,
        "published_at": None,
    }
    doc["_id"] = db.assessments.insert_one(doc).inserted_id
    return assessment_out(db, doc, [])


@router.get("/{assessment_id}", response_model=AssessmentDetail | StudentAssessmentDetail)
def get_assessment(assessment_id: str, user: CurrentUser, db: DB):
    if user["role"] == "teacher":
        a = owned_assessment(db, user, assessment_id)
        questions = assessment_questions(db, a["_id"])
        return {**assessment_out(db, a, questions), "questions": [question_out(q) for q in questions]}
    a = visible_assessment(db, user, assessment_id)
    return _student_view(db, a, user, detail=True)


@router.patch("/{assessment_id}", response_model=AssessmentOut)
def update_assessment(assessment_id: str, body: AssessmentUpdate, teacher: Teacher, db: DB):
    a = owned_assessment(db, teacher, assessment_id)
    changes = body.model_dump(exclude_unset=True, exclude={"clear_deadline"})
    changes = {k: v for k, v in changes.items() if v is not None}
    if "assigned_student_ids" in changes:
        changes["assigned_student_ids"] = _student_ids(db, changes["assigned_student_ids"])
    if body.clear_deadline:
        changes["deadline"] = None
    changes["updated_at"] = now()
    db.assessments.update_one({"_id": a["_id"]}, {"$set": changes})
    return assessment_out(db, db.assessments.find_one({"_id": a["_id"]}))


@router.delete("/{assessment_id}", response_model=Message)
def delete_assessment(assessment_id: str, teacher: Teacher, db: DB):
    a = owned_assessment(db, teacher, assessment_id)
    if db.submissions.count_documents({"assessment_id": a["_id"]}):
        raise Conflict("This assessment already has student submissions and cannot be deleted. Close it instead.")
    db.questions.delete_many({"assessment_id": a["_id"]})
    db.assessments.delete_one({"_id": a["_id"]})
    return {"detail": "Assessment deleted."}


@router.post("/{assessment_id}/publish", response_model=AssessmentOut)
def publish_assessment(assessment_id: str, teacher: Teacher, db: DB):
    """Make the assessment visible to students (also re-opens a closed assessment)."""
    a = owned_assessment(db, teacher, assessment_id)
    questions = assessment_questions(db, a["_id"])
    if not questions:
        raise Conflict("Add at least one question before publishing.", code="no_questions")
    for q in questions:
        try:
            prepare_question(question_spec(q))
        except RubricError as exc:
            raise Conflict(f"Question {q.get('order', 0) + 1}: {exc}", code="rubric_invalid") from None
    if deadline_passed(a):
        raise Conflict("The deadline is in the past. Update or clear it before publishing.", code="deadline_passed")
    ts = now()
    db.assessments.update_one({"_id": a["_id"]},
                              {"$set": {"status": "published", "published_at": a.get("published_at") or ts, "updated_at": ts}})
    return assessment_out(db, db.assessments.find_one({"_id": a["_id"]}), questions)


@router.post("/{assessment_id}/close", response_model=AssessmentOut)
def close_assessment(assessment_id: str, teacher: Teacher, db: DB):
    """Stop accepting submissions. Students keep access to their submissions and results."""
    a = owned_assessment(db, teacher, assessment_id)
    if a["status"] != "published":
        raise Conflict("Only a published assessment can be closed.")
    db.assessments.update_one({"_id": a["_id"]}, {"$set": {"status": "closed", "updated_at": now()}})
    return assessment_out(db, db.assessments.find_one({"_id": a["_id"]}))
