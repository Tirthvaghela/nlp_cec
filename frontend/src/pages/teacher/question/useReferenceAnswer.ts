// Reference-answer lifecycle for the question editor.
//
//   empty      no answer; dependent actions are disabled
//   waiting    the question changed; a draft is scheduled after a short debounce
//   generating a draft request is in flight (duplicates are prevented)
//   ready      an answer exists for the current question (drafted, or the saved one)
//   edited     the teacher changed the answer - it is never replaced without the teacher's confirmation
//   stale      the question changed after the answer was written; the teacher regenerates or keeps it
//   error      drafting failed and there is no answer to fall back on
//
// Rules: a draft is requested automatically only when there is no answer, the last attempt failed, or the answer is an
// untouched draft. Saved or edited answers are protected: a question change marks them stale instead. Every request
// carries an id and an AbortSignal; a response for an older question, a cancelled request, or a request overtaken by the
// teacher's own typing is discarded. A failed regeneration keeps the existing answer.
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, errorMessage, isAbort } from "@/lib/api";
import { draftReferenceAnswer } from "@/lib/generation";
import { plainText } from "@/lib/markdown";

export type RefStatus = "empty" | "waiting" | "generating" | "ready" | "edited" | "stale" | "error";
export type RefOrigin = "generated" | "saved" | "manual" | null;

export const DRAFT_DEBOUNCE_MS = 1200;
export const REFERENCE_MAX_CHARS = 5000;

/** The question as the model sees it, whitespace-collapsed: changes in formatting alone do not count as a new question. */
export function questionKey(markdown: string): string {
  return plainText(markdown).replace(/\s+/g, " ").trim();
}

export function isMeaningfulQuestion(markdown: string): boolean {
  const key = questionKey(markdown);
  return key.length >= 12 && key.split(" ").length >= 3;
}

interface Core {
  text: string;
  basedOn: string | null;
  origin: RefOrigin;
  edited: boolean;
  phase: "idle" | "waiting" | "generating";
  failure: string | null;
  failureCode: string | null;
}

function initialCore(initial: { text: string; question: string } | null): Core {
  const text = initial?.text ?? "";
  return {
    text,
    basedOn: text.trim() ? questionKey(initial!.question) : null,
    origin: text.trim() ? "saved" : null,
    edited: false,
    phase: "idle",
    failure: null,
    failureCode: null,
  };
}

export function deriveStatus(core: Core, key: string): RefStatus {
  if (core.phase === "waiting") return "waiting";
  if (core.phase === "generating") return "generating";
  const has = core.text.trim().length > 0;
  if (!has) return core.failure ? "error" : "empty";
  if (core.basedOn !== key) return "stale";
  return core.edited ? "edited" : "ready";
}

