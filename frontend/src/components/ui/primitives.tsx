// Margin primitives (STYLEGUIDE §4, §7, §10): flat cards, labelled fields, custom checkbox and radio cards, status
// badges, concept tags, tables, inline alerts, progress bars and KPI tiles.
import { Check, CircleAlert, CircleCheck, Info, Minus, TriangleAlert } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/* ---------------------------------------------------------------- cards */

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("relative min-w-0 rounded-md border border-slate-100 bg-white", className)} {...props} />;
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-6 py-4", className)} {...props} />;
}

export function CardTitle({ className, as: Tag = "h2", ...props }: React.HTMLAttributes<HTMLHeadingElement> & { as?: "h2" | "h3" | "h4" }) {
  return <Tag className={cn("m-0 text-h4 font-semibold text-slate-900", className)} {...props} />;
}

export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("m-0 text-small font-normal text-slate-500", className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-6 py-5", className)} {...props} />;
}

export function Overline({ className, as: Tag = "span", ...props }: React.HTMLAttributes<HTMLElement> & { as?: "span" | "div" | "h2" | "h3" | "p" }) {
  return <Tag className={cn("eyebrow m-0 text-slate-500", className)} {...props} />;
}

/* --------------------------------------------------------------- fields */

const controlBase =
  "w-full min-w-0 rounded-sm border border-slate-200 bg-white px-[14px] font-sans text-body text-slate-900 transition-[border-color,box-shadow] duration-150 " +
  "placeholder:text-slate-400 hover:border-slate-300 " +
  "focus-visible:border-ink-600 focus-visible:shadow-[var(--focus-input)] " +
  "disabled:cursor-not-allowed disabled:border-slate-100 disabled:bg-slate-50 disabled:text-slate-400 " +
  "read-only:bg-slate-50 read-only:text-slate-600 " +
  "aria-[invalid=true]:border-danger aria-[invalid=true]:focus-visible:shadow-[var(--focus-error)]";

export const controlClass = controlBase;

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(controlBase, "h-11", className)} {...props} />,
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} className={cn(controlBase, "min-h-24 resize-y px-4 py-[10px]", className)} {...props} />
  ),
);
Textarea.displayName = "Textarea";

/** Input with a suffix add-on (units such as "marks" or "%"). */
export const InputWithSuffix = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { suffix: React.ReactNode }>(
  ({ className, suffix, ...props }, ref) => (
    <div className={cn("flex h-11 min-w-0 overflow-hidden rounded-sm border border-slate-200 bg-white transition-[border-color,box-shadow] duration-150",
      "focus-within:border-ink-600 focus-within:shadow-[var(--focus-input)] has-[[aria-invalid=true]]:border-danger", className)}>
      <input ref={ref} className="tabular min-w-0 flex-1 border-0 bg-transparent px-[14px] font-sans text-body text-slate-900 focus-visible:shadow-none" {...props} />
      <span className="flex items-center border-l border-slate-200 bg-slate-50 px-3 text-small text-slate-600">{suffix}</span>
    </div>
  ),
);
InputWithSuffix.displayName = "InputWithSuffix";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-small font-medium text-slate-800", className)} {...props} />;
}

export function FieldError({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <p id={id} className="m-0 flex items-start gap-1 text-caption text-danger" role="alert">
      <CircleAlert className="mt-px size-4" aria-hidden />
      <span>{children}</span>
    </p>
  );
}

export function FieldHelp({ id, children, className }: { id?: string; children: React.ReactNode; className?: string }) {
  return <p id={id} className={cn("m-0 text-caption text-slate-500", className)}>{children}</p>;
}

/** Label above the control, helper text or error below it, all wired for screen readers. */
export function Field({
  id, label, hint, error, required, optional, children, className, aside,
}: {
  id: string;
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: string | null;
  required?: boolean;
  optional?: boolean;
  children: React.ReactElement<{ id?: string; "aria-invalid"?: boolean; "aria-describedby"?: string; "aria-required"?: boolean }>;
  className?: string;
  /** Right-aligned content in the label row (counts, status). */
  aside?: React.ReactNode;
}) {
  const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("flex min-w-0 flex-col gap-[6px]", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Label htmlFor={id} id={`${id}-label`}
          onClick={() => { const el = document.getElementById(id); if (el?.isContentEditable) el.focus(); }}>
          {label}
          {required && <span className="font-normal text-slate-500"> (required)</span>}
          {optional && <span className="font-normal text-slate-500"> (optional)</span>}
        </Label>
        {aside}
      </div>
      {React.cloneElement(children, {
        id, "aria-invalid": error ? true : undefined, "aria-describedby": describedBy, ...(required ? { "aria-required": true } : {}),
      })}
      {error && <FieldError id={`${id}-error`}>{error}</FieldError>}
      {hint && <FieldHelp id={`${id}-hint`}>{hint}</FieldHelp>}
    </div>
  );
}

/* ------------------------------------------------- checkbox & radio cards */

