import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { AssessmentStatusBadge, EmptyState, ErrorState, LoadingCards, PageBody, PageHeader, SectionTitle } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, KpiRow, KpiTile, Overline, Table, Td, Th, Tr } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Assessment, TeacherOverview } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { firstName, fmtDate, fmtMarks, plural } from "@/lib/utils";

type Task = { key: string; overline: string; title: string; body: string; cta: string; to: string };

/** "Needs your attention", derived only from real submission counts and assessment states. */
function attentionTasks(assessments: Assessment[]): Task[] {
  const due = (a: Assessment) =>
    a.deadline ? (new Date(a.deadline) < new Date() ? `Submissions closed ${fmtDate(a.deadline, false)}.` : `Accepting submissions until ${fmtDate(a.deadline)}.`) : "";
  const evaluation: Task[] = [];
  const drafts: Task[] = [];
  const open: Task[] = [];
  for (const a of assessments) {
    const c = a.submission_counts;
    const subs = `/teacher/submissions?assessment=${a.id}`;
    if (c.submitted > 0 || c.evaluated > 0) {
      evaluation.push({
        key: a.id + "e", overline: `${a.title} · Review`, cta: "Open submissions", to: subs,
        title: c.submitted > 0
          ? `${plural(c.submitted, "submission")} to evaluate${c.evaluated > 0 ? `, ${c.evaluated} to review` : ""}`
          : `${plural(c.evaluated, "answer set")} ${c.evaluated === 1 ? "needs" : "need"} your review`,
        body: `${due(a)} Review the suggested marks and publish when you are satisfied.`.trim(),
      });
    } else if (a.status === "draft") {
      drafts.push({
        key: a.id + "d", overline: `${a.title} · Draft`, cta: "Continue editing", to: `/teacher/assessments/${a.id}`,
        title: a.question_count === 0 ? "No questions yet" : `${plural(a.question_count, "question")} · ${fmtMarks(a.total_marks)} marks`,
        body: "Students cannot see it until you publish it.",
      });
    } else if (a.status === "published") {
      open.push({
        key: a.id + "o", overline: `${a.title} · Published`, cta: "View assessment", to: `/teacher/assessments/${a.id}`,
        title: `${c.published} published · ${plural(c.draft, "draft")} in progress`,
        body: due(a) || "Accepting submissions. No deadline is set.",
      });
    }
  }
  return [...evaluation, ...drafts, ...open].slice(0, 3);
}

