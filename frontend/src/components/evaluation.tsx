// Evaluation components (STYLEGUIDE §10): evidence highlighted inside the answer, missing key points, the suggested
// mark card, rubric breakdown bars, the teacher's concept list and the student feedback card. Everything shown comes
// from the evaluator's result; nothing is inferred or invented here.
import { BookOpen, Minus, TriangleAlert } from "lucide-react";
import { Fragment, useState, type ReactNode } from "react";

import { ConfidenceBadge, LevelTag, Marks } from "@/components/common";
import { RichText } from "@/components/RichText";
import { Segmented } from "@/components/ui/tabs";
import { Alert, Overline } from "@/components/ui/primitives";
import { buildSegments } from "@/lib/highlight";
import { hasFormatting } from "@/lib/markdown";
import { conceptId } from "@/lib/status";
import type { Concept, Confidence, Feedback, Flag, Level, StudentConcept } from "@/lib/types";
import { cn, fmtMarks, fmtScore } from "@/lib/utils";

const LEVEL_RANK: Record<Level, number> = { matched: 2, partial: 1, missing: 0 };
const MARK_CLS: Record<Level, string> = {
  matched: "rounded-[3px] bg-hl-100 shadow-[inset_0_-2px_0_var(--color-hl-500)]",
  partial: "bg-transparent underline decoration-dashed decoration-2 decoration-ink-400 underline-offset-[5px]",
  missing: "",
};

/** The student's answer with matched (highlighter) and partial (dashed ink) evidence, as stored - offsets are exact. */
export function AnswerWithEvidence({ answer, concepts }: { answer: string; concepts: (Concept | StudentConcept)[] }) {
  if (!answer.trim()) {
    return <p className="m-0 rounded-md border border-dashed border-slate-200 p-5 text-center text-body text-slate-500">No answer was written for this question.</p>;
  }
  const sources = concepts.map((c, i) => ({ label: c.label, level: c.level, evidence: c.evidence, index: i + 1 }));
  const segments = buildSegments(answer, sources);
  return (
    <p className="m-0 whitespace-pre-wrap break-words text-feedback text-slate-900">
      {segments.map((seg, i) => {
        if (!seg.covering.length) return <Fragment key={i}>{seg.text}</Fragment>;
        const best = seg.covering.reduce((a, b) => (LEVEL_RANK[b.level] > LEVEL_RANK[a.level] ? b : a));
        const labels = seg.covering.map((c) => `${c.index}. ${c.label}`).join(", ");
        const next = segments[i + 1];
        const ends = seg.covering.filter((c) => !next?.covering.some((n) => n.index === c.index));
        return (
          <Fragment key={i}>
            <mark className={cn("text-slate-900", MARK_CLS[best.level])} title={`Evidence for: ${labels}`}>{seg.text}</mark>
            {ends.length > 0 && <sup className="tabular ml-px text-micro font-semibold text-slate-600" aria-hidden>{ends.map((c) => conceptId(c.index)).join(",")}</sup>}
          </Fragment>
        );
      })}
    </p>
  );
}

export function EvidenceLegend({ showMissing = true }: { showMissing?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-caption text-slate-600" aria-label="Highlight legend">
      <span className="flex items-center gap-2"><span className={cn("px-1 text-slate-900", MARK_CLS.matched)}>text</span>Concept matched</span>
      <span className="flex items-center gap-2"><span className={cn("text-slate-900", MARK_CLS.partial)}>text</span>Partially matched</span>
      {showMissing && <span className="flex items-center gap-2"><Minus className="size-4 text-danger" aria-hidden />Missing key point (listed below)</span>}
    </div>
  );
}

