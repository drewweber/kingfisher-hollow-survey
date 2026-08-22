import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const template = await readFile(
  new URL("../field-guide/service-worker.js", import.meta.url),
  "utf8",
);

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function workerHarness({ reusableHash = null, networkBody = "network asset" } = {}) {
  const writes = [];
  const fetches = [];
  const currentCache = {
    async match() {
      return undefined;
    },
    async put(key, response) {
      writes.push({ key, response });
    },
  };
  const reusableResponse = { source: "previous release" };
  const networkBytes = new TextEncoder().encode(networkBody);
  const networkResponse = {
    ok: true,
    status: 200,
    source: "network",
    clone() {
      return this;
    },
    async arrayBuffer() {
      return networkBytes.buffer.slice(
        networkBytes.byteOffset,
        networkBytes.byteOffset + networkBytes.byteLength,
      );
    },
  };
  const context = {
    URL,
    Uint8Array,
    crypto: webcrypto,
    caches: {
      async open() {
        return currentCache;
      },
      async match(key) {
        return reusableHash && key.endsWith(`?v=${reusableHash}`)
          ? reusableResponse
          : undefined;
      },
      async keys() {
        return [];
      },
      async delete() {
        return true;
      },
    },
    async fetch(url, options) {
      fetches.push({ url, options, response: networkResponse });
      return networkResponse;
    },
    self: {
      registration: { scope: "https://example.test/field/" },
      clients: { async matchAll() { return []; } },
      addEventListener() {},
    },
  };
  context.globalThis = context;
  vm.createContext(context);
  const source = template
    .replace("__VERSION__", JSON.stringify("test-release"))
    .replace("__CACHE_VERSION__", JSON.stringify("test-cache"))
    .replace("__ASSETS__", "[]")
    + "\nglobalThis.cacheOneForTest = cacheOne;";
  new vm.Script(source).runInContext(context);
  return { cacheOne: context.cacheOneForTest, fetches, writes, reusableResponse };
}

test("field worker reuses an exact content-addressed asset", async () => {
  const harness = workerHarness({ reusableHash: "same-hash" });

  await harness.cacheOne(
    { match: async () => undefined, put: async (...args) => harness.writes.push(args) },
    { path: "./app.js", sha256: "same-hash" },
  );

  assert.equal(harness.fetches.length, 0);
  assert.equal(harness.writes.length, 1);
  assert.equal(harness.writes[0][0], "https://example.test/field/app.js?v=same-hash");
  assert.equal(harness.writes[0][1], harness.reusableResponse);
});

test("field worker fetches when the same path has different bytes", async () => {
  const networkBody = "new application bytes";
  const networkHash = sha256(networkBody);
  const harness = workerHarness({
    reusableHash: "old-hash",
    networkBody,
  });

  await harness.cacheOne(
    { match: async () => undefined, put: async (...args) => harness.writes.push(args) },
    { path: "./app.js", sha256: networkHash },
  );

  assert.equal(harness.fetches.length, 1);
  assert.equal(harness.fetches[0].url, "https://example.test/field/app.js");
  assert.equal(harness.fetches[0].options.cache, "no-cache");
  assert.equal(
    harness.writes[0][0],
    `https://example.test/field/app.js?v=${networkHash}`,
  );
  assert.equal(harness.writes[0][1], harness.fetches[0].response);
});

test("field worker rejects a stale response under the expected hash", async () => {
  const harness = workerHarness({ networkBody: "stale deployment bytes" });

  await assert.rejects(
    harness.cacheOne(
      { match: async () => undefined, put: async (...args) => harness.writes.push(args) },
      { path: "./targets.json", sha256: sha256("expected deployment bytes") },
    ),
    /Asset changed while preparing offline access/,
  );

  assert.equal(harness.fetches.length, 1);
  assert.equal(harness.writes.length, 0);
});
