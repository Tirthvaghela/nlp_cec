"""Question-authoring drafts (teacher only): a reference answer for a question, and a rubric for question + reference.

Nothing is stored here; the teacher edits the draft and saves it with the question endpoints. See services/generation.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, StringConstraints

from app.config import get_settings
from app.deps import Teacher
from app.errors import AppError, Forbidden, TooManyRequests, Unprocessable
from app.ratelimit import limiter
from app.schemas.common import ApiModel, HalfMarks
from app.services import generation as gen

router = APIRouter(prefix="/api/generation", tags=["generation"])

GENERATION_LIMIT, GENERATION_WINDOW = 60, 600  # drafts per teacher per 10 minutes

QuestionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=2000)]
ReferenceText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class ServiceUnavailable(AppError):
    status_code, code = 503, "generation_unavailable"


class ReferenceAnswerIn(ApiModel):
    question: QuestionText
    max_marks: HalfMarks = Field(gt=0, le=100)


class ReferenceAnswerOut(BaseModel):
    reference_answer: str
    model: str


class RubricIn(ApiModel):
    question: QuestionText
    max_marks: HalfMarks = Field(gt=0, le=100)
    reference_answer: ReferenceText


class DraftCriterion(BaseModel):
    label: str
    description: str
    marks: float


class RubricOut(BaseModel):
    rubric: list[DraftCriterion]
    source: Literal["model", "derived"]
    model: str | None = None


def _rate_limit(teacher: dict) -> None:
    wait = limiter.hit(f"generation:{teacher['_id']}", GENERATION_LIMIT, GENERATION_WINDOW)
    if wait is not None:
        raise TooManyRequests("Too many drafts requested. Try again in a few minutes.", retry_after=wait)


@router.post("/reference-answer", response_model=ReferenceAnswerOut)
def draft_reference_answer(body: ReferenceAnswerIn, teacher: Teacher):
    if get_settings().pilot_mode:
        # In the classroom pilot no question content leaves the server.
        raise Forbidden("Reference-answer drafting is turned off in the classroom pilot. Write the reference answer yourself.",
                        code="generation_disabled_in_pilot")
    _rate_limit(teacher)
    try:
        text, model = gen.draft_reference_answer(body.question, body.max_marks)
    except gen.GenerationUnavailable as exc:
        # code: generation_unavailable (configuration), generation_rate_limited, generation_temporarily_unavailable
        raise ServiceUnavailable(f"A reference answer could not be drafted: {exc} You can write it yourself.", code=exc.code) from None
    except gen.GenerationFailed as exc:
        raise Unprocessable(str(exc), code="generation_failed") from None
    return {"reference_answer": text, "model": model}


@router.post("/rubric", response_model=RubricOut)
def draft_rubric(body: RubricIn, teacher: Teacher):
    _rate_limit(teacher)
    if not get_settings().pilot_mode:
        try:
            criteria, model = gen.draft_rubric_with_model(body.question, body.max_marks, body.reference_answer)
            return {"rubric": criteria, "source": "model", "model": model}
        except gen.GenerationUnavailable:
            pass  # no model available: derive locally below
        except gen.GenerationFailed as exc:
            raise Unprocessable(str(exc), code="generation_failed") from None
    try:
        return {"rubric": gen.derive_rubric(body.max_marks, body.reference_answer), "source": "derived", "model": None}
    except gen.GenerationFailed as exc:
        raise Unprocessable(str(exc), code="generation_failed") from None