/** Student or teacher answer: evidence view, plus a formatted view when the answer uses lists, tables or emphasis. */
export function AnswerView({ answer, concepts, wordCount }: { answer: string; concepts: (Concept | StudentConcept)[]; wordCount?: number }) {
  const [view, setView] = useState<"evidence" | "formatted">("evidence");
  const formatted = hasFormatting(answer);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Overline>Answer{wordCount !== undefined ? ` · ${wordCount} words` : ""}</Overline>
        {formatted && (
          <Segmented size="sm" label="Answer view" value={view} onChange={setView}
            options={[{ value: "evidence", label: "Evidence" }, { value: "formatted", label: "Formatted" }]} />
        )}
      </div>
      {view === "formatted" && formatted
        ? <RichText text={answer} size="feedback" />
        : <AnswerWithEvidence answer={answer} concepts={concepts} />}
      {view === "evidence" && <EvidenceLegend />}
      <MissingPoints concepts={concepts} />
    </div>
  );
}

/** Missing key points listed under the answer: dashed red border, minus icon, rubric reference and marks. */
export function MissingPoints({ concepts }: { concepts: (Concept | StudentConcept)[] }) {
  const missing = concepts.map((c, i) => ({ c, i })).filter(({ c }) => c.level === "missing");
  if (!missing.length) return null;
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0" aria-label="Missing key points">
      {missing.map(({ c, i }) => (
        <li key={i} className="flex items-start gap-3 rounded-sm border-[1.5px] border-dashed border-danger-line bg-white px-4 py-3">
          <Minus className="mt-0.5 size-5 text-danger" aria-hidden />
          <span className="min-w-0 flex-1 text-body text-slate-900">
            <span className="tabular mr-2 text-small font-semibold text-slate-600">{conceptId(i + 1)}</span>{c.label}
            {c.description && <span className="block text-small text-slate-600">{c.description}</span>}
          </span>
          <span className="tabular whitespace-nowrap text-small text-slate-600">{fmtMarks(c.marks)} {c.marks === 1 ? "mark" : "marks"}</span>
        </li>
      ))}
    </ul>
  );
}

/** Suggested mark card: overline, hero score, confidence badge and three evidence tiles. Actions are passed in. */
export function SuggestedMarkCard({ score, max, confidence, similarity, matched, total, actions }: {
  score: number; max: number; confidence: Confidence; similarity: number | null; matched: number; total: number; actions?: ReactNode;
}) {
  const tiles = [
    { label: "Semantic match", value: similarity != null ? similarity.toFixed(2) : "—" },
    { label: "Concepts", value: `${matched} of ${total}` },
    { label: "Confidence", value: confidence === "high" ? "High" : confidence === "medium" ? "Medium" : "Low" },
  ];
  return (
    <section className="flex flex-col gap-5 rounded-md border border-slate-100 bg-white p-6" aria-label="Suggested mark">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <Overline>Suggested mark</Overline>
          <Marks earned={score} max={max} size="hero" />
        </div>
        <ConfidenceBadge confidence={confidence} />
      </div>
      <dl className="m-0 grid grid-cols-3 gap-2">
        {tiles.map((t) => (
          <div key={t.label} className="flex min-w-0 flex-col gap-1 rounded-sm bg-slate-50 px-3 py-2">
            <dt className="text-caption text-slate-500">{t.label}</dt>
            <dd className="tabular m-0 text-body font-semibold text-slate-900">{t.value}</dd>
          </div>
        ))}
      </dl>
      {actions && <div className="grid gap-3 sm:grid-cols-2 [&>*]:w-full">{actions}</div>}
    </section>
  );
}

