// Assessment editor: the assessment's details, its question list and the selected question (QuestionPanel). Saved
// through the existing API: details with PATCH /api/assessments/:id, questions with POST/PATCH /api/questions.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Pencil, Plus, Send } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { AssessmentStatusBadge, BackLink, ErrorState, LoadingCards, PageBody, PageHeader } from "@/components/common";
import { RichTextEditor } from "@/components/editor/RichTextEditor";
import { ConceptBreakdown, FeedbackPanel, ReviewFlags, SuggestedMarkCard } from "@/components/evaluation";
import { Button } from "@/components/ui/button";
import { DateTimeField } from "@/components/ui/datetime";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Alert, Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Input } from "@/components/ui/primitives";
import { ApiError, api, errorMessage } from "@/lib/api";
import { previewText } from "@/lib/markdown";
import { usePageTitle } from "@/lib/usePageTitle";
import type { Assessment, AssessmentDetail, EngineResult, Page, Question, TeacherSubmissionItem } from "@/lib/types";
import { cn, fmtDate, fmtMarks, fromLocalInput, plural, toLocalInput } from "@/lib/utils";
import { QuestionPanel } from "@/pages/teacher/question/QuestionPanel";

type Confirm = null | "publish" | "close" | "delete" | "delete-question" | "discard";

