// Teacher review of one submission. The suggested mark and the teacher's final mark are shown side by side and stored
// separately; a suggestion becomes final only when the teacher accepts or adjusts it, and nothing reaches the student
// before the teacher publishes.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, History, Minus, Plus, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";

import { BackLink, DemoBadge, ErrorState, LoadingCards, Marks, PageBody, PageHeader, SubmissionStatusBadge } from "@/components/common";
import { RichText } from "@/components/RichText";
import { AnswerView, ConceptBreakdown, FeedbackPanel, ReviewFlags, SuggestedMarkCard } from "@/components/evaluation";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Dialog, DialogContent } from "@/components/ui/dialog";
import { Alert, Card, Field, FieldError, Input, KpiRow, KpiTile, Overline, Skeleton, StatusBadge, Table, Td, Textarea, Th, type BadgeTone } from "@/components/ui/primitives";
import { ApiError, api, errorMessage } from "@/lib/api";
import { wordCountOf } from "@/lib/markdown";
import type { Evaluation, HistoryItem, QuestionReview, SubmissionReview } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn, fmtDate, fmtMarks, fmtScore, plural } from "@/lib/utils";

function questionStatus(q: QuestionReview): { label: string; tone: BadgeTone } {
  const ev = q.evaluation;
  if (!ev) return { label: "Not evaluated", tone: "slate" };
  if (ev.rubric_outdated) return { label: "Rubric changed", tone: "warning" };
  if (ev.status === "reviewed") return { label: "Reviewed", tone: "success" };
  if (ev.result.needs_review) return { label: "Needs review", tone: "warning" };
  return { label: "Evaluated", tone: "ink" };
}

