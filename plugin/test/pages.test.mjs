/**
 * Unit tests for page-range parsing.
 *
 * The dialog exists because the previous implementation used window.prompt(),
 * which Zotero's main window does not reliably provide — and when it threw, the
 * exception was swallowed as "user cancelled". The parser is where a typo turns
 * into translating the wrong pages (real tokens, wrong output), so the error
 * cases matter as much as the happy path.
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import esbuild from "esbuild";

const outDir = mkdtempSync(join(tmpdir(), "paperloom-pages-"));
const bundle = join(outDir, "pages.mjs");
await esbuild.build({
  entryPoints: [
    new URL("../src/pages.ts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  ],
  bundle: true,
  format: "esm",
  platform: "neutral",
  outfile: bundle,
  logLevel: "silent",
});
const { parsePageInput, describePages, formatPageInput } = await import(pathToFileURL(bundle).href);

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

test("parses a range and a single page", () => {
  assert.deepEqual(parsePageInput("1-3,5").pages, [1, 2, 3, 5]);
});

test("accepts full-width commas, spaces and a full-width dash", () => {
  assert.deepEqual(parsePageInput("1，2 3").pages, [1, 2, 3]);
  assert.deepEqual(parsePageInput("1－3").pages, [1, 2, 3]);
  assert.deepEqual(parsePageInput("2~4").pages, [2, 3, 4]);
});

test("de-duplicates and sorts", () => {
  assert.deepEqual(parsePageInput("3,1,2-3").pages, [1, 2, 3]);
});

test("a blank input means the whole paper, not an error", () => {
  const result = parsePageInput("   ");
  assert.deepEqual(result.pages, []);
  assert.equal(result.error, null);
});

test("names the offending fragment instead of a generic failure", () => {
  const result = parsePageInput("1-3,abc");
  assert.equal(result.pages.length, 0);
  assert.match(result.error, /abc/);
});

test("rejects a reversed range and page zero", () => {
  assert.match(parsePageInput("5-2").error, /结束页小于起始页/);
  assert.match(parsePageInput("0").error, /从 1 开始/);
});

test("rejects an absurd page number", () => {
  assert.match(parsePageInput("1-9999").error, /过大/);
});

test("describePages collapses runs", () => {
  assert.equal(describePages([1, 2, 3, 5]), "1-3, 5（共 4 页）");
  assert.equal(describePages([7]), "7（共 1 页）");
  assert.equal(describePages([]), "全文");
});

// The page grid writes back into the text field. If that round trip disagreed
// with the parser, clicking pages 4 and 5 would silently translate something
// else — so the two directions are checked against each other.
test("formatPageInput collapses runs into the input syntax", () => {
  assert.equal(formatPageInput([1, 2, 3, 5]), "1-3,5");
  assert.equal(formatPageInput([7]), "7");
  assert.equal(formatPageInput([]), "");
});

test("formatting and parsing are inverses", () => {
  for (const pages of [[1], [1, 2, 3, 5], [4, 5, 6, 10, 11], [1, 2, 4, 8]]) {
    assert.deepEqual(parsePageInput(formatPageInput(pages)).pages, pages);
  }
});

test("formatPageInput sorts and de-duplicates before collapsing", () => {
  assert.equal(formatPageInput([3, 1, 2, 2]), "1-3");
});

rmSync(outDir, { recursive: true, force: true });

if (failures) {
  console.error(`\n${failures} page test(s) failed`);
  process.exit(1);
}
console.log("\nall page range tests passed");
