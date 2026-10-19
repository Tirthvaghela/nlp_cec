// Reference-answer state machine. The draft API is mocked so each test controls exactly when (and in which order)
// responses arrive; fake timers drive the debounce.
import { act, renderHook } from "@testing-library/react";

import { ApiError } from "@/lib/api";
import { draftReferenceAnswer } from "@/lib/generation";
import { DRAFT_DEBOUNCE_MS, useReferenceAnswer } from "@/pages/teacher/question/useReferenceAnswer";

vi.mock("@/lib/generation", () => ({ draftReferenceAnswer: vi.fn(), draftRubric: vi.fn() }));
const draft = vi.mocked(draftReferenceAnswer);

type Resolver = { resolve: (text: string) => void; reject: (e: unknown) => void; signal?: AbortSignal; question: string };
let pending: Resolver[] = [];

beforeEach(() => {
  vi.useFakeTimers();
  pending = [];
  draft.mockReset();
  draft.mockImplementation((question, _marks, signal) => new Promise((resolve, reject) => {
    const r: Resolver = { question, signal, resolve: (t) => resolve({ reference_answer: t, model: "test-model" }), reject };
    signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    pending.push(r);
  }));
});
afterEach(() => vi.useRealTimers());

const Q1 = "Explain tokenization in natural language processing.";
const Q2 = "Explain stemming and lemmatization with an example.";

function setup(initial: { text: string; question: string } | null = null, question = "") {
  return renderHook((p: { question: string; maxMarks: number }) => useReferenceAnswer({ ...p, initial }), { initialProps: { question, maxMarks: 4 } });
}
const flush = async () => { await act(async () => { await Promise.resolve(); }); };
const settle = async (r: Resolver, text: string) => { await act(async () => { r.resolve(text); await Promise.resolve(); }); };

