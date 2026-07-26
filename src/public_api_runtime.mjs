export const API_VERSION = "1.2.0";

const SNAPSHOT_PATH = "/_api-data/moths.json";
const SUMMARY_PATH = "/_api-data/summary.json";
const DEFAULT_LIMIT = 100;
const MAX_LIMIT = 500;
const RATE_LIMIT = 120;
const RATE_WINDOW_MS = 60_000;
const CACHE_CONTROL = "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400";

const ENDPOINT_PARAMETERS = {
  observations: new Set([
    "observation_id", "taxon_id", "family", "scientific_name", "common_name",
    "date_from", "date_to", "year", "limit", "offset", "format",
  ]),
  species: new Set([
    "taxon_id", "scientific_name", "common_name", "family", "date_from",
    "date_to", "year", "limit", "offset", "format",
  ]),
  nights: new Set([
    "taxon_id", "family", "scientific_name", "date_from", "date_to", "year",
    "limit", "offset", "format",
  ]),
  stats: new Set([
    "taxon_id", "family", "scientific_name", "common_name", "date_from",
    "date_to", "year", "format",
  ]),
};

const CSV_FIELDS = {
  observations: [
    "observation_id", "taxon_id", "scientific_name", "common_name", "order",
    "family", "rank", "observed_on", "observed_at", "inat_url",
  ],
  species: [
    "taxon_id", "scientific_name", "common_name", "order", "family", "rank",
    "observation_count", "night_count", "first_seen", "last_seen",
  ],
  nights: ["date", "observation_count", "species_count", "families"],
  stats: [
    "filters", "observation_count", "species_count", "night_count",
    "first_observation_date", "last_observation_date", "generated_at",
    "timezone", "data_version",
  ],
};

let snapshotPromise = null;
let summaryPromise = null;
const rateBuckets = new Map();

class ApiError extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export function __resetForTests() {
  snapshotPromise = null;
  summaryPromise = null;
  rateBuckets.clear();
}

function isIsoDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function isIsoDateTime(value) {
  if (typeof value !== "string" || !/T.+(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    return false;
  }
  return !Number.isNaN(Date.parse(value));
}

function isCanonicalInatUrl(value, observationId) {
  try {
    const url = new URL(value);
    return url.protocol === "https:"
      && url.hostname === "www.inaturalist.org"
      && url.pathname === `/observations/${observationId}`;
  } catch (_error) {
    return false;
  }
}

function requiredSnapshotText(value, field) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`API snapshot contains an invalid ${field}`);
  }
  return value.trim();
}

function normalizeSnapshot(raw) {
  if (!raw || raw.schema_version !== 1 || !Array.isArray(raw.observations)) {
    throw new Error("Unsupported or malformed API snapshot");
  }

  const seen = new Set();
  const observations = [];
  for (const item of raw.observations) {
    const observationId = Number(item.observation_id);
    const taxonId = Number(item.taxon_id);
    if (!Number.isSafeInteger(observationId) || observationId <= 0) {
      throw new Error("API snapshot contains an invalid observation_id");
    }
    if (seen.has(observationId)) continue;
    if (!Number.isSafeInteger(taxonId) || taxonId <= 0) {
      throw new Error("API snapshot contains an invalid taxon_id");
    }
    if (!isIsoDate(item.observed_on)) {
      throw new Error("API snapshot contains an invalid observed_on date");
    }

    const observedAt = requiredSnapshotText(item.observed_at, "observed_at");
    if (!isIsoDateTime(observedAt)) {
      throw new Error("API snapshot contains an invalid observed_at date-time");
    }
    const inatUrl = requiredSnapshotText(item.inat_url, "inat_url");
    if (!isCanonicalInatUrl(inatUrl, observationId)) {
      throw new Error("API snapshot contains an invalid inat_url");
    }

    seen.add(observationId);
    observations.push({
      observation_id: observationId,
      taxon_id: taxonId,
      scientific_name: requiredSnapshotText(item.scientific_name, "scientific_name"),
      common_name: typeof item.common_name === "string" && item.common_name.trim()
        ? item.common_name.trim()
        : null,
      order: requiredSnapshotText(item.order, "order"),
      family: requiredSnapshotText(item.family, "family"),
      rank: requiredSnapshotText(item.rank, "rank"),
      observed_on: item.observed_on,
      observed_at: observedAt,
      inat_url: inatUrl,
    });
  }

  observations.sort((left, right) => {
    const timestampOrder = Date.parse(right.observed_at) - Date.parse(left.observed_at);
    return timestampOrder || right.observation_id - left.observation_id;
  });

  return {
    schema_version: raw.schema_version,
    dataset: raw.dataset || "kingfisher-hollow-moths",
    generated_at: requiredSnapshotText(raw.generated_at, "generated_at"),
    timezone: requiredSnapshotText(raw.timezone, "timezone"),
    data_version: requiredSnapshotText(raw.data_version, "data_version"),
    observations,
  };
}

