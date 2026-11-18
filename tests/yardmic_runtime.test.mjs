import assert from "node:assert/strict";
import test from "node:test";

import { onRequest } from "../functions/api/yardmic.js";
import { handleYardmic } from "../src/yardmic_runtime.mjs";

const KEY = "yardmic-example-secret-do-not-emit";
const origin = "https://kingfisher.example";
const day = (date, species = []) => ({ date, listening_minutes: 800, species });
const upstream = (days, headers) => Response.json({ site: "Kingfisher Hollow", times: "Eastern", days }, { headers });
const at = (iso) => () => Date.parse(iso);
const expectedFreshness = (state, retrievedAt, sourceCache = null) => ({
  state, retrievedAt, sourceCache,
  snapshot: sourceCache?.cachedAt
    ? { estimatedAt: sourceCache.cachedAt, basis: "source-response-estimate" }
    : { estimatedAt: retrievedAt, basis: "retrieval-estimate" },
});

function makeContext(env = { YARDMIC_API_KEY: KEY }, query = "") {
  return {
    env,
    request: new Request(`${origin}/api/yardmic${query}`),
    pending: [],
    waitUntil(work) {
      this.pending.push(work);
    },
  };
}

function memoryCache() {
  const data = new Map();
  return {
    async match(request) {
      return data.get(request.url)?.clone();
    },
    async put(request, response) {
      data.set(request.url, response);
    },
  };
}