export function SubmissionReviewPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState<null | "evaluate" | "publish" | "unpublish">(null);
  const [sel, setSel] = useState(0);

  const review = useQuery({ queryKey: ["review", id], queryFn: () => api.get<SubmissionReview>(`/api/evaluations/submission/${id}`) });
  const data = review.data;
  usePageTitle(data ? `${data.student.name} · ${data.assessment_title}` : "Review");

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["review", id] });
    if (data) {
      qc.invalidateQueries({ queryKey: ["submissions", data.assessment_id] });
      qc.invalidateQueries({ queryKey: ["assessment", data.assessment_id] });
      qc.invalidateQueries({ queryKey: ["analytics", data.assessment_id] });
    }
    qc.invalidateQueries({ queryKey: ["overview"] });
    qc.invalidateQueries({ queryKey: ["assessments"] });
  };

  const evaluate = useMutation({
    mutationFn: () => api.post<SubmissionReview>(`/api/evaluations/submission/${id}`, {}, { allow_unpublish: data?.status === "published" }),
    onSuccess: (r) => { qc.setQueryData(["review", id], r); invalidate(); setConfirm(null); toast.success("Evaluation finished. Review the suggested marks below."); },
    onError: (err) => { setConfirm(null); toast.error(errorMessage(err)); },
  });
  const publish = useMutation({
    mutationFn: () => api.post(`/api/results/submission/${id}/publish`),
    onSuccess: () => { invalidate(); setConfirm(null); toast.success(data ? `Marks published to ${data.student.name}.` : "Marks published."); },
    onError: (err) => { setConfirm(null); toast.error(errorMessage(err)); },
  });
  const unpublish = useMutation({
    mutationFn: () => api.post(`/api/results/submission/${id}/unpublish`),
    onSuccess: () => { invalidate(); setConfirm(null); toast.success("Result unpublished. You can edit it again."); },
    onError: (err) => { setConfirm(null); toast.error(errorMessage(err)); },
  });

  if (review.isLoading) return <PageBody><LoadingCards /></PageBody>;
  if (review.isError || !data) return <PageBody><ErrorState message={errorMessage(review.error)} onRetry={() => review.refetch()} /></PageBody>;

  const evaluated = data.questions.length > 0 && data.questions.every((q) => q.evaluation);
  const outdated = data.questions.some((q) => q.evaluation?.rubric_outdated);
  const unreviewed = data.questions.filter((q) => q.evaluation && q.evaluation.status !== "reviewed").length;
  const unreviewedFlags = data.questions.filter((q) => q.evaluation?.result.needs_review && q.evaluation.status !== "reviewed").length;
  const published = data.status === "published";
  const answered = data.questions.filter((q) => q.answer.trim()).length;
  const rubricV = Math.max(0, ...data.questions.map((q) => q.rubric_version));
  const index = Math.min(sel, Math.max(0, data.questions.length - 1));
  const current = data.questions[index];

  return (
    <PageBody className="gap-6">
      <PageHeader
        back={<BackLink to={`/teacher/submissions?assessment=${data.assessment_id}`}>{data.assessment_title}</BackLink>}
        title={data.student.name}
        status={<>
          <SubmissionStatusBadge status={data.status} needsReview={unreviewedFlags > 0} />
          {data.source === "seed" && <DemoBadge />}
          <span className="tabular">Submitted {fmtDate(data.submitted_at)}{rubricV ? ` · rubric v${rubricV}` : ""}</span>
        </>}
        actions={evaluated && (published
          ? <Button variant="secondary" onClick={() => setConfirm("unpublish")}>Unpublish result</Button>
          : <Button variant={unreviewed ? "secondary" : "primary"} disabled={outdated} onClick={() => setConfirm("publish")}>Publish marks</Button>)} />

      {evaluated && (
        <KpiRow>
          <KpiTile label="Suggested total" value={<Marks earned={data.ai_total} max={data.max_total} size="score" />} caption="Advisory, from the evaluator" />
          <KpiTile label="Final total" value={<Marks earned={data.final_total} max={data.max_total} size="score" />} caption="What the student sees after publishing" />
          <KpiTile label="Reviewed" value={`${data.questions.length - unreviewed} of ${data.questions.length}`} caption={unreviewedFlags ? `${plural(unreviewedFlags, "flagged answer")} not yet reviewed` : "No unreviewed flags"} />
        </KpiRow>
      )}

      {evaluated && (
        published ? <Alert tone="success" title={`Published ${fmtDate(data.published_at)}`}>Published results are read-only. Unpublish to make changes.</Alert>
          : outdated ? <Alert tone="warning" title="A rubric changed after this evaluation" action={<Button size="sm" variant="secondary" onClick={() => setConfirm("evaluate")}>Re-evaluate</Button>}>Re-evaluate before publishing so the marks match the current rubric.</Alert>
            : unreviewedFlags ? <Alert tone="warning" title={`${plural(unreviewedFlags, "flagged answer")} ${unreviewedFlags === 1 ? "needs" : "need"} your review`}>Check the evidence before you accept or adjust the suggested marks.</Alert>
              : null
      )}

      {!evaluated && !evaluate.isPending && (
        <Card className="flex flex-col items-center gap-3 p-8 text-center sm:p-12">
          <h2 className="m-0 text-h3 font-semibold text-slate-900">Not evaluated yet</h2>
          <p className="m-0 max-w-[56ch] text-body text-slate-600">
            {answered} of {plural(data.questions.length, "answer")} written. The evaluator compares each answer with the reference answer and the rubric,
            and suggests marks for you to review.
          </p>
          <Button className="mt-2" onClick={() => evaluate.mutate()}>Evaluate answers</Button>
        </Card>
      )}
      {evaluate.isPending && (
        <Card className="flex flex-col gap-3 p-6" role="status" aria-live="polite">
          <span className="text-body text-slate-600">Evaluating {plural(data.questions.length, "answer")}</span>
          <Skeleton className="w-3/5" /><Skeleton className="w-[85%]" /><Skeleton className="w-[72%]" /><Skeleton className="h-24 w-full" />
        </Card>
      )}

      {evaluated && !evaluate.isPending && current && (
        <>
          <div role="tablist" aria-label="Questions" className="grid gap-2 [grid-template-columns:repeat(auto-fit,minmax(min(200px,100%),1fr))]">
            {data.questions.map((q, i) => {
              const st = questionStatus(q);
              const ev = q.evaluation!;
              const active = i === index;
              return (
                <button key={q.question_id} role="tab" aria-selected={active} type="button" onClick={() => setSel(i)}
                  className={cn("flex min-h-11 flex-col items-start gap-2 rounded-md border px-4 py-3 text-left transition-colors duration-150",
                    active ? "border-ink-600 bg-ink-50" : "border-slate-100 bg-white hover:border-ink-200")}>
                  <span className="text-body font-semibold text-slate-900">Question {i + 1}</span>
                  <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
                  <span className="tabular text-small text-slate-600">
                    {ev.status === "reviewed" ? `Final ${fmtMarks(ev.final_score)} / ${fmtMarks(ev.max_marks)}` : `Suggested ${fmtMarks(ev.ai_score)} / ${fmtMarks(ev.max_marks)}`}
                  </span>
                </button>
              );
            })}
          </div>
          <QuestionReviewPanel key={current.question_id + current.evaluation!.version} q={current} index={index} locked={published}
            onSaved={invalidate} onReevaluate={() => setConfirm("evaluate")}
            nextLabel={index < data.questions.length - 1 ? `Save and go to question ${index + 2}` : null}
            onNext={() => setSel((s) => Math.min(s + 1, data.questions.length - 1))} />
        </>
      )}

      <ConfirmDialog open={confirm === "evaluate"} onOpenChange={(o) => !o && setConfirm(null)} loading={evaluate.isPending} loadingLabel="Evaluating"
        title="Re-evaluate this submission?" confirmLabel="Re-evaluate answers" onConfirm={() => evaluate.mutate()}
        description={<>
          <p>A new evaluation version is created with the current rubric. The previous version stays in the history.</p>
          <p>Your mark adjustments and comments for this submission will need to be made again.</p>
          {published && <p className="font-medium text-danger">This result is published. Re-evaluating unpublishes it until you publish again.</p>}
        </>} />
      <ConfirmDialog open={confirm === "publish"} onOpenChange={(o) => !o && setConfirm(null)} loading={publish.isPending} loadingLabel="Publishing"
        title="Publish these marks?" confirmLabel="Publish marks" onConfirm={() => publish.mutate()}
        description={<>
          <p>{data.student.name} will see a final mark of <strong className="tabular font-semibold text-slate-900">{fmtMarks(data.final_total)} / {fmtMarks(data.max_total)}</strong>, the feedback for each criterion and your comments.</p>
          {unreviewed > 0 && <p className="font-medium text-warning-text">{plural(unreviewed, "question")} {unreviewed === 1 ? "has" : "have"} not been reviewed. Their suggested marks will be published as final.</p>}
        </>} />
      <ConfirmDialog open={confirm === "unpublish"} onOpenChange={(o) => !o && setConfirm(null)} loading={unpublish.isPending} loadingLabel="Unpublishing"
        title="Unpublish this result?" confirmLabel="Unpublish result" onConfirm={() => unpublish.mutate()}
        description={<p>The student will no longer see the marks and feedback until you publish again.</p>} />
    </PageBody>
  );
}

