/**
 * One number for "how much is translated".
 *
 * The complaint was "翻译段数有误": the footer said 105/472, the reading toolbar
 * said 104/112 and the bilingual header said 3/9 — all measuring different
 * things on the same screen. These tests pin the single rule they now share,
 * and it is the server's rule (`translate.is_translatable`), not an invention.
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import esbuild from "esbuild";

const outDir = mkdtempSync(join(tmpdir(), "paperloom-counts-"));
const bundle = join(outDir, "counts.mjs");
await esbuild.build({
  entryPoints: [
    new URL("../src/counts.ts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  ],
  bundle: true,
  format: "esm",
  platform: "neutral",
  outfile: bundle,
  logLevel: "silent",
});
const { isTranslatable, translationCounts, describeCounts, SKIP_KINDS } = await import(
  pathToFileURL(bundle).href
);

function seg(kind, text, translation = null) {
  return { id: `${kind}-${text.slice(0, 6)}`, page: 1, kind, text, translation };
}

let failures = 0;
function test(name, fn) {
  try {
    fn();
    console.log(`ok   ${name}`);
  } catch (error) {
    failures += 1;
    console.error(`FAIL ${name}`);
    console.error(`     ${error.message}`);
  }
}

const PROSE = "We propose a modality invariant image matching framework.";

test("prose is translatable", () => {
  assert.equal(isTranslatable(seg("body", PROSE)), true);
});

test("every skipped kind is the server's list", () => {
  assert.deepEqual(
    [...SKIP_KINDS].sort(),
    ["figure", "formula", "meta", "noise", "reference", "table"],
  );
  for (const kind of SKIP_KINDS) {
    assert.equal(isTranslatable(seg(kind, PROSE)), false, kind);
  }
});

test("a table cell with words in it is still not translated", () => {
  assert.equal(isTranslatable(seg("table", "MINIMA_LG")), false);
});

test("a picture crop contributes to neither numerator nor denominator", () => {
  const counts = translationCounts([
    seg("figure", ""),
    seg("body", PROSE, "我们提出……"),
  ]);
  assert.deepEqual(counts, { total: 1, done: 1, skipped: 1 });
});

test("a short fragment is not worth translating", () => {
  assert.equal(isTranslatable(seg("body", "SSIM")), false);
  assert.equal(isTranslatable(seg("body", "2")), false);
});

test("headings skip the length floor but still need letters", () => {
  assert.equal(isTranslatable(seg("heading", "3 Method")), true);
  assert.equal(isTranslatable(seg("heading", "1")), false);
  assert.equal(isTranslatable(seg("title", "MINIMA: Image Matching")), true);
});

test("a translated picture is never counted as progress", () => {
  // This is what made the ratio exceed 100% in the old toolbar.
  const counts = translationCounts([seg("figure", "", "译文"), seg("body", PROSE)]);
  assert.equal(counts.done, 0);
  assert.equal(counts.total, 1);
});

test("the number on screen is the number of translatable paragraphs", () => {
  const segments = [
    seg("title", "MINIMA: Modality Invariant Image Matching"),
    seg("body", PROSE, "我们提出一个模态无关的图像匹配框架。"),
    seg("body", "Learning to match across modalities is hard."),
    seg("caption", "Figure 2. Qualitative results on real pairs."),
    seg("reference", "[1] Ren et al. MINIMA. 2025."),
    seg("noise", "Preprint. Under review."),
    seg("table", "ReDFeat"),
    seg("formula", "x = y + z"),
    seg("figure", ""),
  ];
  const counts = translationCounts(segments);
  // title + two body paragraphs + the caption: captions are prose the reader
  // needs, so the server translates them too.
  assert.equal(counts.total, 4);
  assert.equal(counts.done, 1);
  assert.equal(counts.skipped, 5);
  assert.equal(describeCounts(counts), "1/4");
});

test("an empty paper reports 0/0 rather than dividing by the segment count", () => {
  assert.deepEqual(translationCounts([]), { total: 0, done: 0, skipped: 0 });
});

rmSync(outDir, { recursive: true, force: true });
console.log(failures ? `\n${failures} failed` : "\nall counts tests passed");
process.exit(failures ? 1 : 0);
