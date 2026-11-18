import assert from "node:assert/strict";
import test from "node:test";

import { summarizeYardmic } from "../src/yardmic.mjs";
import { handleYardmic } from "../src/yardmic_runtime.mjs";

const bird = (code, minutes) => ({ code, name: code === "belkin1" ? "Belted Kingfisher" : "Blue Jay", confirmed: "reviewed", minutes });
const day = (date, species = []) => ({ date, listening_minutes: 800, species });
const snapshotOptions = (estimatedAt, now = estimatedAt, basis = "source-response-estimate") => ({
  now,
  freshness: {
    recent: { state: "fresh", retrievedAt: now, sourceCache: null, snapshot: { estimatedAt, basis } },
    history: { state: "fresh", retrievedAt: now, sourceCache: null },
  },
});

test("the estimated snapshot fixes the hour and preserves quiet minutes while the kingfisher clock advances", () => {
  const payload = { days: [day("2026-11-18", [bird("blujay", ["11:44"]), bird("belkin1", ["11:30"])])] };
  const initial = summarizeYardmic(payload, snapshotOptions("2026-11-18T17:00:44Z", "2026-11-18T17:05:00Z"));
  const delayed = summarizeYardmic(payload, snapshotOptions("2026-11-18T17:00:44Z", "2026-11-18T18:10:00Z"));
  assert.deepEqual(delayed.recentHour, initial.recentHour);
  assert.equal(initial.recentHour.start, "2026-11-18T16:00:00.000Z");
  assert.equal(initial.recentHour.end, "2026-11-18T17:00:00.000Z");
  assert.equal(initial.recentHour.snapshotEstimatedAt, "2026-11-18T17:00:44.000Z");
  assert.equal(initial.recentHour.windowBasis, "source-response-estimate");
  assert.equal(initial.recentHour.recordingEndAt, null);
  assert.equal(initial.recentHour.species[0].minuteStarts.at(-1), "2026-11-18T16:44:00.000Z");
  assert.equal(initial.kingfisher.elapsedMinutes, 35);
  assert.equal(delayed.kingfisher.elapsedMinutes, 100);
});

test("an old snapshot with no recent birds keeps its quiet hour, including true empty returned records", () => {
  for (const species of [[bird("belkin1", ["09:00"])], []]) {
    const result = summarizeYardmic({ days: [day("2026-11-18", species)] },
      snapshotOptions("2026-11-18T17:00:10Z", "2026-11-18T21:00:00Z"));
    assert.equal(result.recentHour.state, "available");
    assert.equal(result.recentHour.end, "2026-11-18T17:00:00.000Z");
    assert.deepEqual(result.recentHour.species, []);
  }
});

test("unknown timing is explicit and neither wall time nor the last bird invents an hour", () => {
  const result = summarizeYardmic({ days: [day("2026-11-18", [bird("blujay", ["11:44"])])] },
    { now: "2026-11-18T17:00:00Z" });
  assert.equal(result.recentHour.windowBasis, "unknown");
  assert.equal(result.recentHour.snapshotEstimatedAt, null);
  assert.equal(result.recentHour.recordingEndAt, null);
  assert.equal(result.recentHour.start, null);
  assert.equal(result.recentHour.end, null);
  assert.equal(result.recentHour.state, "unavailable");
  assert.deepEqual(result.recentHour.species, []);
  assert.equal(result.latestDetectionAt, "2026-11-18T16:44:00.000Z");
});

test("an invalid or future declared snapshot cannot generate future bins", () => {
  const payload = { days: [day("2026-11-18", [bird("blujay", ["11:44"])])] };
  for (const estimatedAt of [null, "not a timestamp", "2026-11-18T17:00:01Z"]) {
    const result = summarizeYardmic(payload, snapshotOptions(estimatedAt, "2026-11-18T17:00:00Z"));
    assert.equal(result.recentHour.windowBasis, "unknown");
    assert.equal(result.recentHour.end, null);
    assert.deepEqual(result.recentHour.species, []);
  }
  const fallback = summarizeYardmic(payload, {
    now: "2026-11-18T17:00:00Z",
    freshness: {
      recent: { state: "fresh", retrievedAt: "2026-11-18T16:55:00Z", sourceCache: { cachedAt: "2026-11-18T17:10:00Z" } },
      history: { state: "unavailable", retrievedAt: null, sourceCache: null },
    },
  });
  assert.equal(fallback.recentHour.windowBasis, "retrieval-estimate");
  assert.equal(fallback.recentHour.end, "2026-11-18T16:55:00.000Z");
});

