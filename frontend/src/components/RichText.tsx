// Read-only rendering of Margin rich text (lib/markdown). Built from React elements only - never innerHTML - so stored
// text can never inject markup or scripts.
import { Fragment, type ReactNode } from "react";

import { parseMarkdown, type Block, type Inline } from "@/lib/markdown";
import { cn } from "@/lib/utils";

function renderInline(content: Inline[]): ReactNode[] {
  return content.map((n, i) => {
    if (n.kind === "break") return <br key={i} />;
    let node: ReactNode = n.text;
    if (n.italic) node = <em>{node}</em>;
    if (n.bold) node = <strong>{node}</strong>;
    return <Fragment key={i}>{node}</Fragment>;
  });
}

function renderBlock(block: Block, key: number): ReactNode {
  switch (block.kind) {
    case "paragraph": return <p key={key}>{renderInline(block.content)}</p>;
    case "heading": return block.level === 3 ? <h3 key={key}>{renderInline(block.content)}</h3> : <h4 key={key}>{renderInline(block.content)}</h4>;
    case "list": {
      const items = block.items.map((it, i) => <li key={i}>{renderInline(it.content)}{it.children.map(renderBlock)}</li>);
      return block.ordered ? <ol key={key} start={block.start === 1 ? undefined : block.start}>{items}</ol> : <ul key={key}>{items}</ul>;
    }
    case "table": return (
      <div key={key} className="rt-table">
        <table>
          <thead><tr>{block.header.map((c, i) => <th key={i} scope="col">{renderInline(c)}</th>)}</tr></thead>
          <tbody>{block.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{renderInline(c)}</td>)}</tr>)}</tbody>
        </table>
      </div>
    );
  }
}

export function RichText({ text, className, size = "body", empty }: {
  text: string; className?: string; size?: "body" | "body-lg" | "feedback" | "small"; empty?: ReactNode;
}) {
  const blocks = parseMarkdown(text);
  if (!blocks.length) return empty ? <>{empty}</> : null;
  return (
    <div className={cn("rt min-w-0 break-words text-slate-900",
      size === "feedback" && "text-feedback", size === "body-lg" && "text-body-lg", size === "body" && "text-body", size === "small" && "text-small",
      className)}>
      {blocks.map(renderBlock)}
    </div>
  );
}
