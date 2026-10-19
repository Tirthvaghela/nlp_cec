// A published result. The API refuses unpublished results, so nothing here is ever shown before the teacher publishes.
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { BackLink, ErrorState, LoadingCards, Marks, PageBody, PageHeader } from "@/components/common";
import { RichText } from "@/components/RichText";
import { AnswerView, RubricBreakdown, StudentFeedbackCard } from "@/components/evaluation";
import { Card, Overline } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { wordCountOf } from "@/lib/markdown";
import type { ResultDetail } from "@/lib/types";
import { usePageTitle } from "@/lib/usePageTitle";
import { fmtDate, fmtMarks } from "@/lib/utils";

export function ResultDetailPage() {
  const { id } = useParams<{ id: string }>();
  const q = useQuery({ queryKey: ["result", id], queryFn: () => api.get<ResultDetail>(`/api/results/submission/${id}`) });
  usePageTitle(q.data ? `${q.data.assessment_title} result` : "Result");
  if (q.isLoading) return <PageBody width="reading"><LoadingCards /></PageBody>;
  if (q.isError || !q.data) return <PageBody width="reading"><ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /></PageBody>;
  const r = q.data;

  return (
    <PageBody width="reading">
      <PageHeader back={<BackLink to="/student/results">Results</BackLink>} title={r.assessment_title}
        status={<span>{r.subject} · published {fmtDate(r.published_at, false)} · marks confirmed by your teacher</span>}
        actions={
          <div className="flex flex-col items-end gap-1 rounded-md border border-slate-100 bg-white px-5 py-3">
            <Overline>Final marks</Overline>
            <Marks earned={r.total_score} max={r.max_total} size="score" />
            <span className="tabular text-caption text-slate-500">{r.percentage}% of the total</span>
          </div>
        } />

      {r.questions.map((qq, i) => (
        <section key={qq.question_id} className="flex flex-col gap-4" aria-labelledby={`rq-${i}`}>
          <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
            <div className="min-w-0 flex-1">
              <Overline as="h2" id={`rq-${i}`}>Question {i + 1}</Overline>
              <RichText text={qq.text} size="body-lg" className="font-medium" />
            </div>
            <div className="flex flex-col items-end">
              <Marks earned={qq.final_score} max={qq.max_marks} size="score" />
              {qq.adjusted_by_teacher && <span className="tabular text-caption text-slate-500">Adjusted by your teacher (suggested {fmtMarks(qq.ai_score)})</span>}
            </div>
          </div>

          <StudentFeedbackCard score={qq.final_score} max={qq.max_marks} concepts={qq.concepts} feedback={qq.feedback} teacherComment={qq.teacher_feedback} />

          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <Card className="p-5 sm:p-6">
              <AnswerView answer={qq.answer} concepts={qq.concepts} wordCount={wordCountOf(qq.answer)} />
            </Card>
            <Card className="flex flex-col gap-4 p-5 sm:p-6">
              <Overline as="h3">Marks by criterion</Overline>
              <RubricBreakdown items={qq.concepts.map((c) => ({ label: c.label, awarded: c.awarded, marks: c.marks }))} />
              {qq.adjusted_by_teacher && <p className="m-0 text-caption text-slate-500">These criterion marks show the automatic analysis. Your teacher adjusted the question total.</p>}
            </Card>
          </div>
        </section>
      ))}
      <p className="m-0 text-small text-slate-500">
        Marks are suggested by a rubric-matching model and confirmed by your teacher. Highlighted text shows the sentences credited to each
        criterion; a dashed underline means partial credit.
      </p>
    </PageBody>
  );
}
