// Inline status shown beside the section being generated. Announced politely to screen readers; colour is never the
// only signal (each state has an icon and words).
import { CircleAlert, CircleCheck, Clock, Loader2, Pencil, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import type { RefOrigin, RefStatus } from "@/pages/teacher/question/useReferenceAnswer";
import { cn } from "@/lib/utils";

const ITEM: Record<RefStatus, { icon: ReactNode; text: string; cls: string }> = {
  empty: { icon: null, text: "", cls: "text-slate-500" },
  waiting: { icon: <Clock aria-hidden />, text: "Drafting starts when you pause typing", cls: "text-slate-500" },
  generating: { icon: <Loader2 className="animate-spin" aria-hidden />, text: "Generating reference answer", cls: "text-ink-700" },
  ready: { icon: <CircleCheck aria-hidden />, text: "Drafted for this question", cls: "text-success" },
  edited: { icon: <Pencil aria-hidden />, text: "Edited by you", cls: "text-ink-700" },
  stale: { icon: <TriangleAlert aria-hidden />, text: "May be outdated", cls: "text-warning-text" },
  error: { icon: <CircleAlert aria-hidden />, text: "Not generated", cls: "text-danger" },
};

export function ReferenceStatus({ status, origin, canDraft }: { status: RefStatus; origin: RefOrigin; canDraft: boolean }) {
  let { icon, text } = ITEM[status];
  if (status === "ready" && origin === "saved") { icon = <CircleCheck aria-hidden />; text = "Saved reference answer"; }
  if (status === "empty") text = canDraft ? "No reference answer yet" : "Write the question to draft one";
  return <InlineStatus icon={icon} text={text} className={ITEM[status].cls} />;
}

export function InlineStatus({ icon, text, className }: { icon: ReactNode; text: string; className?: string }) {
  return (
    <span role="status" aria-live="polite" className={cn("inline-flex min-h-6 items-center gap-1 text-small font-medium [&_svg]:size-4", className)}>
      {icon}{text}
    </span>
  );
}
