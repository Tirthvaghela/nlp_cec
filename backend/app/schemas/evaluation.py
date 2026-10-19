from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.auth import StudentBrief
from app.schemas.common import ApiModel

Level = Literal["matched", "partial", "missing"]


class EvidenceOut(BaseModel):
    text: str
    start: int
    end: int


class ConceptOut(BaseModel):
    id: str
    label: str
    description: str
    marks: float
    level: Level
    awarded: float
    combined_score: float
    semantic_score: float
    lexical_score: float
    evidence: EvidenceOut | None
    matched_terms: list[str]
    ambiguous: bool
    reason: str
    note: str | None = None
    keyword_list_evidence: bool = False
    recall_score: float = 0.0
    # safeguard that affected this concept: misattributed | reversed_comparison | negated (v3) | antonym | echo (v4)
    issue: str | None = None


class FlagOut(BaseModel):
    code: str
    severity: Literal["info", "review"]
    message: str


class FeedbackOut(BaseModel):
    summary: str
    strengths: list[str]
    partial: list[str]
    missing: list[str]
    suggestions: list[str]
    text: str


class EngineResultOut(BaseModel):
    """What the NLP engine produced (AI suggestion)."""

    suggested_score: float
    max_marks: float
    concepts: list[ConceptOut]
    holistic_similarity: float | None
    relevance_ratio: float | None
    word_count: int
    flags: list[FlagOut]
    confidence: Literal["high", "medium", "low"]
    needs_review: bool
    feedback: FeedbackOut
    corrections: list[dict]
    metadata: dict


class EvaluationOut(BaseModel):
    id: str
    submission_id: str
    question_id: str
    version: int
    rubric_version: int
    rubric_outdated: bool
    engine_version: str
    backend: str
    model_name: str
    config_fingerprint: str
    rubric_fingerprint: str
    ai_score: float
    max_marks: float
    teacher_score: float | None
    final_score: float
    adjustment_reason: str
    teacher_feedback: str
    status: Literal["ai_suggested", "reviewed"]
    published: bool
    evaluated_at: datetime
    reviewed_at: datetime | None
    published_at: datetime | None
    history_count: int
    result: EngineResultOut


class ReviewIn(ApiModel):
    teacher_score: float | None = Field(default=None, ge=0, le=100)
    adjustment_reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""
    teacher_feedback: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    mark_reviewed: bool = True
    # V10: marking a question reviewed needs an explicit decision - either the teacher_score field (null = accept the
    # AI score, as the review panel sends it) or accept_ai_score=true. An empty request no longer counts as a review.
    accept_ai_score: bool = False


class HistoryItem(BaseModel):
    version: int
    rubric_version: int
    engine_version: str
    config_fingerprint: str
    ai_score: float
    teacher_score: float | None
    final_score: float
    evaluated_at: datetime
    archived_at: datetime
    archive_reason: str


class QuestionReview(BaseModel):
    question_id: str
    order: int
    text: str
    max_marks: float
    reference_answer: str
    rubric_levels: dict
    rubric_version: int
    answer: str
    evaluation: EvaluationOut | None


class SubmissionReview(BaseModel):
    id: str
    assessment_id: str
    assessment_title: str
    subject: str
    student: StudentBrief
    status: Literal["draft", "submitted", "evaluated", "published"]
    submitted_at: datetime | None
    published_at: datetime | None
    ai_total: float | None
    final_total: float | None
    max_total: float
    questions: list[QuestionReview]
    source: str | None = None


class BatchEvaluateOut(BaseModel):
    evaluated_submissions: int
    skipped_submissions: int
    evaluations_created: int


class PublishOut(BaseModel):
    published_submissions: int
    skipped: list[dict] = []


# --- student results --------------------------------------------------------------------

class StudentConcept(BaseModel):
    label: str
    description: str
    level: Level
    awarded: float
    marks: float
    evidence: EvidenceOut | None


class StudentQuestionResult(BaseModel):
    question_id: str
    order: int
    text: str
    max_marks: float
    answer: str
    final_score: float
    ai_score: float
    adjusted_by_teacher: bool
    concepts: list[StudentConcept]
    feedback: FeedbackOut
    teacher_feedback: str


class ResultSummary(BaseModel):
    submission_id: str
    assessment_id: str
    assessment_title: str
    subject: str
    total_score: float
    max_total: float
    percentage: float
    submitted_at: datetime | None
    published_at: datetime | None


class ResultDetail(ResultSummary):
    questions: list[StudentQuestionResult]
