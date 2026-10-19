import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState, ErrorState, LoadingCards, PageBody, PageHeader, SectionTitle } from "@/components/common";
import { KpiRow, KpiTile, ProgressBar } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ResultSummary, StudentAssessment, StudentProgress } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { firstName, fmtMarks, plural } from "@/lib/utils";
import { AssessmentCard } from "@/pages/student/shared";

const ORDER: Record<StudentAssessment["my_status"], number> = { draft: 0, not_started: 1, submitted: 2, evaluated: 2, published: 3, missed: 4 };

export function StudentDashboard() {
  usePageTitle("Dashboard");
  const { user } = useAuth();
  const assessments = useQuery({ queryKey: ["student-assessments"], queryFn: () => api.get<StudentAssessment[]>("/api/assessments") });
  const results = useQuery({ queryKey: ["my-results"], queryFn: () => api.get<ResultSummary[]>("/api/results/mine") });
  const progress = useQuery({ queryKey: ["my-progress"], queryFn: () => api.get<StudentProgress>("/api/analytics/student") });

  const list = [...(assessments.data ?? [])].sort((x, y) => ORDER[x.my_status] - ORDER[y.my_status]);
  const todo = list.filter((a) => (a.my_status === "not_started" || a.my_status === "draft") && !a.deadline_passed && a.status === "published");
  const waiting = list.filter((a) => a.my_status === "submitted" || a.my_status === "evaluated").length;
  const scoreBySubmission = new Map((results.data ?? []).map((r) => [r.submission_id, `${fmtMarks(r.total_score)} / ${fmtMarks(r.max_total)}`]));
  const first = firstName(user?.name ?? "");

  return (
    <PageBody>
      <PageHeader title={`Hello, ${first}.`}
        description={assessments.data ? (todo.length ? `${plural(todo.length, "assessment")} ready for you to answer.` : "Nothing is waiting for an answer right now.") : undefined} />

      <KpiRow>
        <KpiTile label="To answer" value={assessments.data ? todo.length : "—"} />
        <KpiTile label="Awaiting results" value={assessments.data ? waiting : "—"} />
        <KpiTile label="Results published" value={results.data ? results.data.length : "—"} />
        <KpiTile label="Average score" value={progress.data?.average_percentage != null ? `${progress.data.average_percentage}%` : "—"}
          caption={progress.data?.best_percentage != null ? `Best ${progress.data.best_percentage}%` : "Shown after your first published result"} />
      </KpiRow>

      <section className="flex flex-col gap-4" aria-labelledby="sa-h">
        <SectionTitle id="sa-h" aside={list.length > 6 && <Link to="/student/assessments" className="text-small font-medium">View all assessments</Link>}>Assessments</SectionTitle>
        {assessments.isLoading ? <LoadingCards count={2} /> : assessments.isError ? <ErrorState message={errorMessage(assessments.error)} onRetry={() => assessments.refetch()} /> :
          list.length === 0 ? (
            <EmptyState title="No assessments yet" description="When a teacher publishes an assessment for you, it appears here." />
          ) : (
            <div className="flex flex-col gap-3">
              {list.slice(0, 6).map((a) => (
                <AssessmentCard key={a.id} a={a} score={a.my_status === "published" && a.submission_id ? scoreBySubmission.get(a.submission_id) : null} />
              ))}
            </div>
          )}
      </section>

      <section className="flex flex-col gap-4" aria-labelledby="sp-h">
        <SectionTitle id="sp-h">Your progress</SectionTitle>
        {progress.isLoading ? <LoadingCards count={1} /> : (progress.data?.results.length ?? 0) === 0 ? (
          <p className="m-0 text-body text-slate-600">Your progress appears after your teacher reviews and publishes your first result.</p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-4 rounded-md border border-slate-100 bg-white p-5 sm:p-6">
            {progress.data!.results.map((r) => (
              <li key={r.submission_id} className="flex flex-col gap-2">
                <div className="flex items-baseline justify-between gap-3">
                  <Link to={`/student/results/${r.submission_id}`} className="min-w-0 truncate text-body text-slate-900 no-underline hover:text-ink-700 hover:underline">{r.assessment_title}</Link>
                  <span className="tabular whitespace-nowrap text-small font-medium text-ink-900">{fmtMarks(r.score)} <span className="font-normal text-slate-400">/ {fmtMarks(r.max_total)}</span></span>
                </div>
                <ProgressBar value={r.percentage} max={100} label={`${r.assessment_title}: ${r.percentage}%`} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </PageBody>
  );
}