test("the Pages route returns safe 503 output without a configured key", async () => {
  const response = await onRequest(makeContext({}));
  const summary = await response.json();
  assert.equal(response.status, 503);
  assert.equal(summary.state, "unavailable");
  assert.equal(summary.recentHour.state, "unavailable");
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("calls only the fixed authenticated upstream endpoint for the split 31-date window", async () => {
  const seen = [];
  const response = await handleYardmic(makeContext(), {
    now: at("2026-11-18T02:00:00Z"),
    async fetcher(url, options) {
      seen.push(String(url));
      assert.equal(new Headers(options.headers).get("Authorization"), `Bearer ${KEY}`);
      assert.match(new Headers(options.headers).get("User-Agent"), /Kingfisher Hollow/);
      assert.equal(options.redirect, "manual");
      assert.equal(options.cache, "no-store");
      return upstream([day(new URL(url).searchParams.get("to"))]);
    },
  });
  assert.equal(response.status, 200);
  assert.deepEqual(seen.sort(), [
    "https://yardmic.aviandavies.workers.dev/api/v1/minutes?from=2026-10-18&to=2026-11-15",
    "https://yardmic.aviandavies.workers.dev/api/v1/minutes?from=2026-11-16&to=2026-11-17",
  ]);
  const summary = await response.json();
  assert.deepEqual(summary.range.requested, { start: "2026-10-18", end: "2026-11-17" });
  assert.deepEqual(summary.range.returnedDates, ["2026-11-15", "2026-11-17"]);
});

test("a client's date and URL parameters cannot change the upstream query", async () => {
  let calls = 0;
  const response = await handleYardmic(makeContext(undefined, `?from=1900-01-01&url=https://elsewhere.example/`), {
    async fetcher() {
      calls += 1;
      return upstream([]);
    },
  });
  assert.equal(response.status, 400);
  assert.equal(calls, 0);
});

test("recent data survives a failed history request without claiming full coverage", async () => {
  const response = await handleYardmic(makeContext(), {
    now: at("2026-11-18T17:00:00Z"),
    async fetcher(url) {
      if (new URL(url).searchParams.get("to") === "2026-11-18") return upstream([day("2026-11-18")]);
      return new Response(null, { status: 302, headers: { Location: "https://elsewhere.example/" } });
    },
  });
  const summary = await response.json();
  assert.equal(response.status, 200);
  assert.equal(summary.state, "partial");
  assert.equal(summary.recentHour.state, "available");
  assert.equal(summary.kingfisher.state, "no-match");
  assert.equal(summary.kingfisher.complete, false);
  assert.equal(summary.freshness.history.state, "unavailable");
});

test("does not echo credentials from known or unknown upstream fields", async () => {
  const response = await handleYardmic(makeContext(), {
    now: at("2026-11-18T17:00:00Z"),
    async fetcher(url) {
      const date = new URL(url).searchParams.get("to");
      if (date === "2026-11-18") {
        return upstream([day(date, [{ code: "belkin1", name: KEY, confirmed: "reviewed", minutes: ["11:44"] }])]);
      }
      return Response.json({ days: [day(date)], site: KEY, raw_auth_header: `Bearer ${KEY}` });
    },
  });
  const body = await response.text();
  assert.equal(response.status, 200);
  assert.equal(body.includes(KEY), false);
  const summary = JSON.parse(body);
  assert.equal(summary.freshness.recent.state, "unavailable");
  assert.equal(summary.freshness.history.state, "fresh");
  assert.equal(summary.kingfisher.latestAt, null);
});

test("falls back to bounded stale caches while preserving original retrieval times", async () => {
  const cache = memoryCache();
  const initial = makeContext();
  const saved = await handleYardmic(initial, {
    cache,
    now: at("2026-11-18T17:00:00Z"),
    async fetcher(url) {
      return upstream([day(new URL(url).searchParams.get("to"))]);
    },
  });
  assert.equal(saved.status, 200);
  await Promise.all(initial.pending);

  const outage = async (iso) => handleYardmic(makeContext(), {
    cache, now: at(iso),
    async fetcher() {
      return new Response(null, { status: 502 });
    },
  });

  const stale = await (await outage("2026-11-18T17:02:01Z")).json();
  assert.deepEqual(stale.freshness.recent, expectedFreshness("stale", "2026-11-18T17:00:00.000Z"));
  assert.deepEqual(stale.freshness.history, expectedFreshness("fresh", "2026-11-18T17:00:00.000Z"));

  const afterMidnight = await (await outage("2026-11-19T05:03:00Z")).json();
  assert.deepEqual(afterMidnight.freshness.recent, expectedFreshness("stale", "2026-11-18T17:00:00.000Z"));
  assert.deepEqual(afterMidnight.freshness.history, expectedFreshness("stale", "2026-11-18T17:00:00.000Z"));
  assert.equal(afterMidnight.recentHour.state, "available");
  assert.equal(afterMidnight.recentHour.end, "2026-11-18T17:00:00.000Z");

  const expiredRecent = await (await outage("2026-11-19T17:00:01Z")).json();
  assert.equal(expiredRecent.freshness.recent.state, "unavailable");
  assert.equal(expiredRecent.freshness.history.state, "stale");
  const expiredHistory = await outage("2026-11-25T17:00:01Z");
  assert.equal(expiredHistory.status, 503);
});

test("keeps YardMic's cache age distinct from the preview receipt time", async () => {
  const cache = memoryCache();
  const initial = makeContext();
  const retrievedAt = "2026-11-18T19:19:52.180Z";
  const seen = await handleYardmic(initial, {
    cache, now: at(retrievedAt),
    async fetcher(url) {
      const to = new URL(url).searchParams.get("to");
      return upstream([day(to)], {
        "Age": "248",
        "Cache-Control": 'public, note="extension, max-age=bogus", MAX-AGE="900"',
        "Last-Modified": "Wed, 18 Nov 2026 18:00:00 GMT",
      });
    },
  });
  await Promise.all(initial.pending);

  const sourceCache = {
    ageSecondsAtRetrieval: 248,
    maxAgeSeconds: 900,
    cachedAt: "2026-11-18T19:15:44.180Z",
  };
  const summary = await seen.json();
  assert.deepEqual(summary.freshness.recent, expectedFreshness("fresh", retrievedAt, sourceCache));
  assert.deepEqual(summary.freshness.history, expectedFreshness("fresh", retrievedAt, sourceCache));

  let upstreamRequests = 0;
  const checkCache = async (now) => {
    const response = await handleYardmic(makeContext(), {
      cache, now: at(now),
      async fetcher() {
        upstreamRequests += 1;
        return new Response(null, { status: 503 });
      },
    });
    return response.json();
  };

  const local = await checkCache("2026-11-18T19:20:00.000Z");
  assert.equal(upstreamRequests, 0);
  assert.deepEqual(local.freshness, summary.freshness);

  const stale = await checkCache("2026-11-18T19:22:00.000Z");
  assert.equal(upstreamRequests, 1);
  assert.deepEqual(stale.freshness.recent, expectedFreshness("stale", retrievedAt, sourceCache));
  assert.deepEqual(stale.freshness.history, summary.freshness.history);

  const afterMidnight = await checkCache("2026-11-19T05:03:00Z");
  assert.deepEqual(afterMidnight.freshness.recent, expectedFreshness("stale", retrievedAt, sourceCache));
});

test("drops invalid cache parameters and keeps valid upstream values independently", async () => {
  const cases = [
    ["-1", "max-age=1e3", null],
    ["86401", "max-age=86401", null],
    ["1.25", 'note="example, max-age=900"', null],
    ["2", "max-age=300, max-age=900", {
      ageSecondsAtRetrieval: 2, maxAgeSeconds: null, cachedAt: "2026-11-18T16:59:58.000Z",
    }],
    ["0", "max-age=86400", {
      ageSecondsAtRetrieval: 0, maxAgeSeconds: 86400, cachedAt: "2026-11-18T17:00:00.000Z",
    }],
    [null, "max-age=0", { ageSecondsAtRetrieval: null, maxAgeSeconds: 0, cachedAt: null }],
    [null, 'extension="uncLOSED, max-age=900', null],
  ];
  for (const [age, cacheControl, expected] of cases) {
    const response = await handleYardmic(makeContext(), {
      now: at("2026-11-18T17:00:00Z"),
      async fetcher(url) {
        const to = new URL(url).searchParams.get("to");
        const headers = new Headers({ "Cache-Control": cacheControl });
        if (age !== null) headers.set("Age", age);
        return upstream([day(to)], headers);
      },
    });
    assert.equal(response.status, 200);
    const summary = await response.json();
    assert.equal(summary.freshness.recent.state, "fresh");
    assert.deepEqual(summary.freshness.recent.sourceCache, expected, `${age}, ${cacheControl}`);
  }
});

test("previously cached records without source metadata still serve with their original receipt time", async () => {
  const cache = memoryCache();
  const retrievedAt = "2026-11-18T17:00:00.000Z";
  await cache.put(new Request(`${origin}/api/yardmic?cached-range-v1=2026-11-17--2026-11-18`), Response.json({
    days: [day("2026-11-18")],
  }, {
    headers: { "Cache-Control": "max-age=86400", "X-YardMic-Retrieved-At": retrievedAt, Age: "10" },
  }));
  const response = await handleYardmic(makeContext(), {
    cache,
    now: at("2026-11-18T17:00:10Z"),
    async fetcher() {
      return new Response(null, { status: 503 });
    },
  });
  assert.equal(response.status, 200);
  const summary = await response.json();
  assert.deepEqual(summary.freshness.recent, expectedFreshness("fresh", retrievedAt));
});

test("rejects invalid values and bounds a streamed response without a length header", async () => {
  let canceled = false;
  const response = await handleYardmic(makeContext(), {
    now: at("2026-11-18T17:00:00Z"),
    async fetcher(url) {
      const date = new URL(url).searchParams.get("to");
      if (date === "2026-11-18") {
        return upstream([day(date, [{ code: "belkin1", name: "Belted Kingfisher", confirmed: "reviewed", minutes: ["24:00"] }])]);
      }
      return new Response(new ReadableStream({
        pull(controller) {
          controller.enqueue(new Uint8Array(128 * 1024));
        },
        cancel() {
          canceled = true;
        },
      }));
    },
  });
  assert.equal(response.status, 503);
  assert.equal(canceled, true);
});

test("the upstream deadline applies after response headers while body streaming is stalled", async () => {
  let aborted = 0;
  const response = await handleYardmic(makeContext(), {
    now: at("2026-11-18T17:00:00Z"),
    timeoutMs: 10,
    async fetcher(_url, { signal }) {
      return new Response(new ReadableStream({
        start(controller) {
          signal.addEventListener("abort", () => {
            aborted += 1;
            controller.error(signal.reason);
          }, { once: true });
        },
      }));
    },
  });
  assert.equal(aborted, 2);
  assert.equal(response.status, 503);
});
