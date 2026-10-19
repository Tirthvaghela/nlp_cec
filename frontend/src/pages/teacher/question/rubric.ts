// Rubric rows as edited in the question editor, and validation mirroring the API (backend/app/schemas/assessment.py):
// 1-12 criteria, unique labels of 1-120 characters, descriptions of 3-600 characters, marks in steps of 0.5 that add
// up exactly to the question's maximum marks.
import type { RubricItem } from "@/lib/types";
import { fmtMarks } from "@/lib/utils";

export interface RubricRow { key: string; id?: string; label: string; description: string; marks: string; keywords: string }

export const MAX_CRITERIA = 12;

let seq = 0;
export const newRow = (r?: Partial<RubricRow>): RubricRow => ({ key: `r${seq++}`, label: "", description: "", marks: "1", keywords: "", ...r });

export const rowsFromRubric = (items: RubricItem[]): RubricRow[] =>
  items.map((r) => newRow({ id: r.id, label: r.label, description: r.description, marks: String(r.marks), keywords: r.keywords.join(", ") }));

export const isHalfStep = (n: number) => n > 0 && Math.abs(n * 2 - Math.round(n * 2)) < 1e-9;

export function parseMarks(value: string): number {
  const n = Number(value.trim().replace(",", "."));
  return value.trim() === "" ? Number.NaN : n;
}

export function rubricTotal(rows: RubricRow[]): number {
  return rows.reduce((s, r) => s + (Number.isFinite(parseMarks(r.marks)) ? parseMarks(r.marks) : 0), 0);
}

export interface RubricErrors {
  rows: Record<string, { label?: string; description?: string; marks?: string }>;
  summary: string | null;
}

export function validateRubric(rows: RubricRow[], maxMarks: number): RubricErrors {
  const out: RubricErrors = { rows: {}, summary: null };
  rows.forEach((r) => {
    const e: RubricErrors["rows"][string] = {};
    if (!r.label.trim()) e.label = "Name the criterion.";
    else if (r.label.trim().length > 120) e.label = "Use at most 120 characters.";
    if (r.description.trim().length < 3) e.description = "Describe what a good answer says (at least 3 characters).";
    else if (r.description.trim().length > 600) e.description = "Use at most 600 characters.";
    const m = parseMarks(r.marks);
    if (!isHalfStep(m) || m > 100) e.marks = "Enter marks in steps of 0.5, for example 1 or 1.5.";
    if (Object.keys(e).length) out.rows[r.key] = e;
  });
  const labels = rows.map((r) => r.label.trim().toLowerCase()).filter(Boolean);
  if (rows.length > MAX_CRITERIA) out.summary = `Use at most ${MAX_CRITERIA} criteria.`;
  else if (new Set(labels).size !== labels.length) out.summary = "Criterion names must be unique.";
  else if (rows.length && Number.isFinite(maxMarks) && Math.abs(rubricTotal(rows) - maxMarks) > 1e-9) {
    out.summary = `Rubric total does not match the question's maximum marks: the criteria add up to ${fmtMarks(rubricTotal(rows))}, the question is worth ${fmtMarks(maxMarks)}.`;
  }
  return out;
}

export function rubricPayload(rows: RubricRow[]) {
  return rows.map((r) => ({
    ...(r.id ? { id: r.id } : {}),
    label: r.label.trim(),
    description: r.description.trim(),
    marks: parseMarks(r.marks),
    keywords: r.keywords.split(",").map((k) => k.trim()).filter(Boolean),
  }));
}

/** A drafted rubric must already be valid; it is shown as an error otherwise, never silently changed. */
export function draftProblem(draft: { label: string; description: string; marks: number }[], maxMarks: number): string | null {
  if (!draft.length) return "The drafted rubric has no criteria.";
  const rows = draft.map((d) => newRow({ label: d.label, description: d.description, marks: String(d.marks) }));
  const v = validateRubric(rows, maxMarks);
  const first = Object.values(v.rows)[0];
  return v.summary ?? (first ? Object.values(first)[0] ?? null : null);
}
