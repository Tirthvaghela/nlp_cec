// Tabs and segmented control (STYLEGUIDE §10.9).
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as React from "react";

import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("relative flex gap-6 overflow-x-auto border-b border-slate-100", className)} {...props} />;
}

export function TabsTrigger({ className, count, children, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger> & { count?: number }) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "-mb-px inline-flex h-11 flex-none items-center gap-2 whitespace-nowrap border-0 border-b-2 border-transparent bg-transparent px-0 font-sans text-body font-medium text-slate-600 " +
          "transition-colors duration-150 hover:text-slate-900 data-[state=active]:border-ink-600 data-[state=active]:font-semibold data-[state=active]:text-ink-900",
        className,
      )}
      {...props}
    >
      {children}
      {count !== undefined && <span className="tabular rounded-full bg-ink-50 px-2 text-caption font-semibold text-ink-700">{count}</span>}
    </TabsPrimitive.Trigger>
  );
}

export function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("pt-6 focus-visible:shadow-none", className)} {...props} />;
}

/** Segmented control: switching views of the same content. A radio group under the hood. */
export function Segmented<T extends string>({ label, value, onChange, options, className, size = "md" }: {
  label: string; value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode; count?: number }[];
  className?: string; size?: "sm" | "md";
}) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);
  const index = Math.max(0, options.findIndex((o) => o.value === value));
  const onKeyDown = (e: React.KeyboardEvent) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (index + step + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  };
  return (
    <div role="radiogroup" aria-label={label} onKeyDown={onKeyDown}
      className={cn("relative inline-flex max-w-full gap-1 overflow-x-auto rounded-[10px] bg-slate-50 p-1", className)}>
      {options.map((o, i) => {
        const active = o.value === value;
        return (
          <button key={o.value} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={active} tabIndex={active ? 0 : -1}
            onClick={() => onChange(o.value)}
            className={cn("inline-flex flex-none items-center gap-2 whitespace-nowrap rounded-sm border-0 px-3 font-sans font-medium transition-colors duration-150",
              size === "sm" ? "h-8 text-small" : "h-9 text-control-sm",
              active ? "bg-white text-ink-900 shadow-e1" : "bg-transparent text-slate-600 hover:text-slate-900")}>
            {o.label}
            {o.count !== undefined && <span className="tabular rounded-full bg-ink-50 px-2 text-caption font-semibold text-ink-700">{o.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
