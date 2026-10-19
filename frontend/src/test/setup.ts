import "@testing-library/jest-dom/vitest";

// jsdom has no layout engine. ProseMirror (the rich-text editor) measures ranges to scroll the selection into view;
// these zero-size stand-ins let it run. They affect measurement only, never document content.
const emptyRect = { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, toJSON: () => ({}) } as DOMRect;
const emptyList = Object.assign([] as DOMRect[], { item: () => null }) as unknown as DOMRectList;
if (typeof Range !== "undefined") {
  Range.prototype.getBoundingClientRect = () => emptyRect;
  Range.prototype.getClientRects = () => emptyList;
}
if (typeof document !== "undefined" && !document.elementFromPoint) {
  document.elementFromPoint = () => null;
}
