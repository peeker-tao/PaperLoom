/**
 * Unit tests for `jumpToPage`.
 *
 * The regression these pin down: the old implementation tried
 * `reader.navigate()` first. That call only posts a message to the reader
 * iframe, so it never throws — the function returned `true` unconditionally and
 * the reliable pdf.js path underneath it was never reached. "在 PDF 中查看"
 * therefore did nothing while the sidebar reported success.
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import esbuild from "esbuild";

const outDir = mkdtempSync(join(tmpdir(), "paperloom-jump-"));
const bundle = join(outDir, "api.mjs");
await esbuild.build({
  entryPoints: [
    new URL("../src/zotero/api.ts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  ],
  bundle: true,
  format: "esm",
  platform: "neutral",
  outfile: bundle,
  logLevel: "silent",
});
const { jumpToPage } = await import(pathToFileURL(bundle).href);

let failures = 0;
async function test(name, fn) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (error) {
    failures += 1;
    console.error(`FAIL ${name}\n     ${error.message}`);
  }
}

/** A reader whose pdf.js viewer accepts page numbers. */
function readerWithPdfJs(onSet) {
  const viewer = {
    currentPageNumber: 1,
  };
  Object.defineProperty(viewer, "currentPageNumber", {
    get: () => viewer._page,
    set: (value) => {
      viewer._page = value;
      onSet?.(value);
    },
  });
  viewer._page = 1;
  return {
    navigate: () => {
      throw new Error("navigate must not be reached when pdf.js works");
    },
    _iframeWindow: { PDFViewerApplication: { pdfViewer: viewer } },
  };
}

await test("uses pdf.js, not reader.navigate", async () => {
  const seen = [];
  const reader = readerWithPdfJs((value) => seen.push(value));
  const moved = await jumpToPage(reader, 7);
  assert.equal(moved, true);
  // 1-based page -> 1-based currentPageNumber; the getter confirms it stuck.
  assert.deepEqual(seen, [7]);
});

await test("converts a 1-based page to a 0-based pageIndex", async () => {
  const calls = [];
  const reader = {
    navigate: (options) => {
      calls.push(options);
      return Promise.resolve();
    },
  };
  const moved = await jumpToPage(reader, 4);
  assert.equal(moved, true);
  assert.deepEqual(calls, [{ pageIndex: 3 }]);
});

await test("awaits an async navigate before reporting success", async () => {
  let settled = false;
  const reader = {
    navigate: () =>
      new Promise((resolve) => {
        setTimeout(() => {
          settled = true;
          resolve();
        }, 5);
      }),
  };
  const moved = await jumpToPage(reader, 2);
  assert.equal(moved, true);
  assert.equal(settled, true);
});

await test("falls back to scrollIntoView when the viewer refuses the page", async () => {
  let scrolled = false;
  const viewer = {
    // A viewer that ignores the assignment (page not laid out yet).
    get currentPageNumber() {
      return 1;
    },
    set currentPageNumber(_value) {
      // no-op
    },
    getPageView: () => ({
      div: {
        scrollIntoView: () => {
          scrolled = true;
        },
      },
    }),
  };
  const reader = {
    navigate: () => {
      throw new Error("navigate must not be reached");
    },
    _iframeWindow: { PDFViewerApplication: { pdfViewer: viewer } },
  };
  const moved = await jumpToPage(reader, 3);
  assert.equal(moved, true);
  assert.equal(scrolled, true);
});

await test("reports failure instead of pretending", async () => {
  assert.equal(await jumpToPage({}, 5), false);
  assert.equal(await jumpToPage({ navigate: () => undefined }, 5), false);
  assert.equal(await jumpToPage(null, 5), false);
  assert.equal(
    await jumpToPage(
      {
        navigate: () => {
          throw new Error("nope");
        },
      },
      5,
    ),
    false,
  );
});

rmSync(outDir, { recursive: true, force: true });

if (failures) {
  console.error(`\n${failures} jump test(s) failed`);
  process.exit(1);
}
console.log("\nall jumpToPage tests passed");
