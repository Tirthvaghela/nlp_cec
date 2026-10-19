// Question-authoring drafts: POST /api/generation/reference-answer and /api/generation/rubric (backend/app/routers/
// generation.py). Drafts are suggestions; nothing is stored until the teacher saves the question.
import { api } from "@/lib/api";

export interface ReferenceDraft {
  reference_answer: string;
  model: string;
}

export interface RubricDraft {
  rubric: { label: string; description: string; marks: number }[];
  /** "model": drafted by the language model; "derived": built locally from the reference answer's sentences. */
  source: "model" | "derived";
  model: string | null;
}

export function draftReferenceAnswer(question: string, maxMarks: number, signal?: AbortSignal) {
  return api.post<ReferenceDraft>("/api/generation/reference-answer", { question, max_marks: maxMarks }, undefined, signal);
}

export function draftRubric(question: string, maxMarks: number, referenceAnswer: string, signal?: AbortSignal) {
  return api.post<RubricDraft>("/api/generation/rubric", { question, max_marks: maxMarks, reference_answer: referenceAnswer }, undefined, signal);
}
