import type { ConceptTone } from "@/components/ui/primitives";
import type { Level } from "@/lib/types";

/** Concept coverage levels: found concepts use the highlighter, partial a dashed ink line, missing a dashed red line. */
export const LEVEL_META: Record<Level, { label: string; tone: ConceptTone; outcome: string }> = {
  matched: { label: "Matched", tone: "found", outcome: "full marks" },
  partial: { label: "Partial", tone: "partial", outcome: "partial marks" },
  missing: { label: "Missing", tone: "missing", outcome: "no marks" },
};
