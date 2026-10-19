from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.schemas.auth import StudentBrief
from app.schemas.common import ApiModel

SubmissionStatus = Literal["draft", "submitted", "evaluated", "published"]
AnswerText = Annotated[str, StringConstraints(max_length=10000)]


class AnswerIn(ApiModel):
    question_id: str = Field(min_length=1, max_length=40)
    text: AnswerText = ""


class SubmissionIn(ApiModel):
    assessment_id: str = Field(min_length=1, max_length=40)
    answers: list[AnswerIn] = Field(default_factory=list, max_length=50)

    @field_validator("answers")
    @classmethod
    def _unique(cls, v: list[AnswerIn]):
        ids = [a.question_id for a in v]
        if len(set(ids)) != len(ids):
            raise ValueError("Each question may only be answered once")
        return v


class SubmissionOut(BaseModel):
    id: str
    assessment_id: str
    status: SubmissionStatus
    answers: list[AnswerIn]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None
    published_at: datetime | None = None


class StudentSubmissionItem(BaseModel):
    id: str
    assessment_id: str
    assessment_title: str
    subject: str
    status: SubmissionStatus
    submitted_at: datetime | None
    updated_at: datetime
    published_at: datetime | None
    total_score: float | None = None
    max_total: float


class TeacherSubmissionItem(BaseModel):
    id: str
    student: StudentBrief
    status: SubmissionStatus
    submitted_at: datetime | None
    updated_at: datetime
    question_count: int
    evaluated_count: int
    needs_review_count: int
    ai_total: float | None
    final_total: float | None
    max_total: float
    rubric_outdated: bool
    source: str | None = None
