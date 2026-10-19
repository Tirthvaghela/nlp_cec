from __future__ import annotations

import re

from fastapi import APIRouter

from app.config import get_settings
from app.db import now
from app.deps import DB, Teacher
from app.errors import Conflict, Forbidden, Unprocessable
from app.schemas.assessment import QuestionIn, QuestionOut, QuestionUpdate, TestAnswerIn
from app.schemas.common import Message
from app.schemas.evaluation import EngineResultOut
from app.services.access import owned_assessment, owned_question
from app.services.evaluation_service import run_engine
from app.services.serializers import question_out

router = APIRouter(prefix="/api/questions", tags=["questions"])

# Fields whose change alters how answers are scored -> new rubric version.
_SCORING_FIELDS = {"text", "max_marks", "reference_answer", "rubric", "settings"}


def _rubric_items(items: list[dict]) -> list[dict]:
    out, used = [], set()
    for n, item in enumerate(items):
        rid = (item.get("id") or "").strip()
        if not rid or rid in used or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", rid):
            rid = f"c{n + 1}"
            while rid in used:
                rid += "x"
        used.add(rid)
        keywords = list(dict.fromkeys(k for k in item.get("keywords", []) if k))
        out.append({"id": rid, "label": item["label"], "description": item["description"],
                    "marks": float(item["marks"]), "keywords": keywords})
    return out


def _clean_settings(settings: dict | None) -> dict:
    return {k: v for k, v in (settings or {}).items() if v is not None}


def _refuse_pilot_overrides(settings: dict) -> None:
    """Sprint 5 (A1): in PILOT_MODE a per-question threshold override cannot be saved. The preflight already fails
    while any override exists (it is outside the frozen engine identity), but it only runs before sessions; this keeps
    an override from changing AI suggestions between two runs. Removing an override stays possible. This enforces the
    current "forbidden until decided" default - it does NOT decide faculty decision D5 (PILOT_READINESS.md)."""
    if settings and get_settings().pilot_mode:
        raise Forbidden("Per-question threshold overrides are disabled in the classroom pilot: they are outside the "
                        "frozen engine (faculty decision D5 is pending).", code="pilot_overrides_disabled")


@router.post("", response_model=QuestionOut, status_code=201)
def create_question(body: QuestionIn, teacher: Teacher, db: DB):
    a = owned_assessment(db, teacher, body.assessment_id)
    _refuse_pilot_overrides(_clean_settings(body.settings.model_dump()))
    if a["status"] != "draft" and db.submissions.count_documents({"assessment_id": a["_id"], "status": {"$ne": "draft"}}):
        raise Conflict("Students have already submitted this assessment, so questions cannot be added.")
    order = body.order
    if order is None:
        last = db.questions.find_one({"assessment_id": a["_id"]}, sort=[("order", -1)])
        order = (last["order"] + 1) if last else 0
    ts = now()
    doc = {
        "assessment_id": a["_id"],
        "order": order,
        "text": body.text,
        "max_marks": body.max_marks,
        "reference_answer": body.reference_answer,
        "rubric": _rubric_items([i.model_dump() for i in body.rubric]),
        "rubric_levels": body.rubric_levels.model_dump(),
        "settings": _clean_settings(body.settings.model_dump()),
        "rubric_version": 1,
        "created_at": ts,
        "updated_at": ts,
    }
    doc["_id"] = db.questions.insert_one(doc).inserted_id
    db.assessments.update_one({"_id": a["_id"]}, {"$set": {"updated_at": ts}})
    return question_out(doc)


@router.get("/{question_id}", response_model=QuestionOut)
def get_question(question_id: str, teacher: Teacher, db: DB):
    q, _ = owned_question(db, teacher, question_id)
    return question_out(q)


@router.patch("/{question_id}", response_model=QuestionOut)
def update_question(question_id: str, body: QuestionUpdate, teacher: Teacher, db: DB):
    """Edit a question. Changing anything that affects scoring increments ``rubric_version``;
    existing evaluations are then marked as outdated until they are re-evaluated."""
    q, a = owned_question(db, teacher, question_id)
    data = body.model_dump(exclude_unset=True)
    # Validate the merged question (e.g. rubric marks vs. a changed max_marks).
    merged_max = data.get("max_marks", q["max_marks"])
    merged_rubric = body.rubric if body.rubric is not None else None
    if merged_rubric is not None or "max_marks" in data:
        from app.schemas.assessment import RubricItemIn

        rubric_models = merged_rubric if merged_rubric is not None else [RubricItemIn(**i) for i in q["rubric"]]
        try:
            QuestionUpdate.check_rubric(rubric_models, merged_max, data.get("reference_answer", q.get("reference_answer", "")))
        except ValueError as exc:
            raise Unprocessable(str(exc), code="validation_error") from None
    changes: dict = {}
    for key, value in data.items():
        if value is None:
            continue
        if key == "rubric":
            value = _rubric_items(value)
        elif key == "settings":
            value = _clean_settings(value)
            _refuse_pilot_overrides(value)
        changes[key] = value
    if not changes:
        return question_out(q)
    if any(k in _SCORING_FIELDS and changes[k] != q.get(k) for k in changes):
        changes["rubric_version"] = q.get("rubric_version", 1) + 1
    changes["updated_at"] = now()
    db.questions.update_one({"_id": q["_id"]}, {"$set": changes})
    db.assessments.update_one({"_id": a["_id"]}, {"$set": {"updated_at": changes["updated_at"]}})
    return question_out(db.questions.find_one({"_id": q["_id"]}))


@router.delete("/{question_id}", response_model=Message)
def delete_question(question_id: str, teacher: Teacher, db: DB):
    q, a = owned_question(db, teacher, question_id)
    if db.submissions.count_documents({"assessment_id": a["_id"], "status": {"$ne": "draft"}}):
        raise Conflict("Students have already submitted this assessment, so its questions cannot be deleted.")
    db.questions.delete_one({"_id": q["_id"]})
    # Keep a contiguous order.
    for n, other in enumerate(db.questions.find({"assessment_id": a["_id"]}).sort("order", 1)):
        db.questions.update_one({"_id": other["_id"]}, {"$set": {"order": n}})
    return {"detail": "Question deleted."}


@router.post("/{question_id}/test-answer", response_model=EngineResultOut)
def test_answer(question_id: str, body: TestAnswerIn, teacher: Teacher, db: DB):
    """Try the rubric on a sample answer without saving anything (rubric sandbox)."""
    q, _ = owned_question(db, teacher, question_id)
    return run_engine(q, body.answer)
