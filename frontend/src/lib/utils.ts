import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// tailwind-merge must know the Margin type scale (text-h1, text-small ...) so it does not treat those font sizes as
// text colours and drop them when a colour class is merged in.
const TEXT_SIZES = new Set(["display", "h1", "h2", "h3", "h4", "feedback", "body-lg", "body", "control-lg", "control-sm", "small", "caption", "micro", "score", "score-hero"]);
const merge = extendTailwindMerge({
  extend: {
    classGroups: { "font-size": [{ text: [(v: string) => TEXT_SIZES.has(v)] }], shadow: [{ shadow: ["e1", "e2", "e3"] }] },
  },
});

export function cn(...inputs: ClassValue[]) {
  return merge(clsx(inputs));
}

const EMPTY = "—";

/** Marks with at most two decimals and no trailing zeros; an empty value is an em dash. */
export function fmtMarks(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return String(Math.round(value * 100) / 100);
}

/** Marks with one decimal as in the style guide ("6.0 / 8") - used for scores shown as a figure. */
export function fmtScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded * 10) ? rounded.toFixed(1) : String(rounded);
}

export function pct(earned: number, max: number): number {
  return max > 0 ? Math.round((1000 * earned) / max) / 10 : 0;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function valid(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "11:30 PM" (12-hour, tabular-friendly). */
export function fmtClock(d: Date): string {
  const h = d.getHours() % 12 || 12;
  return `${String(h).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")} ${d.getHours() < 12 ? "AM" : "PM"}`;
}

/** Short name of the viewer's time zone, e.g. "IST". */
export function timeZoneName(d: Date = new Date()): string {
  try {
    const part = new Intl.DateTimeFormat("en-IN", { timeZoneName: "short" }).formatToParts(d).find((p) => p.type === "timeZoneName");
    return part?.value ?? "";
  } catch {
    return "";
  }
}

/** "24 Oct 2026" or "24 Oct 2026, 11:30 PM". */
export function fmtDate(iso: string | null | undefined, withTime = true): string {
  const d = valid(iso);
  if (!d) return EMPTY;
  const date = `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
  return withTime ? `${date}, ${fmtClock(d)}` : date;
}

/** "Sat, 24 Oct 2026" - the date picker's trigger format. */
export function fmtDateLong(d: Date): string {
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** Relative description of a deadline, e.g. "in 3 days" / "2 hours ago". */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const diff = new Date(iso).getTime() - now.getTime();
  const abs = Math.abs(diff);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86_400_000],
    ["hour", 3_600_000],
    ["minute", 60_000],
  ];
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, ms] of units) {
    if (abs >= ms || unit === "minute") return rtf.format(Math.round(diff / ms), unit);
  }
  return "";
}

/** ISO timestamp -> local "YYYY-MM-DDTHH:mm" (the value format of the date-time field). */
export function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60_000).toISOString().slice(0, 16);
}

export function fromLocalInput(value: string): string | null {
  if (!value) return null;
  return new Date(value).toISOString();
}

/** Words in plain text. For stored rich text use `wordCountOf` from lib/markdown, which ignores markup. */
export function wordCount(text: string): number {
  const m = text.trim().match(/\S+/g);
  return m ? m.length : 0;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

const HONORIFIC = /^(prof|professor|dr|mr|mrs|ms|miss|mx|sir|madam)\.?$/i;

/** First name for greetings: skips honorifics ("Prof.", "Dr.") and trailing punctuation. */
export function firstName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  const first = parts.find((p) => !HONORIFIC.test(p)) ?? parts[0] ?? "";
  return first.replace(/[.,;:]+$/, "");
}
