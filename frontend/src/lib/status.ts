// Status vocabulary: each state has a label and a badge tone (STYLEGUIDE §10.5 - Published success, Evaluated ink,
// Needs review warning, Late/missed danger, Draft slate). Labels only describe states the API has confirmed.
import type { BadgeTone } from "@/components/ui/primitives";
import type { AssessmentStatus, Confidence, StudentStatus, SubmissionStatus } from "@/lib/types";

export const ASSESSMENT_STATUS: Record<AssessmentStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: "Draft", tone: "slate" },
  published: { label: "Published", tone: "success" },
  closed: { label: "Closed", tone: "slate" },
};

export const STUDENT_STATUS: Record<StudentStatus, { label: string; tone: BadgeTone }> = {
  not_started: { label: "Not started", tone: "slate" },
  draft: { label: "Draft saved", tone: "slate" },
  submitted: { label: "Awaiting results", tone: "ink" },
  evaluated: { label: "Awaiting results", tone: "ink" },
  published: { label: "Published", tone: "success" },
  missed: { label: "Missed", tone: "danger" },
};

export const SUBMISSION_TEACHER: Record<SubmissionStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: "Draft", tone: "slate" },
  submitted: { label: "Not evaluated", tone: "slate" },
  evaluated: { label: "Evaluated", tone: "ink" },
  published: { label: "Published", tone: "success" },
};

export const SUBMISSION_STUDENT: Record<SubmissionStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: "Draft saved", tone: "slate" },
  submitted: { label: "Awaiting results", tone: "ink" },
  evaluated: { label: "Under teacher review", tone: "ink" },
  published: { label: "Published", tone: "success" },
};

export const CONFIDENCE: Record<Confidence, { short: string; label: string; title: string; tone: BadgeTone }> = {
  high: { short: "High", label: "High confidence", title: "No warning signs were detected.", tone: "success" },
  medium: { short: "Medium", label: "Check recommended", title: "One warning sign was detected - see the review notes.", tone: "warning" },
  low: { short: "Low", label: "Careful review needed", title: "Several or serious warning signs were detected - see the review notes.", tone: "warning" },
};

/** Display id of the n-th rubric criterion (1-based): C1, C2 ... */
export const conceptId = (index: number) => `C${index}`;
