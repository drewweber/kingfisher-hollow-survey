import { normalizeYardmicDays, shiftYardmicRange, summarizeYardmic, yardmicRanges } from "./yardmic.mjs";

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
  if (cache) {
    const headers = new Headers({
      "Cache-Control": `max-age=${policy.retainedSeconds}`,
      "X-YardMic-Retrieved-At": retrievedAt,
      [SNAPSHOT_AT_HEADER]: snapshot.estimatedAt,
      [SNAPSHOT_BASIS_HEADER]: snapshot.basis,
    });
    if (sourceAge !== null) headers.set(SOURCE_AGE_HEADER, String(sourceAge));
    if (sourceMaxAge !== null) headers.set(SOURCE_MAX_AGE_HEADER, String(sourceMaxAge));
    const pending = Promise.resolve().then(() => (
      cache.put(cacheRequest(context.request, range), Response.json({ days }, { headers }))
    )).catch(() => {});
    context.waitUntil(pending);
  }
  return segment(days, "fresh", retrievedAt, sourceCache, snapshot);
}

function json(summary, status, headers = {}) {
  return Response.json(summary, {
    status,
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", ...headers },
  });
}

function mergeDays(segments) {
  return [...new Map(segments.flatMap(({ days }) => days.map((day) => [day.date, day]))).values()];
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

  const apiKey = context.env?.YARDMIC_API_KEY;
  if (typeof apiKey !== "string" || !apiKey.trim() || apiKey.trim() !== apiKey || /[\r\n]/.test(apiKey)) {
    return json(unavailable(), 503);
  }

  const ranges = yardmicRanges(requestTime);
  const shared = { apiKey, fetcher, cache, clock: now, requestTime, timeoutMs };
  const [recent, history] = await Promise.all([
    loadSegment(context, { ...shared, range: ranges.recent, policy: POLICIES.recent }),
    loadSegment(context, { ...shared, range: ranges.history, policy: POLICIES.history }),
  ]);
  // A retained midnight snapshot may overlap the history query. Current history
  // and kingfisher results use the newest evidence for that date, while the
  // recent-hour rows stay attached to the retained recent source snapshot,
  // including any dates it was missing. Later history cannot fill those gaps.
  const mergedDays = mergeDays([history, recent].sort((left, right) => segmentEstimatedAt(left) - segmentEstimatedAt(right)));
  const summary = summarizeYardmic({ days: mergedDays }, {
    now: now(),
    freshness: { recent: recent.freshness, history: history.freshness },
    recentSnapshotDays: recent.days,
  });
  return json(summary, summary.state === "unavailable" ? 503 : 200);
}