test("snapshot hours use their own dates across midnight while requested and pattern dates use actual now", () => {
  const payload = { days: [
    day("2026-11-17", [bird("blujay", ["23:09", "23:10", "23:11", "23:59"])]),
    day("2026-11-18", [bird("blujay", ["00:05", "00:10", "00:11"])]),
  ] };
  const result = summarizeYardmic(payload, snapshotOptions("2026-11-18T05:10:22Z", "2026-11-19T05:03:00Z"));
  assert.equal(result.recentHour.state, "available");
  assert.deepEqual(result.recentHour.species[0].minuteStarts, [
    "2026-11-18T04:11:00.000Z", "2026-11-18T04:59:00.000Z", "2026-11-18T05:05:00.000Z", "2026-11-18T05:10:00.000Z",
  ]);
  assert.equal(result.range.requested.end, "2026-11-19");
  assert.deepEqual(result.patterns.range, { start: "2026-11-12", end: "2026-11-18" });
  const partial = summarizeYardmic({ days: payload.days.slice(1) },
    snapshotOptions("2026-11-18T05:10:22Z", "2026-11-19T05:03:00Z"));
  assert.equal(partial.recentHour.state, "partial");
});

test("snapshot filtering excludes later records without changing the actual-time kingfisher filter", () => {
  const result = summarizeYardmic({ days: [day("2026-11-18", [bird("belkin1", ["11:59", "12:00", "12:01", "13:01"])])] },
    snapshotOptions("2026-11-18T17:00:44Z", "2026-11-18T18:00:00Z"));
  assert.deepEqual(result.recentHour.species[0].minuteStarts, ["2026-11-18T16:59:00.000Z", "2026-11-18T17:00:00.000Z"]);
  assert.equal(result.kingfisher.latestAt, "2026-11-18T17:01:00.000Z");
  assert.equal(result.kingfisher.elapsedMinutes, 59);
});

function harness() {
  const cacheEntries = new Map();
  const cache = {
    async match(request) { return cacheEntries.get(request.url)?.clone(); },
    async put(request, response) { cacheEntries.set(request.url, response); },
  };
  return async ({ now, age, recentDays, fail = false, failTo, reverse = false }) => {
    let requests = 0;
    const pending = [];
    const response = await handleYardmic({
      request: new Request("https://kingfisher.example/api/yardmic"),
      env: { YARDMIC_API_KEY: "example-key" },
      waitUntil(work) { pending.push(work); },
    }, {
      cache,
      now: () => Date.parse(now),
      async fetcher(url) {
        requests += 1;
        const rangeEnd = new URL(url).searchParams.get("to");
        if (fail || rangeEnd === failTo) return new Response(null, { status: 502 });
        const days = recentDays.filter(({ date }) => date <= rangeEnd
          && date >= new URL(url).searchParams.get("from"));
        if (reverse) for (const entry of days) entry.species = [...entry.species].reverse();
        return Response.json({ days }, { headers: age === undefined ? {} : { Age: String(age), "Cache-Control": "max-age=900" } });
      },
    });
    await Promise.all(pending);
    return { summary: await response.json(), requests };
  };
}

test("local hits, source-cache repeats near a minute boundary, and failed refreshes keep identical bins", async () => {
  const run = harness();
  const recentDays = [day("2026-11-18", [bird("blujay", ["11:45"]), bird("belkin1", ["11:30"])])];
  const initial = await run({ now: "2026-11-18T17:05:59.900Z", age: 300, recentDays });
  assert.equal(initial.summary.recentHour.end, "2026-11-18T17:00:00.000Z");
  const hit = await run({ now: "2026-11-18T17:06:59.900Z", age: 360, recentDays });
  assert.equal(hit.requests, 0);
  assert.deepEqual(hit.summary.recentHour, initial.summary.recentHour);
  const repeated = await run({ now: "2026-11-18T17:09:04.100Z", age: 480, recentDays, reverse: true });
  assert.equal(repeated.requests, 1);
  assert.deepEqual(repeated.summary.recentHour, initial.summary.recentHour);
  assert.equal(repeated.summary.freshness.recent.retrievedAt, "2026-11-18T17:09:04.100Z");
  const stale = await run({ now: "2026-11-18T17:12:00Z", recentDays, fail: true });
  assert.equal(stale.summary.freshness.recent.state, "stale");
  assert.deepEqual(stale.summary.recentHour, initial.summary.recentHour);
});