/** One row per criterion: name, awarded / max, and an 8px bar (ink for awarded marks, slate for the rest). */
export function RubricBreakdown({ items }: { items: { label: string; awarded: number; marks: number }[] }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-4 p-0" aria-label="Rubric breakdown">
      {items.map((it, i) => {
        const p = it.marks > 0 ? Math.max(0, Math.min(1, it.awarded / it.marks)) : 0;
        return (
          <li key={i} className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between gap-3">
              <span className="min-w-0 text-body text-slate-900"><span className="tabular mr-2 text-small font-semibold text-slate-500">{conceptId(i + 1)}</span>{it.label}</span>
              <Marks earned={it.awarded} max={it.marks} size="sm" />
            </div>
            <div className="flex h-2 gap-[2px]" role="img" aria-label={`${it.label}: ${fmtMarks(it.awarded)} of ${fmtMarks(it.marks)} marks`}>
              {p > 0 && <span className="h-full rounded-full bg-ink-600" style={{ width: `${p * 100}%` }} />}
              {p < 1 && <span className="h-full flex-1 rounded-full bg-slate-100" />}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Teacher view: every concept with its level, the reason, the evidence quote and the marks. */
export function ConceptBreakdown({ concepts }: { concepts: Concept[] }) {
  return (
    <ol className="m-0 list-none p-0">
      {concepts.map((c, i) => (
        <li key={c.id} className="grid grid-cols-[32px_minmax(0,1fr)_auto] items-start gap-3 border-b border-slate-100 px-6 py-4 last:border-b-0">
          <span className="tabular pt-1 text-small font-semibold text-slate-500">{conceptId(i + 1)}</span>
          <div className="flex min-w-0 flex-col gap-2">
            <span className="text-body font-medium text-slate-900">{c.label}</span>
            <span className="flex flex-wrap items-center gap-2">
              <LevelTag level={c.level} />
              <span className="tabular text-caption text-slate-500">score {c.combined_score.toFixed(2)}</span>
              {c.ambiguous && <span className="inline-flex items-center gap-1 text-caption text-warning-text" title="The concept score is close to a threshold"><TriangleAlert className="size-4" aria-hidden />Borderline</span>}
            </span>
            {c.evidence && <span className="text-small text-slate-800">“{c.evidence.text}”</span>}
            <span className="text-caption text-slate-500">
              {c.reason}
              {c.matched_terms.length > 0 && <> Matched terms: {c.matched_terms.slice(0, 6).join(", ")}.</>}
            </span>
            {c.note && <span className="text-caption text-warning-text">{c.note}</span>}
          </div>
          <Marks earned={c.awarded} max={c.marks} />
        </li>
      ))}
    </ol>
  );
}

/** Teacher view of the generated feedback (what the student will see). */
export function FeedbackPanel({ feedback, compact }: { feedback: Feedback; compact?: boolean }) {
  const sections: { title: string; items: string[] }[] = [
    { title: "What you did well", items: feedback.strengths },
    { title: "Needs more detail", items: feedback.partial },
    { title: "Missing points", items: feedback.missing },
    { title: "How to improve", items: feedback.suggestions },
  ];
  return (
    <div className="flex flex-col gap-4">
      <p className="m-0 text-body text-slate-800">{feedback.summary}</p>
      <div className={cn("grid gap-x-6 gap-y-4", !compact && "md:grid-cols-2")}>
        {sections.filter((s) => s.items.length).map(({ title, items }) => (
          <section key={title} className="flex flex-col gap-1">
            <h4 className="m-0 text-small font-semibold text-slate-800">{title}</h4>
            <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-small text-slate-600">
              {items.map((it, i) => <li key={i}>{it}</li>)}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

function joinLabels(labels: string[]): string {
  if (labels.length <= 1) return labels[0] ?? "";
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

/** Student feedback card (ink-900): score ring, a lead sentence built from what the evaluator found, then
 *  "What you did well" and "To reach max", and one learning action. */
export function StudentFeedbackCard({ score, max, concepts, feedback, teacherComment, action }: {
  score: number; max: number; concepts: StudentConcept[]; feedback: Feedback; teacherComment?: string; action?: ReactNode;
}) {
  const matched = concepts.filter((c) => c.level === "matched").map((c) => c.label);
  const partial = concepts.filter((c) => c.level === "partial").map((c) => c.label);
  const lead = matched.length
    ? `You covered ${joinLabels(matched)}.`
    : partial.length ? `You made a start on ${joinLabels(partial)}.` : "This answer did not yet cover the key points of the question.";
  const reached = score >= max - 1e-9;
  const toReach = feedback.suggestions.filter((s) => !s.startsWith("Well done"));
  const ratio = max > 0 ? Math.max(0, Math.min(1, score / max)) : 0;
  const r = 30, circ = 2 * Math.PI * r;
  return (
    <section className="flex flex-col gap-5 rounded-lg bg-ink-900 p-6 text-white" aria-label="Your feedback">
      <div className="flex items-center gap-5">
        <div className="relative size-[76px] flex-none" role="img" aria-label={`${fmtScore(score)} out of ${fmtMarks(max)} marks`}>
          <svg viewBox="0 0 76 76" className="size-full -rotate-90">
            <circle cx="38" cy="38" r={r} fill="none" stroke="var(--color-ink-700)" strokeWidth="7" />
            <circle cx="38" cy="38" r={r} fill="none" stroke="var(--color-hl-300)" strokeWidth="7" strokeLinecap="round"
              strokeDasharray={`${circ * ratio} ${circ}`} />
          </svg>
          <span className="tabular absolute inset-0 grid place-items-center text-body font-semibold">{fmtScore(score)}</span>
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <span className="tabular text-small text-ink-200">{fmtScore(score)} / {fmtMarks(max)} marks</span>
          <p className="m-0 text-h4 font-semibold">{lead}</p>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="flex flex-col gap-2 rounded-md bg-ink-800 p-4">
          <h4 className="m-0 text-small font-semibold text-hl-300">What you did well</h4>
          {feedback.strengths.length
            ? <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-small text-ink-50">{feedback.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
            : <p className="m-0 text-small text-ink-100">No concept was fully covered yet. The points on the right show where to start.</p>}
        </div>
        <div className="flex flex-col gap-2 rounded-md bg-ink-800 p-4">
          <h4 className="m-0 text-small font-semibold text-white">{reached ? "Full marks reached" : `To reach ${fmtMarks(max)} / ${fmtMarks(max)}`}</h4>
          {toReach.length && !reached
            ? <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-small text-ink-50">{toReach.slice(0, 4).map((s, i) => <li key={i}>{s}</li>)}</ul>
            : <p className="m-0 text-small text-ink-100">{feedback.suggestions[0] ?? "Every key point is covered."}</p>}
        </div>
      </div>
      {teacherComment && (
        <div className="flex flex-col gap-1 border-t border-ink-700 pt-4">
          <h4 className="m-0 text-small font-semibold text-white">Your teacher's comment</h4>
          <p className="m-0 whitespace-pre-wrap text-small text-ink-50">{teacherComment}</p>
        </div>
      )}
      {action}
    </section>
  );
}

/** Student view: plain-language concept coverage without internal similarity numbers. */
export function StudentConceptList({ concepts }: { concepts: StudentConcept[] }) {
  return (
    <ul className="m-0 flex list-none flex-col gap-3 p-0">
      {concepts.map((c, i) => (
        <li key={i} className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
          <span className="flex min-w-0 flex-col gap-1">
            <span className="flex flex-wrap items-center gap-2"><LevelTag level={c.level} /><span className="text-body text-slate-900">{c.label}</span></span>
            {c.description && <span className="text-small text-slate-600">{c.description}</span>}
          </span>
          <Marks earned={c.awarded} max={c.marks} size="sm" />
        </li>
      ))}
    </ul>
  );
}

export function ReviewFlags({ flags }: { flags: Flag[] }) {
  if (!flags.length) return <p className="m-0 text-small text-slate-500">No warning signs were detected for this answer.</p>;
  const review = flags.filter((f) => f.severity === "review");
  const info = flags.filter((f) => f.severity !== "review");
  return (
    <div className="flex flex-col gap-2">
      {review.map((f, i) => <Alert key={i} tone="warning" title="Review flag">{f.message}</Alert>)}
      {info.map((f, i) => <p key={i} className="m-0 flex items-start gap-2 text-small text-slate-600"><BookOpen className="mt-0.5 size-4" aria-hidden />{f.message}</p>)}
    </div>
  );
}
