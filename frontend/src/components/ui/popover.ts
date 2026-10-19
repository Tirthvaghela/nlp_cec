import { useEffect, useRef, useState } from "react";

/** Open/close state for a trigger + panel pair: closes on outside pointer-down and Escape (focus returns to the trigger). */
export function usePopover<T extends HTMLElement = HTMLButtonElement>() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<T>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const close = (refocus = true) => {
    setOpen(false);
    if (refocus) triggerRef.current?.focus();
  };
  return { open, setOpen, close, rootRef, triggerRef };
}

/** Panel shared look (STYLEGUIDE §8): white, slate-100 border, radius 12, e2 shadow, 6px padding, 6px offset. */
export const panelClass = "absolute left-0 top-[calc(100%+6px)] z-40 rounded-md border border-slate-100 bg-white p-[6px] shadow-e2";

/** Trigger shared look: exactly a text field (44px, radius 8) - the focus style shows while open. */
export const triggerClass =
  "flex h-11 w-full min-w-0 items-center gap-2 rounded-sm border border-slate-200 bg-white px-[14px] text-left font-sans text-body text-slate-900 " +
  "transition-[border-color,box-shadow] duration-150 hover:border-slate-300 focus-visible:border-ink-600 focus-visible:shadow-[var(--focus-input)] " +
  "aria-expanded:border-ink-600 aria-expanded:shadow-[var(--focus-input)] aria-[invalid=true]:border-danger disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400";
