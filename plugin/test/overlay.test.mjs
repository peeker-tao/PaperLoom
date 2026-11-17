/**
 * Unit tests for the overlay geometry used by the bilingual view.
 *
 * The module is TypeScript and has no runtime dependencies, so it is bundled
 * with the project's own esbuild and imported from a temp file. Run with
 * `npm run test:unit` (also part of CI).
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import esbuild from "esbuild";

const outDir = mkdtempSync(join(tmpdir(), "paperloom-overlay-"));
const bundle = join(outDir, "overlay.mjs");
await esbuild.build({
  entryPoints: [new URL("../src/ui/overlay.ts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")],
  bundle: true,
  format: "esm",
  platform: "neutral",
  outfile: bundle,
  logLevel: "silent",
});
const { overlayGeometry, fitPage, MIN_OVERLAY_WIDTH, MIN_OVERLAY_HEIGHT } = await import(
  pathToFileURL(bundle).href
);

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

// A US Letter page rendered into a 612px-wide column: 1 PDF point == 1 px.
const page = {
  width: 612,
  height: 792,
  pageWidth: 612,
  pageHeight: 792,
  rotation: 0,
};

test("keeps x and flips y for an axis-aligned box", () => {
  // Box in the top-left corner of the page: y near the top in PDF space.
  const box = overlayGeometry({ bbox: [72, 700, 300, 720] }, page);
  assert.ok(box);
  assert.equal(box.left, 72);
  // top = pageHeight - y1 = 792 - 720 = 72
  assert.equal(box.top, 72);
  assert.equal(box.width, 228);
  assert.equal(box.height, 20);
});

test("scales with the rendered width", () => {
  const half = { ...page, width: 306, height: 396 };
  const box = overlayGeometry({ bbox: [72, 700, 300, 720] }, half);
  assert.ok(box);
  assert.equal(box.left, 36);
  assert.equal(box.top, 36);
  assert.equal(box.width, 114);
  assert.equal(box.height, 10);
});

test("font size follows the box height and stays readable", () => {
  const tall = overlayGeometry({ bbox: [72, 100, 500, 160] }, page);
  const short = overlayGeometry({ bbox: [72, 100, 500, 110] }, page);
  assert.ok(tall && short);
  assert.ok(tall.fontSize <= 14 && tall.fontSize >= 5.5);
  assert.ok(short.fontSize >= 5.5);
  assert.ok(tall.fontSize > short.fontSize);
});

test("rejects boxes too small for text", () => {
  const tiny = overlayGeometry(
    { bbox: [100, 100, 100 + MIN_OVERLAY_WIDTH / 2, 100 + MIN_OVERLAY_HEIGHT / 2] },
    page,
  );
  assert.equal(tiny, null);
  const oneChar = overlayGeometry({ bbox: [100, 100, 103, 110] }, page);
  assert.equal(oneChar, null);
});

test("rejects inverted and malformed boxes", () => {
  assert.equal(overlayGeometry({ bbox: [300, 700, 72, 720] }, page), null);
  assert.equal(overlayGeometry({ bbox: [72, 720, 300, 700] }, page), null);
  assert.equal(overlayGeometry({ bbox: [72, 700] }, page), null);
  assert.equal(overlayGeometry({ bbox: [] }, page), null);
});

test("rejects rotated pages", () => {
  assert.equal(overlayGeometry({ bbox: [72, 700, 300, 720] }, { ...page, rotation: 90 }), null);
  assert.equal(overlayGeometry({ bbox: [72, 700, 300, 720] }, { ...page, rotation: 270 }), null);
});

test("rejects boxes outside the page", () => {
  assert.equal(overlayGeometry({ bbox: [-40, 700, 300, 720] }, page), null);
  assert.equal(overlayGeometry({ bbox: [72, 900, 300, 950] }, page), null);
});

test("fitPage keeps the aspect ratio", () => {
  assert.deepEqual(fitPage(page, 400), { width: 400, height: (792 / 612) * 400 });
  // A5-ish page in a narrow column.
  const tall = fitPage({ ...page, pageWidth: 400, pageHeight: 560 }, 200);
  assert.equal(tall.width, 200);
  assert.equal(tall.height, 280);
});

rmSync(outDir, { recursive: true, force: true });

if (failures) {
  console.error(`\n${failures} test(s) failed`);
  process.exit(1);
}
console.log("\nall overlay geometry tests passed");