/** Custom checkbox: a real (visually hidden) input underneath for keyboard and screen-reader support. */
export function Checkbox({ checked, indeterminate, onChange, label, helper, disabled, id, className }: {
  checked: boolean; indeterminate?: boolean; onChange: (checked: boolean) => void; label: React.ReactNode; helper?: React.ReactNode;
  disabled?: boolean; id?: string; className?: string;
}) {
  const ref = React.useRef<HTMLInputElement>(null);
  React.useEffect(() => { if (ref.current) ref.current.indeterminate = Boolean(indeterminate); }, [indeterminate]);
  const on = checked || indeterminate;
  return (
    <label className={cn("group flex min-h-11 cursor-pointer items-start gap-3 py-[10px]", disabled && "cursor-not-allowed", className)}>
      <input ref={ref} id={id} type="checkbox" className="peer sr-only" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span aria-hidden className={cn(
        "mt-0.5 grid size-5 flex-none place-items-center rounded-[5px] border-[1.5px] transition-colors duration-150",
        "peer-focus-visible:shadow-[var(--focus-ring)]",
        disabled ? "border-slate-100 bg-slate-50" : on ? "border-ink-600 bg-ink-600 text-white" : "border-slate-300 bg-white group-hover:border-ink-400",
      )}>
        {indeterminate ? <Minus className="size-3.5 [stroke-width:3px]" /> : checked ? <Check className="size-3.5 [stroke-width:3px]" /> : null}
      </span>
      <span className="flex min-w-0 flex-col">
        <span className={cn("text-body", disabled ? "text-slate-400" : "text-slate-900")}>{label}</span>
        {helper && <span className="text-caption text-slate-500">{helper}</span>}
      </span>
    </label>
  );
}

