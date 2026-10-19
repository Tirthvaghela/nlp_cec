// Page chrome and shared display components in the Margin system.
import { ChevronLeft, Inbox, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Alert, Card, Skeleton, StatusBadge } from "@/components/ui/primitives";
import { LEVEL_META } from "@/lib/levels";
import { ASSESSMENT_STATUS, CONFIDENCE, STUDENT_STATUS, SUBMISSION_STUDENT, SUBMISSION_TEACHER } from "@/lib/status";
import type { AssessmentStatus, Confidence, Level, StudentStatus, SubmissionStatus } from "@/lib/types";
import { cn, fmtMarks, fmtScore } from "@/lib/utils";
import { ConceptTag } from "@/components/ui/primitives";

/* ------------------------------------------------------------ page chrome */

/** Page container: max 1200px; side padding 16 (phone) / 24 (tablet) / 40 (desktop). */
export function PageBody({ width = "default", className, children }: {
  width?: "narrow" | "default" | "reading"; className?: string; children: ReactNode;
}) {
  const max = { narrow: "max-w-[760px]", reading: "max-w-[960px]", default: "max-w-[1200px]" }[width];
  return <div className={cn("mx-auto flex w-full min-w-0 flex-col gap-8 px-4 pb-16 pt-6 sm:px-6 sm:pt-8 lg:px-10", max, className)}>{children}</div>;
}

/** Breadcrumb-style back link above a page title. */
export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="inline-flex min-h-6 items-center gap-1 self-start text-small text-slate-600 no-underline hover:text-ink-700">
      <ChevronLeft className="size-4" aria-hidden />{children}
    </Link>
  );
}

export function PageHeader({ title, description, actions, eyebrow, back, status }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode; back?: ReactNode; status?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="flex min-w-0 flex-col gap-2">
        {back}
        {eyebrow && <div className="eyebrow text-slate-500">{eyebrow}</div>}
        <h1 className="m-0 text-h2 font-semibold text-slate-900 sm:text-h1">{title}</h1>
        {status && <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-small text-slate-600">{status}</div>}
        {description && <p className="reading m-0 text-body text-slate-600">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </header>
  );
}

export function SectionTitle({ children, className, id, as: Tag = "h2", aside }: {
  children: ReactNode; className?: string; id?: string; as?: "h2" | "h3"; aside?: ReactNode;
}) {
  const heading = <Tag id={id} className={cn("m-0 font-semibold text-slate-900", Tag === "h2" ? "text-h3" : "text-h4", className)}>{children}</Tag>;
  if (!aside) return heading;
  return <div className="flex flex-wrap items-baseline justify-between gap-3">{heading}{aside}</div>;
}

export function EmptyState({ title, description, action, className, icon }: {
  title: string; description?: ReactNode; action?: ReactNode; className?: string; icon?: ReactNode;
}) {
  return (
    <div className={cn("flex flex-col items-center gap-3 rounded-md border border-dashed border-slate-200 bg-white px-6 py-12 text-center", className)}>
      <span className="grid size-11 place-items-center rounded-full bg-ink-50 text-ink-600">{icon ?? <Inbox className="size-5" aria-hidden />}</span>
      <h2 className="m-0 text-h4 font-semibold text-slate-900">{title}</h2>
      {description && <p className="m-0 max-w-[56ch] text-body text-slate-600">{description}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

/** Quiet note box for neutral information. */
export function Note({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("rounded-md border border-dashed border-slate-200 bg-white px-4 py-3 text-small text-slate-600", className)}>{children}</div>;
}

export function ErrorState({ message, onRetry, title = "This could not be loaded" }: { message: string; onRetry?: () => void; title?: string }) {
  return (
    <Alert tone="danger" title={title}
      action={onRetry && <Button variant="secondary" size="sm" icon={<RefreshCw aria-hidden />} onClick={onRetry}>Try again</Button>}>
      {message}
    </Alert>
  );
}

export function LoadingCards({ count = 3 }: { count?: number }) {
  return (
    <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading" role="status">
      {Array.from({ length: count }).map((_, i) => (
        <Card key={i} className="flex flex-col gap-3 p-6">
          <Skeleton className="w-1/3" />
          <Skeleton className="w-2/3" />
          <Skeleton className="w-1/2" />
        </Card>
      ))}
    </div>
  );
}

/** Marks shown as "earned / maximum": the earned value in ink-900, the maximum lighter. Tabular figures. */
export function Marks({ earned, max, className, size = "md" }: {
  earned: number | null | undefined; max: number; className?: string; size?: "sm" | "md" | "score" | "hero";
}) {
  const big = size === "score" || size === "hero";
  return (
    <span className={cn("tabular whitespace-nowrap",
      size === "sm" && "text-small font-medium", size === "md" && "text-body font-medium",
      size === "score" && "text-score font-medium", size === "hero" && "text-score-hero font-medium", "text-ink-900", className)}>
      {big ? fmtScore(earned) : fmtMarks(earned)}
      <span className={cn("font-normal text-slate-400")}> / {fmtMarks(max)}</span>
    </span>
  );
}

/* ------------------------------------------------------------ statuses */

export function AssessmentStatusBadge({ status }: { status: AssessmentStatus }) {
  const m = ASSESSMENT_STATUS[status];
  return <StatusBadge tone={m.tone}>{m.label}</StatusBadge>;
}

export function SubmissionStatusBadge({ status, audience = "teacher", needsReview }: {
  status: SubmissionStatus; audience?: "teacher" | "student"; needsReview?: boolean;
}) {
  if (audience === "teacher" && status === "evaluated" && needsReview) return <StatusBadge tone="warning">Needs review</StatusBadge>;
  const m = (audience === "student" ? SUBMISSION_STUDENT : SUBMISSION_TEACHER)[status];
  return <StatusBadge tone={m.tone}>{m.label}</StatusBadge>;
}

export function StudentStatusBadge({ status }: { status: StudentStatus }) {
  const m = STUDENT_STATUS[status];
  return <StatusBadge tone={m.tone}>{m.label}</StatusBadge>;
}

export function LevelTag({ level }: { level: Level }) {
  const m = LEVEL_META[level];
  return <ConceptTag tone={m.tone}>{m.label}</ConceptTag>;
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const m = CONFIDENCE[confidence];
  return <StatusBadge tone={m.tone} title={m.title}>{m.label}</StatusBadge>;
}

export function DemoBadge() {
  return <StatusBadge tone="slate" title="Created by the seed script for demonstration (synthetic answer)">Demo data</StatusBadge>;
}
