// Margin rich text: a small Markdown subset stored in the existing string fields (question text, reference answer,
// instructions, student answers). Why Markdown and not HTML: the scoring engine reads these strings directly - it
// treats line breaks and "- " / "1. " bullets as sentence boundaries and stores evidence as character offsets into the
// raw text - so the stored form must stay readable plain text. Every legacy plain-text record is already valid input.
//
// Supported: paragraphs (single newlines are kept as line breaks), "### " / "#### " headings, **bold**, *italic*,
// "- " and "1. " lists (nested by indentation), and pipe tables with a header row. Everything else is literal text.
// Special characters inside text are escaped with a backslash so a save/load round trip never changes the structure.

export type Inline = { kind: "text"; text: string; bold?: boolean; italic?: boolean } | { kind: "break" };
export type ListItem = { content: Inline[]; children: Block[] };
export type Block =
  | { kind: "paragraph"; content: Inline[] }
  | { kind: "heading"; level: 3 | 4; content: Inline[] }
  | { kind: "list"; ordered: boolean; start: number; items: ListItem[] }
  | { kind: "table"; header: Inline[][]; rows: Inline[][][] };

/* ------------------------------------------------------------------------------------------------ parsing */

const LIST_RE = /^( *)([-*+•]|(\d{1,9})[.)])[ \t]+(.*)$/;
const HEADING_RE = /^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$/;
const TABLE_SEP_RE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;
const ESCAPABLE = "\\*_#-+.)|>`[]!";

function parseInlineInto(src: string, out: Inline[], bold: boolean, italic: boolean): void {
  let buf = "";
  const flush = () => {
    if (buf) out.push({ kind: "text", text: buf, ...(bold ? { bold } : {}), ...(italic ? { italic } : {}) });
    buf = "";
  };
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (c === "\\" && i + 1 < src.length && ESCAPABLE.includes(src[i + 1])) {
      buf += src[i + 1];
      i += 2;
      continue;
    }
    if (c === "\n") {
      flush();
      out.push({ kind: "break" });
      i += 1;
      continue;
    }
    if (c === "*") {
      const strong = src.startsWith("**", i);
      const marker = strong ? "**" : "*";
      const after = src[i + marker.length];
      if (after && !/\s/.test(after)) {
        const close = findClose(src, i + marker.length, marker);
        if (close > 0) {
          flush();
          parseInlineInto(src.slice(i + marker.length, close), out, bold || strong, italic || !strong);
          i = close + marker.length;
          continue;
        }
      }
    }
    buf += c;
    i += 1;
  }
  flush();
}

/** Index of the closing marker (not escaped, not preceded by whitespace), or -1. */
function findClose(src: string, from: number, marker: string): number {
  for (let j = from; j < src.length; j++) {
    if (src[j] === "\\") { j += 1; continue; }
    if (src[j] === "\n") return -1;
    if (src.startsWith(marker, j) && !/\s/.test(src[j - 1])) {
      // "**" must not close a single "*" span and vice versa
      if (marker === "*" && src[j + 1] === "*") { j += 1; continue; }
      // "***" closing a bold span that contains an italic one: the italic marker comes first
      if (marker === "**" && src[j + 2] === "*") return j + 1;
      return j;
    }
  }
  return -1;
}

export function parseInline(src: string): Inline[] {
  const out: Inline[] = [];
  parseInlineInto(src, out, false, false);
  return out;
}

function splitRow(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|") && !s.endsWith("\\|")) s = s.slice(0, -1);
  const cells: string[] = [];
  let cur = "";
  for (let i = 0; i < s.length; i++) {
    if (s[i] === "\\" && s[i + 1] === "|") { cur += "\\|"; i += 1; continue; }
    if (s[i] === "|") { cells.push(cur.trim()); cur = ""; continue; }
    cur += s[i];
  }
  cells.push(cur.trim());
  return cells;
}

interface Line { indent: number; text: string }

