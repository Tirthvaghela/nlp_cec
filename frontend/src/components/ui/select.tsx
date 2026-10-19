// Single select (STYLEGUIDE §8.1): a trigger that looks like a text field and a listbox panel. Keyboard: Up/Down to
// move, Home/End, Enter or Space to pick, Escape to close, typing jumps to the first matching option.
import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { panelClass, triggerClass, usePopover } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
  meta?: ReactNode;
}

export function Select<T extends string>({
  id, value, onChange, options, placeholder = "Choose an option", className, disabled,
  "aria-describedby": describedBy, "aria-invalid": invalid, "aria-label": ariaLabel,
}: {
  id?: string;
  value: T | "";
  onChange: (value: T) => void;
  options: SelectOption<T>[];
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
  "aria-label"?: string;
}) {
  const { open, setOpen, close, rootRef, triggerRef } = usePopover<HTMLButtonElement>();
  const listRef = useRef<HTMLUListElement>(null);
  const autoId = useId();
  const listId = `${id ?? autoId}-listbox`;
  const selectedIndex = options.findIndex((o) => o.value === value);
  const [active, setActive] = useState(Math.max(0, selectedIndex));
  const typed = useRef({ text: "", at: 0 });

  useEffect(() => {
    if (!open) return;
    setActive(Math.max(0, selectedIndex));
    listRef.current?.focus();
  }, [open, selectedIndex]);

  useEffect(() => {
    if (open) listRef.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, open]);

  const pick = (i: number) => {
    const o = options[i];
    if (!o) return;
    onChange(o.value);
    close();
  };

  const onTriggerKey = (e: KeyboardEvent) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
      e.preventDefault();
      setOpen(true);
    }
  };

  const onListKey = (e: KeyboardEvent) => {
    const last = options.length - 1;
    switch (e.key) {
      case "ArrowDown": e.preventDefault(); setActive((a) => Math.min(last, a + 1)); return;
      case "ArrowUp": e.preventDefault(); setActive((a) => Math.max(0, a - 1)); return;
      case "Home": e.preventDefault(); setActive(0); return;
      case "End": e.preventDefault(); setActive(last); return;
      case "Enter": case " ": e.preventDefault(); pick(active); return;
      case "Tab": close(false); return;
    }
    if (e.key.length === 1 && /\S/.test(e.key)) {
      const now = Date.now();
      typed.current = { text: (now - typed.current.at < 700 ? typed.current.text : "") + e.key.toLowerCase(), at: now };
      const hit = options.findIndex((o) => o.label.toLowerCase().startsWith(typed.current.text));
      if (hit >= 0) setActive(hit);
    }
  };

  const current = options[selectedIndex];
  return (
    <div ref={rootRef} className={cn("relative min-w-0", className)}>
      <button ref={triggerRef} id={id} type="button" disabled={disabled} className={triggerClass}
        role="combobox" aria-haspopup="listbox" aria-expanded={open} aria-controls={open ? listId : undefined}
        aria-describedby={describedBy} aria-invalid={invalid} aria-label={ariaLabel}
        onClick={() => setOpen(!open)} onKeyDown={onTriggerKey}>
        <span className={cn("min-w-0 flex-1 truncate", !current && "text-slate-400")}>{current?.label ?? placeholder}</span>
        <ChevronDown className={cn("size-[18px] text-slate-500 transition-transform duration-150", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <ul ref={listRef} id={listId} role="listbox" tabIndex={-1} aria-activedescendant={`${listId}-${active}`}
          aria-labelledby={id} onKeyDown={onListKey}
          className={cn(panelClass, "right-0 m-0 max-h-72 list-none overflow-y-auto focus-visible:shadow-e2")}>
          {options.map((o, i) => {
            const selected = o.value === value;
            return (
              <li key={o.value} id={`${listId}-${i}`} data-index={i} role="option" aria-selected={selected}
                onPointerMove={() => setActive(i)} onClick={() => pick(i)}
                className={cn("flex h-10 cursor-pointer items-center gap-2 rounded-sm px-[10px] text-body",
                  selected ? "bg-ink-50 font-semibold text-ink-900" : i === active ? "bg-slate-50 text-slate-900" : "text-slate-900",
                  i === active && "outline outline-1 outline-ink-200")}>
                <span className="min-w-0 flex-1 truncate">{o.label}</span>
                {o.meta !== undefined && <span className="tabular flex-none text-small font-normal text-slate-500">{o.meta}</span>}
                {selected && <Check className="size-[18px] flex-none text-ink-600" aria-hidden />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