function QuestionReviewPanel({ q, index, locked, onSaved, onReevaluate, nextLabel, onNext }: {
  q: QuestionReview; index: number; locked: boolean; onSaved: () => void; onReevaluate: () => void; nextLabel: string | null; onNext: () => void;
}) {
  const ev = q.evaluation!;
  const r = ev.result;
  const [historyOpen, setHistoryOpen] = useState(false);
  const [refOpen, setRefOpen] = useState(false);
  const scoreRef = useRef<HTMLInputElement>(null);
  const matched = r.concepts.filter((c) => c.level === "matched").length;
  const reviewed = ev.status === "reviewed";

  const save = useMutation({
    mutationFn: (v: { score: number | null; reason: string; comment: string; advance: boolean }) =>
      api.patch<Evaluation>(`/api/evaluations/${ev.id}`, {
        // null = accept the suggested mark; a number is recorded as the teacher's own mark, even when equal to it.
        teacher_score: v.score, adjustment_reason: v.score === null ? "" : v.reason, teacher_feedback: v.comment, mark_reviewed: true,
      }),
    onSuccess: (_r, v) => { toast.success(v.score === null ? `Suggested mark ${fmtScore(ev.ai_score)} accepted.` : "Final mark saved."); onSaved(); if (v.advance) onNext(); },
  });

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-6">
        <Card className="flex flex-col gap-2 p-5 sm:p-6">
          <Overline>Question {index + 1} · {fmtMarks(q.max_marks)} marks</Overline>
          <RichText text={q.text} size="body-lg" />
        </Card>
        <Card className="p-5 sm:p-6">
          <AnswerView answer={q.answer} concepts={r.concepts} wordCount={wordCountOf(q.answer)} />
        </Card>
        <ReviewFlags flags={r.flags} />
        {r.corrections.length > 0 && !r.flags.some((f) => f.severity !== "review") && (
          <p className="m-0 text-small text-slate-600">Spelling interpreted: {r.corrections.slice(0, 6).map((c) => `“${c.original}” as “${c.interpreted_as}”`).join(", ")}.</p>
        )}
        <Card>
          <button type="button" aria-expanded={refOpen} aria-controls={`ref-${ev.id}`} onClick={() => setRefOpen((o) => !o)}
            className="flex min-h-11 w-full items-center justify-between gap-3 rounded-md border-0 bg-transparent px-6 py-4 text-left text-body font-medium text-slate-900 hover:bg-slate-25">
            Reference answer and performance expectations
            <ChevronDown className={cn("size-[18px] text-slate-500 transition-transform duration-150", refOpen && "rotate-180")} aria-hidden />
          </button>
          {refOpen && (
            <div id={`ref-${ev.id}`} className="flex flex-col gap-4 border-t border-slate-100 px-6 py-5">
              <RichText text={q.reference_answer} empty={<p className="m-0 text-body italic text-slate-500">No reference answer was provided.</p>} />
              {(q.rubric_levels.excellent || q.rubric_levels.satisfactory || q.rubric_levels.needs_improvement) && (
                <dl className="m-0 grid gap-4 border-t border-slate-100 pt-4 md:grid-cols-3">
                  {([["excellent", "Excellent"], ["satisfactory", "Satisfactory"], ["needs_improvement", "Needs improvement"]] as const).map(([k, l]) =>
                    q.rubric_levels[k] ? <div key={k}><dt className="text-small font-semibold text-slate-800">{l}</dt><dd className="m-0 text-small text-slate-600">{q.rubric_levels[k]}</dd></div> : null)}
                </dl>
              )}
            </div>
          )}
        </Card>
        <Card className="flex flex-col gap-3 p-5 sm:p-6">
          <Overline>Generated feedback · shown to the student after publishing</Overline>
          <FeedbackPanel feedback={r.feedback} compact />
        </Card>
      </div>

      <div className="flex min-w-0 flex-col gap-6">
        <SuggestedMarkCard score={ev.ai_score} max={ev.max_marks} confidence={r.confidence} similarity={r.holistic_similarity}
          matched={matched} total={r.concepts.length}
          actions={!locked && <>
            <Button variant={reviewed ? "secondary" : "primary"} loading={save.isPending && save.variables?.score === null} loadingLabel="Saving"
              disabled={save.isPending} onClick={() => save.mutate({ score: null, reason: "", comment: ev.teacher_feedback, advance: false })}>
              Accept {fmtScore(ev.ai_score)}
            </Button>
            <Button variant="secondary" disabled={save.isPending} onClick={() => { scoreRef.current?.focus(); scoreRef.current?.select(); }}>Adjust mark</Button>
          </>} />
        <Card>
          <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-6 py-4">
            <Overline as="h3">Rubric criteria</Overline>
            <span className="tabular text-small text-slate-600">{matched} of {r.concepts.length} matched</span>
          </div>
          <ConceptBreakdown concepts={r.concepts} />
        </Card>
        <TeacherReviewForm ev={ev} locked={locked} save={save} scoreRef={scoreRef} onReevaluate={onReevaluate} nextLabel={nextLabel} />
        <p className="tabular m-0 text-caption text-slate-500">
          Evaluation v{ev.version} · rubric v{ev.rubric_version} · engine {ev.engine_version} ({ev.backend}) · config {ev.config_fingerprint}
          {ev.history_count > 0 && <> · <Button variant="link" size="sm" className="text-caption" icon={<History className="size-3.5" aria-hidden />} onClick={() => setHistoryOpen(true)}>{plural(ev.history_count, "earlier version")}</Button></>}
        </p>
      </div>
      <HistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} evaluationId={ev.id} />
    </div>
  );
}

