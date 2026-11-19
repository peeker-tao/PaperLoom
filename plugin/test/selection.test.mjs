/**
 * Reading a selection made inside the sidebar.
 *
 * This exists because selecting a paragraph in the reading view did nothing at
 * all: the only handlers read the *reader's* document, which cannot see a
 * selection made inside the sidebar's shadow root. The rules below decide when a
 * toolbar appears, so the false positives (a click, a selection inside the
 * composer, punctuation only) matter as much as the happy path.
 */
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import esbuild from "esbuild";

const outDir = mkdtempSync(join(tmpdir(), "paperloom-sel-"));
const bundle = join(outDir, "text-selection.mjs");
await esbuild.build({
  entryPoints: [
    new URL("../src/ui/text-selection.ts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  ],
  bundle: true,
  format: "esm",
  platform: "neutral",
  outfile: bundle,
  logLevel: "silent",
});
const { clampSelectionText, isEditableNode, segmentIdOf, readSelectionFrom, shadowSelection, MAX_SELECTION_CHARS } =
  await import(pathToFileURL(bundle).href);

let failures = 0;
function test(name, fn) {
  try {
    fn();
    console.log(`ok   ${name}`);
  } catch (error) {
    failures += 1;
    console.error(`FAIL ${name}\n     ${error.message}`);
  }
}

/** A minimal node: just enough for the ancestor walk. */
function node(props = {}) {
  return { tagName: "DIV", parentNode: null, ...props };
}

function selection(text, extra = {}) {
  return {
    isCollapsed: false,
    rangeCount: 1,
    toString: () => text,
    anchorNode: null,
    getRangeAt: () => ({ getBoundingClientRect: () => ({ top: 100, bottom: 120, left: 20, right: 200 }) }),
    ...extra,
  };
}

test("whitespace is flattened so a paragraph wraps into one line", () => {
  assert.equal(clampSelectionText("  a\n\n b\tc  "), "a b c");
});

test("a very long selection is truncated with an ellipsis", () => {
  const long = "x".repeat(MAX_SELECTION_CHARS + 50);
  const out = clampSelectionText(long);
  assert.equal(out.length, MAX_SELECTION_CHARS + 1);
  assert.ok(out.endsWith("…"));
});

test("a normal selection is returned as-is", () => {
  assert.equal(clampSelectionText("diffusion models"), "diffusion models");
});

test("a collapsed selection is ignored", () => {
  assert.equal(readSelectionFrom(selection("hello", { isCollapsed: true })), null);
});

test("a selection with no ranges is ignored", () => {
  assert.equal(readSelectionFrom(selection("hello", { rangeCount: 0 })), null);
});

test("one character is treated as an accidental click", () => {
  assert.equal(readSelectionFrom(selection("a")), null);
});

test("punctuation only does not open a toolbar", () => {
  assert.equal(readSelectionFrom(selection("—— 。")), null);
});

test("text with letters is accepted, including CJK", () => {
  const hit = readSelectionFrom(selection("扩散模型"));
  assert.equal(hit.text, "扩散模型");
});

test("a selection inside a textarea is ignored", () => {
  const area = node({ tagName: "TEXTAREA" });
  assert.equal(readSelectionFrom(selection("hello there", { anchorNode: area })), null);
});

test("a selection inside a contenteditable is ignored", () => {
  const editable = node({ isContentEditable: true });
  assert.equal(readSelectionFrom(selection("hello there", { anchorNode: editable })), null);
});

test("a selection in ordinary text is accepted", () => {
  const para = node();
  const hit = readSelectionFrom(selection("masked diffusion", { anchorNode: para }));
  assert.equal(hit.text, "masked diffusion");
});

test("the segment id comes from the nearest ancestor that has one", () => {
  const outer = node({ dataset: { segmentId: "p3-s7" } });
  const inner = node({ tagName: "SPAN", parentNode: outer });
  assert.equal(segmentIdOf(inner), "p3-s7");
});

test("a direct data-segment-id on the node itself wins", () => {
  const own = node({ dataset: { segmentId: "p1-s0" }, parentNode: node({ dataset: { segmentId: "out" } }) });
  assert.equal(segmentIdOf(own), "p1-s0");
});

test("no ancestor with a segment id yields null", () => {
  assert.equal(segmentIdOf(node({ parentNode: node() })), null);
});

test("the walk crosses a shadow boundary through host", () => {
  const host = node({ dataset: { segmentId: "p9-s1" } });
  const inner = node({ parentNode: null, host });
  assert.equal(segmentIdOf(inner), "p9-s1");
});

test("a cyclic parent chain terminates instead of hanging", () => {
  const loop = node();
  loop.parentNode = loop;
  assert.equal(segmentIdOf(loop), null);
});

test("the bounding rect is reported for placing the toolbar", () => {
  const hit = readSelectionFrom(selection("some text"));
  assert.deepEqual(hit.rect, { top: 100, bottom: 120, left: 20, right: 200 });
});

test("a range that throws still yields a hit, without a rect", () => {
  const hit = readSelectionFrom(
    selection("some text", {
      getRangeAt: () => {
        throw new Error("stale range");
      },
    }),
  );
  assert.equal(hit.text, "some text");
  assert.equal(hit.rect, null);
});

test("null input is handled", () => {
  assert.equal(readSelectionFrom(null), null);
  assert.equal(readSelectionFrom(undefined), null);
});

test("isEditableNode looks through wrappers", () => {
  const area = node({ tagName: "INPUT" });
  const wrapper = node({ tagName: "DIV", parentNode: area });
  assert.equal(isEditableNode(wrapper), true);
  assert.equal(isEditableNode(node()), false);
});

test("a shadow selection resolves through getComposedRanges", () => {
  const host = node({ tagName: "DIV", parentNode: null });
  const paragraph = node({ parentNode: host, dataset: { segmentId: "p2-s3" } });
  const text = node({ tagName: "#text", parentNode: paragraph });
  const selection = {
    isCollapsed: false,
    rangeCount: 1,
    toString: () => "modality invariant matching",
    // Gecko retargets these to the host; the composed range gives the real node.
    anchorNode: host,
    getRangeAt: () => ({ getBoundingClientRect: () => ({ top: 100, left: 20, bottom: 120, right: 200 }) }),
    getComposedRanges: () => [
      {
        startContainer: text,
        getBoundingClientRect: () => ({ top: 100, left: 20, bottom: 120, right: 200 }),
      },
    ],
  };
  const root = { host, ownerDocument: { getSelection: () => selection } };
  const hit = shadowSelection(root, host);
  assert.equal(hit.text, "modality invariant matching");
  assert.equal(hit.segmentId, "p2-s3");
  assert.equal(hit.rect.top, 100);
});

test("a selection outside the overlay is ignored", () => {
  // The PDF's own text layer: Zotero already offers a popup there.
  const host = node({ tagName: "DIV", parentNode: null });
  const pdfText = node({ tagName: "#text", parentNode: node({ parentNode: null }) });
  const selection = {
    isCollapsed: false,
    rangeCount: 1,
    toString: () => "text from the pdf",
    anchorNode: pdfText,
    getRangeAt: () => ({ getBoundingClientRect: () => ({ top: 1, left: 1 }) }),
    getComposedRanges: () => [{ startContainer: pdfText }],
  };
  const root = { host, ownerDocument: { getSelection: () => selection } };
  assert.equal(shadowSelection(root, host), null);
});

test("without getComposedRanges the retargeted host still counts as ours", () => {
  // Older engines report only the host; the text is still usable, the segment is not.
  const host = node({ tagName: "DIV", parentNode: null });
  const selection = {
    isCollapsed: false,
    rangeCount: 1,
    toString: () => "selected words",
    anchorNode: host,
    getRangeAt: () => ({ getBoundingClientRect: () => ({ top: 40, left: 10 }) }),
  };
  const root = { host, ownerDocument: { getSelection: () => selection } };
  const hit = shadowSelection(root, host);
  assert.equal(hit.text, "selected words");
  assert.equal(hit.segmentId, null);
});

test("a collapsed selection never opens the toolbar", () => {
  const host = node({ tagName: "DIV", parentNode: null });
  const selection = {
    isCollapsed: true,
    rangeCount: 1,
    toString: () => "",
    anchorNode: host,
    getRangeAt: () => ({ getBoundingClientRect: () => ({ top: 1, left: 1 }) }),
  };
  const root = { host, ownerDocument: { getSelection: () => selection } };
  assert.equal(shadowSelection(root, host), null);
});

test("no selection at all is handled", () => {
  const host = node({ tagName: "DIV", parentNode: null });
  const root = { host, ownerDocument: { getSelection: () => null } };
  assert.equal(shadowSelection(root, host), null);
  assert.equal(shadowSelection(null, null), null);
});

if (failures) {
  console.error(`\n${failures} selection test(s) failed`);
  process.exit(1);
}
console.log("\nall selection tests passed");