function parseList(lines: Line[], start: number, baseIndent: number): { block: Block; next: number } {
  const first = LIST_RE.exec(" ".repeat(lines[start].indent) + lines[start].text)!;
  const ordered = Boolean(first[3]);
  const block: Extract<Block, { kind: "list" }> = { kind: "list", ordered, start: ordered ? Number(first[3]) : 1, items: [] };
  let i = start;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.text) break;
    const m = LIST_RE.exec(" ".repeat(line.indent) + line.text);
    if (m && line.indent === baseIndent && Boolean(m[3]) === ordered) {
      const contentCol = line.indent + m[2].length + 1;
      const item: ListItem = { content: [], children: [] };
      const text: string[] = [m[4]];
      i += 1;
      while (i < lines.length && lines[i].text) {
        const sub = LIST_RE.exec(" ".repeat(lines[i].indent) + lines[i].text);
        if (sub && lines[i].indent > baseIndent) {
          const nested = parseList(lines, i, lines[i].indent);
          item.children.push(nested.block);
          i = nested.next;
          continue;
        }
        if (!sub && lines[i].indent >= Math.min(contentCol, baseIndent + 2) && !item.children.length) {
          text.push(lines[i].text); // continuation line of the item
          i += 1;
          continue;
        }
        break;
      }
      item.content = parseInline(text.join("\n"));
      block.items.push(item);
      continue;
    }
    break;
  }
  return { block, next: i };
}

export function parseMarkdown(src: string): Block[] {
  const raw = (src ?? "").replace(/\r\n?/g, "\n").replace(/\t/g, "    ").split("\n");
  const lines: Line[] = raw.map((l) => {
    const indent = l.length - l.trimStart().length;
    return { indent, text: l.trim() ? l.slice(indent).replace(/\s+$/, "") : "" };
  });
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.text) { i += 1; continue; }
    const h = HEADING_RE.exec(line.text);
    if (h && line.indent < 4) {
      blocks.push({ kind: "heading", level: h[1].length <= 3 ? 3 : 4, content: parseInline(h[2]) });
      i += 1;
      continue;
    }
    if (line.text.startsWith("|") && i + 1 < lines.length && TABLE_SEP_RE.test(lines[i + 1].text)) {
      const header = splitRow(line.text).map(parseInline);
      const rows: Inline[][][] = [];
      i += 2;
      while (i < lines.length && lines[i].text.startsWith("|")) {
        const cells = splitRow(lines[i].text).map(parseInline);
        while (cells.length < header.length) cells.push([]);
        rows.push(cells.slice(0, header.length));
        i += 1;
      }
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    if (LIST_RE.test(" ".repeat(line.indent) + line.text)) {
      const { block, next } = parseList(lines, i, line.indent);
      blocks.push(block);
      i = next;
      continue;
    }
    const text: string[] = [line.text];
    i += 1;
    while (i < lines.length && lines[i].text && !HEADING_RE.test(lines[i].text) && !LIST_RE.test(" ".repeat(lines[i].indent) + lines[i].text)
      && !(lines[i].text.startsWith("|") && i + 1 < lines.length && TABLE_SEP_RE.test(lines[i + 1].text))) {
      text.push(lines[i].text);
      i += 1;
    }
    blocks.push({ kind: "paragraph", content: parseInline(text.join("\n")) });
  }
  return blocks;
}

/* ---------------------------------------------------------------------------------------------- serializing */

function escapeText(text: string, inCell: boolean): string {
  let s = text.replace(/\\/g, "\\\\").replace(/\*/g, "\\*");
  if (inCell) s = s.replace(/\|/g, "\\|");
  return s;
}

/** Escape what would turn the start of a line into structure (heading, list, table). */
function escapeLineStart(line: string): string {
  if (/^#{1,6}(\s|$)/.test(line)) return "\\" + line;
  if (/^[-+•](\s|$)/.test(line)) return "\\" + line;
  const num = /^(\d{1,9})([.)])(\s|$)/.exec(line);
  if (num) return num[1] + "\\" + line.slice(num[1].length);
  if (line.startsWith("|")) return "\\" + line;
  return line;
}

