import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import test from "node:test";
import { handleYardmic } from "../src/yardmic_runtime.mjs";
import { yardmicStore } from "../src/yardmic_store.mjs";

function sqliteBinding() {
  const sql = new DatabaseSync(":memory:");
  for (const file of ["0001_snapshots.sql", "0002_recent_dates.sql"]) {
    sql.exec(readFileSync(new URL(`../migrations/yardmic/${file}`, import.meta.url), "utf8"));
  }
  return {
    prepare(text) {
      return { bind(...values) {
        const statement = sql.prepare(text);
        return {
          all: () => ({ results: statement.all(...values) }),
          first: () => statement.get(...values),
          run: () => ({ meta: { changes: statement.run(...values).changes } }),
        };
      } };
    },
    async batch(queries) {
      sql.exec("BEGIN");
      try {
        const results = queries.map((query) => query.run());
        sql.exec("COMMIT");
        return results;
      } catch (error) {
        sql.exec("ROLLBACK");
        throw error;
      }
    },
  };
}

const start = Date.parse("2026-11-18T17:00:00Z");
const date = (date, species = []) => ({ date, listening_minutes: 100, species });
const bird = { code: "belkin1", name: "Belted Kingfisher", confirmed: "auto", minutes: ["11:43"] };
const standard = (url) => Response.json({ days: [date(url.searchParams.get("to"), [bird])] });
const broken = () => new Response(null, { status: 502 });

async function request(db, now, fetcher, key = "testkey") {
  const response = await handleYardmic({
    env: { YARDMIC_DB: db, YARDMIC_API_KEY: key }, request: new Request("https://example.test/api/yardmic"),
    waitUntil() {},
  }, { fetcher, now: () => now, timeoutMs: 10, cache: null });
  return { status: response.status, ...await response.json() };
}

test("cold visitors retain independent snapshots through outages and storage survives deployment", async () => {
  const db = sqliteBinding();
  const first = await request(db, start, standard);
  assert.equal(first.recentHour.species[0].code, "belkin1");
  let calls = 0;
  const unavailable = () => { calls++; return broken(); };
  for (const now of [start + 3 * 60_000, start + 3 * 60_000 + 1]) {
    const result = await request(db, now, unavailable);
    assert.equal(result.status, 200);
    assert.equal(result.recentHour.snapshotEstimatedAt, first.recentHour.snapshotEstimatedAt);
    assert.equal(result.freshness.recent.state, "stale");
    assert.equal(result.freshness.history.state, "fresh");
    assert.equal(result.kingfisher.complete, false);
  }
  assert.equal(calls, 1);
  const dayLater = await request(db, start + 86400_000, unavailable);
  assert.equal(dayLater.range.historyAnchorDate, "2026-11-18");
  assert.deepEqual(dayLater.patterns, first.patterns);
  assert.deepEqual(dayLater.insights, first.insights);
  assert.equal(dayLater.kingfisher.elapsedMinutes, first.kingfisher.elapsedMinutes + 1440);
  const noKey = await request(db, start + 2 * 86400_000, unavailable, "");
  assert.equal(noKey.freshness.recent.state, "stale");
  assert.equal(noKey.freshness.history.state, "stale");
  assert.equal(calls, 3);
  const expired = await request(db, start + 30 * 86400_000, unavailable, "");
  assert.equal(expired.status, 503);
  assert.equal(expired.recentHour.state, "unavailable");
});

test("malformed, empty, invalid, missing anchored dates and timeout preserve a good recent snapshot", async () => {
  for (const fail of [() => new Response("{"), () => Response.json({ days: [] }),
    () => Response.json({ days: [{ date: "bad" }] }),
    () => Response.json({ days: [date("2026-11-17")] }),
    (_url, { signal }) => new Promise((_, reject) => signal.addEventListener("abort", () => reject(signal.reason)))]) {
    const db = sqliteBinding();
    await request(db, start, standard);
    const result = await request(db, start + 180000, fail);
    assert.equal(result.recentHour.species[0].code, "belkin1");
    assert.equal(result.freshness.recent.state, "stale");
    const recovery = await request(db, start + 360000, (url) => Response.json({ days: [date(url.searchParams.get("to"))] }));
    assert.equal(recovery.freshness.recent.state, "fresh");
    assert.deepEqual(recovery.recentHour.species, []);
  }
});

