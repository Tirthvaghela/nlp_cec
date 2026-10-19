// Charts (STYLEGUIDE §9): Ink shades only, a title and a one-line caption, tabular 11px axis labels in slate-500,
// recessive gridlines, 4px rounded data-ends with 2px gaps. Every mark is focusable, carries an aria-label with its
// value, and hover or focus updates the chart's header note. Each chart also has a table view.
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

function ChartFrame({ title, caption, note, table, children }: { title: string; caption: string; note: ReactNode; table: ReactNode; children: ReactNode }) {
  const [showTable, setShowTable] = useState(false);
  return (
    <Card className="flex min-w-0 flex-col gap-4 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="m-0 text-[16px] font-semibold leading-6 text-slate-900">{title}</h3>
          <p className="m-0 text-small text-slate-600">{caption}</p>
        </div>
        <span className="tabular min-h-5 text-small font-medium text-slate-800" aria-live="polite">{note}</span>
      </div>
      {showTable ? table : children}
      <Button variant="tertiary" size="sm" className="self-start" aria-pressed={showTable} onClick={() => setShowTable((s) => !s)}>
        {showTable ? "Show chart" : "Show as table"}
      </Button>
    </Card>
  );
}

function DataTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="relative overflow-x-auto rounded-sm border border-slate-100">
      <table className="w-full border-collapse text-small">
        <thead><tr>{head.map((h) => <th key={h} scope="col" className="eyebrow border-b border-slate-100 bg-slate-50 px-3 py-2 text-left text-slate-500">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={cn("tabular border-b border-slate-100 px-3 py-2", j > 0 && "text-right")}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function niceMax(v: number): number {
  if (v <= 4) return Math.max(1, Math.ceil(v));
  const step = Math.pow(10, Math.floor(Math.log10(v)));
  return Math.ceil(v / step) * step;
}

/** Histogram: one bar per band, starting at zero. */
export function Histogram({ title, caption, data, unit = "students" }: {
  title: string; caption: string; data: { label: string; count: number }[]; unit?: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const W = 560, H = 220, padL = 32, padB = 28, padT = 8;
  const max = niceMax(Math.max(0, ...data.map((d) => d.count)));
  const ticks = [0, max / 2, max].filter((t, i, a) => a.indexOf(t) === i);
  const plotW = W - padL, plotH = H - padB - padT;
  const slot = plotW / Math.max(1, data.length);
  const barW = Math.max(4, slot - 2);
  const y = (v: number) => padT + plotH - (v / max) * plotH;
  const note = active !== null ? `${data[active].label}: ${data[active].count} ${unit}` : `${data.reduce((s, d) => s + d.count, 0)} ${unit} in total`;
  return (
    <ChartFrame title={title} caption={caption} note={note}
      table={<DataTable head={["Band", unit[0].toUpperCase() + unit.slice(1)]} rows={data.map((d) => [d.label, d.count])} />}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="group" aria-label={title}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W} y1={y(t)} y2={y(t)} stroke={t === 0 ? "var(--color-slate-300)" : "var(--color-slate-100)"} strokeWidth={1} />
            <text x={padL - 6} y={y(t) + 4} textAnchor="end" className="tabular fill-slate-500 text-micro">{t}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = padL + i * slot + 1;
          const top = y(d.count);
          const h = Math.max(0, padT + plotH - top);
          const r = Math.min(4, h, barW / 2);
          const path = h > 0
            ? `M${x},${top + h} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${top + h} Z`
            : "";
          return (
            <g key={d.label} tabIndex={0} role="img" aria-label={`${d.label}: ${d.count} ${unit}`}
              onPointerEnter={() => setActive(i)} onPointerLeave={() => setActive(null)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
              className="cursor-default outline-none [&:focus-visible>rect]:stroke-ink-500">
              <rect x={padL + i * slot} y={padT} width={slot} height={plotH} fill="transparent" strokeWidth={2} />
              {path && <path d={path} fill={active === i ? "var(--color-ink-800)" : "var(--color-ink-500)"} />}
              <text x={x + barW / 2} y={H - 10} textAnchor="middle" className="tabular fill-slate-500 text-micro">{d.label}</text>
            </g>
          );
        })}
      </svg>
    </ChartFrame>
  );
}

