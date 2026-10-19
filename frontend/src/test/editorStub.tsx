// Test stand-in for the rich-text editor in page-level tests: a labelled textarea with the same value/onChange
// contract, footer and word count (the real editor is covered by richTextEditor.test.tsx). Use with
//   vi.mock("@/components/editor/RichTextEditor", () => import("@/test/editorStub"));
import type { RichTextEditorProps } from "@/components/editor/RichTextEditor";
import { wordCountOf } from "@/lib/markdown";

export type { EditorFeatures } from "@/components/editor/RichTextEditor";

export function RichTextEditor({
  id, value, onChange, onBlur, placeholder, readOnly, footer, showWordCount,
  "aria-describedby": describedBy, "aria-invalid": invalid, "aria-label": ariaLabel,
}: RichTextEditorProps) {
  const words = wordCountOf(value);
  return (
    <div>
      <textarea id={id} value={value} placeholder={placeholder} readOnly={readOnly} aria-describedby={describedBy} aria-invalid={invalid}
        {...(ariaLabel ? { "aria-label": ariaLabel } : { "aria-labelledby": `${id}-label` })}
        onChange={(e) => onChange(e.target.value)} onBlur={onBlur} />
      {footer}
      {showWordCount && <span>{words} {words === 1 ? "word" : "words"}</span>}
    </div>
  );
}
