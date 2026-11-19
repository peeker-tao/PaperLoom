/**
 * Unit tests for chat-model resolution.
 *
 * The regression: the picker only changed local state and `ask` never sent the
 * model, so every question silently ran on `settings.chat_model`. These tests
 * pin the *selection* rule — a saved pick wins, a retired one does not, and an
 * empty service list must not leave the picker blank.
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import esbuild from "esbuild";

const outDir = mkdtempSync(join(tmpdir(), "paperloom-model-"));
const bundle = join(outDir, "model.mjs");
await esbuild.build({
  entryPoints: [
    new URL("../src/model-choice.ts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  ],
  bundle: true,
  format: "esm",
  platform: "neutral",
  outfile: bundle,
  logLevel: "silent",
});
const { resolveChatModel, isKnownModel, modelLabel } = await import(
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

const models = [
  { id: "deepseek-flash", label: "DeepSeek Flash" },
  { id: "deepseek-v4-pro", label: "DeepSeek V4 Pro" },
];

test("a saved selection wins over the service default", () => {
  assert.equal(resolveChatModel("deepseek-v4-pro", models, "deepseek-flash"), "deepseek-v4-pro");
});

test("no saved selection falls back to the service default", () => {
  assert.equal(resolveChatModel("", models, "deepseek-flash"), "deepseek-flash");
  assert.equal(resolveChatModel(null, models, "deepseek-flash"), "deepseek-flash");
  assert.equal(resolveChatModel(undefined, models, "deepseek-flash"), "deepseek-flash");
});

test("a retired model id is not restored", () => {
  // The provider removes models; a stale preference must not wedge every question.
  assert.equal(resolveChatModel("deepseek-v2-retired", models, "deepseek-flash"), "deepseek-flash");
});

test("a stale default is also rejected in favour of an offered model", () => {
  assert.equal(resolveChatModel("gone", models, "also-gone"), "deepseek-flash");
});

test("an empty model list does not blank the picker", () => {
  // Before /v1/settings answers, `models` is empty; trust whatever we have.
  assert.equal(resolveChatModel("deepseek-v4-pro", [], "deepseek-flash"), "deepseek-v4-pro");
  assert.equal(resolveChatModel("", [], "deepseek-flash"), "deepseek-flash");
  assert.equal(resolveChatModel("", [], ""), "");
});

test("isKnownModel rejects unknown ids when a list is available", () => {
  assert.equal(isKnownModel("deepseek-flash", models), true);
  assert.equal(isKnownModel("deepseek-v4-pro", models), true);
  assert.equal(isKnownModel("mystery", models), false);
  assert.equal(isKnownModel("", models), false);
  // No list yet: nothing to contradict the value.
  assert.equal(isKnownModel("mystery", []), true);
});

test("modelLabel prefers the human label and states the fallback", () => {
  assert.equal(modelLabel("deepseek-v4-pro", models), "DeepSeek V4 Pro");
  assert.equal(modelLabel("unknown-id", models), "unknown-id");
  assert.equal(modelLabel("", models), "默认模型");
});

rmSync(outDir, { recursive: true, force: true });

if (failures) {
  console.error(`\n${failures} model test(s) failed`);
  process.exit(1);
}
console.log("\nall model choice tests passed");