function inlineToMd(content: Inline[], inCell = false): string {
  // merge adjacent runs with the same marks so markers are not split mid-word
  const runs: Inline[] = [];
  for (const node of content) {
    const prev = runs[runs.length - 1];
    if (node.kind === "text" && prev?.kind === "text" && !!prev.bold === !!node.bold && !!prev.italic === !!node.italic) {
      runs[runs.length - 1] = { ...prev, text: prev.text + node.text };
    } else runs.push(node);
  }
  let out = "";
  for (const node of runs) {
    if (node.kind === "break") { out += inCell ? " " : "\n"; continue; }
    if (!node.text) continue;
    let text = escapeText(node.text, inCell);
    if (node.bold || node.italic) {
      // markers must hug non-space characters: move surrounding spaces outside the markers
      const lead = /^\s*/.exec(text)![0];
      const trail = /\s*$/.exec(text)![0];
      const core = text.slice(lead.length, text.length - trail.length);
      if (!core) { out += text; continue; }
      const marker = node.bold && node.italic ? "***" : node.bold ? "**" : "*";
      text = `${lead}${marker}${core}${marker}${trail}`;
    }
    out += text;
  }
  return out;
}

function linesOf(content: Inline[]): string[] {
  return inlineToMd(content).split("\n").map((l, idx) => (idx === 0 ? escapeLineStart(l) : escapeLineStart(l.trimStart())));
}

function listToMd(block: Extract<Block, { kind: "list" }>, indent: string): string[] {
  const out: string[] = [];
  block.items.forEach((item, n) => {
    const marker = block.ordered ? `${block.start + n}. ` : "- ";
    const pad = indent + " ".repeat(marker.length);
    const [first = "", ...rest] = linesOf(item.content);
    out.push(indent + marker + first);
    for (const l of rest) out.push(pad + l);
    for (const child of item.children) {
      if (child.kind === "list") out.push(...listToMd(child, pad));
      else out.push(...blockToMd(child).split("\n").map((l) => pad + l));
    }
  });
  return out;
}

function blockToMd(block: Block): string {
  switch (block.kind) {
    case "paragraph": return linesOf(block.content).join("\n");
    case "heading": return `${block.level === 3 ? "###" : "####"} ${inlineToMd(block.content).replace(/\n/g, " ")}`;
    case "list": return listToMd(block, "").join("\n");
    case "table": {
      const width = Math.max(1, block.header.length);
      const row = (cells: Inline[][]) => {
        const padded = [...cells];
        while (padded.length < width) padded.push([]);
        return `| ${padded.slice(0, width).map((c) => inlineToMd(c, true).trim()).join(" | ")} |`;
      };
      return [row(block.header), `| ${Array(width).fill("---").join(" | ")} |`, ...block.rows.map(row)].join("\n");
    }
  }
}

export function serializeMarkdown(blocks: Block[]): string {
  return blocks
    .filter((b) => !(b.kind === "paragraph" && !b.content.some((n) => n.kind === "text" && n.text.trim())))
    .map(blockToMd)
    .join("\n\n")
    .trim();
}

/** Re-serialize stored text into canonical form (used to compare versions without false "unsaved changes"). */
export function normalizeMarkdown(src: string): string {
  return serializeMarkdown(parseMarkdown(src));
}

/* ------------------------------------------------------------------------------------------------ plain text */

function inlineText(content: Inline[]): string {
  return content.map((n) => (n.kind === "break" ? "\n" : n.text)).join("");
}

function blockText(block: Block): string {
  switch (block.kind) {
    case "paragraph": case "heading": return inlineText(block.content);
    case "list": return block.items.map((it) => [inlineText(it.content), ...it.children.map(blockText)].join("\n")).join("\n");
    case "table": return [block.header, ...block.rows].map((r) => r.map(inlineText).join(" ")).join("\n");
  }
}

/** Visible text without any markup (for word counts, previews and validation). */
export function plainText(src: string): string {
  return parseMarkdown(src).map(blockText).join("\n\n");
}

/** Words a reader sees - markers, pipes and escapes are not counted. */
export function wordCountOf(src: string): number {
  const m = plainText(src).match(/[^\s|]+/g);
  return m ? m.filter((w) => /[\p{L}\p{N}]/u.test(w)).length : 0;
}

/** True when the text uses any structure beyond plain paragraphs. */
export function hasFormatting(src: string): boolean {
  const blocks = parseMarkdown(src);
  return blocks.some((b) => b.kind !== "paragraph" || b.content.some((n) => n.kind === "text" && (n.bold || n.italic)));
}

/** One-line preview of the visible text. */
export function previewText(src: string, words = 6): string {
  const all = plainText(src).trim().split(/\s+/).filter(Boolean);
  const head = all.slice(0, words).join(" ");
  return all.length > words ? `${head}…` : head;
}

