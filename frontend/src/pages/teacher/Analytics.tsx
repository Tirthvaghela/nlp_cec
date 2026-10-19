// Assessment analytics from GET /api/analytics/assessment/:id. Only evaluated submissions are counted and no figure is
// invented: charts the service has no data for are not drawn.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { Heatmap, Histogram, MeterBars } from "@/components/charts";
import { EmptyState, ErrorState, LoadingCards, Note, PageBody, PageHeader } from "@/components/common";
import { Field, KpiRow, KpiTile } from "@/components/ui/primitives";
import { Select } from "@/components/ui/select";
import { api, errorMessage } from "@/lib/api";
import { previewText } from "@/lib/markdown";
import { conceptId } from "@/lib/status";
import type { Assessment, AssessmentAnalytics } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { fmtMarks, plural } from "@/lib/utils";

export function AnalyticsPage() {
  usePageTitle("Analytics");
  const [params, setParams] = useSearchParams();
  const assessments = useQuery({ queryKey: ["assessments"], queryFn: () => api.get<Assessment[]>("/api/assessments") });
  const withData = useMemo(() => (assessments.data ?? []).filter((a) => a.status !== "draft"), [assessments.data]);
  const selected = params.get("assessment") ?? "";

  useEffect(() => {
    if (!selected && withData.length) {
      const best = withData.find((a) => a.submission_counts.evaluated + a.submission_counts.published > 0) ?? withData[0];
      setParams({ assessment: best.id }, { replace: true });
    }
  }, [selected, withData, setParams]);

  const stats = useQuery({
    queryKey: ["analytics", selected],
    queryFn: () => api.get<AssessmentAnalytics>(`/api/analytics/assessment/${selected}`),
    enabled: Boolean(selected),
  });
  const s = stats.data;
  const maxConcepts = Math.max(0, ...(s?.questions ?? []).map((q) => q.concepts.length));

  return (
    <PageBody>
      <PageHeader title="Analytics" description="Class results by question and criterion, from evaluated submissions only." />

      {assessments.isLoading ? <LoadingCards count={2} /> : assessments.isError ? <ErrorState message={errorMessage(assessments.error)} onRetry={() => assessments.refetch()} /> :
        withData.length === 0 ? (
          <EmptyState title="No published assessments yet" description="Analytics appear once students have submitted and you have evaluated their answers." />
        ) : (
          <>
            <Field id="analytics-assessment" label="Assessment" className="max-w-md">
              <Select value={selected} onChange={(v) => setParams({ assessment: v })} options={withData.map((a) => ({ value: a.id, label: a.title }))} />
            </Field>

            {stats.isLoading ? <LoadingCards /> : stats.isError ? <ErrorState message={errorMessage(stats.error)} onRetry={() => stats.refetch()} /> : s && (
              s.basis.evaluated === 0 ? (
                <EmptyState title="No evaluated submissions yet"
                  description={`${plural(s.submission_status.submitted, "submission")} ${s.submission_status.submitted === 1 ? "is" : "are"} waiting for evaluation. Statistics appear after evaluation.`} />
              ) : (
                <>
                  <p className="m-0 text-small text-slate-600">
                    Based on {plural(s.basis.evaluated, "evaluated submission")}, {s.basis.published} published. Final marks are your adjusted mark where
                    you changed it, otherwise the suggested mark.
                  </p>
                  <KpiRow>
                    <KpiTile label="Class average" value={s.average_percentage !== null ? `${s.average_percentage}%` : "—"}
                      caption={s.median_percentage !== null ? `Median ${s.median_percentage}%` : undefined} />
                    <KpiTile label="Range" value={s.lowest_percentage !== null ? `${s.lowest_percentage}–${s.highest_percentage}%` : "—"} caption="Lowest to highest" />
                    <KpiTile label="Answers adjusted" value={`${s.review.adjusted} of ${s.review.evaluations}`}
                      caption={s.review.mean_absolute_adjustment !== null ? `Mean change ${s.review.mean_absolute_adjustment} marks` : "Changed from the suggested mark"} />
                    <KpiTile label="Flagged for review" value={s.review.flagged_for_review} caption={`${s.review.reviewed} reviewed by you`} />
                  </KpiRow>

                  <div className="grid items-start gap-6 lg:grid-cols-2">
                    <Histogram title="How are marks spread?" caption="Number of students in each final-mark band, as a share of the total marks."
                      data={s.distribution.map((d) => ({ label: d.range, count: d.count }))} />
                    <MeterBars title="Average mark per question" caption="Mean final mark of evaluated answers, out of each question's maximum."
                      data={s.questions.map((q) => ({
                        label: `Q${q.order + 1} · ${previewText(q.text, 5)}`, detail: q.text, value: q.average_score, max: q.max_marks,
                        display: q.average_score !== null ? `${fmtMarks(q.average_score)} / ${fmtMarks(q.max_marks)}` : "—",
                      }))} />
                  </div>

                  {maxConcepts > 0 ? (
                    <Heatmap title="Which criteria are students missing?" measure="matched"
                      caption="Share of answers that fully matched each criterion. Lighter cells are criteria students often miss."
                      columns={Array.from({ length: maxConcepts }, (_, i) => conceptId(i + 1))}
                      rows={s.questions.map((q) => ({
                        label: `Q${q.order + 1}`, detail: q.text,
                        cells: Array.from({ length: maxConcepts }, (_, i) => {
                          const c = q.concepts[i];
                          if (!c) return null;
                          const total = c.matched + c.partial + c.missing;
                          return { value: total ? Math.round((100 * c.matched) / total) : 0, label: c.label };
                        }),
                      }))} />
                  ) : <Note>These questions have no rubric criteria, so criterion coverage cannot be shown.</Note>}

                  <Note>
                    Agreement charts (suggested against final mark per answer, and agreement over time) need per-answer history that the analytics
                    service does not provide yet, so they are not shown.
                  </Note>
                </>
              )
            )}
          </>
        )}
    </PageBody>
  );
}
