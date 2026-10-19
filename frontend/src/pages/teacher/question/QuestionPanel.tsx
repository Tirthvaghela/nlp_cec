// Question authoring (teacher): 1 question, 2 maximum marks, 3 reference answer, 4 rubric, 5 save.
//
// * The reference answer is drafted automatically once the question has meaningful text (debounced, stale-safe - see
//   useReferenceAnswer). It can be regenerated with a secondary action; teacher edits are never replaced silently.
// * "Generate rubric" is a separate, explicit action that becomes available when the reference answer is ready. It is
//   offered only while the question has never had a rubric: once criteria exist they belong to the teacher and can be
//   edited, added, removed and reordered, but never regenerated.
// * Saving uses the existing POST/PATCH /api/questions endpoints and their validation.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ListChecks, RefreshCw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { RichTextEditor } from "@/components/editor/RichTextEditor";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Alert, Card, Field, FieldError, Input, InputWithSuffix, Textarea } from "@/components/ui/primitives";
import { api, ApiError, errorMessage, isAbort } from "@/lib/api";
import { draftRubric } from "@/lib/generation";
import { normalizeMarkdown, plainText } from "@/lib/markdown";
import type { Question } from "@/lib/types";
import { cn } from "@/lib/utils";
import { InlineStatus, ReferenceStatus } from "@/pages/teacher/question/GenerationStatus";
import {
  draftProblem, isHalfStep, newRow, parseMarks, rowsFromRubric, rubricPayload, validateRubric, type RubricRow,
} from "@/pages/teacher/question/rubric";
import { RubricEditor, RubricTotal } from "@/pages/teacher/question/RubricEditor";
import { questionKey, REFERENCE_MAX_CHARS, useReferenceAnswer } from "@/pages/teacher/question/useReferenceAnswer";

const QUESTION_MAX_CHARS = 2000;
const LEVELS = [["excellent", "Excellent"], ["satisfactory", "Satisfactory"], ["needs_improvement", "Needs improvement"]] as const;
type Levels = Record<(typeof LEVELS)[number][0], string>;

function initialState(q: Question | null) {
  return {
    text: q?.text ?? "",
    maxMarks: q ? String(q.max_marks) : "4",
    reference: q?.reference_answer ?? "",
    rows: q ? rowsFromRubric(q.rubric) : ([] as RubricRow[]),
    levels: { excellent: q?.rubric_levels.excellent ?? "", satisfactory: q?.rubric_levels.satisfactory ?? "", needs_improvement: q?.rubric_levels.needs_improvement ?? "" } as Levels,
    match: q?.settings.match_threshold != null ? String(q.settings.match_threshold) : "",
    partial: q?.settings.partial_threshold != null ? String(q.settings.partial_threshold) : "",
  };
}
type State = ReturnType<typeof initialState>;

const signature = (s: Omit<State, "rows"> & { rows: RubricRow[] }) => JSON.stringify({
  ...s, text: normalizeMarkdown(s.text), reference: normalizeMarkdown(s.reference), rows: s.rows.map(({ key: _k, ...r }) => r),
});

function SectionHead({ n, title, aside, id }: { n: number; title: string; aside?: ReactNode; id?: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <h3 id={id} className="m-0 flex items-center gap-3 text-h4 font-semibold text-slate-900">
        <span aria-hidden className="tabular grid size-7 place-items-center rounded-full bg-ink-50 text-small font-semibold text-ink-700">{n}</span>
        {title}
      </h3>
      {aside}
    </div>
  );
}

function Disclosure({ title, children, id }: { title: string; children: ReactNode; id: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-slate-100 pt-4">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}
        className="flex min-h-11 w-full items-center justify-between gap-3 rounded-sm border-0 bg-transparent px-0 text-left text-body font-medium text-slate-900 hover:text-ink-700">
        {title}
        <ChevronDown className={cn("size-[18px] text-slate-500 transition-transform duration-150", open && "rotate-180")} aria-hidden />
      </button>
      {open && <div id={id} className="flex flex-col gap-4 pt-2">{children}</div>}
    </div>
  );
}