export function useReferenceAnswer({ question, maxMarks, initial }: {
  question: string;
  maxMarks: number;
  initial: { text: string; question: string } | null;
}) {
  const [core, setCore] = useState<Core>(() => initialCore(initial));
  const coreRef = useRef(core);
  coreRef.current = core;

  const key = questionKey(question);
  const marksOk = maxMarks > 0 && Math.abs(maxMarks * 2 - Math.round(maxMarks * 2)) < 1e-9 && maxMarks <= 100;
  const meaningful = isMeaningfulQuestion(question) && marksOk;

  const live = useRef({ question, key, maxMarks });
  live.current = { question, key, maxMarks };
  const requestId = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Invalidate every scheduled or in-flight request. */
  const cancel = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    controller.current?.abort();
    controller.current = null;
    requestId.current += 1;
  }, []);

  const generate = useCallback(async () => {
    cancel();
    const { question: q, key: k, maxMarks: marks } = live.current;
    const id = requestId.current;
    const ctrl = new AbortController();
    controller.current = ctrl;
    setCore((c) => ({ ...c, phase: "generating", failure: null, failureCode: null }));
    try {
      const draft = await draftReferenceAnswer(q, marks, ctrl.signal);
      if (id !== requestId.current || ctrl.signal.aborted || live.current.key !== k) return;
      controller.current = null;
      setCore({ text: draft.reference_answer, basedOn: k, origin: "generated", edited: false, phase: "idle", failure: null, failureCode: null });
    } catch (err) {
      if (isAbort(err) || id !== requestId.current) return;
      controller.current = null;
      setCore((c) => ({ ...c, phase: "idle", failure: errorMessage(err), failureCode: err instanceof ApiError ? err.code : null }));
    }
  }, [cancel]);

  // React to meaningful question changes (and to the question becoming empty).
  useEffect(() => {
    const c = coreRef.current;
    if (!meaningful) {
      cancel();
      if (c.phase !== "idle") setCore((s) => ({ ...s, phase: "idle" }));
      return;
    }
    const has = c.text.trim().length > 0;
    if (has && c.basedOn === key) {
      // the answer belongs to this question (e.g. the teacher undid an edit): stop any scheduled draft
      if (c.phase === "waiting") { cancel(); setCore((s) => ({ ...s, phase: "idle" })); }
      return;
    }
    const protectedAnswer = has && (c.edited || c.origin === "saved" || c.origin === "manual");
    if (protectedAnswer) {
      // never overwrite the teacher's answer: it becomes stale and the teacher decides
      if (c.phase !== "idle") { cancel(); setCore((s) => ({ ...s, phase: "idle" })); }
      return;
    }
    if (c.failureCode === "generation_unavailable" || c.failureCode === "generation_disabled_in_pilot") {
      return; // drafting is not available on this server: do not retry on every edit
    }
    cancel();
    setCore((s) => ({ ...s, phase: "waiting", failure: null, failureCode: null }));
    timer.current = setTimeout(() => { timer.current = null; void generate(); }, DRAFT_DEBOUNCE_MS);
    return () => { if (timer.current) { clearTimeout(timer.current); timer.current = null; } };
  }, [key, meaningful, cancel, generate]);

  // Unmount: abandon anything in flight.
  useEffect(() => () => cancel(), [cancel]);

  /** The teacher typed in the reference answer: their text wins over any pending draft. */
  const setText = useCallback((markdown: string) => {
    if (coreRef.current.phase !== "idle") cancel();
    setCore((c) => {
      if (!markdown.trim()) return { text: "", basedOn: null, origin: null, edited: false, phase: "idle", failure: null, failureCode: c.failureCode };
      if (markdown === c.text && c.phase === "idle") return c;
      return {
        ...c,
        text: markdown,
        edited: true,
        origin: c.text.trim() ? c.origin : "manual",
        basedOn: c.text.trim() ? c.basedOn : live.current.key,
        phase: "idle",
        failure: null, // the teacher has an answer now; failureCode is kept so unavailable drafting is not retried per edit
      };
    });
  }, [cancel]);

  /** Keep the current answer for the changed question (resolves "stale"). */
  const keepCurrent = useCallback(() => setCore((c) => ({ ...c, basedOn: live.current.key })), []);

  /** Restore a known state (discard changes, or after the question was saved). */
  const reset = useCallback((next: { text: string; question: string } | null) => {
    cancel();
    setCore(initialCore(next));
  }, [cancel]);

  const status = deriveStatus(core, key);
  const text = core.text;
  const tooLong = text.length > REFERENCE_MAX_CHARS;
  const isValid = (status === "ready" || status === "edited") && text.trim().length > 0 && !tooLong;
  const isProtected = text.trim().length > 0 && (core.edited || core.origin === "saved" || core.origin === "manual");

  return {
    status, text, origin: core.origin, failure: core.failure, failureCode: core.failureCode,
    isValid, tooLong, isProtected, canDraft: meaningful,
    busy: status === "waiting" || status === "generating",
    setText, regenerate: generate, keepCurrent, reset, cancel,
  };
}

export type ReferenceAnswer = ReturnType<typeof useReferenceAnswer>;