export function RadioCards<T extends string>({ name, legend, value, onChange, options, className, columns = 2 }: {
  name: string; legend: React.ReactNode; value: T; onChange: (v: T) => void; className?: string; columns?: 1 | 2 | 3;
  options: { value: T; label: React.ReactNode; description?: React.ReactNode }[];
}) {
  return (
    <fieldset className={cn("m-0 flex min-w-0 flex-col gap-[6px] border-0 p-0", className)}>
      <legend className="mb-[6px] p-0 text-small font-medium text-slate-800">{legend}</legend>
      <div className={cn("grid gap-3", columns === 2 && "sm:grid-cols-2", columns === 3 && "sm:grid-cols-3")}>
        {options.map((o) => {
          const selected = value === o.value;
          return (
            <label key={o.value} className={cn(
              "flex min-h-11 cursor-pointer items-start gap-3 rounded-[10px] border px-4 py-[14px] transition-colors duration-150",
              "has-[:focus-visible]:shadow-[var(--focus-ring)]",
              selected ? "border-ink-600 bg-ink-50" : "border-slate-100 bg-white hover:border-ink-200",
            )}>
              <input type="radio" name={name} value={o.value} checked={selected} onChange={() => onChange(o.value)} className="sr-only" />
              <span aria-hidden className={cn("mt-0.5 grid size-5 flex-none place-items-center rounded-full border-[1.5px] bg-white",
                selected ? "border-ink-600" : "border-slate-300")}>
                {selected && <span className="size-2.5 rounded-full bg-ink-600" />}
              </span>
              <span className="flex min-w-0 flex-col">
                <span className={cn("text-body font-medium", selected ? "text-ink-900" : "text-slate-900")}>{o.label}</span>
                {o.description && <span className="text-small text-slate-600">{o.description}</span>}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

/* ---------------------------------------------------------------- badges */

export type BadgeTone = "success" | "ink" | "warning" | "danger" | "slate";

const BADGE_TONE: Record<BadgeTone, { box: string; dot: string }> = {
  success: { box: "bg-success-bg text-success", dot: "bg-success" },
  ink: { box: "bg-ink-50 text-ink-700", dot: "bg-ink-600" },
  warning: { box: "bg-warning-bg text-warning-text", dot: "bg-warning" },
  danger: { box: "bg-danger-bg text-danger", dot: "bg-danger" },
  slate: { box: "bg-slate-50 text-slate-600", dot: "bg-slate-400" },
};

/** Status badge: 24px, radius 4, 12/600, a 6px dot plus a text label - never colour alone. */
export function StatusBadge({ tone = "slate", className, children, ...props }: React.HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  const t = BADGE_TONE[tone];
  return (
    <span className={cn("inline-flex h-6 flex-none items-center gap-[6px] self-start whitespace-nowrap rounded-xs px-2 text-caption font-semibold", t.box, className)} {...props}>
      <span aria-hidden className={cn("size-[6px] rounded-full", t.dot)} />
      {children}
    </span>
  );
}

export type ConceptTone = "found" | "partial" | "missing";

/** Concept tag: 28px pill, 13/500. Found uses highlighter, partial a dashed ink border, missing a dashed red border. */
export function ConceptTag({ tone, className, children, ...props }: React.HTMLAttributes<HTMLSpanElement> & { tone: ConceptTone }) {
  return (
    <span className={cn("inline-flex h-7 flex-none items-center gap-1 self-start whitespace-nowrap rounded-full border px-3 text-small font-medium",
      tone === "found" && "border-hl-300 bg-hl-100 text-hl-text",
      tone === "partial" && "border-dashed border-ink-400 bg-white text-ink-700",
      tone === "missing" && "border-dashed border-danger-line bg-white text-danger",
      className)} {...props}>
      {children}
    </span>
  );
}

/* ------------------------------------------------------------- feedback */

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden className={cn("margin-pulse h-4 rounded-xs bg-slate-100", className)} {...props} />;
}

export type AlertTone = "info" | "success" | "warning" | "danger";

const ALERT: Record<AlertTone, { box: string; icon: React.ReactNode }> = {
  info: { box: "border-ink-100 bg-ink-50 text-ink-900", icon: <Info className="size-5 text-ink-600" aria-hidden /> },
  success: { box: "border-success/25 bg-success-bg text-slate-900", icon: <CircleCheck className="size-5 text-success" aria-hidden /> },
  warning: { box: "border-warning/25 bg-warning-bg text-slate-900", icon: <TriangleAlert className="size-5 text-warning" aria-hidden /> },
  danger: { box: "border-danger/25 bg-danger-bg text-slate-900", icon: <CircleAlert className="size-5 text-danger" aria-hidden /> },
};

/** Inline alert: status background, tinted 1px border, 20px icon, bold title, one line of body. No side stripe. */
export function Alert({ tone = "info", title, children, action, className, live }: {
  tone?: AlertTone; title: React.ReactNode; children?: React.ReactNode; action?: React.ReactNode; className?: string;
  /** Overrides the default role (alert for warning/danger, status otherwise). */
  live?: "alert" | "status" | "none";
}) {
  const a = ALERT[tone];
  const role = live === "none" ? undefined : live ?? (tone === "warning" || tone === "danger" ? "alert" : "status");
  return (
    <div role={role} className={cn("flex flex-col gap-3 rounded-[10px] border px-4 py-[14px] sm:flex-row sm:items-start", a.box, className)}>
      <div className="flex min-w-0 flex-1 gap-3">
        <span className="mt-0.5 flex-none">{a.icon}</span>
        <div className="flex min-w-0 flex-col">
          <span className="text-body font-semibold">{title}</span>
          {children && <div className="text-small text-slate-600 [&_p]:m-0">{children}</div>}
        </div>
      </div>
      {action && <div className="flex flex-none flex-wrap gap-2 pl-8 sm:pl-0">{action}</div>}
    </div>
  );
}

/* --------------------------------------------------------------- tables */

/** Wide tables scroll horizontally inside their card, never the page. */
export function Table({ className, wrapperClassName, ...props }: React.TableHTMLAttributes<HTMLTableElement> & { wrapperClassName?: string }) {
  return (
    <div className={cn("relative w-full overflow-x-auto rounded-md border border-slate-100 bg-white", wrapperClassName)}>
      <table className={cn("w-full border-collapse text-body", className)} {...props} />
    </div>
  );
}
export const Th = ({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) => (
  <th scope="col" className={cn("eyebrow h-10 whitespace-nowrap border-b border-slate-100 bg-slate-50 px-4 text-left text-slate-500", className)} {...props} />
);
export const Td = ({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) => (
  <td className={cn("h-14 border-b border-slate-100 px-4 align-middle", className)} {...props} />
);
export function Tr({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("transition-colors duration-150 hover:bg-ink-50 [&:last-child>td]:border-b-0", className)} {...props} />;
}

/* ------------------------------------------------------- progress & KPIs */

/** Linear progress: 8px, full radius, slate-100 track, ink-600 fill. */
export function ProgressBar({ value, max, className, label, size = "md" }: {
  value: number; max: number; className?: string; label: string; size?: "sm" | "md";
}) {
  const p = max > 0 ? Math.max(0, Math.min(100, (100 * value) / max)) : 0;
  return (
    <div className={cn("w-full overflow-hidden rounded-full bg-slate-100", size === "sm" ? "h-[6px]" : "h-2", className)}
      role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-label={label}>
      <div className="h-full rounded-full bg-ink-600 transition-[width] duration-150" style={{ width: `${p}%` }} />
    </div>
  );
}

/** A single headline number: eyebrow label, tabular score figure, optional caption. */
export function KpiTile({ label, value, caption, className }: { label: React.ReactNode; value: React.ReactNode; caption?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1 rounded-md border border-slate-100 bg-white px-5 py-4", className)}>
      <Overline as="div">{label}</Overline>
      <div className="tabular text-score font-medium text-ink-900">{value}</div>
      {caption && <div className="text-caption text-slate-500">{caption}</div>}
    </div>
  );
}

export function KpiRow({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(180px,100%),1fr))]", className)}>{children}</div>;
}