export function QuestionPanel({ assessmentId, question, number, canDelete, onDelete, onDirtyChange }: {
  assessmentId: string; question: Question | null; number: number; canDelete: boolean; onDelete: () => void; onDirtyChange: (d: boolean) => void;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const editing = Boolean(question);
  const [base, setBase] = useState(() => initialState(question));
  const [text, setText] = useState(base.text);
  const [maxMarks, setMaxMarks] = useState(base.maxMarks);
  const [rows, setRows] = useState<RubricRow[]>(base.rows);
  const [levels, setLevels] = useState<Levels>(base.levels);
  const [match, setMatch] = useState(base.match);
  const [partial, setPartial] = useState(base.partial);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);
  const [confirmReplace, setConfirmReplace] = useState(false);

  const max = parseMarks(maxMarks);
  const ref = useReferenceAnswer({
    question: text, maxMarks: max,
    initial: question ? { text: question.reference_answer, question: question.text } : null,
  });

  // rubric generation (explicit, once)
  const [rubricBusy, setRubricBusy] = useState(false);
  const [rubricError, setRubricError] = useState<string | null>(null);
  const [rubricSource, setRubricSource] = useState<"model" | "derived" | null>(null);
  const [generatedOnce, setGeneratedOnce] = useState(false);
  const rubricCtrl = useRef<AbortController | null>(null);
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  useEffect(() => () => rubricCtrl.current?.abort(), []);

  // what the rubric was written against, to flag it as possibly outdated (never to replace it)
  const [rubricBasis, setRubricBasis] = useState(() => ({ q: questionKey(base.text), ref: normalizeMarkdown(base.reference) }));
  const [rubricBasisReviewed, setRubricBasisReviewed] = useState(false);

  // Re-sync when the saved question changes underneath (after a save or a refetch).
  const [loadedVersion, setLoadedVersion] = useState(question?.updated_at);
  useEffect(() => {
    if (!question || question.updated_at === loadedVersion) return;
    const s = initialState(question);
    setLoadedVersion(question.updated_at);
    setBase(s); setText(s.text); setMaxMarks(s.maxMarks); setRows(s.rows); setLevels(s.levels); setMatch(s.match); setPartial(s.partial);
    ref.reset({ text: question.reference_answer, question: question.text });
    setRubricBasis({ q: questionKey(s.text), ref: normalizeMarkdown(s.reference) });
    setRubricBasisReviewed(false);
    setSubmitted(false);
    // ref.reset is stable
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question, loadedVersion]);

  const current = { text, maxMarks, reference: ref.text, rows, levels, match, partial };
  const dirty = signature(current) !== signature(base);
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  /* ---------------------------------------------------------------- validation */

  const rubricErrors = useMemo(() => validateRubric(rows, max), [rows, max]);
  const legacyNoReference = editing && !question!.reference_answer.trim() && rows.length > 0 && !ref.text.trim();
  const errors = useMemo(() => {
    const e: Record<string, string> = {};
    const plain = plainText(text).trim();
    if (plain.length < 5) e.text = "Write the question (at least 5 characters).";
    else if (text.trim().length > QUESTION_MAX_CHARS) e.text = `Shorten the question to ${QUESTION_MAX_CHARS.toLocaleString()} characters or fewer, including formatting.`;
    if (!isHalfStep(max) || max > 100) e.max = "Enter a value between 0.5 and 100, in steps of 0.5.";
    if (ref.tooLong) e.reference = `Shorten the reference answer to ${REFERENCE_MAX_CHARS.toLocaleString()} characters or fewer.`;
    else if (!ref.text.trim() && !legacyNoReference) e.reference = "Add a reference answer. It is drafted automatically from the question, or you can write it.";
    if ((match && !partial) || (!match && partial)) e.thresholds = "Set both thresholds or leave both empty.";
    else if (match && partial && Number(partial) >= Number(match)) e.thresholds = "The partial threshold must be lower than the matched threshold.";
    return e;
  }, [text, max, ref.tooLong, ref.text, legacyNoReference, match, partial]);
  const show = (k: string) => (submitted || touched[k]) && errors[k];

  const refBlocking = ref.status === "stale" || (!legacyNoReference && (ref.busy || !ref.isValid));
  const canSave = !refBlocking && !rubricBusy;

  /* ---------------------------------------------------------------- rubric */

  const qKey = questionKey(text);
  const rubricOutdated = rows.length > 0 && !rubricBasisReviewed && (rubricBasis.q !== qKey || rubricBasis.ref !== normalizeMarkdown(ref.text));
  const offerGenerate = rows.length === 0 && !generatedOnce && !(question?.rubric.length);
  const generateReady = ref.isValid && ref.canDraft && !rubricBusy;
  const generateBlockedReason = !ref.canDraft ? "Write the question and its maximum marks first."
    : ref.status === "stale" ? "Resolve the outdated reference answer first."
      : !ref.isValid ? "The rubric is generated from the reference answer, so it needs one first." : null;

  async function generateRubric() {
    if (!generateReady) return;
    rubricCtrl.current?.abort();
    const ctrl = new AbortController();
    rubricCtrl.current = ctrl;
    setRubricBusy(true);
    setRubricError(null);
    try {
      const draft = await draftRubric(text.trim(), max, ref.text.trim(), ctrl.signal);
      if (ctrl.signal.aborted) return;
      const problem = draftProblem(draft.rubric, max);
      if (problem) { setRubricError(`The drafted rubric is not valid: ${problem} Try again, or add criteria yourself.`); return; }
      if (rowsRef.current.length) { setRubricError("Criteria were added while the rubric was being drafted, so the draft was not applied."); return; }
      setRows(draft.rubric.map((c) => newRow({ label: c.label, description: c.description, marks: String(c.marks) })));
      setGeneratedOnce(true);
      setRubricSource(draft.source);
      setRubricBasis({ q: qKey, ref: normalizeMarkdown(ref.text) });
      setRubricBasisReviewed(false);
    } catch (err) {
      if (!isAbort(err)) setRubricError(errorMessage(err));
    } finally {
      if (rubricCtrl.current === ctrl) { rubricCtrl.current = null; setRubricBusy(false); }
    }
  }

  /* ---------------------------------------------------------------- save */

  const save = useMutation({
    mutationFn: () => {
      const body = {
        text: text.trim(),
        max_marks: max,
        reference_answer: ref.text.trim(),
        rubric: rubricPayload(rows),
        rubric_levels: levels,
        settings: { match_threshold: match ? Number(match) : null, partial_threshold: partial ? Number(partial) : null },
      };
      return editing
        ? api.patch<Question>(`/api/questions/${question!.id}`, body)
        : api.post<Question>("/api/questions", { assessment_id: assessmentId, ...body });
    },
    onSuccess: (q) => {
      qc.invalidateQueries({ queryKey: ["assessment", assessmentId] });
      qc.invalidateQueries({ queryKey: ["submissions", assessmentId] });
      qc.invalidateQueries({ queryKey: ["assessments"] });
      const bumped = editing && question && q.rubric_version !== question.rubric_version;
      toast.success(bumped ? `Saved as rubric version ${q.rubric_version}. Existing evaluations are marked as outdated.` : `Question ${number} saved.`);
      if (!editing) {
        onDirtyChange(false);
        navigate(`/teacher/assessments/${assessmentId}/questions/${q.id}`, { replace: true });
      }
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : errorMessage(err)),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    if (Object.keys(errors).length || Object.keys(rubricErrors.rows).length || rubricErrors.summary || !canSave) {
      toast.error("Some fields need attention before this question can be saved.");
      return;
    }
    if (save.isPending) return;
    save.mutate();
  }

  const discard = () => {
    setText(base.text); setMaxMarks(base.maxMarks); setRows(base.rows); setLevels(base.levels); setMatch(base.match); setPartial(base.partial);
    ref.reset(question ? { text: question.reference_answer, question: question.text } : null);
    setSubmitted(false); setTouched({});
  };

  const askRegenerate = () => (ref.isProtected ? setConfirmReplace(true) : void ref.regenerate());
  const nextIsRubric = offerGenerate && generateReady;

  return (
    <Card className="flex flex-col">
      <form onSubmit={onSubmit} noValidate aria-label={editing ? `Question ${number}` : "New question"} className="flex flex-col">
        {/* 1-2: question and maximum marks */}
        <section className="flex flex-col gap-4 border-b border-slate-100 p-6" aria-labelledby="q-sec-1">
          <SectionHead n={1} id="q-sec-1" title={`Question ${number}`} />
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_168px]">
            <Field id="q-text" label="Question text" error={show("text") || null}
              hint="Lists, tables and emphasis are kept. A reference answer is drafted when you pause typing.">
              <RichTextEditor id="q-text" value={text} onChange={setText} features="full" maxLength={QUESTION_MAX_CHARS}
                placeholder="e.g. Explain tokenization in NLP and why it is important." minHeight={96}
                onBlur={() => setTouched((t) => ({ ...t, text: true }))} />
            </Field>
            <Field id="q-max" label="Maximum marks" error={show("max") || null} hint="Steps of 0.5.">
              <InputWithSuffix suffix="marks" inputMode="decimal" value={maxMarks} onChange={(e) => setMaxMarks(e.target.value)}
                onBlur={() => setTouched((t) => ({ ...t, max: true }))} />
            </Field>
          </div>
        </section>

        {/* 3: reference answer */}
        <section className="flex flex-col gap-4 border-b border-slate-100 p-6" aria-labelledby="q-sec-3">
          <SectionHead n={2} id="q-sec-3" title="Reference answer" aside={<ReferenceStatus status={ref.status} origin={ref.origin} canDraft={ref.canDraft} />} />
          <p className="reading m-0 text-small text-slate-600">
            Used to cross-check relevance and to build the rubric. Never shown to students. Review a drafted answer before saving.
          </p>

          {ref.status === "stale" && (
            <Alert tone="warning" title="The reference answer may be outdated because the question changed."
              action={<>
                <Button size="sm" variant="secondary" icon={<RefreshCw aria-hidden />} onClick={askRegenerate}>Regenerate reference answer</Button>
                <Button size="sm" variant="tertiary" onClick={ref.keepCurrent}>Keep this answer</Button>
              </>}>
              Regenerate it for the new question, or keep the current answer if it still fits.
            </Alert>
          )}
          {ref.failure && (
            <Alert tone={ref.text.trim() ? "warning" : "danger"}
              title={ref.text.trim() ? "A new reference answer could not be generated. Your current answer is unchanged." : "The reference answer could not be generated."}
              action={ref.canDraft && ref.failureCode !== "generation_disabled_in_pilot" && (
                <Button size="sm" variant="secondary" icon={<RefreshCw aria-hidden />} onClick={() => void ref.regenerate()}>Try again</Button>
              )}>
              {ref.failure}{!ref.text.trim() && " You can also write the reference answer below."}
            </Alert>
          )}

          <Field id="q-ref" label="Reference answer text" error={show("reference") || null}>
            <RichTextEditor id="q-ref" value={ref.text} onChange={ref.setText} features="full" maxLength={REFERENCE_MAX_CHARS}
              placeholder={ref.status === "generating" ? "Generating reference answer…" : "The drafted answer appears here. You can also write it yourself."}
              minHeight={160} onBlur={() => setTouched((t) => ({ ...t, reference: true }))} />
          </Field>

          <div className="flex flex-wrap items-center gap-3">
            {ref.text.trim() && ref.status !== "stale" && (
              <Button variant="secondary" icon={<RefreshCw aria-hidden />} onClick={askRegenerate}
                disabled={!ref.canDraft || ref.busy} loading={ref.status === "generating"} loadingLabel="Generating reference answer">
                Regenerate reference answer
              </Button>
            )}
            {!ref.text.trim() && (
              <Button variant="secondary" icon={<Sparkles aria-hidden />} onClick={() => void ref.regenerate()}
                disabled={!ref.canDraft || ref.busy} loading={ref.status === "generating"} loadingLabel="Generating reference answer">
                Generate reference answer
              </Button>
            )}
            {!ref.canDraft && <span className="text-small text-slate-500">Write a question of at least three words and set its maximum marks to draft an answer.</span>}
          </div>
        </section>

        {/* 4: rubric */}
        <section className="flex flex-col gap-4 border-b border-slate-100 p-6" aria-labelledby="q-sec-4">
          <SectionHead n={3} id="q-sec-4" title="Rubric" aside={rows.length > 0 ? <RubricTotal rows={rows} maxMarks={max} /> :
            rubricBusy ? <InlineStatus icon={<span className="size-4 animate-spin rounded-full border-2 border-ink-200 border-t-ink-600" aria-hidden />} text="Generating rubric" className="text-ink-700" /> : undefined} />

          {rubricOutdated && (
            <Alert tone="warning" title="The rubric may be outdated because the question or reference answer changed."
              action={<Button size="sm" variant="tertiary" onClick={() => setRubricBasisReviewed(true)}>Mark rubric as reviewed</Button>}>
              Review the criteria below. The rubric is never changed automatically.
            </Alert>
          )}
          {rubricSource === "derived" && rows.length > 0 && (
            <Alert tone="info" title="These criteria were built from the reference answer's sentences.">
              The drafting model is not available, so each criterion groups sentences of your reference answer. Rename and refine them before saving.
            </Alert>
          )}
          {rubricError && <Alert tone="danger" title="The rubric could not be generated.">{rubricError}</Alert>}

          {rows.length === 0 && (
            <div className="flex flex-col gap-3 rounded-md border border-dashed border-slate-200 bg-slate-25 p-5">
              <div className="flex items-start gap-3">
                <span className="grid size-11 flex-none place-items-center rounded-full bg-ink-50 text-ink-600"><ListChecks className="size-5" aria-hidden /></span>
                <div className="flex min-w-0 flex-col gap-1">
                  <span className="text-body font-medium text-slate-900">No criteria yet</span>
                  <span className="text-small text-slate-600">
                    {offerGenerate
                      ? "Generate a rubric from the reference answer, then edit it. A rubric is generated once; after that it is yours to edit."
                      : "Add the key points a good answer must contain, with their marks."}
                  </span>
                  {offerGenerate && generateBlockedReason && <span className="text-small text-slate-500">{generateBlockedReason}</span>}
                </div>
              </div>
              {offerGenerate && (
                <Button className="self-start" variant={nextIsRubric ? "primary" : "secondary"} icon={<Sparkles aria-hidden />}
                  onClick={() => void generateRubric()} disabled={!generateReady} loading={rubricBusy} loadingLabel="Generating rubric">
                  Generate rubric
                </Button>
              )}
            </div>
          )}

          <RubricEditor rows={rows} onChange={setRows} errors={rubricErrors} showErrors={submitted} disabled={rubricBusy} />
          {!rows.length && !ref.text.trim() && submitted && <FieldError>Add at least one criterion or a reference answer.</FieldError>}

          <Disclosure id="q-levels" title="Performance expectations (optional)">
            <p className="m-0 text-small text-slate-600">Describes each performance level. Shown beside the suggested mark while you review answers.</p>
            <div className="grid gap-4 md:grid-cols-3">
              {LEVELS.map(([k, l]) => (
                <Field key={k} id={`lvl-${k}`} label={l}>
                  <Textarea rows={3} value={levels[k]} maxLength={500} onChange={(e) => setLevels({ ...levels, [k]: e.target.value })} />
                </Field>
              ))}
            </div>
          </Disclosure>

          <Disclosure id="q-thresholds" title="Advanced: matching thresholds">
            <p className="reading m-0 text-small text-slate-600">
              Concept thresholds for this question. Leave both empty to use the calibrated defaults (matched at 0.57, partial at 0.52 on the
              concept score). Overrides are refused in the classroom pilot.
            </p>
            <div className="grid max-w-md gap-4 sm:grid-cols-2">
              <Field id="q-match" label="Match threshold">
                <Input inputMode="decimal" value={match} onChange={(e) => setMatch(e.target.value)} placeholder="0.57" className="tabular" />
              </Field>
              <Field id="q-partial" label="Partial threshold">
                <Input inputMode="decimal" value={partial} onChange={(e) => setPartial(e.target.value)} placeholder="0.52" className="tabular" />
              </Field>
            </div>
            {errors.thresholds && (submitted || match || partial) && <FieldError>{errors.thresholds}</FieldError>}
          </Disclosure>
        </section>

        {/* 5: save */}
        <div className="flex flex-col gap-3 p-6">
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant={nextIsRubric ? "secondary" : "primary"} loading={save.isPending} loadingLabel="Saving" disabled={!canSave}>
              {editing ? "Save changes" : "Save question"}
            </Button>
            {editing ? (
              <Button variant="secondary" disabled={!dirty || save.isPending} onClick={discard}>Discard changes</Button>
            ) : (
              <Button variant="tertiary" onClick={() => { onDirtyChange(false); navigate(`/teacher/assessments/${assessmentId}`); }}>Cancel</Button>
            )}
            {editing && canDelete && <Button variant="destructive" className="sm:ml-auto" onClick={onDelete}>Delete question</Button>}
          </div>
          <p className="m-0 text-small text-slate-500" aria-live="polite">
            {!canSave && ref.status === "stale" ? "Resolve the outdated reference answer to save."
              : !canSave && ref.busy ? "Saving is available once the reference answer is ready."
                : !canSave && !ref.isValid && !legacyNoReference ? "Saving is available once the question has a reference answer."
                  : dirty ? "Your edits have not been saved." : editing ? "All changes saved." : ""}
          </p>
        </div>
      </form>

      <ConfirmDialog open={confirmReplace} onOpenChange={setConfirmReplace}
        title="Replace your reference answer?" confirmLabel="Regenerate reference answer" cancelLabel="Keep my answer"
        onConfirm={() => { setConfirmReplace(false); void ref.regenerate(); }}
        description={<>
          <p>The current reference answer {ref.origin === "saved" && ref.status !== "edited" ? "was saved with this question" : "contains your edits"}.</p>
          <p>A new draft replaces it only once it has been generated successfully. If drafting fails, your answer stays as it is.</p>
        </>} />
    </Card>
  );
}

