// Submissions of one assessment: counts, suggested vs final totals, bulk evaluation and publication through the
// existing endpoints. Nothing is shown to students before publication.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { DemoBadge, EmptyState, ErrorState, LoadingCards, Marks, PageBody, PageHeader, SubmissionStatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Alert, Field, KpiRow, KpiTile, StatusBadge, Table, Td, Th, Tr } from "@/components/ui/primitives";
import { Select } from "@/components/ui/select";
import { api, errorMessage } from "@/lib/api";
import type { Assessment, Page, TeacherSubmissionItem } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { fmtDate, fmtMarks, plural } from "@/lib/utils";

type Confirm = null | "evaluate" | "reevaluate" | "publish";

export function TeacherSubmissionsPage() {
  usePageTitle("Submissions");
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState<Confirm>(null);
  const assessments = useQuery({ queryKey: ["assessments"], queryFn: () => api.get<Assessment[]>("/api/assessments") });
  const list = useMemo(() => assessments.data ?? [], [assessments.data]);
  const selectedId = params.get("assessment") ?? "";

  useEffect(() => {
    if (selectedId || !list.length) return;
    const pending = (a: Assessment) => a.submission_counts.submitted + a.submission_counts.evaluated;
    const best = [...list].sort((x, y) => pending(y) - pending(x))[0];
    setParams({ assessment: best.id }, { replace: true });
  }, [selectedId, list, setParams]);

  const a = list.find((x) => x.id === selectedId);
  const subs = useQuery({
    queryKey: ["submissions", selectedId],
    queryFn: () => api.get<Page<TeacherSubmissionItem>>("/api/submissions", { assessment_id: selectedId, limit: 200 }),
    enabled: Boolean(selectedId),
  });
  const items = subs.data?.items ?? [];
  const notEvaluated = items.filter((s) => s.status === "submitted");
  const evaluated = items.filter((s) => s.status === "evaluated");
  const published = items.filter((s) => s.status === "published");
  const outdated = items.filter((s) => s.rubric_outdated && s.status !== "published").length;
  const flagged = items.reduce((n, s) => n + (s.status === "evaluated" ? s.needs_review_count : 0), 0);

  const refresh = () => {
    for (const key of [["submissions", selectedId], ["assessment", selectedId], ["assessments"], ["overview"], ["analytics", selectedId]]) qc.invalidateQueries({ queryKey: key });
  };
  const action = useMutation({
    mutationFn: async (kind: Exclude<Confirm, null>) => {
      switch (kind) {
        case "evaluate": return api.post<{ evaluated_submissions: number }>(`/api/evaluations/assessment/${selectedId}`, {}, { scope: "pending" })
          .then((r) => `${plural(r.evaluated_submissions, "submission")} evaluated. Review the suggested marks before publishing.`);
        case "reevaluate": return api.post<{ evaluated_submissions: number }>(`/api/evaluations/assessment/${selectedId}`, {}, { scope: "outdated" })
          .then((r) => `${plural(r.evaluated_submissions, "submission")} re-evaluated with the updated rubric.`);
        case "publish": return api.post<{ published_submissions: number; skipped: { reason: string }[] }>(`/api/results/assessment/${selectedId}/publish`, {})
          .then((r) => `Marks published for ${plural(r.published_submissions, "student")}${a ? ` in ${a.title}` : ""}.` + (r.skipped.length ? ` ${r.skipped.length} skipped: ${r.skipped[0].reason}` : ""));
      }
    },
    onSuccess: (msg) => { toast.success(msg); setConfirm(null); refresh(); },
    onError: (err) => { toast.error(errorMessage(err)); setConfirm(null); },
  });

  if (assessments.isLoading) return <PageBody><LoadingCards /></PageBody>;
  if (assessments.isError) return <PageBody><ErrorState message={errorMessage(assessments.error)} onRetry={() => assessments.refetch()} /></PageBody>;
  if (!list.length) {
    return (
      <PageBody>
        <PageHeader title="Submissions" />
        <EmptyState title="No assessments yet" description="Submissions appear here once students answer a published assessment."
          action={<Button asChild><Link to="/teacher/assessments/new">Create assessment</Link></Button>} />
      </PageBody>
    );
  }

  return (
    <PageBody>
      <PageHeader title="Submissions"
        description={a ? [`${plural(a.question_count, "question")}`, `${fmtMarks(a.total_marks)} marks`, a.deadline ? (new Date(a.deadline) < new Date() ? `closed ${fmtDate(a.deadline, false)}` : `due ${fmtDate(a.deadline)}`) : null].filter(Boolean).join(" · ") : undefined}
        actions={<>
          {outdated > 0 && <Button variant="secondary" onClick={() => setConfirm("reevaluate")}>Re-evaluate {outdated} outdated</Button>}
          <Button variant="secondary" disabled={notEvaluated.length === 0} onClick={() => setConfirm("evaluate")}>
            {notEvaluated.length === 0 ? "All answers evaluated" : `Evaluate ${notEvaluated.length} ${notEvaluated.length === 1 ? "submission" : "submissions"}`}
          </Button>
          <Button onClick={() => setConfirm("publish")} disabled={evaluated.length === 0}>Publish marks</Button>
        </>} />

      <Field id="sub-assessment" label="Assessment" className="max-w-md">
        <Select value={selectedId} onChange={(v) => setParams({ assessment: v })}
          options={list.map((x) => ({ value: x.id, label: x.title, meta: x.submission_counts.submitted + x.submission_counts.evaluated + x.submission_counts.published }))} />
      </Field>

      {subs.isLoading || !a ? <LoadingCards count={2} /> : subs.isError ? <ErrorState message={errorMessage(subs.error)} onRetry={() => subs.refetch()} /> : (
        <>
          <KpiRow>
            <KpiTile label="Submitted" value={items.length} />
            <KpiTile label="Not evaluated" value={notEvaluated.length} />
            <KpiTile label="Evaluated" value={evaluated.length} />
            <KpiTile label="Answers flagged" value={flagged} />
            <KpiTile label="Published" value={published.length} />
          </KpiRow>

          {outdated > 0 && (
            <Alert tone="warning" title={`${plural(outdated, "submission")} used an older rubric`}
              action={<Button size="sm" variant="secondary" onClick={() => setConfirm("reevaluate")}>Re-evaluate</Button>}>
              Re-evaluate them before publishing so the marks match the current rubric.
            </Alert>
          )}

          {items.length === 0 ? (
            <EmptyState title="No submissions yet"
              description={a.status === "draft" ? "Publish the assessment so students can answer it." : "Submitted answers appear here. Drafts stay private to students."} />
          ) : (
            <Table>
              <thead><tr><Th>Student</Th><Th>Submitted</Th><Th>Status</Th><Th className="text-right">Suggested</Th><Th className="text-right">Final</Th><Th><span className="sr-only">Actions</span></Th></tr></thead>
              <tbody>
                {items.map((s) => {
                  const evaluatedRow = s.status !== "submitted";
                  return (
                    <Tr key={s.id}>
                      <Td className="min-w-44">
                        <div className="font-medium text-slate-900">{s.student.name}</div>
                        <div className="text-caption text-slate-500">{s.student.email}</div>
                      </Td>
                      <Td className="tabular whitespace-nowrap text-slate-600">{fmtDate(s.submitted_at)}</Td>
                      <Td>
                        <div className="flex flex-wrap gap-1">
                          {s.rubric_outdated && s.status !== "published" ? <StatusBadge tone="warning">Rubric changed</StatusBadge> :
                            <SubmissionStatusBadge status={s.status} needsReview={s.needs_review_count > 0} />}
                          {s.source === "seed" && <DemoBadge />}
                        </div>
                      </Td>
                      <Td className="text-right">{s.ai_total !== null ? <Marks earned={s.ai_total} max={s.max_total} /> : "—"}</Td>
                      <Td className="text-right">{s.final_total !== null ? <Marks earned={s.final_total} max={s.max_total} /> : "—"}</Td>
                      <Td className="text-right">
                        <Button size="sm" variant="secondary" asChild>
                          <Link to={`/teacher/submissions/${s.id}`}>{!evaluatedRow ? "Evaluate" : s.status === "evaluated" ? "Review" : "View"}</Link>
                        </Button>
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          )}
          <p className="reading m-0 text-small text-slate-500">
            Suggested marks are advisory. Students see marks only after you publish them. The final mark is your adjusted mark where you changed it,
            otherwise the suggestion you accepted.
          </p>
        </>
      )}

      <ConfirmDialog open={confirm === "evaluate"} onOpenChange={(o) => !o && setConfirm(null)} loading={action.isPending} loadingLabel={`Evaluating ${notEvaluated.length} submissions`}
        title={`Evaluate ${plural(notEvaluated.length, "submission")}?`} confirmLabel="Evaluate answers"
        onConfirm={() => action.mutate("evaluate")}
        description={<p>The evaluator suggests marks, concept coverage and feedback for each answer. Nothing is shown to students until you publish.</p>} />
      <ConfirmDialog open={confirm === "reevaluate"} onOpenChange={(o) => !o && setConfirm(null)} loading={action.isPending} loadingLabel="Re-evaluating"
        title="Re-evaluate with the updated rubric?" confirmLabel="Re-evaluate answers" onConfirm={() => action.mutate("reevaluate")}
        description={<p>A new evaluation version is created for each affected submission. Earlier versions, including your adjustments, stay in the history, but adjustments must be made again.</p>} />
      <ConfirmDialog open={confirm === "publish"} onOpenChange={(o) => !o && setConfirm(null)} loading={action.isPending} loadingLabel="Publishing"
        title={`Publish marks for ${a?.title ?? "this assessment"}?`} confirmLabel={`Publish ${evaluated.length} ${evaluated.length === 1 ? "result" : "results"}`}
        confirmDisabled={evaluated.length === 0} onConfirm={() => action.mutate("publish")}
        description={<p>{evaluated.length
          ? `${plural(evaluated.length, "student")} will see their marks and feedback. You can unpublish a result later from its review page.`
          : "No evaluated results are waiting. Evaluate and review submissions first."}</p>}>
        {evaluated.length > 0 && (
          <div className="flex max-h-64 flex-col overflow-y-auto rounded-md border border-slate-100">
            {evaluated.map((s) => (
              <div key={s.id} className="flex justify-between gap-3 border-b border-slate-100 px-4 py-2 text-body last:border-b-0">
                <span className="min-w-0 truncate">{s.student.name}{s.needs_review_count > 0 && <span className="text-warning-text"> · {s.needs_review_count} flagged</span>}</span>
                <Marks earned={s.final_total} max={s.max_total} />
              </div>
            ))}
          </div>
        )}
        {(notEvaluated.length > 0 || flagged > 0) && (
          <p className="m-0 text-small text-slate-600">
            {notEvaluated.length > 0 && `${plural(notEvaluated.length, "submission")} ${notEvaluated.length === 1 ? "is" : "are"} not evaluated and will stay hidden. `}
            {flagged > 0 && `${plural(flagged, "answer")} ${flagged === 1 ? "is" : "are"} flagged for careful review. `}
            Results the server cannot publish (for example with an outdated rubric, or an unreviewed answer when review is required) are skipped and reported.
          </p>
        )}
      </ConfirmDialog>
    </PageBody>
  );
}
