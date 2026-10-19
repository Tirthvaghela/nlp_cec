import { Link } from "react-router-dom";

import { StudentStatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import { actionFor } from "@/lib/studentActions";
import type { StudentAssessment } from "@/lib/types";
import { fmtDate, fmtMarks, plural, relativeTime } from "@/lib/utils";

/** Assessment row on student screens: title and meta, status, final marks once published, and the next step. */
export function AssessmentCard({ a, score }: { a: StudentAssessment; score?: string | null }) {
  const act = actionFor(a);
  const meta = a.submitted_at
    ? `Submitted ${fmtDate(a.submitted_at)}`
    : [plural(a.question_count, "question"), `${fmtMarks(a.total_marks)} marks`,
      a.deadline ? (a.deadline_passed ? `closed ${fmtDate(a.deadline)}` : `due ${fmtDate(a.deadline)} (${relativeTime(a.deadline)})`) : null,
    ].filter(Boolean).join(" · ");
  const variant = a.my_status === "published" ? "highlight" : act.primary ? "primary" : "secondary";
  return (
    <Card className="grid items-center gap-x-6 gap-y-3 p-5 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
      <div className="flex min-w-0 flex-col gap-1">
        <span className="text-body font-semibold text-slate-900">{a.title}</span>
        <span className="tabular text-small text-slate-600">{meta}</span>
        <span className="text-caption text-slate-500">{a.subject} · {a.teacher_name}</span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <StudentStatusBadge status={a.my_status} />
        {score && <span className="tabular text-body font-medium text-ink-900">{score}</span>}
      </div>
      <Button asChild variant={variant} className="justify-self-start sm:justify-self-end">
        <Link to={act.to}>{act.label}</Link>
      </Button>
    </Card>
  );
}