async function loadSnapshot(env, requestUrl) {
  if (!snapshotPromise) {
    snapshotPromise = (async () => {
      if (!env?.ASSETS || typeof env.ASSETS.fetch !== "function") {
        throw new Error("The Pages ASSETS binding is unavailable");
      }
      const assetUrl = new URL(SNAPSHOT_PATH, requestUrl);
      const response = await env.ASSETS.fetch(assetUrl);
      if (!response.ok) {
        throw new Error(`API snapshot returned HTTP ${response.status}`);
      }
      return normalizeSnapshot(await response.json());
    })().catch((error) => {
      snapshotPromise = null;
      throw error;
    });
  }
  return snapshotPromise;
}

function normalizeSummary(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("Unsupported or malformed biodiversity summary");
  }
  const fields = ["birds", "moths", "totalSpecies"];
  for (const field of fields) {
    if (!Number.isSafeInteger(raw[field]) || raw[field] < 0) {
      throw new Error(`Biodiversity summary contains an invalid ${field}`);
    }
  }
  if (raw.totalSpecies < raw.birds || raw.totalSpecies < raw.moths) {
    throw new Error("Biodiversity summary totalSpecies is inconsistent");
  }
  const updatedAt = requiredSnapshotText(raw.updatedAt, "updatedAt");
  if (
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(updatedAt)
    || !isIsoDateTime(updatedAt)
  ) {
    throw new Error("Biodiversity summary contains an invalid updatedAt date-time");
  }
  return {
    birds: raw.birds,
    moths: raw.moths,
    totalSpecies: raw.totalSpecies,
    updatedAt,
  };
}

async function loadSummary(env, requestUrl) {
  if (!summaryPromise) {
    summaryPromise = (async () => {
      if (!env?.ASSETS || typeof env.ASSETS.fetch !== "function") {
        throw new Error("The Pages ASSETS binding is unavailable");
      }
      const assetUrl = new URL(SUMMARY_PATH, requestUrl);
      const response = await env.ASSETS.fetch(assetUrl);
      if (!response.ok) {
        throw new Error(`Biodiversity summary returned HTTP ${response.status}`);
      }
      return normalizeSummary(await response.json());
    })().catch((error) => {
      summaryPromise = null;
      throw error;
    });
  }
  return summaryPromise;
}

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Accept, Content-Type, If-None-Match",
    "Access-Control-Expose-Headers": [
      "ETag", "X-Result-Count", "X-Total-Count", "X-Limit", "X-Offset",
      "RateLimit-Limit", "RateLimit-Remaining", "RateLimit-Reset",
    ].join(", "),
    "Access-Control-Max-Age": "86400",
  };
}

function baseHeaders({ cache = false, contentType = null, rate = null } = {}) {
  const headers = new Headers(corsHeaders());
  headers.set("Cache-Control", cache ? CACHE_CONTROL : "no-store");
  headers.set("X-API-Version", API_VERSION);
  headers.set("X-Content-Type-Options", "nosniff");
  if (contentType) headers.set("Content-Type", contentType);
  if (rate) {
    headers.set("RateLimit-Limit", String(rate.limit));
    if (rate.remaining !== null) {
      headers.set("RateLimit-Remaining", String(Math.max(0, rate.remaining)));
    }
    headers.set("RateLimit-Reset", String(rate.resetSeconds));
  }
  return headers;
}

