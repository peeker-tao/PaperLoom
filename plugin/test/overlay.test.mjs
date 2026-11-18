/**
 * Unit tests for the bilingual-view overlay geometry and text layout.
 *
 * The module is TypeScript with no runtime dependencies, so it is bundled with
 * the project's own esbuild and imported from a temp file. Run with
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
  entryPoints: [
    new URL("../src/ui/overlay.ts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  ],
  bundle: true,
  format: "esm",
  platform: "neutral",
  outfile: bundle,
  logLevel: "silent",
});
const {
  overlayGeometry,
  fitPage,
  fitFontSize,
  wrapEstimated,
  MIN_OVERLAY_WIDTH,
  MIN_OVERLAY_HEIGHT,
} = await import(pathToFileURL(bundle).href);

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
const ZH =
  "摘要。近期文本到图像生成系统的进展在很大程度上由扩散模型驱动。然而，单阶段文本到图像扩散模型在计算效率和图像细节精修方面仍面临挑战。";

test("keeps x and flips y for an axis-aligned box", () => {
  const box = overlayGeometry({ bbox: [72, 700, 300, 720], translation: ZH }, page);
  assert.ok(box);
  assert.equal(box.left, 72);
  // top = pageHeight - y1 = 792 - 720 = 72
  assert.equal(box.top, 72);
  assert.equal(box.width, 228);
  assert.equal(box.height, 20);
});

test("scales with the rendered width", () => {
  const half = { ...page, width: 306, height: 396 };
  // Short text: a long translation would not fit into a half-size box and would
  // be rejected, which is the behaviour tested separately.
  const box = overlayGeometry({ bbox: [72, 700, 300, 720], translation: "扩散模型推动。" }, half);
  assert.ok(box);
  assert.equal(box.left, 36);
  assert.equal(box.top, 36);
  assert.equal(box.width, 114);
});

test("font size grows with the box until the text fills it", () => {
  const tall = overlayGeometry({ bbox: [72, 100, 500, 200], translation: ZH }, page);
  const short = overlayGeometry(
    { bbox: [72, 100, 500, 120], translation: "扩散模型推动。" },
    page,
  );
  assert.ok(tall && short);
  assert.ok(tall.fontSize >= short.fontSize);
  // The translation must fit inside the box: lines * size * lineHeight <= height.
  const block = tall.lines.length * tall.fontSize * tall.lineHeight;
  assert.ok(block <= tall.height + 0.5, `block ${block} > height ${tall.height}`);
});

test("rejects boxes too small for text", () => {
  const tiny = overlayGeometry(
    { bbox: [100, 100, 100 + MIN_OVERLAY_WIDTH / 2, 100 + MIN_OVERLAY_HEIGHT / 2], translation: ZH },
    page,
  );
  assert.equal(tiny, null);
});

test("rejects inverted and malformed boxes", () => {
  assert.equal(overlayGeometry({ bbox: [300, 700, 72, 720], translation: ZH }, page), null);
  assert.equal(overlayGeometry({ bbox: [72, 700] , translation: ZH }, page), null);
  assert.equal(overlayGeometry({ bbox: [], translation: ZH }, page), null);
});

test("rejects rotated pages", () => {
  assert.equal(
    overlayGeometry({ bbox: [72, 700, 300, 720], translation: ZH }, { ...page, rotation: 90 }),
    null,
  );
});

test("rejects boxes outside the page", () => {
  assert.equal(overlayGeometry({ bbox: [-40, 700, 300, 720], translation: ZH }, page), null);
  assert.equal(overlayGeometry({ bbox: [72, 900, 300, 950], translation: ZH }, page), null);
});

test("rejects a box covering the whole page", () => {
  // Regression: a cross-page paragraph once produced a bbox spanning both pages,
  // and the opaque panel painted over the entire page (figures included).
  const real = { width: 414, height: 615, pageWidth: 414, pageHeight: 615, rotation: 0 };
  assert.equal(overlayGeometry({ bbox: [34, 32, 380, 579], translation: ZH }, real), null);
});

test("skips untranslatable empty text", () => {
  assert.equal(overlayGeometry({ bbox: [72, 700, 300, 720], translation: "" }, page), null);
  assert.equal(overlayGeometry({ bbox: [72, 700, 300, 720], translation: null }, page), null);
});

test("never splits a Latin word across lines", () => {
  const lines = wrapEstimated("CogView3 是首个实现 relay diffusion 的模型，性能优于 SDXL。", 12, 120);
  assert.ok(lines.length > 1);
  for (const line of lines) {
    assert.ok(!line.startsWith("ogView3"), line);
    assert.ok(!line.startsWith("iffusion"), line);
  }
});

test("closing punctuation never starts a line", () => {
  const lines = wrapEstimated("扩散模型的效率提升明显。然而单阶段模型仍有挑战。", 12, 96);
  assert.ok(lines.length > 1);
  for (const line of lines) {
    assert.ok(!"，。、；：！？".includes(line[0]), `line starts with punctuation: ${line}`);
  }
});

test("fitFontSize shrinks until the text fits, or gives up", () => {
  const loose = fitFontSize("短句。", 300, 120);
  assert.ok(loose && loose > 10);
  const impossible = fitFontSize("模型".repeat(400), 40, 20);
  assert.equal(impossible, null);
});

test("fitPage keeps the aspect ratio", () => {
  assert.deepEqual(fitPage(page, 400), { width: 400, height: (792 / 612) * 400 });
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