export function AssessmentEditorPage() {
  const { id, questionId } = useParams<{ id: string; questionId?: string }>();
  const location = useLocation();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const isNew = location.pathname.endsWith("/questions/new");

  const detail = useQuery({ queryKey: ["assessment", id], queryFn: () => api.get<AssessmentDetail>(`/api/assessments/${id}`) });
  const subs = useQuery({
    queryKey: ["submissions", id],
    queryFn: () => api.get<Page<TeacherSubmissionItem>>("/api/submissions", { assessment_id: id!, limit: 200 }),
  });
  usePageTitle(detail.data?.title ?? "Assessment");

  const [confirm, setConfirm] = useState<Confirm>(null);
  const [block, setBlock] = useState<string | null>(null);
  const [panelDirty, setPanelDirty] = useState(false);
  const [pendingNav, setPendingNav] = useState<string | null>(null);

  const refresh = () => {
    for (const key of [["assessment", id], ["submissions", id], ["assessments"], ["overview"], ["analytics", id]]) qc.invalidateQueries({ queryKey: key });
  };

  const action = useMutation({
    mutationFn: async (kind: "publish" | "close" | "delete" | "delete-question") => {
      switch (kind) {
        case "publish": return api.post<Assessment>(`/api/assessments/${id}/publish`).then(() => "Assessment published. Assigned students can now see it.");
        case "close": return api.post<Assessment>(`/api/assessments/${id}/close`).then(() => "Submissions closed. No new answers are accepted.");
        case "delete": return api.delete(`/api/assessments/${id}`).then(() => "Assessment deleted.");
        case "delete-question": return api.delete(`/api/questions/${questionId}`).then(() => "Question deleted.");
      }
    },
    onSuccess: (msg, kind) => {
      toast.success(msg);
      setConfirm(null);
      setBlock(null);
      if (kind === "delete") {
        qc.invalidateQueries({ queryKey: ["assessments"] });
        navigate("/teacher/assessments");
        return;
      }
      if (kind === "delete-question") { setPanelDirty(false); navigate(`/teacher/assessments/${id}`, { replace: true }); }
      refresh();
    },
    onError: (err, kind) => {
      setConfirm(null);
      if (kind === "publish") setBlock(errorMessage(err));
      else toast.error(errorMessage(err));
    },
  });

  if (params.get("tab") === "submissions") return <Navigate to={`/teacher/submissions?assessment=${id}`} replace />;
  if (detail.isLoading) return <PageBody><LoadingCards /></PageBody>;
  if (detail.isError || !detail.data) return <PageBody><ErrorState message={errorMessage(detail.error)} onRetry={() => detail.refetch()} /></PageBody>;

  const a = detail.data;
  const questions = a.questions ?? [];
  const items = subs.data?.items ?? [];
  const hasSubmissions = items.length > 0;
  const total = questions.reduce((s, q) => s + q.max_marks, 0);
  const selected: Question | null = isNew ? null : questions.find((q) => q.id === questionId) ?? (questionId ? null : questions[0] ?? null);
  const selectedIndex = selected ? questions.indexOf(selected) : questions.length;
  const creating = !selected;

  const go = (to: string) => {
    if (panelDirty) { setPendingNav(to); setConfirm("discard"); }
    else navigate(to);
  };

  return (
    <PageBody className="gap-8">
      <PageHeader
        back={<BackLink to="/teacher/assessments">Assessments</BackLink>}
        title={a.title}
        status={<>
          <AssessmentStatusBadge status={a.status} />
          <span className="tabular">{plural(questions.length, "question")} · {fmtMarks(total)} marks{a.deadline ? ` · due ${fmtDate(a.deadline)}` : ""}</span>
        </>}
        actions={<>
          {hasSubmissions && <Button variant="secondary" asChild><Link to={`/teacher/submissions?assessment=${a.id}`}>Submissions ({items.length})</Link></Button>}
          <Button variant="secondary" icon={<Pencil aria-hidden />} asChild><Link to={`/teacher/assessments/${a.id}/edit`}><Pencil aria-hidden />Edit details</Link></Button>
          {a.status === "published"
            ? <Button variant="secondary" onClick={() => setConfirm("close")}>Close submissions</Button>
            : <Button variant="secondary" icon={<Send aria-hidden />} onClick={() => setConfirm("publish")}>{a.status === "closed" ? "Reopen to students" : "Publish to students"}</Button>}
          {!hasSubmissions && subs.isSuccess && <Button variant="tertiary" className="text-danger hover:text-danger" onClick={() => setConfirm("delete")}>Delete assessment</Button>}
        </>}
      />

      {block && <Alert tone="danger" title="The assessment could not be published.">{block}</Alert>}

      <DetailsForm a={a} />

      <div className="grid items-start gap-6 lg:grid-cols-[248px_minmax(0,1fr)]">
        <nav aria-label="Questions" className="flex flex-col overflow-hidden rounded-md border border-slate-100 bg-white lg:sticky lg:top-6">
          <div className="eyebrow border-b border-slate-100 bg-slate-50 px-4 py-3 text-slate-500">Questions</div>
          <ol className="m-0 list-none p-0">
            {questions.map((q, i) => {
              const alloc = q.rubric.reduce((s, r) => s + r.marks, 0);
              const active = selected?.id === q.id;
              return (
                <li key={q.id}>
                  <button type="button" onClick={() => go(`/teacher/assessments/${a.id}/questions/${q.id}`)} aria-current={active ? "true" : undefined}
                    className={cn("flex w-full flex-col items-start gap-1 border-0 border-b border-slate-100 px-4 py-3 text-left transition-colors duration-150",
                      active ? "bg-ink-50" : "bg-transparent hover:bg-slate-50")}>
                    <span className={cn("text-body font-medium", active ? "text-ink-900" : "text-slate-900")}>Q{i + 1} · {previewText(q.text, 4)}</span>
                    <span className="tabular text-caption text-slate-500">
                      {q.rubric.length ? `${fmtMarks(alloc)} of ${fmtMarks(q.max_marks)} marks · ${plural(q.rubric.length, "criterion", "criteria")}` : `${fmtMarks(q.max_marks)} marks · reference answer only`}
                    </span>
                  </button>
                </li>
              );
            })}
            {creating && (
              <li className="flex flex-col gap-1 border-b border-slate-100 bg-ink-50 px-4 py-3" aria-current="true">
                <span className="text-body font-medium text-ink-900">Q{questions.length + 1} · New question</span>
                <span className="text-caption text-slate-500">Not saved yet</span>
              </li>
            )}
          </ol>
          <div className="p-2">
            <Button variant="tertiary" className="w-full justify-start" icon={<Plus aria-hidden />} disabled={hasSubmissions || creating}
              title={hasSubmissions ? "Students have already submitted this assessment, so questions cannot be added." : undefined}
              onClick={() => go(`/teacher/assessments/${a.id}/questions/new`)}>
              Add question
            </Button>
          </div>
        </nav>

        <div className="flex min-w-0 flex-col gap-6">
          <QuestionPanel key={selected?.id ?? "new"} assessmentId={a.id} question={selected} number={selectedIndex + 1}
            canDelete={!hasSubmissions && subs.isSuccess} onDelete={() => setConfirm("delete-question")} onDirtyChange={setPanelDirty} />
          {selected && <RubricSandbox questionId={selected.id} />}
        </div>
      </div>

      <ConfirmDialog open={confirm === "publish"} onOpenChange={(o) => !o && setConfirm(null)} loading={action.isPending} loadingLabel="Publishing"
        title={a.status === "closed" ? "Reopen this assessment?" : "Publish to students?"} confirmLabel={a.status === "closed" ? "Reopen to students" : "Publish to students"}
        onConfirm={() => action.mutate("publish")}
        description={<p>{(a.assigned_student_ids ?? []).length ? "The students you selected" : "All registered students"} will see the questions and can submit answers{a.deadline ? ` until ${fmtDate(a.deadline)}` : ""}. Reference answers and rubrics stay private.</p>} />
      <ConfirmDialog open={confirm === "close"} onOpenChange={(o) => !o && setConfirm(null)} loading={action.isPending} loadingLabel="Closing"
        title="Close submissions?" confirmLabel="Close submissions" onConfirm={() => action.mutate("close")}
        description={<p>No new answers will be accepted. Students keep access to their submissions and published results. You can reopen it later.</p>} />
      <ConfirmDialog open={confirm === "delete"} onOpenChange={(o) => !o && setConfirm(null)} loading={action.isPending} loadingLabel="Deleting" tone="destructive"
        title="Delete this assessment?" confirmLabel="Delete assessment" onConfirm={() => action.mutate("delete")}
        description={<p>This permanently deletes the assessment and its questions. This cannot be undone.</p>} />
      <ConfirmDialog open={confirm === "delete-question"} onOpenChange={(o) => !o && setConfirm(null)} loading={action.isPending} loadingLabel="Deleting" tone="destructive"
        title="Delete this question?" confirmLabel="Delete question" onConfirm={() => action.mutate("delete-question")}
        description={<p>The question, its reference answer and its rubric will be removed.</p>} />
      <ConfirmDialog open={confirm === "discard"} onOpenChange={(o) => { if (!o) { setConfirm(null); setPendingNav(null); } }}
        title="Discard unsaved changes?" confirmLabel="Discard changes" cancelLabel="Keep editing" tone="destructive"
        onConfirm={() => { const to = pendingNav; setConfirm(null); setPendingNav(null); setPanelDirty(false); if (to) navigate(to); }}
        description={<p>Your edits to this question have not been saved.</p>} />
    </PageBody>
  );
}