/* ------------------------------------------------------------------------------------ editor (ProseMirror) */

export interface PMNode {
  type: string;
  attrs?: Record<string, unknown>;
  content?: PMNode[];
  text?: string;
  marks?: { type: string }[];
}

function inlineToPM(content: Inline[]): PMNode[] {
  return content.flatMap<PMNode>((n) => {
    if (n.kind === "break") return [{ type: "hardBreak" }];
    if (!n.text) return [];
    const marks = [...(n.bold ? [{ type: "bold" }] : []), ...(n.italic ? [{ type: "italic" }] : [])];
    return [{ type: "text", text: n.text, ...(marks.length ? { marks } : {}) }];
  });
}

const para = (content: Inline[]): PMNode => {
  const c = inlineToPM(content);
  return c.length ? { type: "paragraph", content: c } : { type: "paragraph" };
};

function blockToPM(block: Block): PMNode {
  switch (block.kind) {
    case "paragraph": return para(block.content);
    case "heading": return { type: "heading", attrs: { level: block.level }, content: inlineToPM(block.content) };
    case "list": return {
      type: block.ordered ? "orderedList" : "bulletList",
      ...(block.ordered ? { attrs: { start: block.start } } : {}),
      content: block.items.map((it) => ({ type: "listItem", content: [para(it.content), ...it.children.map(blockToPM)] })),
    };
    case "table": return {
      type: "table",
      content: [
        { type: "tableRow", content: block.header.map((c) => ({ type: "tableHeader", content: [para(c)] })) },
        ...block.rows.map((r) => ({ type: "tableRow", content: r.map((c) => ({ type: "tableCell", content: [para(c)] })) })),
      ],
    };
  }
}

export function markdownToDoc(src: string): PMNode {
  const content = parseMarkdown(src).map(blockToPM);
  return { type: "doc", content: content.length ? content : [{ type: "paragraph" }] };
}

function pmInline(nodes: PMNode[] | undefined): Inline[] {
  const out: Inline[] = [];
  for (const n of nodes ?? []) {
    if (n.type === "text" && n.text) {
      const marks = new Set((n.marks ?? []).map((m) => m.type));
      out.push({ kind: "text", text: n.text, ...(marks.has("bold") ? { bold: true } : {}), ...(marks.has("italic") ? { italic: true } : {}) });
    } else if (n.type === "hardBreak") out.push({ kind: "break" });
    else if (n.content) out.push(...pmInline(n.content));
  }
  return out;
}

/** Flatten any block content (e.g. paragraphs inside a table cell) into inline content. */
function pmFlat(nodes: PMNode[] | undefined, sep: Inline = { kind: "text", text: " " }): Inline[] {
  const out: Inline[] = [];
  (nodes ?? []).forEach((n, idx) => {
    if (idx > 0) out.push(sep);
    out.push(...(n.type === "paragraph" || n.type === "heading" ? pmInline(n.content) : pmFlat(n.content)));
  });
  return out;
}

function pmBlock(n: PMNode): Block | null {
  switch (n.type) {
    case "paragraph": return { kind: "paragraph", content: pmInline(n.content) };
    case "heading": return { kind: "heading", level: Number(n.attrs?.level) >= 4 ? 4 : 3, content: pmInline(n.content) };
    case "bulletList": case "orderedList": return {
      kind: "list", ordered: n.type === "orderedList", start: Number(n.attrs?.start ?? 1) || 1,
      items: (n.content ?? []).map((li) => {
        const kids = li.content ?? [];
        const textual = kids.filter((k) => k.type === "paragraph" || k.type === "heading");
        const lists = kids.filter((k) => k.type === "bulletList" || k.type === "orderedList");
        return { content: pmFlat(textual, { kind: "break" }), children: lists.map(pmBlock).filter((b): b is Block => b !== null) };
      }),
    };
    case "table": {
      const rows = (n.content ?? []).map((r) => (r.content ?? []).map((c) => pmFlat(c.content)));
      if (!rows.length) return null;
      return { kind: "table", header: rows[0], rows: rows.slice(1) };
    }
    default: return n.content ? { kind: "paragraph", content: pmFlat(n.content) } : null;
  }
}

export function docToMarkdown(doc: PMNode): string {
  return serializeMarkdown((doc.content ?? []).map(pmBlock).filter((b): b is Block => b !== null));
}