test("sparse history uses original per-date evidence, accepting explicit corrections", async () => {
  const db = sqliteBinding();
  await request(db, start, (url) => url.searchParams.get("to") === "2026-11-16"
    ? Response.json({ days: [date("2026-11-15", [bird]), date("2026-11-16", [bird])] }) : standard(url));
  const result = await request(db, start + 7 * 3600000, (url) => url.searchParams.get("to") === "2026-11-16"
    ? Response.json({ days: [date("2026-11-15")] }) : broken());
  assert.equal(result.freshness.history.state, "stale");
  assert.deepEqual(result.freshness.history.dateEvidence, [
    { date: "2026-11-15", estimatedAt: new Date(start + 7 * 3600000).toISOString(), retained: false },
    { date: "2026-11-16", estimatedAt: new Date(start).toISOString(), retained: true },
  ]);
});

test("lease limits concurrent cold refreshes and fences expired owners across chunked writes", async () => {
  const db = sqliteBinding();
  const store = yardmicStore(db, "recent");
  const claims = await Promise.all([store.claim(start, "2026-11-18"), store.claim(start, "2026-11-18")]);
  assert.equal(claims.filter(Boolean).length, 1);
  const replacement = await store.claim(start + 30001, "2026-11-18");
  const text = "a".repeat(262137) + "🐦".repeat(70000);
  assert.equal(await store.save(replacement, { x: text }, start + 60000), true);
  assert.equal(await store.save(claims.find(Boolean), { x: "old" }, start + 60000), false);
  assert.deepEqual(await store.read(), { x: text });
});

test("cold outage or missing auth returns unavailable; storage outages still permit live results", async () => {
  assert.equal((await request(sqliteBinding(), start, broken)).status, 503);
  assert.equal((await request(sqliteBinding(), start, standard, "")).status, 503);
  const failedDb = { prepare() { throw new Error("Database unavailable"); } };
  assert.equal((await request(failedDb, start, standard)).recentHour.state, "available");
  const failedWrite = sqliteBinding();
  failedWrite.batch = async () => { throw new Error("Database unavailable"); };
  assert.equal((await request(failedWrite, start, standard)).recentHour.state, "available");
});

test("a cold visitor retains dated effort and an earlier kingfisher through a multiweek outage", async () => {
  const db = sqliteBinding();
  const first = await request(db, start, (url) => url.searchParams.get("to") === "2026-11-16"
    ? Response.json({ days: [date("2026-11-15", [bird]), date("2026-11-16")] }) : broken());
  const late = await request(db, start + 29 * 86400_000, broken);
  assert.equal(late.status, 200);
  assert.deepEqual(late.patterns, first.patterns);
  assert.deepEqual(late.insights, first.insights);
  assert.equal(late.dailyEffort.length, 0);
  assert.equal(late.patterns.dailyEffort.length, 2);
  assert.equal(late.kingfisher.latestAt, first.kingfisher.latestAt);
  assert.equal(late.kingfisher.elapsedMinutes, first.kingfisher.elapsedMinutes + 29 * 1440);
  assert.equal(late.kingfisher.complete, false);
});

