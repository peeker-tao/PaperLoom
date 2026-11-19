/**
 * Unit tests for composer image attachments.
 *
 * The rules here decide whether a picture reaches the model at all, and getting
 * them wrong is invisible in the UI: an image that is silently dropped looks
 * exactly like a model that ignored it. So the boundary cases (exactly at the
 * limit, duplicate paste, wrong format) are tested explicitly.
 */
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import esbuild from "esbuild";

const outDir = mkdtempSync(join(tmpdir(), "paperloom-attach-"));
const bundle = join(outDir, "attachments.mjs");
await esbuild.build({
  entryPoints: [
    new URL("../src/attachments.ts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  ],
  bundle: true,
  format: "esm",
  platform: "neutral",
  outfile: bundle,
  logLevel: "silent",
});
const {
  MAX_IMAGES,
  MAX_IMAGE_BYTES,
  MAX_TOTAL_BYTES,
  ACCEPT_ATTRIBUTE,
  addImage,
  checkCandidate,
  dataUrlBytes,
  describeImages,
  formatBytes,
  mimeOf,
  removeImage,
  setCaption,
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

/** A data URL whose payload is `bytes` long and uniquely tagged by `seed`. */
let seedCounter = 0;
function imageOf(bytes, mime = "image/png") {
  seedCounter += 1;
  const chars = Math.ceil(bytes / 3) * 4;
  // Seed character keeps payloads distinct, so the duplicate check does not fire
  // on images that merely have the same size.
  const seed = String.fromCharCode(65 + (seedCounter % 26));
  return `data:${mime};base64,${seed}${"A".repeat(Math.max(0, chars - 1))}`;
}

function candidate(type, size) {
  return { type, size, name: "shot.png" };
}

test("a PNG of ordinary size is accepted", () => {
  assert.equal(checkCandidate(candidate("image/png", 120_000)), null);
});

test("format is matched case-insensitively", () => {
  assert.equal(checkCandidate(candidate("IMAGE/PNG", 1000)), null);
});

test("a screenshot pasted as BMP is refused with the allowed list", () => {
  const message = checkCandidate(candidate("image/bmp", 1000));
  assert.match(message, /BMP/);
  assert.match(message, /PNG/);
});

test("a file with no type is refused rather than guessed", () => {
  assert.match(checkCandidate(candidate("", 1000)), /无法识别/);
});

test("a PDF dragged into the composer is refused", () => {
  assert.match(checkCandidate(candidate("application/pdf", 1000)), /不支持/);
});

test("an image exactly at the per-image limit is accepted", () => {
  assert.equal(checkCandidate(candidate("image/png", MAX_IMAGE_BYTES)), null);
});

test("one byte over the per-image limit is refused, with both numbers", () => {
  const message = checkCandidate(candidate("image/png", MAX_IMAGE_BYTES + 1));
  assert.match(message, /上限/);
});

test("bytes are counted from the base64 length, not the string length", () => {
  // "AAAA" is 4 base64 chars = 3 bytes, not 4.
  assert.equal(dataUrlBytes("data:image/png;base64,AAAA"), 3);
  assert.equal(dataUrlBytes("data:image/png;base64,"), 0);
  assert.equal(dataUrlBytes("not-a-data-url"), 0);
});

test("padding at the end of the payload is not counted as data", () => {
  // "AAA=" is 2 bytes: 3 chars of data plus one pad.
  assert.equal(dataUrlBytes("data:image/png;base64,AAA="), 2);
});

test("the mime type is read back out of a data URL", () => {
  assert.equal(mimeOf("data:image/webp;base64,AAAA"), "image/webp");
  assert.equal(mimeOf("data:,"), "");
  assert.equal(mimeOf("garbage"), "");
});

test("adding an image returns a new list and no error", () => {
  const result = addImage([], { id: "1", dataUrl: imageOf(300), caption: "", name: "a.png" });
  assert.equal(result.error, null);
  assert.equal(result.list.length, 1);
});

test("adding past the count limit explains the limit", () => {
  let list = [];
  for (let index = 0; index < MAX_IMAGES; index += 1) {
    list = addImage(list, {
      id: String(index),
      dataUrl: imageOf(300 + index),
      caption: "",
      name: `a${index}.png`,
    }).list;
  }
  const result = addImage(list, { id: "x", dataUrl: imageOf(999), caption: "", name: "x.png" });
  assert.match(result.error, new RegExp(String(MAX_IMAGES)));
  assert.equal(result.list.length, MAX_IMAGES);
});

test("pasting the same image twice is refused, not duplicated", () => {
  const one = { id: "1", dataUrl: imageOf(300), caption: "", name: "a.png" };
  const first = addImage([], one);
  const second = addImage(first.list, { ...one, id: "2" });
  assert.match(second.error, /已经添加/);
  assert.equal(second.list.length, 1);
});

test("an empty data URL is refused", () => {
  assert.match(addImage([], { id: "1", dataUrl: "", caption: "", name: "" }).error, /没有读到/);
});

test("an unsupported mime inside a data URL is refused", () => {
  const result = addImage([], {
    id: "1",
    dataUrl: imageOf(300, "image/tiff"),
    caption: "",
    name: "a.tiff",
  });
  assert.match(result.error, /TIFF/);
});

test("the total cap refuses even when each image is individually fine", () => {
  // Two ~2.4MB images fit; the third would cross the 6MB total.
  const each = 2_400_000;
  let list = [];
  for (let index = 0; index < 2; index += 1) {
    list = addImage(list, {
      id: String(index),
      dataUrl: imageOf(each),
      caption: "",
      name: `a${index}.png`,
    }).list;
  }
  assert.equal(list.length, 2);
  const result = addImage(list, {
    id: "x",
    dataUrl: imageOf(each),
    caption: "",
    name: "x.png"
  });
  assert.ok(result.error, "a third image of the same size must not fit");
  assert.match(result.error, /合计/);
  assert.equal(result.list.length, 2);
});

test("removing an image keeps the others", () => {
  const list = removeImage(
    [
      { id: "1", dataUrl: imageOf(300), caption: "", name: "a.png" },
      { id: "2", dataUrl: imageOf(600), caption: "", name: "b.png" },
    ],
    "1",
  );
  assert.deepEqual(list.map((item) => item.id), ["2"]);
});

test("setting a caption leaves the data untouched", () => {
  const list = setCaption(
    [{ id: "1", dataUrl: imageOf(300), caption: "", name: "a.png" }],
    "1",
    "结果对比",
  );
  assert.equal(list[0].caption, "结果对比");
  assert.ok(list[0].dataUrl.startsWith("data:image/png;base64,"));
});

test("the summary mentions captions only when some exist", () => {
  const list = [{ id: "1", dataUrl: imageOf(300), caption: "", name: "a.png" }];
  assert.match(describeImages(list), /^1 张图 · /);
  assert.match(describeImages(setCaption(list, "1", "左图")), /1 张有说明/);
  assert.equal(describeImages([]), "");
});

test("byte sizes are shown in the unit a person would use", () => {
  assert.equal(formatBytes(512), "512B");
  assert.equal(formatBytes(2048), "2KB");
  assert.equal(formatBytes(2_500_000), "2.5MB");
});

test("the file picker advertises exactly the formats we accept", () => {
  assert.equal(ACCEPT_ATTRIBUTE, "image/png,image/jpeg,image/webp");
});

if (failures) {
  console.error(`\n${failures} attachment test(s) failed`);
  process.exit(1);
}
console.log("\nall attachment tests passed");