/* ------------------------------------------------------------------ details */

function DetailsForm({ a }: { a: AssessmentDetail }) {
  const qc = useQueryClient();
  const initial = useMemo(() => ({ subject: a.subject ?? "", deadline: toLocalInput(a.deadline ?? null), instructions: a.instructions ?? "" }), [a.subject, a.deadline, a.instructions]);
  const [form, setForm] = useState(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => setForm(initial), [initial]);
  const dirty = form.subject !== initial.subject || form.deadline !== initial.deadline || form.instructions.trim() !== initial.instructions.trim();
  const audience = (a.assigned_student_ids ?? []).length;

  const save = useMutation({
    mutationFn: () => api.patch<Assessment>(`/api/assessments/${a.id}`, {
      subject: form.subject.trim(),
      instructions: form.instructions.trim(),
      ...(form.deadline !== initial.deadline ? (form.deadline ? { deadline: fromLocalInput(form.deadline) } : { clear_deadline: true }) : {}),
    }),
    onSuccess: () => {
      toast.success(a.status === "draft" ? "Draft saved." : "Details saved.");
      qc.invalidateQueries({ queryKey: ["assessment", a.id] });
      qc.invalidateQueries({ queryKey: ["assessments"] });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.fieldErrors.length) setErrors(Object.fromEntries(err.fieldErrors.map((f) => [f.field, f.message])));
      else toast.error(errorMessage(err));
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const errs: Record<string, string> = {};
    if (form.subject.trim().length < 2) errs.subject = "Enter the subject (at least 2 characters).";
    if (form.deadline && form.deadline !== initial.deadline && new Date(form.deadline) <= new Date()) errs.deadline = "Choose a deadline in the future.";
    if (form.instructions.trim().length > 5000) errs.instructions = "Shorten the instructions to 5,000 characters or fewer.";
    setErrors(errs);
    if (!Object.keys(errs).length) save.mutate();
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-1">
          <CardTitle>Details</CardTitle>
          <CardDescription>Subject, deadline and what students read before they start.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-5" aria-label="Assessment details" noValidate>
          <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_minmax(0,1fr)]">
            <Field id="ed-subject" label="Subject" error={errors.subject}>
              <Input value={form.subject} maxLength={100} onChange={(e) => setForm({ ...form, subject: e.target.value })} />
            </Field>
            <Field id="ed-deadline" label="Deadline" optional error={errors.deadline}>
              <DateTimeField value={form.deadline} onChange={(deadline) => setForm({ ...form, deadline })} />
            </Field>
            <div className="flex min-w-0 flex-col gap-[6px]">
              <span className="text-small font-medium text-slate-800">Who can take it</span>
              <div className="flex h-11 items-center justify-between gap-2 rounded-sm border border-slate-100 bg-slate-50 px-[14px] text-body text-slate-600">
                <span className="truncate">{audience ? plural(audience, "selected student") : "All registered students"}</span>
                <Link to={`/teacher/assessments/${a.id}/edit`} className="text-small">Change</Link>
              </div>
            </div>
          </div>
          <Field id="ed-instructions" label="Instructions to students" optional error={errors.instructions}>
            <RichTextEditor id="ed-instructions" value={form.instructions} features="lists" minHeight={72} maxLength={5000}
              onChange={(instructions) => setForm((f) => ({ ...f, instructions }))} placeholder="e.g. Answer every question in full sentences." />
          </Field>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="secondary" disabled={!dirty} loading={save.isPending} loadingLabel="Saving">{a.status === "draft" ? "Save draft" : "Save details"}</Button>
            {dirty && <span className="text-small text-slate-500" aria-live="polite">Your edits to the details have not been saved.</span>}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

/* --------------------------------------------------------------- sandbox */

function RubricSandbox({ questionId }: { questionId: string }) {
  const [open, setOpen] = useState(false);
  const [answer, setAnswer] = useState("");
  const test = useMutation({
    mutationFn: () => api.post<EngineResult>(`/api/questions/${questionId}/test-answer`, { answer }),
    onError: (err) => toast.error(errorMessage(err)),
  });
  const r = test.data;
  return (
    <Card>
      <button type="button" aria-expanded={open} aria-controls="sandbox" onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-3 rounded-md border-0 bg-transparent px-6 py-5 text-left hover:bg-slate-25">
        <FlaskConical className="mt-0.5 size-5 text-ink-600" aria-hidden />
        <span className="flex min-w-0 flex-col gap-1">
          <span className="text-h4 font-semibold text-slate-900">Test the rubric</span>
          <span className="text-small text-slate-600">Try a sample answer against the saved rubric. Nothing is stored and students see nothing.</span>
        </span>
      </button>
      {open && (
        <div id="sandbox" className="flex flex-col gap-5 border-t border-slate-100 px-6 py-5">
          <Field id="sandbox-answer" label="Sample answer">
            <RichTextEditor id="sandbox-answer" value={answer} onChange={setAnswer} features="full" maxLength={10000} minHeight={120}
              placeholder="Write or paste a sample student answer" showWordCount />
          </Field>
          <Button className="self-start" variant="secondary" onClick={() => test.mutate()} loading={test.isPending} loadingLabel="Evaluating" disabled={!answer.trim()}>
            Evaluate sample answer
          </Button>
          {r && (
            <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
              <SuggestedMarkCard score={r.suggested_score} max={r.max_marks} confidence={r.confidence} similarity={r.holistic_similarity}
                matched={r.concepts.filter((c) => c.level === "matched").length} total={r.concepts.length} />
              <div className="flex min-w-0 flex-col gap-4">
                <div className="rounded-md border border-slate-100"><ConceptBreakdown concepts={r.concepts} /></div>
                <ReviewFlags flags={r.flags} />
                <FeedbackPanel feedback={r.feedback} compact />
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