type SaveMutation = ReturnType<typeof useMutation<Evaluation, Error, { score: number | null; reason: string; comment: string; advance: boolean }>>;

function TeacherReviewForm({ ev, locked, save, scoreRef, onReevaluate, nextLabel }: {
  ev: Evaluation; locked: boolean; save: SaveMutation; scoreRef: React.RefObject<HTMLInputElement | null>; onReevaluate: () => void; nextLabel: string | null;
}) {
  const [score, setScore] = useState(String(ev.final_score));
  const [reason, setReason] = useState(ev.adjustment_reason);
  const [comment, setComment] = useState(ev.teacher_feedback);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setScore(String(ev.final_score));
    setReason(ev.adjustment_reason);
    setComment(ev.teacher_feedback);
  }, [ev.id, ev.version, ev.final_score, ev.adjustment_reason, ev.teacher_feedback]);

  useEffect(() => { if (save.error) setError(save.error instanceof ApiError ? save.error.message : errorMessage(save.error)); }, [save.error]);

  const n = Number(score.replace(",", "."));
  const valid = score.trim() !== "" && !Number.isNaN(n) && n >= 0 && n <= ev.max_marks;
  const changed = valid && Math.abs(n - ev.ai_score) > 1e-9;
  const step = (d: number) => {
    const base = valid ? n : ev.final_score;
    setScore(String(Math.max(0, Math.min(ev.max_marks, Math.round((base + d) * 4) / 4))));
  };

  function submit(advance: boolean) {
    setError(null);
    if (!valid) return setError(`Enter a mark between 0 and ${fmtMarks(ev.max_marks)}.`);
    if (Math.abs(n * 4 - Math.round(n * 4)) > 1e-9) return setError("Use steps of 0.25 marks, for example 2.25 or 2.5.");
    if (changed && !reason.trim()) return setError("Give a short reason for changing the suggested mark.");
    save.mutate({ score: n, reason: reason.trim(), comment: comment.trim(), advance });
  }

  const reviewed = ev.status === "reviewed";
  const head = (
    <div className="flex items-center justify-between gap-3">
      <h3 className="m-0 text-h4 font-semibold text-slate-900">Your decision</h3>
      <StatusBadge tone={reviewed ? "success" : "slate"}>{reviewed ? "Reviewed" : "Not reviewed"}</StatusBadge>
    </div>
  );

  if (locked) {
    return (
      <Card className="flex flex-col gap-3 p-5 sm:p-6">
        {head}
        <div className="flex items-baseline gap-3"><Overline>Final mark</Overline><Marks earned={ev.final_score} max={ev.max_marks} size="score" /></div>
        {ev.adjustment_reason && <p className="m-0 text-body"><span className="text-slate-500">Reason for adjustment:</span> {ev.adjustment_reason}</p>}
        {ev.teacher_feedback && <p className="m-0 text-body"><span className="text-slate-500">Comment to student:</span> {ev.teacher_feedback}</p>}
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-5 p-5 sm:p-6" aria-label="Your decision">
      {head}
      <div className="flex min-w-0 flex-col gap-[6px]">
        <label htmlFor={`score-${ev.id}`} className="text-small font-medium text-slate-800">Final mark</label>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="icon" aria-label="Decrease by 0.25" data-tooltip="Decrease by 0.25" onClick={() => step(-0.25)}><Minus aria-hidden /></Button>
          <div className="flex h-11 items-center overflow-hidden rounded-sm border border-slate-200 bg-white focus-within:border-ink-600 focus-within:shadow-[var(--focus-input)]">
            <input ref={scoreRef} id={`score-${ev.id}`} inputMode="decimal" value={score} onChange={(e) => setScore(e.target.value)}
              aria-describedby={`score-${ev.id}-max`}
              className="tabular w-20 border-0 bg-transparent px-3 text-center text-body font-semibold text-slate-900 focus-visible:shadow-none" />
            <span id={`score-${ev.id}-max`} className="tabular flex h-full items-center border-l border-slate-200 bg-slate-50 px-3 text-small text-slate-600">/ {fmtMarks(ev.max_marks)}</span>
          </div>
          <Button variant="secondary" size="icon" aria-label="Increase by 0.25" data-tooltip="Increase by 0.25" onClick={() => step(0.25)}><Plus aria-hidden /></Button>
        </div>
        {changed && (
          <span className="tabular text-small text-ink-700">{n > ev.ai_score ? "+" : "−"}{fmtMarks(Math.abs(n - ev.ai_score))} from the suggestion. Both values are kept.</span>
        )}
      </div>
      <Field id={`reason-${ev.id}`} label="Reason for adjustment" required={changed} hint={changed ? undefined : "Needed only when you change the suggested mark."}>
        <Input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} placeholder="e.g. The example given is correct but was not matched" />
      </Field>
      <Field id={`comment-${ev.id}`} label="Comment to the student" optional hint="Shown with the generated feedback after publishing.">
        <Textarea value={comment} onChange={(e) => setComment(e.target.value)} maxLength={4000} rows={4} />
      </Field>
      {error && <FieldError>{error}</FieldError>}
      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" onClick={() => submit(Boolean(nextLabel))} loading={save.isPending && save.variables?.score !== null} loadingLabel="Saving"
          disabled={save.isPending}>{nextLabel ?? "Save final mark"}</Button>
        <Button variant="tertiary" icon={<RefreshCw aria-hidden />} disabled={save.isPending} onClick={onReevaluate}>Re-evaluate</Button>
      </div>
    </Card>
  );
}

