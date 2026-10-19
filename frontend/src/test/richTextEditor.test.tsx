// The rich-text editor in jsdom: real TipTap/ProseMirror, no mocks. Selections are set through the editor instance
// (jsdom has no layout for mouse selection); every formatting change goes through the visible toolbar buttons.
import type { Editor } from "@tiptap/react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { RichTextEditor, type EditorFeatures } from "@/components/editor/RichTextEditor";
import { RichText } from "@/components/RichText";

function Harness({ initial = "", features = "full", onValue }: { initial?: string; features?: EditorFeatures; onValue?: (v: string) => void }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <span id="ed-label">Answer</span>
      <RichTextEditor id="ed" value={value} features={features} showWordCount
        onChange={(v) => { setValue(v); onValue?.(v); }} onReady={(e) => { (window as unknown as { __ed: Editor }).__ed = e; }} />
      <output data-testid="value">{value}</output>
    </>
  );
}
const ed = () => (window as unknown as { __ed: Editor }).__ed;
const value = () => screen.getByTestId("value").textContent;

describe("rich-text editor", () => {
  it("loads legacy plain text unchanged and labels the editable area", () => {
    render(<Harness initial={"Line one\nLine two\n\nSecond paragraph"} />);
    const box = screen.getByRole("textbox", { name: "Answer" });
    expect(box).toHaveAttribute("aria-multiline", "true");
    expect(box.querySelectorAll("p")).toHaveLength(2);
    expect(box.querySelector("br")).not.toBeNull();
    expect(screen.getByText("6 words")).toBeInTheDocument();
  });

  it("applies bold, italic, heading and lists from the toolbar and serializes them", async () => {
    const user = userEvent.setup();
    render(<Harness initial="Tokenization splits text" />);
    act(() => { ed().commands.setTextSelection({ from: 1, to: 13 }); });
    await user.click(screen.getByRole("button", { name: /^Bold/ }));
    expect(value()).toBe("**Tokenization** splits text");
    expect(screen.getByRole("button", { name: /^Bold/ })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: /^Italic/ }));
    expect(value()).toBe("***Tokenization*** splits text");

    await user.click(screen.getByRole("button", { name: /^Bulleted list/ }));
    expect(value()).toBe("- ***Tokenization*** splits text");
    await user.click(screen.getByRole("button", { name: /^Bulleted list/ }));
    await user.click(screen.getByRole("button", { name: /^Numbered list/ }));
    expect(value()).toBe("1. ***Tokenization*** splits text");
    await user.click(screen.getByRole("button", { name: /^Numbered list/ }));

    await user.click(screen.getByRole("button", { name: "Section heading" }));
    expect(value()).toBe("### ***Tokenization*** splits text");

    await user.click(screen.getByRole("button", { name: "Clear formatting" }));
    expect(value()).toBe("Tokenization splits text");
  });

  it("indents and outdents list items", async () => {
    const user = userEvent.setup();
    render(<Harness initial={"- one\n- two"} />);
    const pos = ed().state.doc.textContent.indexOf("two");
    act(() => { ed().commands.setTextSelection(pos + 6); }); // inside the second item
    expect(screen.getByRole("button", { name: /^Indent list item/ })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: /^Indent list item/ }));
    expect(value()).toBe("- one\n  - two");
    await user.click(screen.getByRole("button", { name: /^Outdent list item/ }));
    expect(value()).toBe("- one\n- two");
  });

  it("creates tables and adds and removes rows and columns", async () => {
    const user = userEvent.setup();
    render(<Harness initial="" />);
    act(() => { ed().commands.focus(); });
    await user.click(screen.getByRole("button", { name: "Insert table" }));
    expect(value()).toBe("|  |  |\n| --- | --- |\n|  |  |\n|  |  |");
    act(() => { ed().commands.insertContent("Unit"); });
    expect(value()?.split("\n")[0]).toBe("| Unit |  |");
    await user.click(screen.getByRole("button", { name: "Add column right" }));
    expect(value()!.split("\n")[0].split("|").length - 2).toBe(3);
    await user.click(screen.getByRole("button", { name: "Delete column" }));
    expect(value()!.split("\n")[0].split("|").length - 2).toBe(2);
    await user.click(screen.getByRole("button", { name: "Add row below" }));
    expect(value()?.split("\n")).toHaveLength(5);
    await user.click(screen.getByRole("button", { name: "Delete table" }));
    expect(value()).toBe("");
    expect(screen.getByRole("button", { name: "Insert table" })).toBeInTheDocument();
  });

  it("undoes and redoes", async () => {
    const user = userEvent.setup();
    render(<Harness initial="abc" />);
    act(() => { ed().commands.setTextSelection({ from: 1, to: 4 }); });
    await user.click(screen.getByRole("button", { name: /^Bold/ }));
    expect(value()).toBe("**abc**");
    await user.click(screen.getByRole("button", { name: /^Undo/ }));
    expect(value()).toBe("abc");
    await user.click(screen.getByRole("button", { name: /^Redo/ }));
    expect(value()).toBe("**abc**");
  });

  it("sanitizes pasted HTML down to the supported structure", () => {
    render(<Harness initial="" />);
    act(() => {
      ed().view.pasteHTML(
        '<h1 style="color:red">Title</h1><p onclick="steal()">Hello <b>bold</b> <a href="javascript:alert(1)">link</a></p>' +
        '<script>alert(1)</script><img src=x onerror="alert(1)"><ul><li>item</li></ul>' +
        "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>",
        new Event("paste") as ClipboardEvent, // jsdom has no ClipboardEvent constructor
      );
    });
    const md = value() ?? "";
    expect(md).not.toMatch(/script|onerror|onclick|javascript|<|style/i);
    expect(md).toContain("**bold**");
    expect(md).toContain("link");
    expect(md).toContain("- item");
    expect(md).toContain("| A | B |");
    const box = screen.getByRole("textbox", { name: "Answer" });
    // TipTap's own table width style is allowed; nothing from the pasted markup may survive
    expect(box.querySelector('script, img, a, [onclick], [onerror], [style*="color"]')).toBeNull();
  });

  it("offers only the configured tools", () => {
    render(<Harness features="basic" />);
    expect(screen.getByRole("toolbar", { name: "Formatting" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Bulleted list/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Insert table" })).not.toBeInTheDocument();
  });

  it("moves through the toolbar with arrow keys as one tab stop", async () => {
    const user = userEvent.setup();
    render(<Harness initial="abc" />);
    const buttons = screen.getByRole("toolbar").querySelectorAll<HTMLButtonElement>("button[tabindex='0']");
    expect(buttons).toHaveLength(1);
    buttons[0].focus();
    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toHaveAttribute("tabindex", "0");
    expect(document.activeElement).not.toBe(buttons[0]);
  });

  it("replaces content when the value changes from outside (e.g. a generated answer)", () => {
    function Outer() {
      const [v, setV] = useState("old");
      return (<>
        <span id="x-label">X</span>
        <RichTextEditor id="x" value={v} onChange={setV} />
        <button type="button" onClick={() => setV("- new\n- list")}>replace</button>
      </>);
    }
    render(<Outer />);
    act(() => { screen.getByText("replace").click(); });
    expect(screen.getByRole("textbox", { name: "X" }).querySelectorAll("li")).toHaveLength(2);
  });
});

describe("rich text display", () => {
  it("renders the stored structure without HTML injection", () => {
    const { container } = render(<RichText text={"### Title\n\n**b** <script>x</script>\n\n| A |\n| --- |\n| 1 |"} />);
    expect(container.querySelector("h3")).toHaveTextContent("Title");
    expect(container.querySelector("strong")).toHaveTextContent("b");
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>x</script>");
    expect(container.querySelector("th")).toHaveTextContent("A");
  });
});
