import { normalizeYardmicDays, shiftYardmicRange, summarizeYardmic, yardmicRanges } from "./yardmic.mjs";

import { yardmicStore } from "./yardmic_store.mjs";

const UPSTREAM = "https://yardmic.aviandavies.workers.dev/api/v1/minutes";
const TIMEOUT_MS = 5000;
const MAX_BYTES = 2 * 1024 * 1024;
const HOUR_SECONDS = 3600;
const DAY_SECONDS = 24 * HOUR_SECONDS;
const SOURCE_AGE_HEADER = "X-YardMic-Source-Age";
const SOURCE_MAX_AGE_HEADER = "X-YardMic-Source-Max-Age";
const SNAPSHOT_AT_HEADER = "X-YardMic-Snapshot-Estimated-At";
const SNAPSHOT_BASIS_HEADER = "X-YardMic-Snapshot-Basis";
// Bound the normal request deadline plus the integer Age header's resolution.
const SOURCE_ESTIMATE_JITTER_MS = TIMEOUT_MS + 1000;
const POLICIES = {
  recent: { freshSeconds: 120, retainedSeconds: DAY_SECONDS, lookbackDays: 1, retainSnapshotDates: true },
  history: { freshSeconds: 6 * HOUR_SECONDS, retainedSeconds: 7 * DAY_SECONDS, lookbackDays: 7 },
};

function cacheRequest(request, range) {
  const url = new URL("/api/yardmic", request.url);
  url.searchParams.set("cached-range-v1", `${range.start}--${range.end}`);
  return new Request(url);
}

function discardBody(response) {
  if (response.body) void response.body.cancel().catch(() => {});
}

async function readBoundedJson(response) {
  const length = Number(response.headers.get("Content-Length"));
  if (!response.body || length > MAX_BYTES) {
    discardBody(response);
    throw new Error("Invalid YardMic response size");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let total = 0;
  let body = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAX_BYTES) throw new Error("Invalid YardMic response size");
      body += decoder.decode(value, { stream: true });
    }
    return JSON.parse(body + decoder.decode());
  } catch (error) {
    void reader.cancel().catch(() => {});
    throw error;
  } finally {
    reader.releaseLock();
  }
}

function boundedSeconds(value) {
  if (typeof value !== "string" || !/^\d+$/.test(value)) return null;
  const seconds = Number(value);
  return seconds <= DAY_SECONDS ? seconds : null;
}

