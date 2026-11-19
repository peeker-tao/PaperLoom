/**
 * Unit tests for the composer's Enter handling.
 *
 * The bug: pressing Enter to confirm a Chinese IME candidate also fires a
 * keydown with key === "Enter", and the composer sent the half-finished
 * sentence. The same applies to Japanese, Korean and Vietnamese input, so this
 * is not a Chinese-only problem — just one that Chinese users hit on every
 * single message.
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import esbuild from "esbuild";

const outDir = mkdtempSync(join(tmpdir(), "paperloom-composer-"));
const bundle = join(outDir, "composer.mjs");
await esbuild.build({
  entryPoints: [
    new URL("../src/composer.ts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  ],
  bundle: true,
  format: "esm",
  platform: "neutral",
  outfile: bundle,
  logLevel: "silent",
});
const { shouldSendOnEnter, isImeConfirmation } = await import(pathToFileURL(bundle).href);

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

const base = { key: "Enter", shiftKey: false, composing: false };

test("a plain Enter sends", () => {
  assert.equal(shouldSendOnEnter(base), true);
});

test("Shift+Enter inserts a newline", () => {
  assert.equal(shouldSendOnEnter({ ...base, shiftKey: true }), false);
});

test("Enter while an IME candidate window is open does not send", () => {
  // Chinese/Japanese/Korean: this Enter picks the candidate.
  assert.equal(shouldSendOnEnter({ ...base, composing: true }), false);
  assert.equal(shouldSendOnEnter({ ...base, isComposing: true }), false);
  // Belt and braces: some Gecko builds only report keyCode 229.
  assert.equal(shouldSendOnEnter({ ...base, keyCode: 229 }), false);
});

test("keyCode 229 wins even when isComposing says false", () => {
  assert.equal(isImeConfirmation({ key: "Enter", shiftKey: false, keyCode: 229, composing: false }), true);
});

test("our own composition tracker is honoured after compositionend", () => {
  // The keydown that confirms the candidate can arrive after compositionend.
  assert.equal(shouldSendOnEnter({ ...base, composing: true, isComposing: false }), false);
});

test("modifier combinations are left to the browser", () => {
  assert.equal(shouldSendOnEnter({ ...base, ctrlKey: true }), false);
  assert.equal(shouldSendOnEnter({ ...base, metaKey: true }), false);
  assert.equal(shouldSendOnEnter({ ...base, altKey: true }), false);
});

test("other keys never send", () => {
  assert.equal(shouldSendOnEnter({ ...base, key: "a" }), false);
  assert.equal(shouldSendOnEnter({ ...base, key: "Escape" }), false);
});

test("an English Enter after IME finished still sends", () => {
  // Regression guard: the tracker must clear, or typing English would stop working.
  assert.equal(shouldSendOnEnter({ ...base, composing: false, isComposing: false }), true);
});

rmSync(outDir, { recursive: true, force: true });

if (failures) {
  console.error(`\n${failures} composer test(s) failed`);
  process.exit(1);
}
console.log("\nall composer tests passed");
