// Date and time pickers (STYLEGUIDE §8.3, §8.4) and the deadline field that pairs them. The value format is the
// local "YYYY-MM-DDTHH:mm" string used by toLocalInput/fromLocalInput, so no browser date control is ever shown.
import { CalendarDays, ChevronLeft, ChevronRight, Clock } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { panelClass, triggerClass, usePopover } from "@/components/ui/popover";
import { cn, fmtClock, fmtDateLong, timeZoneName } from "@/lib/utils";

const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WEEKDAYS_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const WEEK_HEAD = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

const pad = (n: number) => String(n).padStart(2, "0");
const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const sameDay = (a: Date, b: Date) => ymd(a) === ymd(b);
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const fullLabel = (d: Date) => `${WEEKDAYS_LONG[d.getDay()]} ${d.getDate()} ${MONTHS_LONG[d.getMonth()]} ${d.getFullYear()}`;

function parseDate(value: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
}

/** 6 x 7 grid of days starting on Monday. */
function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const lead = (first.getDay() + 6) % 7;
  return Array.from({ length: 42 }, (_, i) => new Date(year, month, 1 - lead + i));
}

export function DatePicker({ id, value, onChange, placeholder = "Choose a date", "aria-describedby": describedBy, "aria-invalid": invalid, minDate }: {
  id?: string; value: string; onChange: (ymd: string) => void; placeholder?: string;
  "aria-describedby"?: string; "aria-invalid"?: boolean; minDate?: Date;
}) {
  const { open, setOpen, close, rootRef, triggerRef } = usePopover<HTMLButtonElement>();
  const selected = parseDate(value);
  const [focus, setFocus] = useState<Date>(selected ?? new Date());
  const [pending, setPending] = useState<Date | null>(selected);
  const gridRef = useRef<HTMLDivElement>(null);
  const today = new Date();

  useEffect(() => {
    if (!open) return;
    const start = parseDate(value) ?? new Date();
    setFocus(start);
    setPending(parseDate(value));
  }, [open, value]);

  useEffect(() => {
    if (open) gridRef.current?.querySelector<HTMLButtonElement>(`[data-day="${ymd(focus)}"]`)?.focus();
  }, [focus, open]);

  const disabledDay = (d: Date) => Boolean(minDate && ymd(d) < ymd(minDate));
  const commit = (d: Date | null) => {
    if (!d) return;
    onChange(ymd(d));
    close();
  };

  const onGridKey = (e: KeyboardEvent) => {
    const moves: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    if (e.key in moves) { e.preventDefault(); setFocus((f) => addDays(f, moves[e.key])); }
    else if (e.key === "PageUp") { e.preventDefault(); setFocus((f) => new Date(f.getFullYear(), f.getMonth() - 1, Math.min(f.getDate(), 28))); }
    else if (e.key === "PageDown") { e.preventDefault(); setFocus((f) => new Date(f.getFullYear(), f.getMonth() + 1, Math.min(f.getDate(), 28))); }
    else if (e.key === "Home") { e.preventDefault(); setFocus((f) => addDays(f, -((f.getDay() + 6) % 7))); }
    else if (e.key === "End") { e.preventDefault(); setFocus((f) => addDays(f, 6 - ((f.getDay() + 6) % 7))); }
  };

  const days = monthGrid(focus.getFullYear(), focus.getMonth());
  const shiftMonth = (n: number) => setFocus((f) => new Date(f.getFullYear(), f.getMonth() + n, 1));

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button ref={triggerRef} id={id} type="button" className={triggerClass} aria-haspopup="dialog" aria-expanded={open}
        aria-describedby={describedBy} aria-invalid={invalid} onClick={() => setOpen(!open)}>
        <CalendarDays className="size-[18px] text-slate-500" aria-hidden />
        <span className={cn("tabular min-w-0 flex-1 truncate", !selected && "text-slate-400")}>{selected ? fmtDateLong(selected) : placeholder}</span>
      </button>
      {open && (
        <div role="dialog" aria-label="Choose a date" className={cn(panelClass, "w-[min(312px,calc(100vw-32px))] p-3")}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <Button variant="tertiary" size="icon-sm" aria-label="Previous month" data-tooltip="Previous month" onClick={() => shiftMonth(-1)}><ChevronLeft aria-hidden /></Button>
            <span className="text-h4 font-semibold text-slate-900" aria-live="polite">{MONTHS_LONG[focus.getMonth()]} {focus.getFullYear()}</span>
            <Button variant="tertiary" size="icon-sm" aria-label="Next month" data-tooltip="Next month" onClick={() => shiftMonth(1)}><ChevronRight aria-hidden /></Button>
          </div>
          <div ref={gridRef} role="grid" aria-label={`${MONTHS_LONG[focus.getMonth()]} ${focus.getFullYear()}`} onKeyDown={onGridKey}>
            <div role="row" className="grid grid-cols-7">
              {WEEK_HEAD.map((w) => <span key={w} role="columnheader" className="grid h-8 place-items-center text-caption font-semibold text-slate-500">{w}</span>)}
            </div>
            {Array.from({ length: 6 }, (_, r) => (
              <div key={r} role="row" className="grid grid-cols-7">
                {days.slice(r * 7, r * 7 + 7).map((d) => {
                  const inMonth = d.getMonth() === focus.getMonth();
                  const isSel = pending && sameDay(d, pending);
                  const isToday = sameDay(d, today);
                  const off = disabledDay(d);
                  return (
                    <span key={ymd(d)} role="gridcell" aria-selected={Boolean(isSel)}>
                      <button type="button" data-day={ymd(d)} tabIndex={sameDay(d, focus) ? 0 : -1} disabled={off}
                        aria-label={fullLabel(d)} aria-current={isToday ? "date" : undefined}
                        onClick={() => { setPending(d); setFocus(d); }} onDoubleClick={() => commit(d)}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(d); } }}
                        className={cn("tabular grid size-10 place-items-center rounded-sm border text-body transition-colors duration-150",
                          isSel ? "border-ink-600 bg-ink-600 font-semibold text-white"
                            : isToday ? "border-ink-300 font-semibold text-slate-900 hover:bg-ink-50"
                              : "border-transparent hover:bg-ink-50",
                          !isSel && !inMonth && "text-slate-300", off && "cursor-not-allowed text-slate-300 hover:bg-transparent")}>
                        {d.getDate()}
                      </button>
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
            <Button variant="tertiary" size="sm" onClick={() => { const t = new Date(); setFocus(t); setPending(t); }} disabled={disabledDay(today)}>Today</Button>
            <Button size="sm" onClick={() => commit(pending)} disabled={!pending}>Set date</Button>
          </div>
        </div>
      )}
    </div>
  );
}

const HOURS = Array.from({ length: 12 }, (_, i) => i + 1);
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);

export function TimePicker({ id, value, onChange, "aria-label": ariaLabel, "aria-describedby": describedBy, disabled }: {
  id?: string; value: string; onChange: (hhmm: string) => void; "aria-label"?: string; "aria-describedby"?: string; disabled?: boolean;
}) {
  const { open, setOpen, rootRef, triggerRef } = usePopover<HTMLButtonElement>();
  const m = /^(\d{2}):(\d{2})$/.exec(value);
  const h24 = m ? Number(m[1]) : null;
  const min = m ? Number(m[2]) : null;
  const h12 = h24 === null ? null : h24 % 12 || 12;
  const pm = h24 !== null && h24 >= 12;
  const set = (hour12: number, minute: number, isPm: boolean) => onChange(`${pad((hour12 % 12) + (isPm ? 12 : 0))}:${pad(minute)}`);
  const display = h24 === null ? "Choose a time" : fmtClock(new Date(2000, 0, 1, h24, min ?? 0));
  const tz = timeZoneName();

  const column = (label: string, items: { key: string; text: string; on: boolean; pick: () => void }[]) => (
    <div role="group" aria-label={label} className="flex max-h-[232px] min-w-0 flex-1 flex-col gap-0.5 overflow-y-auto">
      {items.map((it) => (
        <button key={it.key} type="button" aria-pressed={it.on} onClick={it.pick}
          className={cn("tabular h-9 flex-none rounded-sm border-0 text-body transition-colors duration-150",
            it.on ? "bg-ink-600 font-semibold text-white" : "bg-transparent text-slate-900 hover:bg-ink-50")}>
          {it.text}
        </button>
      ))}
    </div>
  );

  return (
    <div ref={rootRef} className="relative min-w-0">
      <button ref={triggerRef} id={id} type="button" className={triggerClass} aria-haspopup="dialog" aria-expanded={open}
        aria-label={ariaLabel ? `${ariaLabel}: ${display}` : undefined} aria-describedby={describedBy} disabled={disabled} onClick={() => setOpen(!open)}>
        <Clock className="size-[18px] text-slate-500" aria-hidden />
        <span className={cn("tabular min-w-0 flex-1 truncate", h24 === null && "text-slate-400")}>{display}</span>
        {tz && <span className="text-small text-slate-500">{tz}</span>}
      </button>
      {open && (
        <div role="dialog" aria-label="Choose a time" className={cn(panelClass, "flex w-[232px] gap-1")}>
          {column("Hour", HOURS.map((h) => ({ key: `h${h}`, text: pad(h), on: h === h12, pick: () => set(h, min ?? 0, pm) })))}
          {column("Minute", MINUTES.map((mm) => ({ key: `m${mm}`, text: pad(mm), on: mm === min, pick: () => set(h12 ?? 12, mm, pm) })))}
          {column("AM or PM", [false, true].map((p) => ({ key: p ? "pm" : "am", text: p ? "PM" : "AM", on: h24 !== null && p === pm, pick: () => set(h12 ?? 12, min ?? 0, p) })))}
        </div>
      )}
    </div>
  );
}

const DEFAULT_TIME = "23:55";

/** Deadline field: a date picker and a time picker side by side, plus a clear action. Value: "YYYY-MM-DDTHH:mm" | "". */
export function DateTimeField({ id, value, onChange, "aria-describedby": describedBy, "aria-invalid": invalid, label = "Deadline" }: {
  id?: string; value: string; onChange: (v: string) => void; "aria-describedby"?: string; "aria-invalid"?: boolean; label?: string;
}) {
  const [date, time] = value ? value.split("T") : ["", ""];
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <DatePicker id={id} value={date} aria-describedby={describedBy} aria-invalid={invalid} minDate={new Date()}
          onChange={(d) => onChange(`${d}T${time || DEFAULT_TIME}`)} />
        <TimePicker id={id ? `${id}-time` : undefined} value={time} aria-label={`${label} time`} aria-describedby={describedBy}
          disabled={!date} onChange={(t) => onChange(`${date}T${t}`)} />
      </div>
      {value && <Button variant="link" size="sm" className="self-start text-small" onClick={() => onChange("")}>Remove {label.toLowerCase()}</Button>}
    </div>
  );
}