function sourceMaxAge(cacheControl) {
  if (!cacheControl) return null;
  // Commas inside quoted directive arguments do not start new directives.
  const parts = cacheControl.match(/(?:[^",]|"(?:\\.|[^"\\])*")+|,/g) ?? [];
  if (parts.join("") !== cacheControl) return null;
  const directives = parts.filter((part) => /^\s*max-age(?:\s*=|\s*$)/i.test(part));
  if (directives.length !== 1) return null;
  const match = /^\s*max-age\s*=\s*(?:"(\d+)"|(\d+))\s*$/i.exec(directives[0]);
  return boundedSeconds(match?.[1] ?? match?.[2]);
}

function describeSourceCache(receivedMs, ageSecondsAtRetrieval, maxAgeSeconds) {
  if (ageSecondsAtRetrieval === null && maxAgeSeconds === null) return null;
  return {
    ageSecondsAtRetrieval,
    maxAgeSeconds,
    cachedAt: ageSecondsAtRetrieval === null
      ? null
      : new Date(receivedMs - ageSecondsAtRetrieval * 1000).toISOString(),
  };
}

function describeSnapshot(retrievedAt, sourceCache) {
  return sourceCache?.cachedAt
    ? { estimatedAt: sourceCache.cachedAt, basis: "source-response-estimate" }
    : { estimatedAt: retrievedAt, basis: retrievedAt ? "retrieval-estimate" : "unknown" };
}

function normalizedIdentity(days) {
  return JSON.stringify(days.map((day) => ({
    ...day, species: [...day.species].sort((left, right) => left.code.localeCompare(right.code)),
  })));
}

function retainSnapshot(snapshot, days, cached) {
  if (!cached || normalizedIdentity(days) !== normalizedIdentity(cached.days)) return snapshot;
  // No Age provides no evidence of a new response generation, even if a quiet
  // payload was fetched again. Integer Age values also introduce receipt jitter.
  if (snapshot.basis === "retrieval-estimate"
    || (cached.snapshot.basis === "source-response-estimate"
      && Math.abs(Date.parse(snapshot.estimatedAt) - Date.parse(cached.snapshot.estimatedAt)) <= SOURCE_ESTIMATE_JITTER_MS)) {
    return cached.snapshot;
  }
  return snapshot;
}

async function getCached(cache, request, cachedRange, apiKey, now, retainedSeconds) {
  if (!cache) return null;
  try {
    const response = await cache.match(cacheRequest(request, cachedRange));
    if (!response?.ok) return null;
    const receivedMs = Date.parse(response.headers.get("X-YardMic-Retrieved-At"));
    const ageMs = now - receivedMs;
    if (!Number.isFinite(ageMs) || ageMs < 0 || ageMs >= retainedSeconds * 1000) {
      discardBody(response);
      return null;
    }
    const days = normalizeYardmicDays(await readBoundedJson(response), { range: cachedRange, apiKey });
    const sourceCache = describeSourceCache(
      receivedMs,
      boundedSeconds(response.headers.get(SOURCE_AGE_HEADER)),
      boundedSeconds(response.headers.get(SOURCE_MAX_AGE_HEADER)),
    );
    const retrievedAt = new Date(receivedMs).toISOString();
    let snapshot = describeSnapshot(retrievedAt, sourceCache);
    const estimatedAt = response.headers.get(SNAPSHOT_AT_HEADER);
    const basis = response.headers.get(SNAPSHOT_BASIS_HEADER);
    const estimatedMs = Date.parse(estimatedAt);
    if (Number.isFinite(estimatedMs) && estimatedMs <= receivedMs
      && (basis === "source-response-estimate" || basis === "retrieval-estimate")) {
      snapshot = { estimatedAt: new Date(estimatedMs).toISOString(), basis };
    }
    return { days, retrievedAt, ageMs, sourceCache, snapshot };
  } catch {
    return null;
  }
}

async function fetchSegment(fetcher, range, apiKey, timeoutMs) {
  const url = new URL(UPSTREAM);
  url.searchParams.set("from", range.start);
  url.searchParams.set("to", range.end);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher(url, {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${apiKey}`,
        "User-Agent": "Kingfisher Hollow Biodiversity Survey (YardMic summary)",
      },
      signal: controller.signal,
      redirect: "manual",
      cache: "no-store",
      cf: { cacheTtlByStatus: { "200-599": -1 } },
    });
    if (!response.ok) {
      discardBody(response);
      throw new Error("YardMic request failed");
    }
    return {
      days: normalizeYardmicDays(await readBoundedJson(response), { range, apiKey }),
      sourceAge: boundedSeconds(response.headers.get("Age")),
      sourceMaxAge: sourceMaxAge(response.headers.get("Cache-Control")),
    };
  } finally {
    clearTimeout(timeout);
  }
}

function segment(days, state, retrievedAt = null, sourceCache = null, snapshot = describeSnapshot(retrievedAt, sourceCache)) {
  return { days, freshness: { state, retrievedAt, sourceCache, snapshot } };
}

async function loadSegment(context, { range, policy, apiKey, fetcher, cache, clock, requestTime, timeoutMs }) {
  const get = (cachedRange) => getCached(cache, context.request, cachedRange, apiKey, requestTime, policy.retainedSeconds);
  const cached = await get(range);
  if (cached && cached.ageMs < policy.freshSeconds * 1000) {
    return segment(cached.days, "fresh", cached.retrievedAt, cached.sourceCache, cached.snapshot);
  }

  let upstream;
  try {
    upstream = await fetchSegment(fetcher, range, apiKey, timeoutMs);
  } catch {
    if (cached) return segment(cached.days, "stale", cached.retrievedAt, cached.sourceCache, cached.snapshot);
    // A failed fetch just after midnight can still use overlapping dates from an earlier window.
    const candidates = await Promise.all(Array.from({ length: policy.lookbackDays }, (_, index) => (
      get(shiftYardmicRange(range, -(index + 1)))
    )));
    for (const previous of candidates) {
      // A snapshot just after midnight still needs the preceding date, even
      // after that date moves out of today's recent query. The final merge is
      // deduplicated and remains inside the actual-current 31-date bound.
      if (previous && policy.retainSnapshotDates) {
        return segment(previous.days, "stale", previous.retrievedAt, previous.sourceCache, previous.snapshot);
      }
      const retained = previous?.days.filter(({ date }) => date >= range.start && date <= range.end);
      if (retained?.length) return segment(retained, "stale", previous.retrievedAt, previous.sourceCache, previous.snapshot);
    }
    return segment([], "unavailable");
  }

  const { days, sourceAge, sourceMaxAge } = upstream;
  const receivedMs = clock();
  const retrievedAt = new Date(receivedMs).toISOString();
  const sourceCache = describeSourceCache(receivedMs, sourceAge, sourceMaxAge);
  const snapshot = retainSnapshot(describeSnapshot(retrievedAt, sourceCache), days, cached);
  const value = segment(days, "fresh", retrievedAt, sourceCache, snapshot);
  cacheSegment(context, cache, range, policy, value);
  return value;
}

function cacheSegment(context, cache, range, policy, value) {
  if (!cache || value.freshness.state !== "fresh") return;
  const { retrievedAt, sourceCache, snapshot } = value.freshness;
  const headers = new Headers({
    "Cache-Control": `max-age=${policy.retainedSeconds}`,
    "X-YardMic-Retrieved-At": retrievedAt,
    [SNAPSHOT_AT_HEADER]: snapshot.estimatedAt,
    [SNAPSHOT_BASIS_HEADER]: snapshot.basis,
  });
  if (sourceCache?.ageSecondsAtRetrieval != null) headers.set(SOURCE_AGE_HEADER, String(sourceCache.ageSecondsAtRetrieval));
  if (sourceCache?.maxAgeSeconds != null) headers.set(SOURCE_MAX_AGE_HEADER, String(sourceCache.maxAgeSeconds));
  const pending = Promise.resolve().then(() => (
    cache.put(cacheRequest(context.request, range), Response.json({ days: value.days }, { headers }))
  )).catch(() => {});
  context.waitUntil(pending);
}

const RETENTION_MS = 30 * DAY_SECONDS * 1000;
const unavailableSegment = () => segment([], "unavailable");

function usableEvidence(stamp, now) {
  const age = now - Date.parse(stamp);
  return age >= 0 && age < RETENTION_MS;
}

function markStale(value) {
  if (!value.days.length) return value;
  const { freshness } = value;
  return { ...value, freshness: { ...freshness, state: "stale",
    ...(freshness.dateEvidence && { dateEvidence: freshness.dateEvidence.map((entry) => ({ ...entry, retained: true })) }) } };
}

function durableView(saved, name, now, range, apiKey, failed = false) {
  if (!saved || !usableEvidence(saved.freshness?.snapshot?.estimatedAt, now)) return unavailableSegment();
  const { freshness } = saved;
  let days = normalizeYardmicDays({ days: saved.days }, { range: freshness.range, apiKey });
  let evidence;
  if (name === "history") {
    evidence = freshness.dateEvidence.filter((entry) => usableEvidence(entry.estimatedAt, now));
    const dates = new Set(evidence.map(({ date }) => date));
    days = days.filter(({ date }) => dates.has(date));
  }
  if (!days.length) return unavailableSegment();
  const result = { days, freshness: { ...freshness, ...(evidence && { dateEvidence: evidence }) } };
  if (name === "history" && saved.companion && usableEvidence(saved.companion.estimatedAt, now)) {
    const priorDate = shiftYardmicRange(freshness.range, 1).end;
    const [day] = normalizeYardmicDays({ days: [saved.companion.day] }, { range: { start: priorDate, end: priorDate }, apiKey });
    result.companion = { day, estimatedAt: saved.companion.estimatedAt };
  }
  return failed || freshness.range.end !== range.end || now - Date.parse(freshness.retrievedAt) >= POLICIES[name].freshSeconds * 1000
    ? markStale(result) : result;
}

function reconcileHistory(current, previous) {
  const { range, snapshot } = current.freshness;
  const records = new Map(current.days.map((day) => [day.date, {
    day, evidence: { date: day.date, estimatedAt: snapshot.estimatedAt, retained: false },
  }]));
  // Bound reconciled history as well as each incoming request. Prefer current
  // validated records and the most recently observed missing dates.
  let bytes = new TextEncoder().encode(JSON.stringify(current.days)).length;
  const prior = new Map(previous.days.map((day) => [day.date, day]));
  const priorEvidence = [...(previous.freshness.dateEvidence ?? [])];
  if (previous.companion) {
    const { day, estimatedAt } = previous.companion;
    prior.set(day.date, day);
    priorEvidence.push({ date: day.date, estimatedAt, retained: true });
  }
  for (const evidence of priorEvidence.sort((a, b) => b.estimatedAt.localeCompare(a.estimatedAt))) {
    if (evidence.date < range.start || evidence.date > range.end) continue;
    const incoming = records.get(evidence.date);
    if (incoming && incoming.evidence.estimatedAt >= evidence.estimatedAt) continue;
    const day = prior.get(evidence.date);
    if (!day) continue;
    const delta = new TextEncoder().encode(JSON.stringify(day)).length
      - (incoming ? new TextEncoder().encode(JSON.stringify(incoming.day)).length : 0);
    if (bytes + delta > MAX_BYTES && !incoming) continue;
    bytes += delta;
    records.set(day.date, { day, evidence: { ...evidence, retained: true } });
  }
  const sorted = [...records.values()].sort((a, b) => a.day.date.localeCompare(b.day.date));
  const dateEvidence = sorted.map(({ evidence }) => evidence);
  return { days: sorted.map(({ day }) => day), freshness: { ...current.freshness,
    state: dateEvidence.some(({ retained }) => retained) ? "stale" : "fresh", dateEvidence } };
}

// During rollout, a populated edge can seed a new database even when the
// upstream is already offline. Preserve the original source and receipt clocks.
async function existingEdgeSnapshot(context, options, name) {
  const { cache, range, apiKey, requestTime, policy } = options;
  if (!cache) return unavailableSegment();
  for (let offset = 0; offset <= policy.lookbackDays; offset++) {
    const savedRange = shiftYardmicRange(range, -offset);
    const old = await getCached(cache, context.request, savedRange, apiKey, requestTime, policy.retainedSeconds);
    if (!old?.days.length || !usableEvidence(old.snapshot.estimatedAt, requestTime)) continue;
    const value = segment(old.days, "stale", old.retrievedAt, old.sourceCache, old.snapshot);
    value.freshness.range = savedRange;
    if (name === "history") {
      value.freshness.dateEvidence = value.days.map(({ date }) => ({ date, estimatedAt: old.snapshot.estimatedAt, retained: true }));
    } else {
      const anchorDate = yardmicRanges(Date.parse(old.snapshot.estimatedAt)).recent.end;
      if (!value.days.some(({ date }) => date === anchorDate)) continue;
    }
    return value;
  }
  return unavailableSegment();
}

// History refreshes less frequently than recent. A later review or detection
// from recent must still win after midnight moves that date out of its window.
async function latestCompletedDate(db, date, prior, now, apiKey) {
  try {
    const saved = await yardmicStore(db, "recent").completedDate(date, new Date(now - RETENTION_MS).toISOString());
    if (!saved || !usableEvidence(saved.estimatedAt, now) || (prior && saved.estimatedAt <= prior.estimatedAt)) return prior;
    const [day] = normalizeYardmicDays({ days: [saved.day] }, { range: { start: date, end: date }, apiKey });
    return { day, estimatedAt: saved.estimatedAt };
  } catch {
    return prior;
  }
}

async function loadDurable(context, options, name, recentResult) {
  const { apiKey, range, requestTime, clock, fetcher, timeoutMs, policy } = options;
  const store = yardmicStore(context.env.YARDMIC_DB, name);
  let previous = unavailableSegment();
  let token;
  try {
    // Read after acquiring the lease so a newly claimed writer observes the
    // commit of the writer it follows.
    if (apiKey) token = await store.claim(requestTime, range.end);
    try {
      previous = durableView(await store.read(), name, requestTime, range, apiKey, !apiKey);
    } catch (error) {
      // A lease holder can repair unreadable saved data with a validated refresh.
      if (!token) throw error;
    }
    if (!token) {
      return (await store.status())?.failures ? markStale(previous) : previous;
    }
  } catch {
    if (!apiKey) return previous;
    return loadSegment(context, options);
  }

  let candidate;
  try {
    const { days, sourceAge, sourceMaxAge } = await fetchSegment(fetcher, range, apiKey, timeoutMs);
    if (!days.length) throw new Error("No returned dates");
    const receivedMs = clock();
    const retrievedAt = new Date(receivedMs).toISOString();
    const sourceCache = describeSourceCache(receivedMs, sourceAge, sourceMaxAge);
    const snapshot = retainSnapshot(describeSnapshot(retrievedAt, sourceCache), days, previous.days.length
      ? { days: previous.days, snapshot: previous.freshness.snapshot } : null);
    if (!usableEvidence(snapshot.estimatedAt, receivedMs)
      || snapshot.estimatedAt < (previous.freshness.snapshot?.estimatedAt ?? "")) throw new Error("Older evidence");
    candidate = segment(days, "fresh", retrievedAt, sourceCache, snapshot);
    candidate.freshness.range = { ...range };
    if (name === "recent") {
      const anchorDate = yardmicRanges(Date.parse(snapshot.estimatedAt)).recent.end;
      if (!days.some(({ date }) => date === anchorDate)) throw new Error("Missing snapshot date");
    }
    if (name === "history") {
      // The final completed date for patterns comes from the recent query.
      // Preserve that day with this fenced history write. The recent-hour
      // calculation continues to use its own original snapshot exclusively.
      const recent = await recentResult;
      if (previous.freshness.range) {
        const priorDate = shiftYardmicRange(previous.freshness.range, 1).end;
        previous.companion = await latestCompletedDate(context.env.YARDMIC_DB, priorDate, previous.companion, clock(), apiKey);
        if (previous.companion && recent.days.some((day) => day.date === priorDate)
          && recent.freshness.snapshot.estimatedAt >= previous.companion.estimatedAt) {
          previous.companion = { day: recent.days.find((day) => day.date === priorDate), estimatedAt: recent.freshness.snapshot.estimatedAt };
        }
      }
      candidate = reconcileHistory(candidate, previous);
      const lastCompleteDate = shiftYardmicRange(range, 1).end;
      const prior = previous.companion?.day.date === lastCompleteDate ? previous.companion : null;
      const day = recent.days.find((entry) => entry.date === lastCompleteDate);
      if (day && (!prior || recent.freshness.snapshot.estimatedAt >= prior.estimatedAt)) {
        candidate.companion = { day, estimatedAt: recent.freshness.snapshot.estimatedAt };
      } else if (prior) {
        candidate.companion = prior;
      }
    }
  } catch {
    if (!previous.days.length) {
      const edge = await existingEdgeSnapshot(context, options, name);
      if (edge.days.length) {
        const won = await store.save(token, edge, clock() + 120000).catch(() => null);
        if (won === false) return durableView(await store.read(), name, clock(), range, apiKey);
        return edge;
      }
    }
    await store.fail(token, clock()).catch(() => {});
    return markStale(previous);
  }

  try {
    const returned = new Set(candidate.days.map(({ date }) => date));
    const completed = name === "recent" ? previous.days.filter(({ date }) => !returned.has(date))
      .map((day) => ({ day, estimatedAt: previous.freshness.snapshot.estimatedAt })) : [];
    const saved = await store.save(token, candidate, clock() + policy.freshSeconds * 1000, completed,
      new Date(clock() - RETENTION_MS).toISOString());
    if (!saved) return durableView(await store.read(), name, clock(), range, apiKey);
  } catch {
    // A valid live response remains usable if persistence is temporarily down.
  }
  cacheSegment(context, options.cache, range, policy, candidate);
  return candidate;
}

function json(summary, status, headers = {}) {
  return Response.json(summary, {
    status,
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", ...headers },
  });
}

function segmentEstimatedAt({ freshness }) {
  return Date.parse(freshness.snapshot?.estimatedAt ?? freshness.retrievedAt) || 0;
}

export async function handleYardmic(context, {
  fetcher = fetch,
  cache = globalThis.caches?.default,
  now = Date.now,
  timeoutMs = TIMEOUT_MS,
} = {}) {
  const requestTime = now();
  const unavailable = () => summarizeYardmic(null, { now: requestTime });
  if (context.request.method !== "GET") return json(unavailable(), 405, { Allow: "GET" });
  if (new URL(context.request.url).search) return json(unavailable(), 400);

  let apiKey = context.env?.YARDMIC_API_KEY;
  if (typeof apiKey !== "string" || !apiKey.trim() || apiKey.trim() !== apiKey || /[\r\n]/.test(apiKey)) {
    apiKey = null;
    if (!context.env?.YARDMIC_DB) return json(unavailable(), 503);
  }

  const ranges = yardmicRanges(requestTime);
  const shared = { apiKey, fetcher, cache, clock: now, requestTime, timeoutMs };
  const load = (name, recentResult) => {
    const options = { ...shared, range: ranges[name], policy: POLICIES[name] };
    return context.env?.YARDMIC_DB ? loadDurable(context, options, name, recentResult) : loadSegment(context, options);
  };
  const recentResult = load("recent");
  const [recent, history] = await Promise.all([recentResult, load("history", recentResult)]);
  const byDate = new Map(history.days.map((day) => [day.date, day]));
  const dateEvidence = new Map(history.days.map(({ date }) => [date, {
    date, estimatedAt: history.freshness.snapshot.estimatedAt, retained: history.freshness.state === "stale",
  }]));
  for (const entry of history.freshness.dateEvidence ?? []) dateEvidence.set(entry.date, entry);
  for (const day of recent.days) {
    const prior = dateEvidence.get(day.date);
    if (!prior || segmentEstimatedAt(recent) >= Date.parse(prior.estimatedAt)) {
      byDate.set(day.date, day);
      dateEvidence.set(day.date, { date: day.date, estimatedAt: recent.freshness.snapshot.estimatedAt,
        retained: recent.freshness.state === "stale" });
    }
  }
  const mergedDays = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
  let companionDay;
  if (context.env?.YARDMIC_DB && history.freshness.range) {
    const comparisonDate = shiftYardmicRange(history.freshness.range, 1).end;
    if (!recent.days.some((day) => day.date === comparisonDate)) {
      history.companion = await latestCompletedDate(context.env.YARDMIC_DB, comparisonDate, history.companion, requestTime, apiKey);
    }
  }
  if (history.companion) {
    const { day, estimatedAt } = history.companion;
    const existing = dateEvidence.get(day.date);
    if (!existing || estimatedAt > existing.estimatedAt) {
      companionDay = day;
      dateEvidence.set(day.date, { date: day.date, estimatedAt, retained: true });
    }
  }
  const summary = summarizeYardmic({ days: mergedDays }, {
    now: now(),
    freshness: { recent: recent.freshness, history: history.freshness },
    recentSnapshotDays: recent.days,
    companionDay,
    historyAnchorDate: history.freshness.range && shiftYardmicRange(history.freshness.range, 2).end,
  });
  summary.range.dateEvidence = summary.range.returnedDates.map((date) => dateEvidence.get(date));
  const detectionDate = summary.kingfisher.latestLocal?.slice(0, 10);
  summary.kingfisher.evidenceEstimatedAt = dateEvidence.get(detectionDate)?.estimatedAt ?? null;
  if (summary.state === "unavailable" && (recent.days.length || history.days.length)) summary.state = "partial";
  return json(summary, summary.state === "unavailable" ? 503 : 200);
}
