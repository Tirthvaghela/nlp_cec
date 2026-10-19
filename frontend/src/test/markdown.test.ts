import {
  docToMarkdown, hasFormatting, markdownToDoc, normalizeMarkdown, parseMarkdown, plainText, previewText, serializeMarkdown, wordCountOf,
} from "@/lib/markdown";

const roundTrip = (md: string) => docToMarkdown(markdownToDoc(md));

describe("Margin Markdown subset", () => {
  it("keeps legacy plain-text answers unchanged, including single line breaks", () => {
    const legacy = "Tokenization splits text into tokens.\nIt is the first step.\n\nA second paragraph.";
    expect(roundTrip(legacy)).toBe(legacy);
    expect(plainText(legacy)).toBe("Tokenization splits text into tokens.\nIt is the first step.\n\nA second paragraph.");
  });

  it("round-trips headings, emphasis, nested lists and tables through the editor document", () => {
    const md = [
      "### Definition",
      "**Tokenization** splits *raw* text into ***tokens***.",
      "- Words\n- Subwords\n  - BPE\n  - WordPiece\n- Characters",
      "1. Normalise\n2. Split\n3. Map to ids",
      "| Unit | Example |\n| --- | --- |\n| Word | cat |\n| Subword | un-, -able |",
    ].join("\n\n");
    expect(roundTrip(md)).toBe(md);
    const blocks = parseMarkdown(md);
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "paragraph", "list", "list", "table"]);
    const list = blocks[2] as Extract<(typeof blocks)[number], { kind: "list" }>;
    expect(list.items[1].children[0]).toMatchObject({ kind: "list", ordered: false });
  });

  it("escapes characters that would otherwise change the structure on reload", () => {
    const doc = {
      type: "doc", content: [
        { type: "paragraph", content: [{ type: "text", text: "# not a heading, 2 * 3 = 6, a|b and C:\\path" }] },
        { type: "paragraph", content: [{ type: "text", text: "1. not a list" }] },
        { type: "paragraph", content: [{ type: "text", text: "- not a bullet" }] },
      ],
    };
    const md = docToMarkdown(doc);
    const back = markdownToDoc(md);
    expect(back.content!.map((n) => n.type)).toEqual(["paragraph", "paragraph", "paragraph"]);
    expect(plainText(md)).toBe("# not a heading, 2 * 3 = 6, a|b and C:\\path\n\n1. not a list\n\n- not a bullet");
  });

  it("escapes pipes inside table cells", () => {
    const md = "| A | B |\n| --- | --- |\n| x \\| y | z |";
    expect(roundTrip(md)).toBe(md);
    expect(plainText(md)).toContain("x | y");
  });

  it("treats unmatched markers as literal text", () => {
    expect(plainText("5 * 3 and *open")).toBe("5 * 3 and *open");
    expect(hasFormatting("5 * 3 and *open")).toBe(false);
  });

  it("counts visible words only, never markup", () => {
    expect(wordCountOf("**Bold** and *italic* words")).toBe(4);
    expect(wordCountOf("| Unit | Example |\n| --- | --- |\n| Word | cat |")).toBe(4);
    expect(wordCountOf("- one\n- two\n  - three")).toBe(3);
    expect(wordCountOf("   ")).toBe(0);
  });

  it("normalizes equivalent text to one canonical form", () => {
    expect(normalizeMarkdown("* a\n* b")).toBe("- a\n- b");
    expect(normalizeMarkdown("# Title")).toBe("### Title");
    expect(normalizeMarkdown("\n\nText  \n\n\n")).toBe("Text");
  });

  it("drops empty paragraphs and produces an empty string for an empty document", () => {
    expect(docToMarkdown({ type: "doc", content: [{ type: "paragraph" }] })).toBe("");
    expect(serializeMarkdown([])).toBe("");
  });

  it("flattens block content inside table cells instead of losing it", () => {
    const doc = {
      type: "doc", content: [{
        type: "table", content: [
          { type: "tableRow", content: [{ type: "tableHeader", content: [{ type: "paragraph", content: [{ type: "text", text: "H" }] }] }] },
          { type: "tableRow", content: [{ type: "tableCell", content: [
            { type: "paragraph", content: [{ type: "text", text: "line one" }] },
            { type: "paragraph", content: [{ type: "text", text: "line two" }] },
          ] }] },
        ],
      }],
    };
    expect(docToMarkdown(doc)).toBe("| H |\n| --- |\n| line one line two |");
  });

  it("previews the visible text", () => {
    expect(previewText("**Explain** tokenization in NLP and why it matters", 4)).toBe("Explain tokenization in NLP…");
  });
});
