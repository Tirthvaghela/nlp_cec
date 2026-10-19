from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.schemas.common import ApiModel, HalfMarks, UtcDatetime

AssessmentStatus = Literal["draft", "published", "closed"]
StudentStatus = Literal["not_started", "draft", "submitted", "evaluated", "published", "missed"]

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=150)]
Subject = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Instructions = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class AssessmentIn(ApiModel):
    title: Title
    subject: Subject
    instructions: Instructions = ""
    deadline: UtcDatetime | None = None
    assigned_student_ids: list[str] = Field(default_factory=list, max_length=500)


class AssessmentUpdate(ApiModel):
    title: Title | None = None
    subject: Subject | None = None
    instructions: Instructions | None = None
    deadline: UtcDatetime | None = None
    clear_deadline: bool = False
    assigned_student_ids: list[str] | None = Field(default=None, max_length=500)


class SubmissionCounts(BaseModel):
    draft: int = 0
    submitted: int = 0
    evaluated: int = 0
    published: int = 0


class AssessmentOut(BaseModel):
    id: str
    title: str
    subject: str
    instructions: str
    status: AssessmentStatus
    deadline: datetime | None
    assigned_student_ids: list[str]
    question_count: int
    total_marks: float
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None
    submission_counts: SubmissionCounts


# --- questions & rubric --------------------------------------------------------------

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=600)]
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
LevelText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class RubricItemIn(ApiModel):
    id: str | None = Field(default=None, max_length=40)
    label: Label
    description: Description
    marks: HalfMarks = Field(gt=0, le=100)
    keywords: list[Keyword] = Field(default_factory=list, max_length=10)


class RubricItemOut(BaseModel):
    id: str
    label: str
    description: str
    marks: float
    keywords: list[str] = []


class RubricLevels(ApiModel):
    """Optional descriptions of performance levels, shown to the teacher while reviewing."""

    excellent: LevelText = ""
    satisfactory: LevelText = ""
    needs_improvement: LevelText = ""


class QuestionSettings(ApiModel):
    """Per-question overrides of the engine thresholds (None = calibrated default)."""

    match_threshold: float | None = Field(default=None, ge=0.2, le=0.95)
    partial_threshold: float | None = Field(default=None, ge=0.1, le=0.9)

    @model_validator(mode="after")
    def _order(self):
        if self.match_threshold is not None and self.partial_threshold is not None:
            if self.partial_threshold >= self.match_threshold:
                raise ValueError("partial_threshold must be lower than match_threshold")
        return self


QuestionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=2000)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class _QuestionBody(ApiModel):
    @staticmethod
    def check_rubric(rubric: list[RubricItemIn] | None, max_marks: float | None, reference: str | None) -> None:
        if rubric is not None and max_marks is not None and rubric:
            total = sum(i.marks for i in rubric)
            if abs(total - max_marks) > 1e-6:
                raise ValueError(f"Rubric marks ({total:g}) must add up to the question's maximum marks ({max_marks:g})")
        if rubric is not None and not rubric and reference is not None and not reference.strip():
            raise ValueError("Provide at least one rubric concept or a reference answer")
        if rubric:
            labels = [i.label.lower() for i in rubric]
            if len(set(labels)) != len(labels):
                raise ValueError("Rubric concept labels must be unique")


class QuestionIn(_QuestionBody):
    assessment_id: str
    text: QuestionText
    max_marks: HalfMarks = Field(gt=0, le=100)
    reference_answer: Reference = ""
    rubric: list[RubricItemIn] = Field(default_factory=list, max_length=12)
    rubric_levels: RubricLevels = Field(default_factory=RubricLevels)
    settings: QuestionSettings = Field(default_factory=QuestionSettings)
    order: int | None = Field(default=None, ge=0, le=1000)

    @model_validator(mode="after")
    def _validate(self):
        self.check_rubric(self.rubric, self.max_marks, self.reference_answer)
        return self


class QuestionUpdate(_QuestionBody):
    text: QuestionText | None = None
    max_marks: HalfMarks | None = Field(default=None, gt=0, le=100)
    reference_answer: Reference | None = None
    rubric: list[RubricItemIn] | None = Field(default=None, max_length=12)
    rubric_levels: RubricLevels | None = None
    settings: QuestionSettings | None = None
    order: int | None = Field(default=None, ge=0, le=1000)


class QuestionOut(BaseModel):
    id: str
    assessment_id: str
    order: int
    text: str
    max_marks: float
    reference_answer: str
    rubric: list[RubricItemOut]
    rubric_levels: dict
    settings: dict
    rubric_version: int
    created_at: datetime
    updated_at: datetime


class AssessmentDetail(AssessmentOut):
    questions: list[QuestionOut]


class TestAnswerIn(ApiModel):
    answer: Annotated[str, StringConstraints(max_length=10000)]


# --- student-facing views (no reference answers, rubrics or thresholds) --------------

class StudentQuestionOut(BaseModel):
    id: str
    order: int
    text: str
    max_marks: float


class StudentAssessmentOut(BaseModel):
    id: str
    title: str
    subject: str
    instructions: str
    status: AssessmentStatus
    deadline: datetime | None
    deadline_passed: bool
    question_count: int
    total_marks: float
    teacher_name: str
    my_status: StudentStatus
    submission_id: str | None = None
    submitted_at: datetime | None = None


class StudentAnswerOut(BaseModel):
    question_id: str
    text: str


class StudentAssessmentDetail(StudentAssessmentOut):
    questions: list[StudentQuestionOut]
    answers: list[StudentAnswerOut]
    can_edit: bool

    @field_validator("questions")
    @classmethod
    def _sorted(cls, v):
        return sorted(v, key=lambda q: q.order)