function errorResponse(code, message, status = 400, rate = null, extraHeaders = {}) {
  const headers = baseHeaders({
    contentType: "application/json; charset=utf-8",
    rate,
  });
  for (const [name, value] of Object.entries(extraHeaders)) headers.set(name, value);
  return new Response(JSON.stringify({ error: code, message }), { status, headers });
}

function optionsResponse() {
  const headers = baseHeaders();
  headers.set("Cache-Control", "public, max-age=86400");
  return new Response(null, { status: 204, headers });
}

function methodNotAllowed() {
  return errorResponse(
    "method_not_allowed",
    "This public API is read-only; use GET, HEAD, or OPTIONS.",
    405,
    null,
    { Allow: "GET, HEAD, OPTIONS" },
  );
}

function cleanRateBuckets(now) {
  if (rateBuckets.size < 1_000) return;
  for (const [key, bucket] of rateBuckets) {
    if (bucket.resetAt <= now) rateBuckets.delete(key);
  }
}

function localRateLimit(key) {
  const now = Date.now();
  cleanRateBuckets(now);
  let bucket = rateBuckets.get(key);
  if (!bucket || bucket.resetAt <= now) {
    bucket = { count: 0, resetAt: now + RATE_WINDOW_MS };
    rateBuckets.set(key, bucket);
  }
  bucket.count += 1;
  return {
    success: bucket.count <= RATE_LIMIT,
    limit: RATE_LIMIT,
    remaining: RATE_LIMIT - bucket.count,
    resetSeconds: Math.max(1, Math.ceil((bucket.resetAt - now) / 1_000)),
  };
}

async function checkRateLimit(context, endpoint) {
  const client = context.request.headers.get("cf-connecting-ip") || "local-client";
  const key = `${client}:${endpoint}`;
  const binding = context.env?.API_RATE_LIMITER;
  if (binding && typeof binding.limit === "function") {
    try {
      const result = await binding.limit({ key });
      return {
        success: Boolean(result.success),
        limit: RATE_LIMIT,
        remaining: null,
        resetSeconds: 60,
      };
    } catch (_error) {
      // The in-memory fallback keeps the endpoint protected if a binding is misconfigured.
    }
  }
  return localRateLimit(key);
}

function singleParameter(params, name) {
  const values = params.getAll(name);
  if (values.length > 1) {
    throw new ApiError(
      "duplicate_parameter",
      `${name} may only be provided once`,
    );
  }
  return values.length ? values[0] : null;
}

function parseText(params, name) {
  const raw = singleParameter(params, name);
  if (raw === null) return null;
  const value = raw.trim();
  if (!value || value.length > 200) {
    throw new ApiError(
      `invalid_${name}`,
      `${name} must contain between 1 and 200 characters`,
    );
  }
  return value;
}

function parseInteger(params, name, { minimum, maximum = Number.MAX_SAFE_INTEGER }) {
  const raw = singleParameter(params, name);
  if (raw === null) return null;
  if (!/^\d+$/.test(raw)) {
    throw new ApiError(`invalid_${name}`, `${name} must be an integer`);
  }
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new ApiError(
      `invalid_${name}`,
      `${name} must be between ${minimum} and ${maximum}`,
    );
  }
  return value;
}

function parseDate(params, name) {
  const raw = singleParameter(params, name);
  if (raw === null) return null;
  if (!isIsoDate(raw)) {
    throw new ApiError("invalid_date", `${name} must use YYYY-MM-DD format`);
  }
  return raw;
}

function parseYear(params) {
  const raw = singleParameter(params, "year");
  if (raw === null) return null;
  if (!/^\d{4}$/.test(raw)) {
    throw new ApiError("invalid_year", "year must be a four-digit year");
  }
  const year = Number(raw);
  if (year < 1900 || year > 2100) {
    throw new ApiError("invalid_year", "year must be between 1900 and 2100");
  }
  return year;
}