function HistoryDialog({ open, onOpenChange, evaluationId }: { open: boolean; onOpenChange: (o: boolean) => void; evaluationId: string }) {
  const h = useQuery({ queryKey: ["history", evaluationId], queryFn: () => api.get<HistoryItem[]>(`/api/evaluations/${evaluationId}/history`), enabled: open });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Evaluation history" description="Earlier versions are kept for transparency and reproducibility." className="max-w-[760px]">
        {h.isLoading ? <p className="m-0 text-body text-slate-600">Loading history</p> : h.isError ? <ErrorState message={errorMessage(h.error)} /> : (
          <Table>
            <thead><tr><Th>Version</Th><Th>Rubric</Th><Th className="text-right">Suggested</Th><Th className="text-right">Final</Th><Th>Evaluated</Th><Th>Replaced because</Th></tr></thead>
            <tbody>
              {(h.data ?? []).map((v) => (
                <tr key={v.version}>
                  <Td className="tabular">v{v.version}</Td><Td className="tabular">v{v.rubric_version}</Td>
                  <Td className="tabular text-right">{fmtMarks(v.ai_score)}</Td><Td className="tabular text-right">{fmtMarks(v.final_score)}</Td>
                  <Td className="tabular whitespace-nowrap text-small">{fmtDate(v.evaluated_at)}</Td><Td className="text-small text-slate-600">{v.archive_reason}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </DialogContent>
    </Dialog>
  );
}
