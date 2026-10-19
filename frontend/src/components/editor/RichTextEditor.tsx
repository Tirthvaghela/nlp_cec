// Rich-text editor for descriptive content (TipTap / ProseMirror). It reads and writes the Margin Markdown subset
// (lib/markdown), so the value is always a plain string that the existing API and scoring engine accept.
//
// Safety: ProseMirror only keeps content its schema knows (paragraphs, headings, lists, tables, bold, italic, line
// breaks). Pasted HTML is parsed into that schema, so scripts, styles, images, links and event attributes never survive;
// nothing is ever rendered with innerHTML.
//
// Accessibility: the editable area is a labelled multi-line textbox; the toolbar is a single tab stop with arrow-key
// navigation (role="toolbar"); Escape moves focus out of the editor so Tab can leave a table or list.
import { Extension } from "@tiptap/core";
import { TableKit } from "@tiptap/extension-table";
import { Placeholder } from "@tiptap/extensions";
import { EditorContent, useEditor, useEditorState, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  BetweenHorizontalEnd, BetweenVerticalEnd, Bold, Columns3, Grid2x2X, Heading, Italic, List, ListIndentDecrease, ListIndentIncrease,
  ListOrdered, Redo2, RemoveFormatting, Rows3, Table, Undo2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { docToMarkdown, markdownToDoc, wordCountOf, type PMNode } from "@/lib/markdown";
import { cn } from "@/lib/utils";

export type EditorFeatures = "basic" | "lists" | "full";

export interface RichTextEditorProps {
  id: string;
  value: string;
  onChange: (markdown: string) => void;
  /** basic: bold/italic; lists: + lists; full: + headings and tables. */
  features?: EditorFeatures;
  placeholder?: string;
  readOnly?: boolean;
  size?: "default" | "answer";
  minHeight?: number;
  maxLength?: number;
  className?: string;
  onBlur?: () => void;
  /** Exposes the editor instance (tests and integrations). */
  onReady?: (editor: Editor) => void;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
  "aria-required"?: boolean;
  "aria-label"?: string;
  /** Extra content under the editor, left of the counters (e.g. autosave status). */
  footer?: ReactNode;
  showWordCount?: boolean;
}

export function RichTextEditor({
  id, value, onChange, features = "full", placeholder, readOnly, size = "default", minHeight, maxLength, className, onBlur, onReady,
  "aria-describedby": describedBy, "aria-invalid": invalid, "aria-required": required, "aria-label": ariaLabel, footer, showWordCount,
}: RichTextEditorProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const lastEmitted = useRef<string>(value);
  const onChangeRef = useRef(onChange);
  const onBlurRef = useRef(onBlur);
  useEffect(() => { onChangeRef.current = onChange; onBlurRef.current = onBlur; });

  const extensions = useMemo(() => {
    const lists = features !== "basic";
    const full = features === "full";
    return [
      StarterKit.configure({
        heading: full ? { levels: [3, 4] } : false,
        bulletList: lists ? {} : false,
        orderedList: lists ? {} : false,
        listItem: lists ? {} : false,
        listKeymap: lists ? {} : false,
        blockquote: false, code: false, codeBlock: false, horizontalRule: false, strike: false, underline: false, link: false,
      }),
      ...(full ? [TableKit.configure({ table: { resizable: false } })] : []),
      Placeholder.configure({ placeholder: placeholder ?? "" }),
      Extension.create({
        name: "marginEscape",
        addKeyboardShortcuts: () => ({ Escape: () => { wrapperRef.current?.focus(); return true; } }),
      }),
    ];
    // The schema is fixed for the lifetime of the editor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const editor = useEditor({
    extensions,
    content: markdownToDoc(value),
    editable: !readOnly,
    immediatelyRender: true,
    shouldRerenderOnTransaction: false,
    editorProps: {
      attributes: {
        id,
        role: "textbox",
        "aria-multiline": "true",
        ...(ariaLabel ? { "aria-label": ariaLabel } : { "aria-labelledby": `${id}-label` }),
        ...(describedBy ? { "aria-describedby": describedBy } : {}),
        ...(invalid ? { "aria-invalid": "true" } : {}),
        ...(required ? { "aria-required": "true" } : {}),
        ...(readOnly ? { "aria-readonly": "true" } : {}),
        class: cn("min-w-0 px-4 py-[14px] text-slate-900", size === "answer" ? "text-body-lg" : "text-body", "rt"),
        style: `min-height:${minHeight ?? (size === "answer" ? 280 : 120)}px`,
      },
    },
    onUpdate: ({ editor: e }) => {
      const md = docToMarkdown(e.getJSON() as PMNode);
      lastEmitted.current = md;
      onChangeRef.current(md);
    },
    onBlur: () => onBlurRef.current?.(),
  });

  // Keep accessibility attributes current without recreating the editor.
  useEffect(() => {
    if (!editor) return;
    editor.setOptions({
      editorProps: {
        ...editor.options.editorProps,
        attributes: {
          ...(editor.options.editorProps.attributes as Record<string, string>),
          ...(describedBy ? { "aria-describedby": describedBy } : { "aria-describedby": "" }),
          "aria-invalid": invalid ? "true" : "false",
        },
      },
    });
  }, [editor, describedBy, invalid]);

  useEffect(() => { editor?.setEditable(!readOnly); }, [editor, readOnly]);
  useEffect(() => { if (editor && onReady) onReady(editor); }, [editor, onReady]);

  // External value changes (a generated reference answer, a reload, a discard) replace the content - but only when the
  // value differs from what the editor itself last produced, so typing never resets the cursor.
  useEffect(() => {
    if (!editor || value === lastEmitted.current) return;
    lastEmitted.current = value;
    editor.commands.setContent(markdownToDoc(value) as never, { emitUpdate: false });
  }, [editor, value]);

  const words = showWordCount ? wordCountOf(value) : 0;
  const over = maxLength !== undefined && value.length > maxLength;
  const nearLimit = maxLength !== undefined && value.length > maxLength * 0.8;

  return (
    <div className={cn("margin-editor flex min-w-0 flex-col gap-[6px]", className)}>
      <div ref={wrapperRef} tabIndex={-1}
        className={cn("min-w-0 overflow-hidden rounded-sm border bg-white transition-[border-color,box-shadow] duration-150",
          "focus-within:border-ink-600 focus-within:shadow-[var(--focus-input)] focus-visible:shadow-[var(--focus-input)]",
          invalid || over ? "border-danger focus-within:shadow-[var(--focus-error)]" : "border-slate-200 hover:border-slate-300",
          readOnly && "bg-slate-50")}>
        {!readOnly && editor && <Toolbar editor={editor} features={features} editorId={id} />}
        <EditorContent editor={editor} />
      </div>
      {(footer || showWordCount || nearLimit) && (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-caption text-slate-500">
          <div className="min-w-0">{footer}</div>
          <div className="tabular flex items-center gap-3" aria-live="polite">
            {showWordCount && <span>{words} {words === 1 ? "word" : "words"}</span>}
            {nearLimit && maxLength !== undefined && (
              <span className={cn(over && "font-semibold text-danger")}>{value.length.toLocaleString()} / {maxLength.toLocaleString()} characters</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------------------------------------------- toolbar */

interface Tool { key: string; label: string; icon: ReactNode; run: () => void; active?: boolean; disabled?: boolean; shortcut?: string }

function Toolbar({ editor, features, editorId }: { editor: Editor; features: EditorFeatures; editorId: string }) {
  const s = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e.isActive("bold"),
      italic: e.isActive("italic"),
      heading: e.isActive("heading", { level: 3 }),
      bullet: e.isActive("bulletList"),
      ordered: e.isActive("orderedList"),
      inTable: e.isActive("table"),
      canUndo: e.can().undo(),
      canRedo: e.can().redo(),
      canSink: features !== "basic" && e.can().sinkListItem("listItem"),
      canLift: features !== "basic" && e.can().liftListItem("listItem"),
    }),
  });
  const chain = () => editor.chain().focus();
  const mod = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl+";

  const groups: Tool[][] = [
    [
      { key: "undo", label: "Undo", icon: <Undo2 />, run: () => chain().undo().run(), disabled: !s.canUndo, shortcut: `${mod}Z` },
      { key: "redo", label: "Redo", icon: <Redo2 />, run: () => chain().redo().run(), disabled: !s.canRedo, shortcut: `${mod}Shift+Z` },
    ],
    [
      ...(features === "full" ? [{ key: "heading", label: "Section heading", icon: <Heading />, run: () => chain().toggleHeading({ level: 3 }).run(), active: s.heading }] : []),
      { key: "bold", label: "Bold", icon: <Bold />, run: () => chain().toggleBold().run(), active: s.bold, shortcut: `${mod}B` },
      { key: "italic", label: "Italic", icon: <Italic />, run: () => chain().toggleItalic().run(), active: s.italic, shortcut: `${mod}I` },
    ],
    ...(features !== "basic" ? [[
      { key: "bullet", label: "Bulleted list", icon: <List />, run: () => chain().toggleBulletList().run(), active: s.bullet, shortcut: `${mod}Shift+8` },
      { key: "ordered", label: "Numbered list", icon: <ListOrdered />, run: () => chain().toggleOrderedList().run(), active: s.ordered, shortcut: `${mod}Shift+7` },
      { key: "indent", label: "Indent list item", icon: <ListIndentIncrease />, run: () => chain().sinkListItem("listItem").run(), disabled: !s.canSink, shortcut: "Tab" },
      { key: "outdent", label: "Outdent list item", icon: <ListIndentDecrease />, run: () => chain().liftListItem("listItem").run(), disabled: !s.canLift, shortcut: "Shift+Tab" },
    ]] : []),
    ...(features === "full" ? [s.inTable ? [
      { key: "row", label: "Add row below", icon: <BetweenHorizontalEnd />, run: () => chain().addRowAfter().run() },
      { key: "col", label: "Add column right", icon: <BetweenVerticalEnd />, run: () => chain().addColumnAfter().run() },
      { key: "delrow", label: "Delete row", icon: <Rows3 />, run: () => chain().deleteRow().run() },
      { key: "delcol", label: "Delete column", icon: <Columns3 />, run: () => chain().deleteColumn().run() },
      { key: "deltable", label: "Delete table", icon: <Grid2x2X />, run: () => chain().deleteTable().run() },
    ] : [
      { key: "table", label: "Insert table", icon: <Table />, run: () => chain().insertTable({ rows: 3, cols: 2, withHeaderRow: true }).run() },
    ]] : []),
    [{ key: "clear", label: "Clear formatting", icon: <RemoveFormatting />, run: () => chain().unsetAllMarks().clearNodes().run() }],
  ];

  const flat = groups.flat();
  const [focusKey, setFocusKey] = useState(flat[0].key);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const enabled = flat.filter((t) => !t.disabled);
  const current = enabled.some((t) => t.key === focusKey) ? focusKey : enabled[0]?.key;

  const onKeyDown = (e: KeyboardEvent) => {
    const idx = enabled.findIndex((t) => t.key === current);
    let next = -1;
    if (e.key === "ArrowRight") next = (idx + 1) % enabled.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + enabled.length) % enabled.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = enabled.length - 1;
    if (next < 0) return;
    e.preventDefault();
    setFocusKey(enabled[next].key);
    refs.current[enabled[next].key]?.focus();
  };

  return (
    <div role="toolbar" aria-label="Formatting" aria-controls={editorId} onKeyDown={onKeyDown}
      className="flex flex-wrap items-center gap-1 border-b border-slate-100 bg-slate-25 px-2 py-1">
      {groups.map((g, gi) => (
        <div key={gi} className="flex items-center gap-0.5" role="group">
          {gi > 0 && <span aria-hidden className="mx-1 h-5 w-px bg-slate-200" />}
          {g.map((t) => (
            <button key={t.key} ref={(el) => { refs.current[t.key] = el; }} type="button" tabIndex={t.key === current ? 0 : -1}
              aria-label={t.shortcut ? `${t.label} (${t.shortcut})` : t.label} data-tooltip={t.shortcut ? `${t.label} · ${t.shortcut}` : t.label}
              aria-pressed={t.active === undefined ? undefined : t.active} disabled={t.disabled}
              onMouseDown={(e) => e.preventDefault()} onClick={() => { setFocusKey(t.key); t.run(); }}
              className={cn("grid size-9 place-items-center rounded-sm border-0 transition-colors duration-150 [&_svg]:size-[18px]",
                t.active ? "bg-ink-100 text-ink-800" : "bg-transparent text-slate-600 hover:bg-ink-50 hover:text-ink-700",
                "disabled:bg-transparent disabled:text-slate-300")}>
              {t.icon}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
