// Answering an assessment: one question at a time in the rich-text editor, drafts saved automatically through
// PUT /api/submissions/draft, explicit submission with POST /api/submissions/submit. "Saved" is shown only after the
// server confirmed the save; text typed while a save is in flight stays marked as unsaved until it is saved too.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CircleAlert, CircleCheck, Loader2, Send } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import { BackLink, ErrorState, LoadingCards, Note, PageBody, PageHeader, StudentStatusBadge } from "@/components/common";
import { RichText } from "@/components/RichText";
import { RichTextEditor } from "@/components/editor/RichTextEditor";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Alert, Card, Overline } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { wordCountOf } from "@/lib/markdown";
import type { StudentAssessmentDetail, StudentStatus } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { cn, fmtClock, fmtDate, fmtMarks, plural, relativeTime } from "@/lib/utils";

const AUTOSAVE_MS = 5_000;
const ANSWER_MAX_CHARS = 10_000;

export function TakeAssessmentPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["student-assessment", id], queryFn: () => api.get<StudentAssessmentDetail>(`/api/assessments/${id}`) });
  usePageTitle(q.data?.title ?? "Assessment");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [savedJson, setSavedJson] = useState<string>("{}");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submittedAt, setSubmittedAt] = useState<Date | null>(null);
  const [sel, setSel] = useState(0);
  const loaded = useRef<string | null>(null);

  useEffect(() => {
    if (!q.data || loaded.current === q.data.id) return;
    loaded.current = q.data.id;
    const initial = Object.fromEntries(q.data.answers.map((a) => [a.question_id, a.text]));
    setAnswers(initial);
    setSavedJson(JSON.stringify(initial));
  }, [q.data]);

  const answersJson = JSON.stringify(answers);
  const dirty = answersJson !== savedJson;

  const payload = useCallback(() => ({
    assessment_id: id,
    answers: (q.data?.questions ?? []).map((qq) => ({ question_id: qq.id, text: answers[qq.id] ?? "" })),
  }), [id, q.data, answers]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["student-assessments"] });
    qc.invalidateQueries({ queryKey: ["student-assessment", id] });
    qc.invalidateQueries({ queryKey: ["my-submissions"] });
  };

  const saveDraft = useMutation({
    mutationFn: (snapshot: string) => api.put("/api/submissions/draft", payload()).then(() => snapshot),
    onSuccess: (snapshot) => { setSavedJson(snapshot); setSavedAt(new Date()); setSaveError(null); },
    onError: (err) => setSaveError(errorMessage(err)),
  });
  const submit = useMutation({
    mutationFn: () => api.post("/api/submissions/submit", payload()),
    onSuccess: () => { setSavedJson(answersJson); setConfirmOpen(false); setSubmittedAt(new Date()); refresh(); window.scrollTo({ top: 0 }); },
    onError: (err) => { setConfirmOpen(false); toast.error(errorMessage(err)); },
  });

  const canEdit = Boolean(q.data?.can_edit) && !submittedAt;
  const { mutate: autosave, isPending: saving } = saveDraft;
  useEffect(() => {
    if (!dirty || !canEdit || saving || saveError) return;
    const t = setTimeout(() => autosave(answersJson), AUTOSAVE_MS);
    return () => clearTimeout(t);
  }, [dirty, canEdit, saving, saveError, autosave, answersJson]);

  // Warn before leaving with unsaved changes.
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  if (q.isLoading) return <PageBody width="reading"><LoadingCards /></PageBody>;
  if (q.isError || !q.data) return <PageBody width="reading"><ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /></PageBody>;
  const a = q.data;
  const questions = a.questions;
  const unanswered = questions.filter((qq) => !(answers[qq.id] ?? "").trim());
  const answered = questions.length - unanswered.length;
  const meta = [
    plural(questions.length, "question"), `${fmtMarks(a.total_marks)} marks`,
    a.deadline ? (a.deadline_passed ? `closed ${fmtDate(a.deadline)}` : `due ${fmtDate(a.deadline)} (${relativeTime(a.deadline)})`) : null,
  ].filter(Boolean).join(" · ");

  const status: StudentStatus = submittedAt ? "submitted" : a.my_status;
  const submitted = Boolean(submittedAt) || ["submitted", "evaluated", "published"].includes(a.my_status);

  if (submitted) {
    return (
      <PageBody width="reading">
        <SubmittedCard title={a.title} status={status} submittedAt={submittedAt ? submittedAt.toISOString() : a.submitted_at}
          resultId={a.my_status === "published" ? a.submission_id : null} />
        <ReadOnlyAnswers questions={questions} answers={answers} />
      </PageBody>
    );
  }

  if (!canEdit) {
    return (
      <PageBody width="reading">
        <PageHeader back={<BackLink to="/student">Dashboard</BackLink>} title={a.title}
          status={<><StudentStatusBadge status={a.my_status} /><span className="tabular">{meta}</span></>} />
        <Alert tone="info" title="This assessment no longer accepts answers.">Your saved answers are shown below.</Alert>
        <ReadOnlyAnswers questions={questions} answers={answers} />
      </PageBody>
    );
  }

  const index = Math.min(sel, Math.max(0, questions.length - 1));
  const current = questions[index];
  const text = current ? answers[current.id] ?? "" : "";
  const tooLong = Object.values(answers).some((t) => t.length > ANSWER_MAX_CHARS);

  const saveState = saving
    ? <span className="inline-flex items-center gap-1 text-slate-600"><Loader2 className="size-4 animate-spin" aria-hidden />Saving draft</span>
    : saveError
      ? <span className="inline-flex flex-wrap items-center gap-2 text-danger"><CircleAlert className="size-4" aria-hidden />Draft not saved: {saveError}
        <Button variant="link" size="sm" onClick={() => { setSaveError(null); autosave(answersJson); }}>Try again</Button></span>
      : dirty
        ? <span className="text-slate-600">Your latest changes are not saved yet</span>
        : savedAt
          ? <span className="inline-flex items-center gap-1 text-success"><CircleCheck className="size-4" aria-hidden />Draft saved at {fmtClock(savedAt)}</span>
          : <span className="text-slate-500">{a.my_status === "draft" ? "Saved draft loaded" : "Drafts save automatically while you write"}</span>;

  return (
    <PageBody width="reading" className="gap-6">
      <PageHeader back={<BackLink to="/student">Dashboard</BackLink>} title={a.title}
        status={<span className="tabular">{meta} · {a.subject} · {a.teacher_name}</span>}
        actions={<>
          <Button variant="secondary" onClick={() => saveDraft.mutate(answersJson)} loading={saving} loadingLabel="Saving" disabled={!dirty}>Save draft</Button>
          <Button icon={<Send aria-hidden />} onClick={() => setConfirmOpen(true)} disabled={answered === 0 || tooLong}>Submit answers</Button>
        </>} />

      <Card className="flex flex-col gap-2 px-5 py-4">
        <Overline as="h2">Instructions</Overline>
        {a.instructions ? <RichText text={a.instructions} /> : <p className="m-0 text-body text-slate-800">Answer in your own words, in full sentences.</p>}
        <p className="m-0 text-small text-slate-600">Your drafts save automatically. Nothing is sent to your teacher until you submit.</p>
      </Card>

      {questions.length === 0 ? (
        <Note>This assessment has no questions yet.</Note>
      ) : (
        <>
          <div className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between gap-3 text-small">
              <span className="font-medium text-slate-800">Question {index + 1} of {questions.length}</span>
              <span className="tabular text-slate-600">{answered} of {questions.length} answered</span>
            </div>
            <ol className="m-0 flex list-none gap-[6px] p-0" aria-label="Questions">
              {questions.map((qq, i) => {
                const done = Boolean((answers[qq.id] ?? "").trim());
                return (
                  <li key={qq.id} className="min-w-0 flex-1">
                    <button type="button" onClick={() => setSel(i)} aria-current={i === index ? "step" : undefined}
                      aria-label={`Question ${i + 1}: ${done ? "answered" : "not answered"}`}
                      className="flex h-11 w-full items-center border-0 bg-transparent p-0">
                      <span className={cn("h-[6px] w-full rounded-full transition-colors duration-150",
                        i === index ? "bg-ink-300" : done ? "bg-ink-600" : "bg-slate-100")} />
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>

          <Card className="flex flex-col gap-4 p-5 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
              <div id={`ans-${current.id}-label`} className="min-w-0 flex-1">
                <span className="sr-only">Question {index + 1}: </span>
                <RichText text={current.text} size="body-lg" className="font-medium" />
              </div>
              <span className="tabular whitespace-nowrap text-body font-medium text-slate-600">{fmtMarks(current.max_marks)} marks</span>
            </div>
            <RichTextEditor key={current.id} id={`ans-${current.id}`} value={text} size="answer" features="full" maxLength={ANSWER_MAX_CHARS}
              placeholder="Write your answer here" showWordCount footer={<span className="text-small" aria-live="polite">{saveState}</span>}
              onChange={(v) => setAnswers((s) => ({ ...s, [current.id]: v }))} />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Button size="md" variant="secondary" icon={<ArrowLeft aria-hidden />} disabled={index === 0} onClick={() => setSel(index - 1)}>Previous question</Button>
              <Button size="md" variant="secondary" disabled={index === questions.length - 1} onClick={() => setSel(index + 1)}>
                Next question<ArrowRight aria-hidden />
              </Button>
            </div>
          </Card>
        </>
      )}

      <ConfirmDialog open={confirmOpen} onOpenChange={setConfirmOpen} loading={submit.isPending} loadingLabel="Submitting"
        title={`Submit ${a.title}?`} confirmLabel="Submit answers" cancelLabel="Keep writing" onConfirm={() => submit.mutate()}
        description={<>
          <p>{answered} of {questions.length} questions answered.{unanswered.length > 0 && ` Not answered: ${unanswered.map((u) => `Q${questions.indexOf(u) + 1}`).join(", ")}. These will receive no marks.`}</p>
          <p>You cannot change your answers after submitting.</p>
        </>} />
    </PageBody>
  );
}

function SubmittedCard({ title, status, submittedAt, resultId }: { title: string; status: StudentStatus; submittedAt: string | null; resultId: string | null }) {
  const steps = [
    { label: "Submitted", done: true, detail: fmtDate(submittedAt) },
    { label: "Evaluated", done: status === "evaluated" || status === "published", detail: status === "evaluated" ? "Your teacher is reviewing" : status === "published" ? "Done" : "Pending" },
    { label: "Published", done: status === "published", detail: status === "published" ? "Results available" : "Pending" },
  ];
  return (
    <Card className="flex flex-col gap-5 p-6 sm:p-8">
      <div className="flex flex-col gap-2">
        <span className="inline-flex items-center gap-2 text-small font-semibold text-success"><CircleCheck className="size-5" aria-hidden />Answers submitted</span>
        <h1 className="m-0 text-h2 font-semibold text-slate-900">{title}</h1>
        <p className="reading m-0 text-body text-slate-600">
          Submitted {fmtDate(submittedAt)}. Your answers can no longer be changed. Marks and feedback appear here once your teacher has reviewed and published them.
        </p>
      </div>
      <ol className="m-0 grid list-none gap-3 p-0 sm:grid-cols-3" aria-label="Progress">
        {steps.map((s, i) => (
          <li key={s.label} className="flex flex-col gap-2">
            <span className={cn("h-[6px] rounded-full", s.done ? "bg-ink-600" : "bg-slate-100")} aria-hidden />
            <span className="text-small font-semibold text-slate-900">{i + 1}. {s.label}{s.done && <span className="sr-only"> (done)</span>}</span>
            <span className="text-small text-slate-600">{s.detail}</span>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-3">
        {resultId && <Button variant="highlight" asChild><Link to={`/student/results/${resultId}`}>View your feedback</Link></Button>}
        <Button variant="secondary" asChild><Link to="/student">Back to dashboard</Link></Button>
        <Button variant="tertiary" asChild><Link to="/student/submissions">My submissions</Link></Button>
      </div>
    </Card>
  );
}

function ReadOnlyAnswers({ questions, answers }: { questions: StudentAssessmentDetail["questions"]; answers: Record<string, string> }) {
  if (!questions.length) return null;
  return (
    <section className="flex flex-col gap-4" aria-labelledby="your-answers">
      <h2 id="your-answers" className="m-0 text-h3 font-semibold text-slate-900">Your answers</h2>
      {questions.map((qq, i) => {
        const t = answers[qq.id] ?? "";
        return (
          <Card key={qq.id} className="flex flex-col gap-3 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1"><Overline>Question {i + 1}</Overline><RichText text={qq.text} className="font-medium" /></div>
              <span className="tabular whitespace-nowrap text-small text-slate-600">{fmtMarks(qq.max_marks)} marks · {wordCountOf(t)} words</span>
            </div>
            <RichText text={t} size="body-lg" empty={<p className="m-0 text-body italic text-slate-500">No answer</p>} />
          </Card>
        );
      })}
    </section>
  );
}