export function TeacherDashboard() {
  usePageTitle("Dashboard");
  const { user } = useAuth();
  const overview = useQuery({ queryKey: ["overview"], queryFn: () => api.get<TeacherOverview>("/api/analytics/overview") });
  const assessments = useQuery({ queryKey: ["assessments"], queryFn: () => api.get<Assessment[]>("/api/assessments") });
  const o = overview.data;
  const list = assessments.data ?? [];
  const tasks = attentionTasks(list);
  const first = firstName(user?.name ?? "");
  const upcoming = list.filter((a) => a.deadline && new Date(a.deadline) > new Date()).sort((x, y) => x.deadline!.localeCompare(y.deadline!)).slice(0, 4);

  return (
    <PageBody>
      <PageHeader title={`Good to see you, ${first}.`}
        description={o ? (o.answers_flagged_for_review > 0 ? `${plural(o.answers_flagged_for_review, "answer")} ${o.answers_flagged_for_review === 1 ? "needs" : "need"} your review.` : "No answers are waiting for review.") : undefined}
        actions={<Button icon={<Plus aria-hidden />} asChild><Link to="/teacher/assessments/new"><Plus aria-hidden />New assessment</Link></Button>} />

      {overview.isError ? <ErrorState message={errorMessage(overview.error)} onRetry={() => overview.refetch()} /> : (
        <KpiRow>
          <KpiTile label="Awaiting evaluation" value={o ? o.submissions_awaiting_evaluation : "—"} caption="Submitted, not yet evaluated" />
          <KpiTile label="Awaiting publication" value={o ? o.submissions_awaiting_publication : "—"} caption="Evaluated, not yet published" />
          <KpiTile label="Answers flagged" value={o ? o.answers_flagged_for_review : "—"} caption="Need careful review" />
          <KpiTile label="Results published" value={o ? o.results_published : "—"}
            caption={o?.average_published_percentage != null ? `Class average ${o.average_published_percentage}%` : "No published results yet"} />
        </KpiRow>
      )}

      <section className="flex flex-col gap-4" aria-labelledby="attention-h">
        <SectionTitle id="attention-h">Needs your attention</SectionTitle>
        {assessments.isLoading ? <LoadingCards count={1} /> : assessments.isError ? (
          <ErrorState message={errorMessage(assessments.error)} onRetry={() => assessments.refetch()} />
        ) : tasks.length === 0 ? (
          <EmptyState title="Nothing is waiting for you" description="Submissions to evaluate or publish, and draft assessments, appear here." />
        ) : (
          <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr))]">
            {tasks.map((t) => (
              <Card key={t.key} className="flex flex-col gap-2 p-5">
                <Overline className="truncate">{t.overline}</Overline>
                <span className="text-h4 font-semibold text-slate-900">{t.title}</span>
                <span className="flex-1 text-small text-slate-600">{t.body}</span>
                <Button variant="tertiary" size="sm" asChild className="mt-1 self-start px-0 hover:bg-transparent hover:underline"><Link to={t.to}>{t.cta}<ArrowRight aria-hidden /></Link></Button>
              </Card>
            ))}
          </div>
        )}
      </section>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section className="flex min-w-0 flex-col gap-4" aria-labelledby="assess-h">
          <SectionTitle id="assess-h" aside={<Link to="/teacher/assessments" className="text-small font-medium">View all assessments</Link>}>Recent assessments</SectionTitle>
          {assessments.isLoading ? <LoadingCards count={2} /> : list.length === 0 ? (
            <EmptyState title="No assessments yet" description="Create your first assessment to get started."
              action={<Button asChild><Link to="/teacher/assessments/new">Create assessment</Link></Button>} />
          ) : (
            <Table>
              <thead><tr><Th>Assessment</Th><Th>Status</Th><Th className="text-right">Submissions</Th></tr></thead>
              <tbody>
                {[...list].sort((x, y) => y.updated_at.localeCompare(x.updated_at)).slice(0, 6).map((a) => {
                  const c = a.submission_counts;
                  return (
                    <Tr key={a.id}>
                      <Td className="min-w-48"><Link to={`/teacher/assessments/${a.id}`} className="font-medium text-slate-900 no-underline hover:text-ink-700 hover:underline">{a.title}</Link>
                        <div className="text-caption text-slate-500">Updated {fmtDate(a.updated_at, false)}</div></Td>
                      <Td><AssessmentStatusBadge status={a.status} /></Td>
                      <Td className="tabular text-right">{c.submitted + c.evaluated + c.published}</Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </section>
        <section className="flex min-w-0 flex-col gap-4" aria-labelledby="due-h">
          <SectionTitle id="due-h">Upcoming deadlines</SectionTitle>
          <Card className="p-2">
            {upcoming.length === 0 ? <p className="m-0 p-3 text-body text-slate-600">No upcoming deadlines.</p> : (
              <ul className="m-0 list-none p-0">
                {upcoming.map((a) => (
                  <li key={a.id} className="flex flex-col gap-0.5 border-b border-slate-100 px-3 py-3 last:border-b-0">
                    <Link to={`/teacher/assessments/${a.id}`} className="text-body font-medium text-slate-900 no-underline hover:text-ink-700 hover:underline">{a.title}</Link>
                    <span className="tabular text-small text-slate-600">Due {fmtDate(a.deadline)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </section>
      </div>
    </PageBody>
  );
}