function parseQuery(endpoint, url) {
  const allowed = ENDPOINT_PARAMETERS[endpoint];
  if (!allowed) throw new Error(`Unknown API endpoint ${endpoint}`);
  for (const name of url.searchParams.keys()) {
    if (!allowed.has(name)) {
      throw new ApiError(
        "unknown_parameter",
        `${name} is not supported for /api/${endpoint}`,
      );
    }
  }

  const observationId = allowed.has("observation_id")
    ? parseInteger(url.searchParams, "observation_id", { minimum: 1 })
    : null;
  const taxonId = allowed.has("taxon_id")
    ? parseInteger(url.searchParams, "taxon_id", { minimum: 1 })
    : null;
  const year = allowed.has("year") ? parseYear(url.searchParams) : null;
  const dateFrom = allowed.has("date_from") ? parseDate(url.searchParams, "date_from") : null;
  const dateTo = allowed.has("date_to") ? parseDate(url.searchParams, "date_to") : null;
  if (dateFrom && dateTo && dateFrom > dateTo) {
    throw new ApiError(
      "invalid_date_range",
      "date_from must be earlier than or equal to date_to",
    );
  }

  const formatValue = singleParameter(url.searchParams, "format");
  const format = formatValue === null ? "json" : formatValue.trim().toLowerCase();
  if (!new Set(["json", "csv"]).has(format)) {
    throw new ApiError("invalid_format", "format must be json or csv");
  }

  const paginated = endpoint !== "stats";
  const parsedLimit = paginated
    ? parseInteger(url.searchParams, "limit", { minimum: 1, maximum: MAX_LIMIT })
    : null;
  const parsedOffset = paginated
    ? parseInteger(url.searchParams, "offset", { minimum: 0, maximum: 1_000_000 })
    : null;

  return {
    filters: {
      observation_id: observationId,
      taxon_id: taxonId,
      family: allowed.has("family") ? parseText(url.searchParams, "family") : null,
      scientific_name: allowed.has("scientific_name")
        ? parseText(url.searchParams, "scientific_name")
        : null,
      common_name: allowed.has("common_name")
        ? parseText(url.searchParams, "common_name")
        : null,
      year,
      date_from: dateFrom,
      date_to: dateTo,
    },
    format,
    limit: paginated ? (parsedLimit ?? DEFAULT_LIMIT) : null,
    offset: paginated ? (parsedOffset ?? 0) : null,
  };
}

function sameText(left, right) {
  return typeof left === "string" && left.toLowerCase() === right.toLowerCase();
}

function filterObservations(observations, filters) {
  return observations.filter((item) => {
    if (
      filters.observation_id !== null
      && item.observation_id !== filters.observation_id
    ) return false;
    if (filters.taxon_id !== null && item.taxon_id !== filters.taxon_id) return false;
    if (filters.family !== null && !sameText(item.family, filters.family)) return false;
    if (
      filters.scientific_name !== null
      && !sameText(item.scientific_name, filters.scientific_name)
    ) return false;
    if (
      filters.common_name !== null
      && !sameText(item.common_name, filters.common_name)
    ) return false;
    if (filters.year !== null && item.observed_on.slice(0, 4) !== String(filters.year)) {
      return false;
    }
    if (filters.date_from !== null && item.observed_on < filters.date_from) return false;
    if (filters.date_to !== null && item.observed_on > filters.date_to) return false;
    return true;
  });
}

function speciesRows(observations) {
  const species = new Map();
  for (const item of observations) {
    let row = species.get(item.taxon_id);
    if (!row) {
      row = {
        taxon_id: item.taxon_id,
        scientific_name: item.scientific_name,
        common_name: item.common_name,
        order: item.order,
        family: item.family,
        rank: item.rank,
        observation_count: 0,
        dates: new Set(),
        first_seen: item.observed_on,
        last_seen: item.observed_on,
      };
      species.set(item.taxon_id, row);
    }
    row.observation_count += 1;
    row.dates.add(item.observed_on);
    if (item.observed_on < row.first_seen) row.first_seen = item.observed_on;
    if (item.observed_on > row.last_seen) row.last_seen = item.observed_on;
  }

  return Array.from(species.values()).map((row) => ({
    taxon_id: row.taxon_id,
    scientific_name: row.scientific_name,
    common_name: row.common_name,
    order: row.order,
    family: row.family,
    rank: row.rank,
    observation_count: row.observation_count,
    night_count: row.dates.size,
    first_seen: row.first_seen,
    last_seen: row.last_seen,
  })).sort((left, right) => (
    left.scientific_name.localeCompare(right.scientific_name)
    || left.taxon_id - right.taxon_id
  ));
}

