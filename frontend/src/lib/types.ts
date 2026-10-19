// Types mirroring the FastAPI response models (backend/app/schemas).

export type Role = "teacher" | "student";
export type AssessmentStatus = "draft" | "published" | "closed";
export type SubmissionStatus = "draft" | "submitted" | "evaluated" | "published";
export type StudentStatus = "not_started" | "draft" | "submitted" | "evaluated" | "published" | "missed";
export type Level = "matched" | "partial" | "missing";
export type Confidence = "high" | "medium" | "low";

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface StudentBrief {
  id: string;
  name: string;
  email: string;
}

export interface SubmissionCounts {
  draft: number;
  submitted: number;
  evaluated: number;
  published: number;
}

export interface RubricItem {
  id: string;
  label: string;
  description: string;
  marks: number;
  keywords: string[];
}

export interface RubricLevels {
  excellent?: string;
  satisfactory?: string;
  needs_improvement?: string;
}

export interface QuestionSettings {
  match_threshold?: number | null;
  partial_threshold?: number | null;
}

export interface Question {
  id: string;
  assessment_id: string;
  order: number;
  text: string;
  max_marks: number;
  reference_answer: string;
  rubric: RubricItem[];
  rubric_levels: RubricLevels;
  settings: QuestionSettings;
  rubric_version: number;
  created_at: string;
  updated_at: string;
}

export interface Assessment {
  id: string;
  title: string;
  subject: string;
  instructions: string;
  status: AssessmentStatus;
  deadline: string | null;
  assigned_student_ids: string[];
  question_count: number;
  total_marks: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  submission_counts: SubmissionCounts;
}

export interface AssessmentDetail extends Assessment {
  questions: Question[];
}

export interface StudentAssessment {
  id: string;
  title: string;
  subject: string;
  instructions: string;
  status: AssessmentStatus;
  deadline: string | null;
  deadline_passed: boolean;
  question_count: number;
  total_marks: number;
  teacher_name: string;
  my_status: StudentStatus;
  submission_id: string | null;
  submitted_at: string | null;
}

export interface StudentQuestion {
  id: string;
  order: number;
  text: string;
  max_marks: number;
}

export interface StudentAssessmentDetail extends StudentAssessment {
  questions: StudentQuestion[];
  answers: { question_id: string; text: string }[];
  can_edit: boolean;
}

export interface Evidence {
  text: string;
  start: number;
  end: number;
}

export interface Concept {
  id: string;
  label: string;
  description: string;
  marks: number;
  level: Level;
  awarded: number;
  combined_score: number;
  semantic_score: number;
  lexical_score: number;
  evidence: Evidence | null;
  matched_terms: string[];
  ambiguous: boolean;
  reason: string;
  note: string | null;
  keyword_list_evidence: boolean;
  recall_score?: number;
  /** v3 correctness safeguard that affected this concept */
  issue?: "misattributed" | "reversed_comparison" | "negated" | "antonym" | "echo" | null;
}

export interface Flag {
  code: string;
  severity: "info" | "review";
  message: string;
}

export interface Feedback {
  summary: string;
  strengths: string[];
  partial: string[];
  missing: string[];
  suggestions: string[];
  text: string;
}

export interface EngineResult {
  suggested_score: number;
  max_marks: number;
  concepts: Concept[];
  holistic_similarity: number | null;
  relevance_ratio: number | null;
  word_count: number;
  flags: Flag[];
  confidence: Confidence;
  needs_review: boolean;
  feedback: Feedback;
  corrections: { original: string; interpreted_as: string }[];
  metadata: {
    engine_version: string;
    backend: string;
    model_name: string;
    fallback_reason: string | null;
    config: Record<string, unknown>;
    config_fingerprint: string;
    rubric_fingerprint: string;
  };
}

export interface Evaluation {
  id: string;
  submission_id: string;
  question_id: string;
  version: number;
  rubric_version: number;
  rubric_outdated: boolean;
  engine_version: string;
  backend: string;
  model_name: string;
  config_fingerprint: string;
  rubric_fingerprint: string;
  ai_score: number;
  max_marks: number;
  teacher_score: number | null;
  final_score: number;
  adjustment_reason: string;
  teacher_feedback: string;
  status: "ai_suggested" | "reviewed";
  published: boolean;
  evaluated_at: string;
  reviewed_at: string | null;
  published_at: string | null;
  history_count: number;
  result: EngineResult;
}