test("missing Age retains the first retrieval estimate for unchanged records, including an empty response", async () => {
  for (const recentDays of [[day("2026-11-18")], [], [day("2026-11-18", [bird("blujay", ["11:45"])])]]) {
    const run = harness();
    const initial = await run({ now: "2026-11-18T17:00:45Z", recentDays });
    const repeated = await run({ now: "2026-11-18T18:00:45Z", recentDays });
    assert.equal(initial.summary.recentHour.windowBasis, "retrieval-estimate");
    assert.equal(initial.summary.recentHour.snapshotEstimatedAt, "2026-11-18T17:00:45.000Z");
    assert.deepEqual(repeated.summary.recentHour, initial.summary.recentHour);
    assert.equal(repeated.summary.freshness.recent.retrievedAt, "2026-11-18T18:00:45.000Z");
  }
});

test("a newly generated source response advances a quiet window even when no birds changed", async () => {
  const run = harness();
  const recentDays = [day("2026-11-18", [bird("blujay", ["10:00"])])];
  const initial = await run({ now: "2026-11-18T17:00:00Z", age: 0, recentDays });
  const updated = await run({ now: "2026-11-18T17:20:00Z", age: 0, recentDays });
  assert.equal(initial.summary.recentHour.end, "2026-11-18T17:00:00.000Z");
  assert.equal(updated.summary.recentHour.end, "2026-11-18T17:20:00.000Z");
  assert.deepEqual(updated.summary.recentHour.species, []);
});

test("stale midnight fallback retains both original recent dates for the snapshot hour", async () => {
  const run = harness();
  const recentDays = [
    day("2026-11-17", [bird("blujay", ["23:55"])]),
    day("2026-11-18", [bird("blujay", ["00:05"])]) ,
  ];
  const initial = await run({ now: "2026-11-18T05:10:00Z", age: 0, recentDays });
  const fallback = await run({ now: "2026-11-19T05:03:00Z", recentDays, fail: true });
  assert.equal(fallback.summary.freshness.recent.state, "stale");
  assert.deepEqual(fallback.summary.recentHour, initial.summary.recentHour);
});

test("fresh overlapping history corrections update actual patterns and kingfisher without replacing the retained snapshot", async () => {
  const run = harness();
  const initial = await run({ now: "2026-11-18T05:10:00Z", age: 0, recentDays: [
    day("2026-11-17", [bird("belkin1", ["11:00"])]), day("2026-11-18"),
  ] });
  const fallback = await run({ now: "2026-11-19T05:03:00Z", age: 0, failTo: "2026-11-19", recentDays: [
    day("2026-11-17", [bird("belkin1", ["23:59"])]),
  ] });
  assert.equal(fallback.summary.freshness.recent.state, "stale");
  assert.equal(fallback.summary.freshness.history.state, "fresh");
  assert.equal(fallback.summary.kingfisher.latestAt, "2026-11-18T04:59:00.000Z");
  assert.equal(fallback.summary.patterns.speciesHours[0].daysByHour[23], 1);
  assert.equal(fallback.summary.patterns.speciesHours[0].daysByHour[11], 0);
  assert.deepEqual(fallback.summary.recentHour, initial.summary.recentHour);
});

test("later history cannot fill a missing date in an unchanged partial snapshot", async () => {
  const run = harness();
  const initial = await run({ now: "2026-11-18T05:10:00Z", age: 0, recentDays: [
    day("2026-11-18", [bird("blujay", ["00:05"])]),
  ] });
  assert.equal(initial.summary.recentHour.state, "partial");
  const fallback = await run({ now: "2026-11-19T05:03:00Z", age: 0, failTo: "2026-11-19", recentDays: [
    day("2026-11-17", [bird("belkin1", ["23:59"])]),
  ] });
  assert.equal(fallback.summary.freshness.recent.state, "stale");
  assert.equal(fallback.summary.freshness.history.state, "fresh");
  assert.equal(fallback.summary.kingfisher.latestAt, "2026-11-18T04:59:00.000Z");
  assert.equal(fallback.summary.patterns.speciesHours.find(({ code }) => code === "belkin1").daysByHour[23], 1);
  assert.deepEqual(fallback.summary.recentHour, initial.summary.recentHour);
});