function nightRows(observations) {
  const nights = new Map();
  for (const item of observations) {
    let row = nights.get(item.observed_on);
    if (!row) {
      row = {
        date: item.observed_on,
        observation_count: 0,
        species: new Set(),
        families: new Set(),
      };
      nights.set(item.observed_on, row);
    }
    row.observation_count += 1;
    row.species.add(item.taxon_id);
    row.families.add(item.family);
  }

  return Array.from(nights.values()).map((row) => ({
    date: row.date,
    observation_count: row.observation_count,
    species_count: row.species.size,
    families: Array.from(row.families).sort((left, right) => left.localeCompare(right)),
  })).sort((left, right) => right.date.localeCompare(left.date));
}

function appliedFilters(filters) {
  return Object.fromEntries(
    Object.entries(filters).filter(([_name, value]) => value !== null),
  );
}

function statsRow(observations, snapshot, filters) {
  const dates = observations.map((item) => item.observed_on);
  const applied = appliedFilters(filters);
  return {
    ...(Object.keys(applied).length ? { filters: applied } : {}),
    observation_count: observations.length,
    species_count: new Set(observations.map((item) => item.taxon_id)).size,
    night_count: new Set(dates).size,
    first_observation_date: dates.length ? dates.reduce((a, b) => (a < b ? a : b)) : null,
    last_observation_date: dates.length ? dates.reduce((a, b) => (a > b ? a : b)) : null,
    generated_at: snapshot.generated_at,
    timezone: snapshot.timezone,
    data_version: snapshot.data_version,
  };
}

function collectionPayload(rows, query, snapshot) {
  const results = rows.slice(query.offset, query.offset + query.limit);
  const nextOffset = query.offset + results.length < rows.length
    ? query.offset + results.length
    : null;
  return {
    count: results.length,
    total: rows.length,
    limit: query.limit,
    offset: query.offset,
    next_offset: nextOffset,
    results,
    generated_at: snapshot.generated_at,
    timezone: snapshot.timezone,
    data_version: snapshot.data_version,
  };
}