/** Horizontal bars for a value out of a maximum (e.g. average mark per question), each on a slate-100 track. */
export function MeterBars({ title, caption, data }: {
  title: string; caption: string; data: { label: string; value: number | null; max: number; display: string; detail?: string }[];
}) {
  const [active, setActive] = useState<number | null>(null);
  const note = active !== null ? `${data[active].label}: ${data[active].display}` : "";
  return (
    <ChartFrame title={title} caption={caption} note={note}
      table={<DataTable head={["Item", "Value"]} rows={data.map((d) => [d.label, d.display])} />}>
      <ul className="m-0 flex list-none flex-col gap-4 p-0">
        {data.map((d, i) => {
          const p = d.value === null || d.max <= 0 ? 0 : Math.max(0, Math.min(1, d.value / d.max));
          return (
            <li key={d.label + i} tabIndex={0} aria-label={`${d.label}: ${d.display}`}
              onPointerEnter={() => setActive(i)} onPointerLeave={() => setActive(null)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
              className="flex flex-col gap-2 rounded-xs">
              <div className="flex items-baseline justify-between gap-3 text-small">
                <span className="min-w-0 truncate text-slate-800" title={d.detail}>{d.label}</span>
                <span className="tabular whitespace-nowrap text-slate-600">{d.display}</span>
              </div>
              <div className="flex h-2 gap-[2px]" aria-hidden>
                {p > 0 && <span className={cn("h-full rounded-[4px]", active === i ? "bg-ink-800" : "bg-ink-500")} style={{ width: `${p * 100}%` }} />}
                {p < 1 && <span className="h-full flex-1 rounded-[4px] bg-slate-100" />}
              </div>
            </li>
          );
        })}
      </ul>
    </ChartFrame>
  );
}

const STEPS = ["--color-ink-50", "--color-ink-100", "--color-ink-200", "--color-ink-300", "--color-ink-400", "--color-ink-500", "--color-ink-600", "--color-ink-800"];

function step(pct: number): number {
  return Math.min(STEPS.length - 1, Math.floor((pct / 100) * STEPS.length));
}

/** Heatmap: rows x columns of percentages on the sequential ink ramp, with a low-to-high legend. */
export function Heatmap({ title, caption, rows, columns, measure }: {
  title: string; caption: string; columns: string[]; measure: string;
  rows: { label: string; detail?: string; cells: ({ value: number; label: string } | null)[] }[];
}) {
  const [active, setActive] = useState<string>("");
  return (
    <ChartFrame title={title} caption={caption} note={active}
      table={<DataTable head={["Row", ...columns]} rows={rows.map((r) => [r.label, ...r.cells.map((c) => (c ? `${c.value}% (${c.label})` : "—"))])} />}>
      <div className="relative overflow-x-auto">
        <table className="border-separate border-spacing-[2px]" aria-label={title}>
          <thead>
            <tr>
              <th scope="col" className="sr-only">Row</th>
              {columns.map((c) => <th key={c} scope="col" className="tabular h-6 min-w-12 px-1 text-center text-micro font-medium text-slate-500">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <th scope="row" className="tabular whitespace-nowrap pr-3 text-left text-small font-medium text-slate-800" title={r.detail}>{r.label}</th>
                {r.cells.map((c, j) => {
                  if (!c) return <td key={j} className="h-11 min-w-12 rounded-xs bg-slate-25" aria-label="No criterion" />;
                  const s = step(c.value);
                  const text = `${r.label} ${columns[j]} (${c.label}): ${c.value}% ${measure}`;
                  return (
                    <td key={j} tabIndex={0} aria-label={text} title={text}
                      onPointerEnter={() => setActive(text)} onPointerLeave={() => setActive("")} onFocus={() => setActive(text)} onBlur={() => setActive("")}
                      className={cn("tabular h-11 min-w-12 rounded-xs text-center text-caption font-semibold", s >= 4 ? "text-white" : "text-ink-900")}
                      style={{ background: `var(${STEPS[s]})` }}>
                      {c.value}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-2 text-micro text-slate-500" aria-hidden>
        <span>0% low</span>
        <span className="flex gap-[2px]">{STEPS.map((v) => <span key={v} className="h-3 w-5 rounded-[2px]" style={{ background: `var(${v})` }} />)}</span>
        <span>100% high</span>
      </div>
    </ChartFrame>
  );
}
