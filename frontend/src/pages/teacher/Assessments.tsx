import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { AssessmentStatusBadge, EmptyState, ErrorState, LoadingCards, PageBody, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Table, Td, Th, Tr } from "@/components/ui/primitives";
import { Segmented } from "@/components/ui/tabs";
import { api, errorMessage } from "@/lib/api";
import type { Assessment, AssessmentStatus } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { fmtDate, fmtMarks } from "@/lib/utils";

const FILTERS: { value: AssessmentStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "draft", label: "Drafts" },
  { value: "published", label: "Published" },
  { value: "closed", label: "Closed" },
];

function rowAction(a: Assessment): { label: string; to: string } {
  const c = a.submission_counts;
  if (c.submitted > 0 || c.evaluated > 0) return { label: "Review", to: `/teacher/submissions?assessment=${a.id}` };
  if (a.status === "draft") return { label: "Edit", to: `/teacher/assessments/${a.id}` };
  return { label: "Open", to: `/teacher/assessments/${a.id}` };
}

export function AssessmentsPage() {
  usePageTitle("Assessments");
  const [filter, setFilter] = useState<AssessmentStatus | "all">("all");
  const q = useQuery({ queryKey: ["assessments"], queryFn: () => api.get<Assessment[]>("/api/assessments") });
  const all = q.data ?? [];
  const items = all.filter((a) => filter === "all" || a.status === filter);
  const count = (v: AssessmentStatus | "all") => all.filter((a) => v === "all" || a.status === v).length;

  return (
    <PageBody>
      <PageHeader title="Assessments" description="Create assessments, write questions with reference answers and rubrics, and manage submissions."
        actions={<Button asChild><Link to="/teacher/assessments/new"><Plus aria-hidden />New assessment</Link></Button>} />

      {q.isLoading ? <LoadingCards /> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> : (
        <>
          <Segmented label="Filter by status" value={filter} onChange={setFilter} className="self-start"
            options={FILTERS.map((f) => ({ ...f, count: count(f.value) }))} />
          {items.length === 0 ? (
            <EmptyState title={filter === "all" ? "No assessments yet" : `No ${FILTERS.find((f) => f.value === filter)!.label.toLowerCase()} assessments`}
              description="An assessment groups descriptive questions with their reference answers and rubrics."
              action={filter === "all" ? <Button asChild><Link to="/teacher/assessments/new">Create assessment</Link></Button> : undefined} />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Assessment</Th><Th>Status</Th><Th className="text-right">Questions</Th><Th className="text-right">Marks</Th>
                  <Th>Deadline</Th><Th className="text-right">Submissions</Th><Th><span className="sr-only">Actions</span></Th>
                </tr>
              </thead>
              <tbody>
                {items.map((a) => {
                  const c = a.submission_counts;
                  const act = rowAction(a);
                  const total = c.submitted + c.evaluated + c.published;
                  return (
                    <Tr key={a.id}>
                      <Td className="min-w-56">
                        <Link to={`/teacher/assessments/${a.id}`} className="font-medium text-slate-900 no-underline hover:text-ink-700 hover:underline">{a.title}</Link>
                        <div className="text-caption text-slate-500">{a.subject}</div>
                      </Td>
                      <Td><AssessmentStatusBadge status={a.status} /></Td>
                      <Td className="tabular text-right">{a.question_count}</Td>
                      <Td className="tabular text-right">{fmtMarks(a.total_marks)}</Td>
                      <Td className="tabular whitespace-nowrap text-slate-600">{a.deadline ? fmtDate(a.deadline) : "—"}</Td>
                      <Td className="tabular text-right" title={`${c.submitted} not evaluated · ${c.evaluated} evaluated · ${c.published} published`}>
                        {total}
                        {(c.submitted > 0 || c.evaluated > 0) && <div className="text-caption text-slate-500">{c.submitted + c.evaluated} to review</div>}
                      </Td>
                      <Td className="text-right"><Button size="sm" variant="secondary" asChild><Link to={act.to}>{act.label}</Link></Button></Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </>
      )}
    </PageBody>
  );
}