function csvValue(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join("|");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function csvCell(value) {
  const text = csvValue(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function toCsv(rows, fields) {
  const lines = [fields.map(csvCell).join(",")];
  for (const row of rows) lines.push(fields.map((field) => csvCell(row[field])).join(","));
  return `${lines.join("\r\n")}\r\n`;
}

function hashText(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function representationEtag(snapshot, endpoint, url, format) {
  const query = Array.from(url.searchParams.entries())
    .sort(([leftName, leftValue], [rightName, rightValue]) => (
      leftName.localeCompare(rightName) || leftValue.localeCompare(rightValue)
    ))
    .map(([name, value]) => `${name}=${value}`)
    .join("&");
  return `W/"${snapshot.data_version}-${hashText(`${snapshot.generated_at}:${endpoint}:${format}:${query}`)}"`;
}

function successResponse({ endpoint, request, query, payload, snapshot, rate }) {
  const isCollection = endpoint !== "stats";
  const rows = isCollection ? payload.results : [payload];
  const contentType = query.format === "csv"
    ? "text/csv; charset=utf-8"
    : "application/json; charset=utf-8";
  const headers = baseHeaders({ cache: true, contentType, rate });
  const etag = representationEtag(snapshot, endpoint, new URL(request.url), query.format);
  headers.set("ETag", etag);
  if (isCollection) {
    headers.set("X-Result-Count", String(payload.count));
    headers.set("X-Total-Count", String(payload.total));
    headers.set("X-Limit", String(payload.limit));
    headers.set("X-Offset", String(payload.offset));
  }
  if (query.format === "csv") {
    headers.set(
      "Content-Disposition",
      `inline; filename="kingfisher-hollow-${endpoint}.csv"`,
    );
  }
  if (request.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers });
  }

  const body = query.format === "csv"
    ? toCsv(rows, CSV_FIELDS[endpoint])
    : JSON.stringify(payload);
  return new Response(request.method === "HEAD" ? null : body, { status: 200, headers });
}

export async function handleEndpoint(endpoint, context) {
  const method = context.request.method.toUpperCase();
  if (method === "OPTIONS") return optionsResponse();
  if (!new Set(["GET", "HEAD"]).has(method)) return methodNotAllowed();

  const rate = await checkRateLimit(context, endpoint);
  if (!rate.success) {
    return errorResponse(
      "rate_limited",
      "Too many API requests; try again shortly.",
      429,
      rate,
      { "Retry-After": String(rate.resetSeconds) },
    );
  }

  let query;
  try {
    query = parseQuery(endpoint, new URL(context.request.url));
  } catch (error) {
    if (error instanceof ApiError) {
      return errorResponse(error.code, error.message, error.status, rate);
    }
    throw error;
  }

  let snapshot;
  try {
    snapshot = await loadSnapshot(context.env, context.request.url);
  } catch (error) {
    console.error("Unable to load the public moth API snapshot", error);
    return errorResponse(
      "server_error",
      "The survey data could not be loaded.",
      500,
      rate,
    );
  }

  try {
    const observations = filterObservations(snapshot.observations, query.filters);
    let payload;
    if (endpoint === "observations") {
      payload = collectionPayload(observations, query, snapshot);
    } else if (endpoint === "species") {
      payload = collectionPayload(speciesRows(observations), query, snapshot);
    } else if (endpoint === "nights") {
      payload = collectionPayload(nightRows(observations), query, snapshot);
    } else if (endpoint === "stats") {
      payload = statsRow(observations, snapshot, query.filters);
    } else {
      return errorResponse("not_found", "API endpoint not found", 404, rate);
    }

    return successResponse({
      endpoint,
      request: context.request,
      query,
      payload,
      snapshot,
      rate,
    });
  } catch (error) {
    console.error("Unable to build the public moth API response", error);
    return errorResponse(
      "server_error",
      "The survey request could not be completed.",
      500,
      rate,
    );
  }
}

export async function handleSummary(context) {
  const method = context.request.method.toUpperCase();
  if (method === "OPTIONS") return optionsResponse();
  if (!new Set(["GET", "HEAD"]).has(method)) return methodNotAllowed();

  const rate = await checkRateLimit(context, "summary");
  if (!rate.success) {
    return errorResponse(
      "rate_limited",
      "Too many API requests; try again shortly.",
      429,
      rate,
      { "Retry-After": String(rate.resetSeconds) },
    );
  }

  const url = new URL(context.request.url);
  const firstParameter = url.searchParams.keys().next();
  if (!firstParameter.done) {
    return errorResponse(
      "unknown_parameter",
      `${firstParameter.value} is not supported for /api/summary`,
      400,
      rate,
    );
  }

  let summary;
  try {
    summary = await loadSummary(context.env, context.request.url);
  } catch (error) {
    console.error("Unable to load the biodiversity summary", error);
    return errorResponse(
      "server_error",
      "The biodiversity summary data could not be loaded.",
      500,
      rate,
    );
  }

  const body = JSON.stringify(summary);
  const etag = `W/"summary-${hashText(body)}"`;
  const headers = baseHeaders({
    cache: true,
    contentType: "application/json; charset=utf-8",
    rate,
  });
  headers.set("ETag", etag);
  if (context.request.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers });
  }
  return new Response(method === "HEAD" ? null : body, { status: 200, headers });
}

export function handleNotFound(context) {
  if (context.request.method.toUpperCase() === "OPTIONS") return optionsResponse();
  return errorResponse("not_found", "API endpoint not found", 404);
}
