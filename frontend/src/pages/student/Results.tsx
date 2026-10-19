import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState, ErrorState, LoadingCards, Marks, PageBody, PageHeader, SectionTitle } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Alert, Card, ProgressBar, Table, Td, Th, Tr } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import type { StudentAssessment, StudentProgress } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { fmtDate } from "@/lib/utils";

export function ResultsPage() {
  usePageTitle("Results");
  const q = useQuery({ queryKey: ["my-progress"], queryFn: () => api.get<StudentProgress>("/api/analytics/student") });
  const assessments = useQuery({ queryKey: ["student-assessments"], queryFn: () => api.get<StudentAssessment[]>("/api/assessments") });
  const p = q.data;
  const awaiting = (assessments.data ?? []).filter((a) => a.my_status === "submitted" || a.my_status === "evaluated");

  return (
    <PageBody>
      <PageHeader title="Results" description="Published results only. Marks are final once your teacher has reviewed them." />
      {q.isLoading ? <LoadingCards /> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> : (
        <>
          {awaiting.map((a) => (
            <Alert key={a.id} tone="info" title={`${a.title}: awaiting results`}>Submitted {fmtDate(a.submitted_at)}. Your result appears here once your teacher publishes it.</Alert>
          ))}
          {!p || p.results.length === 0 ? (
            <EmptyState title="No published results yet" description="Once your teacher reviews and publishes a result, your marks and feedback appear here." />
          ) : (
            <>
              <Table>
                <thead><tr><Th>Assessment</Th><Th>Published</Th><Th className="text-right">Final marks</Th><Th><span className="sr-only">Actions</span></Th></tr></thead>
                <tbody>
                  {[...p.results].reverse().map((r) => (
                    <Tr key={r.submission_id}>
                      <Td className="min-w-48"><div className="font-medium text-slate-900">{r.assessment_title}</div><div className="text-caption text-slate-500">{r.subject}</div></Td>
                      <Td className="tabular whitespace-nowrap text-slate-600">{fmtDate(r.published_at, false)}</Td>
                      <Td className="text-right"><Marks earned={r.score} max={r.max_total} /></Td>
                      <Td className="text-right"><Button size="sm" variant="highlight" asChild><Link to={`/student/results/${r.submission_id}`}>View feedback</Link></Button></Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
              <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                <section className="flex flex-col gap-4" aria-labelledby="prog-h">
                  <SectionTitle id="prog-h">Progress</SectionTitle>
                  <ul className="m-0 flex list-none flex-col gap-4 rounded-md border border-slate-100 bg-white p-5">
                    {p.results.map((r) => (
                      <li key={r.submission_id} className="flex flex-col gap-2">
                        <div className="flex items-baseline justify-between gap-3 text-body">
                          <span className="min-w-0 truncate text-slate-900">{r.assessment_title}</span>
                          <span className="tabular font-medium text-ink-900">{r.percentage}%</span>
                        </div>
                        <ProgressBar value={r.percentage} max={100} label={`${r.assessment_title}: ${r.percentage}%`} />
                      </li>
                    ))}
                  </ul>
                  {p.average_percentage != null && <p className="tabular m-0 text-small text-slate-600">Average {p.average_percentage}% · best {p.best_percentage}%</p>}
                </section>
                <Card className="flex flex-col gap-3 p-5">
                  <h2 className="m-0 text-h4 font-semibold text-slate-900">Concepts to revisit</h2>
                  <p className="m-0 text-small text-slate-600">The criteria most often missing from your answers.</p>
                  {p.most_missed_concepts.length === 0 ? <p className="m-0 text-body text-slate-600">No missing concepts so far.</p> : (
                    <ul className="m-0 flex list-none flex-col p-0">
                      {p.most_missed_concepts.map((c) => (
                        <li key={c.label} className="flex justify-between gap-3 border-b border-slate-100 py-2 text-body last:border-b-0">
                          <span>{c.label}</span><span className="tabular text-slate-500">{c.count}×</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
              </div>
            </>
          )}
        </>
      )}
    </PageBody>
  );
}