describe("useReferenceAnswer", () => {
  it("does not request a draft for an empty or too-short question", () => {
    const h = setup();
    h.rerender({ question: "   ", maxMarks: 4 });
    h.rerender({ question: "Explain it", maxMarks: 4 });
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS * 3); });
    expect(draft).not.toHaveBeenCalled();
    expect(h.result.current.status).toBe("empty");
    expect(h.result.current.isValid).toBe(false);
  });

  it("debounces typing into one request, shows progress and becomes ready", async () => {
    const h = setup();
    for (let i = 20; i <= Q1.length; i += 5) h.rerender({ question: Q1.slice(0, i), maxMarks: 4 });
    h.rerender({ question: Q1, maxMarks: 4 });
    expect(h.result.current.status).toBe("waiting");
    expect(h.result.current.isValid).toBe(false);
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS - 1); });
    expect(draft).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1); });
    expect(draft).toHaveBeenCalledTimes(1);
    expect(draft.mock.calls[0][0]).toBe(Q1);
    expect(h.result.current.status).toBe("generating");
    await settle(pending[0], "Tokenization splits text into tokens.");
    expect(h.result.current.status).toBe("ready");
    expect(h.result.current.text).toBe("Tokenization splits text into tokens.");
    expect(h.result.current.isValid).toBe(true);
  });

  it("never lets a response for an earlier question overwrite the answer for a newer one", async () => {
    const h = setup(null, "");
    h.rerender({ question: Q1, maxMarks: 4 });
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS); });
    const first = pending[0];
    h.rerender({ question: Q2, maxMarks: 4 }); // the question changes while the first draft is in flight
    expect(first.signal?.aborted).toBe(true);
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS); });
    const second = pending[1];
    await act(async () => { first.resolve("Answer for the OLD question."); await Promise.resolve(); });
    expect(h.result.current.text).toBe("");
    await settle(second, "Answer for the new question.");
    expect(h.result.current.text).toBe("Answer for the new question.");
    expect(h.result.current.status).toBe("ready");
  });

  it("replaces an untouched draft when the question changes, but protects teacher edits", async () => {
    const h = setup(null, "");
    h.rerender({ question: Q1, maxMarks: 4 });
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS); });
    await settle(pending[0], "Draft one.");
    act(() => { h.result.current.setText("Draft one, improved by the teacher."); });
    expect(h.result.current.status).toBe("edited");

    h.rerender({ question: Q2, maxMarks: 4 });
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS * 2); });
    expect(draft).toHaveBeenCalledTimes(1); // no automatic overwrite
    expect(h.result.current.status).toBe("stale");
    expect(h.result.current.isValid).toBe(false);
    expect(h.result.current.text).toBe("Draft one, improved by the teacher.");

    act(() => { h.result.current.keepCurrent(); });
    expect(h.result.current.status).toBe("edited");
    expect(h.result.current.isValid).toBe(true);
  });

  it("treats a saved answer as protected: a question change marks it stale", () => {
    const h = setup({ text: "Saved answer.", question: Q1 }, Q1);
    expect(h.result.current.status).toBe("ready");
    expect(h.result.current.origin).toBe("saved");
    h.rerender({ question: Q2, maxMarks: 4 });
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS * 2); });
    expect(draft).not.toHaveBeenCalled();
    expect(h.result.current.status).toBe("stale");
    h.rerender({ question: Q1, maxMarks: 4 }); // undoing the change makes it current again
    expect(h.result.current.status).toBe("ready");
  });

  it("marks the answer stale when the question is cleared and cancels pending drafts", async () => {
    const h = setup({ text: "Saved answer.", question: Q1 }, Q1);
    h.rerender({ question: "", maxMarks: 4 });
    expect(h.result.current.status).toBe("stale");
    const fresh = setup(null, "");
    fresh.rerender({ question: Q1, maxMarks: 4 });
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS); });
    fresh.rerender({ question: "", maxMarks: 4 });
    expect(pending[0].signal?.aborted).toBe(true);
    expect(fresh.result.current.status).toBe("empty");
  });

  it("shows a recoverable error when drafting fails, and keeps the existing answer when regeneration fails", async () => {
    const h = setup(null, "");
    h.rerender({ question: Q1, maxMarks: 4 });
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS); });
    await act(async () => { pending[0].reject(new ApiError(503, "Drafting is not set up on this server.", "generation_unavailable")); await Promise.resolve(); });
    expect(h.result.current.status).toBe("error");
    expect(h.result.current.failure).toMatch(/not set up/);

    // unavailable drafting is not retried on every edit
    h.rerender({ question: `${Q1} Give one example.`, maxMarks: 4 });
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS * 2); });
    expect(draft).toHaveBeenCalledTimes(1);

    // the teacher can still retry explicitly
    act(() => { void h.result.current.regenerate(); });
    await settle(pending[1], "Recovered answer.");
    expect(h.result.current.status).toBe("ready");

    act(() => { void h.result.current.regenerate(); });
    expect(h.result.current.status).toBe("generating");
    expect(h.result.current.text).toBe("Recovered answer.");
    await act(async () => { pending[2].reject(new ApiError(502, "The drafting service had a temporary problem.", "generation_failed")); await Promise.resolve(); });
    expect(h.result.current.text).toBe("Recovered answer.");
    expect(h.result.current.status).toBe("ready");
    expect(h.result.current.failure).toMatch(/temporary problem/);
  });

  it("lets the teacher's typing win over a draft in flight", async () => {
    const h = setup(null, "");
    h.rerender({ question: Q1, maxMarks: 4 });
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS); });
    act(() => { h.result.current.setText("I will write it myself."); });
    expect(pending[0].signal?.aborted).toBe(true);
    await flush();
    expect(h.result.current.text).toBe("I will write it myself.");
    expect(h.result.current.status).toBe("edited");
    expect(h.result.current.origin).toBe("manual");
    expect(h.result.current.isValid).toBe(true);
  });

  it("prevents duplicate requests while one is in flight", () => {
    const h = setup(null, Q1);
    act(() => { void h.result.current.regenerate(); });
    act(() => { void h.result.current.regenerate(); });
    expect(pending[0].signal?.aborted).toBe(true); // the earlier one is cancelled, never both applied
    expect(pending.filter((p) => !p.signal?.aborted)).toHaveLength(1);
  });

  it("abandons in-flight requests on unmount", () => {
    const h = setup(null, "");
    h.rerender({ question: Q1, maxMarks: 4 });
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS); });
    h.unmount();
    expect(pending[0].signal?.aborted).toBe(true);
  });
});