export interface QuestionReview {
  question_id: string;
  order: number;
  text: string;
  max_marks: number;
  reference_answer: string;
  rubric_levels: RubricLevels;
  rubric_version: number;
  answer: string;
  evaluation: Evaluation | null;
}

export interface SubmissionReview {
  id: string;
  assessment_id: string;
  assessment_title: string;
  subject: string;
  student: StudentBrief;
  status: SubmissionStatus;
  submitted_at: string | null;
  published_at: string | null;
  ai_total: number | null;
  final_total: number | null;
  max_total: number;
  questions: QuestionReview[];
  source: string | null;
}

export interface TeacherSubmissionItem {
  id: string;
  student: StudentBrief;
  status: SubmissionStatus;
  submitted_at: string | null;
  updated_at: string;
  question_count: number;
  evaluated_count: number;
  needs_review_count: number;
  ai_total: number | null;
  final_total: number | null;
  max_total: number;
  rubric_outdated: boolean;
  source: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

export interface StudentSubmissionItem {
  id: string;
  assessment_id: string;
  assessment_title: string;
  subject: string;
  status: SubmissionStatus;
  submitted_at: string | null;
  updated_at: string;
  published_at: string | null;
  total_score: number | null;
  max_total: number;
}

export interface HistoryItem {
  version: number;
  rubric_version: number;
  engine_version: string;
  config_fingerprint: string;
  ai_score: number;
  teacher_score: number | null;
  final_score: number;
  evaluated_at: string;
  archived_at: string;
  archive_reason: string;
}

export interface ResultSummary {
  submission_id: string;
  assessment_id: string;
  assessment_title: string;
  subject: string;
  total_score: number;
  max_total: number;
  percentage: number;
  submitted_at: string | null;
  published_at: string | null;
}

export interface StudentConcept {
  label: string;
  description: string;
  level: Level;
  awarded: number;
  marks: number;
  evidence: Evidence | null;
}

export interface StudentQuestionResult {
  question_id: string;
  order: number;
  text: string;
  max_marks: number;
  answer: string;
  final_score: number;
  ai_score: number;
  adjusted_by_teacher: boolean;
  concepts: StudentConcept[];
  feedback: Feedback;
  teacher_feedback: string;
}

export interface ResultDetail extends ResultSummary {
  questions: StudentQuestionResult[];
}

export interface TeacherOverview {
  assessments_total: number;
  assessments_by_status: Record<AssessmentStatus, number>;
  submissions_awaiting_evaluation: number;
  submissions_awaiting_publication: number;
  results_published: number;
  answers_flagged_for_review: number;
  average_published_percentage: number | null;
}

export interface ConceptStat {
  id: string;
  label: string;
  matched: number;
  partial: number;
  missing: number;
  missing_rate: number | null;
}

export interface AssessmentAnalytics {
  assessment: { id: string; title: string; subject: string; status: AssessmentStatus };
  submission_status: SubmissionCounts;
  basis: { evaluated: number; published: number };
  average_percentage: number | null;
  median_percentage: number | null;
  highest_percentage: number | null;
  lowest_percentage: number | null;
  distribution: { range: string; count: number }[];
  questions: {
    question_id: string;
    order: number;
    text: string;
    max_marks: number;
    n: number;
    average_score: number | null;
    average_percentage: number | null;
    concepts: ConceptStat[];
  }[];
  review: {
    evaluations: number;
    reviewed: number;
    adjusted: number;
    mean_absolute_adjustment: number | null;
    flagged_for_review: number;
  };
}

export interface StudentProgress {
  results: {
    submission_id: string;
    assessment_title: string;
    subject: string;
    published_at: string | null;
    score: number;
    max_total: number;
    percentage: number;
  }[];
  average_percentage: number | null;
  best_percentage: number | null;
  most_missed_concepts: { label: string; count: number }[];
}
