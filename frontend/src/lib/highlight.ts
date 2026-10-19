import type { Evidence, Level } from "@/lib/types";

export type HighlightSource = { label: string; level: Level; evidence: Evidence | null; index: number };

/** Split the answer into segments so overlapping evidence spans can be highlighted together. */
export function buildSegments(text: string, sources: HighlightSource[]) {
  const spans = sources.filter((s) => s.evidence && s.level !== "missing" && s.evidence.end > s.evidence.start);
  const cuts = new Set<number>([0, text.length]);
  for (const s of spans) {
    cuts.add(Math.max(0, Math.min(text.length, s.evidence!.start)));
    cuts.add(Math.max(0, Math.min(text.length, s.evidence!.end)));
  }
  const points = [...cuts].sort((a, b) => a - b);
  const segments: { text: string; covering: HighlightSource[] }[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [a, b] = [points[i], points[i + 1]];
    if (a === b) continue;
    const covering = spans.filter((s) => s.evidence!.start <= a && s.evidence!.end >= b);
    segments.push({ text: text.slice(a, b), covering });
  }
  return segments;
}
