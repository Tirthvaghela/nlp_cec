import type { StudentAssessment } from "@/lib/types";

export function actionFor(a: StudentAssessment): { label: string; to: string; primary: boolean } {
  switch (a.my_status) {
    case "not_started": return { label: "Start", to: `/student/assessments/${a.id}`, primary: true };
    case "draft": return { label: a.deadline_passed || a.status === "closed" ? "View" : "Continue", to: `/student/assessments/${a.id}`, primary: !a.deadline_passed };
    case "published": return { label: "View result", to: `/student/results/${a.submission_id}`, primary: true };
    default: return { label: "View submission", to: `/student/assessments/${a.id}`, primary: false };
  }
}
