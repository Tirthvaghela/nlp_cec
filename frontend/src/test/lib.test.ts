import { buildSegments } from "@/lib/highlight";
import { actionFor } from "@/lib/studentActions";
import type { StudentAssessment } from "@/lib/types";
import { firstName, fmtMarks, fromLocalInput, pct, toLocalInput, wordCount } from "@/lib/utils";
import { EMAIL_RE, validatePassword } from "@/lib/validation";

describe("utils", () => {
  it("formats marks without trailing zeros", () => {
    expect(fmtMarks(3)).toBe("3");
    expect(fmtMarks(2.5)).toBe("2.5");
    expect(fmtMarks(1.256)).toBe("1.26");
    expect(fmtMarks(null)).toBe("—"); // STYLEGUIDE §10.8: an empty value is an em dash
  });
  it("computes percentages safely", () => {
    expect(pct(3, 4)).toBe(75);
    expect(pct(1, 3)).toBe(33.3);
    expect(pct(1, 0)).toBe(0);
  });
  it("round-trips datetime-local values", () => {
    const iso = "2026-11-02T09:30:00.000Z";
    expect(fromLocalInput(toLocalInput(iso))).toBe(iso);
    expect(fromLocalInput("")).toBeNull();
  });
  it("greets by first name without honorifics or punctuation", () => {
    expect(firstName("Prof. Meera Iyer")).toBe("Meera");
    expect(firstName("Dr Asha Rao")).toBe("Asha");
    expect(firstName("Aarav Shah")).toBe("Aarav");
    expect(firstName("  ")).toBe("");
  });
  it("counts words", () => {
    expect(wordCount("  one two\nthree ")).toBe(3);
    expect(wordCount("   ")).toBe(0);
  });
});

describe("validation", () => {
  it("enforces the same password rules as the API", () => {
    expect(validatePassword("short1")).toMatch(/8 characters/);
    expect(validatePassword("onlyletters")).toMatch(/letter and one number/);
    expect(validatePassword("Passw0rd")).toBeNull();
  });
  it("validates email format", () => {
    expect(EMAIL_RE.test("a@b.co")).toBe(true);
    expect(EMAIL_RE.test("not an email")).toBe(false);
  });
});

describe("buildSegments", () => {
  const text = "First sentence. Second sentence here.";
  it("splits text so overlapping evidence is highlighted once per segment", () => {
    const segs = buildSegments(text, [
      { label: "A", level: "matched", evidence: { text: "First sentence.", start: 0, end: 15 }, index: 1 },
      { label: "B", level: "partial", evidence: { text, start: 0, end: text.length }, index: 2 },
      { label: "C", level: "missing", evidence: null, index: 3 },
    ]);
    expect(segs.map((s) => s.text).join("")).toBe(text); // nothing lost or duplicated
    expect(segs[0].covering.map((c) => c.label)).toEqual(["A", "B"]);
    expect(segs[segs.length - 1].covering.map((c) => c.label)).toEqual(["B"]);
  });
  it("ignores missing concepts and out-of-range offsets", () => {
    const segs = buildSegments(text, [{ label: "X", level: "missing", evidence: { text: "x", start: 0, end: 5 }, index: 1 }]);
    expect(segs).toEqual([{ text, covering: [] }]);
  });
});

describe("student actions", () => {
  const base: StudentAssessment = {
    id: "a1", title: "T", subject: "S", instructions: "", status: "published", deadline: null, deadline_passed: false,
    question_count: 1, total_marks: 4, teacher_name: "X", my_status: "not_started", submission_id: null, submitted_at: null,
  };
  it("maps each status to the right next step", () => {
    expect(actionFor(base).label).toBe("Start");
    expect(actionFor({ ...base, my_status: "draft" }).label).toBe("Continue");
    expect(actionFor({ ...base, my_status: "submitted" }).label).toBe("View submission");
    const pub = actionFor({ ...base, my_status: "published", submission_id: "s9" });
    expect(pub).toMatchObject({ label: "View result", to: "/student/results/s9" });
  });
});
