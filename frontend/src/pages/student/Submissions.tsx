import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState, ErrorState, LoadingCards, Marks, PageBody, PageHeader, SubmissionStatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Table, Td, Th, Tr } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import type { StudentSubmissionItem } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { fmtDate } from "@/lib/utils";

export function SubmissionsPage() {
  usePageTitle("Submissions");
  const q = useQuery({ queryKey: ["my-submissions"], queryFn: () => api.get<StudentSubmissionItem[]>("/api/submissions/mine") });
  return (
    <PageBody>
      <PageHeader title="Submissions" description="Everything you have saved or submitted, with its current status." />
      {q.isLoading ? <LoadingCards /> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> :
        (q.data ?? []).length === 0 ? (
          <EmptyState title="No submissions yet" description="Start an assessment to see it here."
            action={<Button asChild><Link to="/student/assessments">Browse assessments</Link></Button>} />
        ) : (
          <Table>
            <thead><tr><Th>Assessment</Th><Th>Status</Th><Th>Last saved</Th><Th className="text-right">Final marks</Th><Th><span className="sr-only">Actions</span></Th></tr></thead>
            <tbody>
              {(q.data ?? []).map((s) => (
                <Tr key={s.id}>
                  <Td className="min-w-48"><div className="font-medium text-slate-900">{s.assessment_title}</div><div className="text-caption text-slate-500">{s.subject}</div></Td>
                  <Td><SubmissionStatusBadge status={s.status} audience="student" /></Td>
                  <Td className="tabular whitespace-nowrap text-slate-600">{s.submitted_at ? `Submitted ${fmtDate(s.submitted_at)}` : `Draft ${fmtDate(s.updated_at)}`}</Td>
                  <Td className="text-right">{s.total_score !== null ? <Marks earned={s.total_score} max={s.max_total} /> : <span className="text-small text-slate-500">Not published</span>}</Td>
                  <Td className="text-right">
                    <Button size="sm" variant={s.status === "published" ? "highlight" : "secondary"} asChild>
                      <Link to={s.status === "published" ? `/student/results/${s.id}` : `/student/assessments/${s.assessment_id}`}>
                        {s.status === "published" ? "View feedback" : s.status === "draft" ? "Continue" : "View answers"}
                      </Link>
                    </Button>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
    </PageBody>
  );
}