test("rollout promotes an existing authenticated edge snapshot during an outage", async () => {
  const db = sqliteBinding();
  const entries = new Map();
  const cache = {
    async match(request) { return entries.get(request.url)?.clone(); },
    async put(request, response) { entries.set(request.url, response); },
  };
  const pending = [];
  const context = { request: new Request("https://example.test/api/yardmic"), env: { YARDMIC_API_KEY: "testkey" },
    waitUntil(promise) { pending.push(promise); } };
  await handleYardmic(context, { now: () => start, fetcher: standard, cache });
  await Promise.all(pending);
  context.env.YARDMIC_DB = db;
  const promoted = await (await handleYardmic(context, { now: () => start + 180000, fetcher: broken, cache })).json();
  assert.equal(promoted.freshness.recent.state, "stale");
  assert.equal(promoted.recentHour.snapshotEstimatedAt, new Date(start).toISOString());
  const cold = await request(db, start + 180001, broken);
  assert.deepEqual(cold.recentHour, promoted.recentHour);
});

test("fresh recent recovery does not remove the last completed date from a frozen history view", async () => {
  const db = sqliteBinding();
  const first = await request(db, start, (url) => url.searchParams.get("to") === "2026-11-18"
    ? Response.json({ days: [date("2026-11-17", [bird]), date("2026-11-18")] }) : standard(url));
  const recovered = await request(db, start + 3 * 86400_000, (url) => url.searchParams.get("to") === "2026-11-21"
    ? standard(url) : broken());
  assert.equal(recovered.freshness.recent.state, "fresh");
  assert.equal(recovered.freshness.history.state, "stale");
  assert.deepEqual(recovered.patterns, first.patterns);
  assert.deepEqual(recovered.insights, first.insights);
  assert.equal(recovered.recentHour.end, "2026-11-21T17:00:00.000Z");
});

test("mixed-date history cannot promote older evidence to a newer timestamp through the edge cache", async () => {
  const db = sqliteBinding();
  const entries = new Map();
  const pending = [];
  const cache = {
    async match(request) { return entries.get(request.url)?.clone(); },
    async put(request, response) { entries.set(request.url, response); },
  };
  const context = { request: new Request("https://example.test/api/yardmic"), env: { YARDMIC_API_KEY: "testkey", YARDMIC_DB: db },
    waitUntil(work) { pending.push(work); } };
  const run = async (time, fetcher) => {
    const summary = await (await handleYardmic(context, { now: () => time, fetcher, cache })).json();
    await Promise.all(pending.splice(0));
    return summary;
  };
  await run(start, (url) => url.searchParams.get("to") === "2026-11-16"
    ? Response.json({ days: [date("2026-11-15"), date("2026-11-16")] }) : standard(url));
  const later = start + 7 * 3600000;
  const mixed = await run(later, (url) => Response.json({ days: [date(url.searchParams.get("to"))] }));
  assert.equal(mixed.freshness.history.dateEvidence.find((row) => row.date === "2026-11-15").retained, true);
  context.env.YARDMIC_DB = sqliteBinding();
  const seeded = await run(later + 1000, broken);
  assert.equal(seeded.freshness.history.dateEvidence.find((row) => row.date === "2026-11-15").estimatedAt, new Date(start).toISOString());
});

test("corrections and late detections remain authoritative after recent rolls over while history is offline", async () => {
  for (const [original, corrected, expected] of [[[bird], [], "no-match"], [[], [bird], "detected"]]) {
    const db = sqliteBinding();
    await request(db, start, (url) => url.searchParams.get("to") === "2026-11-18"
      ? Response.json({ days: [date("2026-11-17", original), date("2026-11-18")] }) : Response.json({ days: [date("2026-11-16")] }));
    const changedAt = start + 180000;
    const changed = await request(db, changedAt, () => Response.json({ days: [date("2026-11-17", corrected), date("2026-11-18")] }));
    const after = await request(db, start + 86400_000, (url) => url.searchParams.get("to") === "2026-11-19"
      ? Response.json({ days: [date("2026-11-18"), date("2026-11-19")] }) : broken());
    assert.equal(after.kingfisher.state, expected);
    assert.deepEqual(after.patterns, changed.patterns);
    assert.deepEqual(after.insights, changed.insights);
    assert.equal(after.range.dateEvidence.find((entry) => entry.date === "2026-11-17").estimatedAt, new Date(changedAt).toISOString());
  }
});
