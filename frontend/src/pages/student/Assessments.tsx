import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { EmptyState, ErrorState, LoadingCards, PageBody, PageHeader } from "@/components/common";
import { Segmented } from "@/components/ui/tabs";
import { api, errorMessage } from "@/lib/api";
import type { ResultSummary, StudentAssessment } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { fmtMarks } from "@/lib/utils";
import { AssessmentCard } from "@/pages/student/shared";

export function StudentAssessmentsPage() {
  usePageTitle("Assessments");
  const [view, setView] = useState<"open" | "done">("open");
  const q = useQuery({ queryKey: ["student-assessments"], queryFn: () => api.get<StudentAssessment[]>("/api/assessments") });
  const results = useQuery({ queryKey: ["my-results"], queryFn: () => api.get<ResultSummary[]>("/api/results/mine") });
  const items = q.data ?? [];
  const open = items.filter((a) => a.my_status === "not_started" || a.my_status === "draft");
  const done = items.filter((a) => !(a.my_status === "not_started" || a.my_status === "draft"));
  const scores = new Map((results.data ?? []).map((r) => [r.submission_id, `${fmtMarks(r.total_score)} / ${fmtMarks(r.max_total)}`]));
  const scoreOf = (a: StudentAssessment) => (a.my_status === "published" && a.submission_id ? scores.get(a.submission_id) : null);
  const shown = view === "open" ? open : done;

  return (
    <PageBody>
      <PageHeader title="Assessments" description="Assessments your teachers have published for you." />
      {q.isLoading ? <LoadingCards /> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> :
        items.length === 0 ? (
          <EmptyState title="No assessments yet" description="When a teacher publishes an assessment for you, it appears here." />
        ) : (
          <>
            <Segmented label="Show assessments" value={view} onChange={setView} className="self-start"
              options={[{ value: "open", label: "To answer", count: open.length }, { value: "done", label: "Submitted and past", count: done.length }]} />
            {shown.length ? (
              <div className="flex flex-col gap-3">{shown.map((a) => <AssessmentCard key={a.id} a={a} score={scoreOf(a)} />)}</div>
            ) : (
              <EmptyState title={view === "open" ? "Nothing to answer right now" : "Nothing submitted yet"}
                description={view === "open" ? "New assessments appear here when your teacher publishes them." : "Assessments you submit appear here with their status."} />
            )}
          </>
        )}
    </PageBody>
  );
}
