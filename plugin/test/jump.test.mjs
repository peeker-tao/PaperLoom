/**
 * Unit tests for `jumpToPage`.
 *
 * The regressions these pin down:
 *
 *  1. The old implementation tried `reader.navigate()` first. That call only
 *     posts a message to the reader iframe, so it never throws — the function
 *     returned `true` unconditionally and the reliable pdf.js path underneath it
 *     was never reached. "在 PDF 中查看" did nothing while the sidebar reported
 *     success.
 *  2. Returning `true` because a function returned is not the same as a scroll
 *     that happened. The result is now verified against the viewer's state, so a
 *     refused jump is reported as a failure and is not saved as the reading
 *     position.
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
function readerWithPdfJs(onSet, extra = {}) {
  const viewer = { _page: 1 };
  Object.defineProperty(viewer, "currentPageNumber", {
    get: () => viewer._page,
    set: (value) => {
      viewer._page = value;
      onSet?.(value);
    },
  });
  return {
    ...extra,
    navigate: () => {
      throw new Error("navigate must not be reached when pdf.js works");
    },
    _iframeWindow: { PDFViewerApplication: { pdfViewer: viewer } },
  };
}

await test("uses pdf.js, not reader.navigate", async () => {
  const seen = [];
  const reader = readerWithPdfJs((value) => seen.push(value));
  const result = await jumpToPage(reader, 7);
  assert.equal(result.ok, true);
  assert.equal(result.level, "page");
  assert.equal(result.via, "pdfjs");
  // 1-based page -> 1-based currentPageNumber; the getter confirms it stuck.
  assert.deepEqual(seen, [7]);
});

await test("converts a 1-based page to a 0-based pageIndex", async () => {
  const calls = [];
  const reader = {
    state: { pageIndex: 3 },
    navigate: (options) => {
      calls.push(options);
      return Promise.resolve();
    },
  };
  // The reader reports pageIndex 3, so the jump is verified as landed.
  const result = await jumpToPage(reader, 4);
  assert.equal(result.ok, true);
  assert.equal(result.via, "reader.navigate");
  assert.deepEqual(calls, [{ pageIndex: 3 }]);
});

await test("awaits an async navigate before reporting success", async () => {
  let settled = false;
  const reader = {
    state: { pageIndex: 0 },
    navigate: () =>
      new Promise((resolve) => {
        setTimeout(() => {
          settled = true;
          reader.state.pageIndex = 1;
          resolve();
        }, 5);
      }),
  };
  const result = await jumpToPage(reader, 2);
  assert.equal(result.ok, true);
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
        isConnected: true,
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
  const result = await jumpToPage(reader, 3);
  assert.equal(result.ok, true);
  assert.equal(result.via, "pdfjs+scrollIntoView");
  assert.equal(scrolled, true);
});

await test("reports failure instead of pretending", async () => {
  const empty = await jumpToPage({}, 5);
  assert.equal(empty.ok, false);
  assert.equal(empty.level, "none");
  assert.match(empty.reason, /第 1 页/);

  const dead = await jumpToPage({ state: { pageIndex: 0 }, navigate: () => undefined }, 5);
  assert.equal(dead.ok, false);

  const nullReader = await jumpToPage(null, 5);
  assert.equal(nullReader.ok, false);

  const throwing = await jumpToPage(
    {
      state: { pageIndex: 0 },
      navigate: () => {
        throw new Error("nope");
      },
    },
    5,
  );
  assert.equal(throwing.ok, false);
});

await test("a navigate that resolves without moving is not a success", async () => {
  // Exactly the shape of the old bug: the call returns, nothing scrolls.
  let calls = 0;
  const reader = {
    state: { pageIndex: 0 },
    navigate: () => {
      calls += 1;
      return Promise.resolve();
    },
  };
  const result = await jumpToPage(reader, 9);
  assert.equal(calls >= 1, true);
  assert.equal(result.ok, false);
  assert.equal(result.page, 9);
});

await test("a region is only claimed when it was scrolled to", async () => {
  const scroller = { clientHeight: 800, scrollTop: 0 };
  const pageView = {
    div: { isConnected: true, parentElement: scroller },
    viewport: { convertToViewportRectangle: () => [0, 400, 100, 460] },
  };
  const viewer = { _page: 1 };
  Object.defineProperty(viewer, "currentPageNumber", {
    get: () => viewer._page,
    set: (value) => {
      viewer._page = value;
    },
  });
  viewer.getPageView = () => pageView;
  const reader = {
    _iframeWindow: { PDFViewerApplication: { pdfViewer: viewer } },
    navigate: () => {
      throw new Error("unused");
    },
  };
  const result = await jumpToPage(reader, 2, [10, 700, 200, 740]);
  assert.equal(result.ok, true);
  assert.equal(result.level, "region");
  assert.equal(result.via, "pdfjs+region");
  // 400 - 800*0.25 = 200: the region sits a quarter down the viewport.
  assert.equal(scroller.scrollTop, 200);
});

rmSync(outDir, { recursive: true, force: true });

if (failures) {
  console.error(`\n${failures} jump test(s) failed`);
  process.exit(1);
}
console.log("\nall jumpToPage tests passed");
