const INAT_API = "https://api.inaturalist.org/v1/observations";
const PAGE_SIZE = 200;
const MAX_ATTEMPTS = 3;
const INAT_REQUEST_INTERVAL_MS = 1_100;
const INAT_USER_AGENT = "KingfisherHollowCountySpeciesDetector/1.0 (+https://survey.kingfisher-hollow.com/tools/new-county-species/)";
const RESULT_CACHE_SECONDS = 60 * 60;

export class NewCountySpeciesError extends Error {
  constructor(code, message, status = 400, retryable = false) {
    super(message);
    this.code = code;
    this.status = status;
    this.retryable = retryable;
  }
}

function validDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function previousDate(value) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function retryDelay(response, attempt) {
  const retryAfter = Number(response?.headers?.get("retry-after"));
  if (Number.isFinite(retryAfter) && retryAfter > 0) return Math.min(retryAfter * 1_000, 120_000);
  return Math.min(1_000 * (2 ** attempt), 10_000);
}

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export function createRequestPacer({
  delay = wait,
  now = () => Date.now(),
  intervalMs = INAT_REQUEST_INTERVAL_MS,
} = {}) {
  let nextRequestAt = 0;
  return {
    async beforeRequest() {
      const current = now();
      const scheduled = Math.max(current, nextRequestAt);
      nextRequestAt = scheduled + intervalMs;
      if (scheduled > current) await delay(scheduled - current);
    },
  };
}

export function normalizeQuery(searchParams) {
  const placeId = Number(searchParams.get("place_id"));
  const dateFrom = searchParams.get("d1") || "";
  const dateTo = searchParams.get("d2") || "";
  const includeCasualValue = searchParams.get("include_casual") || "false";

  if (!Number.isSafeInteger(placeId) || placeId <= 0) {
    throw new NewCountySpeciesError("invalid_place_id", "place_id must be a positive iNaturalist place ID.");
  }
  if (!validDate(dateFrom) || !validDate(dateTo)) {
    throw new NewCountySpeciesError("invalid_date", "d1 and d2 must use YYYY-MM-DD dates.");
  }
  if (dateFrom > dateTo) {
    throw new NewCountySpeciesError("invalid_date_range", "d1 must be on or before d2.");
  }
  if (!["true", "false"].includes(includeCasualValue)) {
    throw new NewCountySpeciesError(
      "invalid_include_casual",
      "include_casual must be true or false.",
    );
  }
  return {
    placeId,
    dateFrom,
    dateTo,
    includeCasual: includeCasualValue === "true",
  };
}

function qualifyingParams(query) {
  return {
    place_id: String(query.placeId),
    taxon_rank: "species",
    ...(query.includeCasual ? {} : { verifiable: "true" }),
  };
}

async function fetchPage(url, { fetchImpl = fetch, delay = wait, pacer } = {}) {
  let response;
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
    try {
      await pacer?.beforeRequest();
      response = await fetchImpl(url, {
        headers: {
          Accept: "application/json",
          "User-Agent": INAT_USER_AGENT,
        },
      });
    } catch (_error) {
      if (attempt < MAX_ATTEMPTS - 1) {
        await delay(retryDelay(null, attempt));
        continue;
      }
      throw new NewCountySpeciesError(
        "inat_unavailable",
        "iNaturalist could not be reached. Check the connection and try again.",
        502,
        true,
      );
    }
    if ((response.status === 429 || response.status >= 500) && attempt < MAX_ATTEMPTS - 1) {
      await delay(retryDelay(response, attempt));
      continue;
    }
    break;
  }
  if (response.status === 429) {
    throw new NewCountySpeciesError(
      "inat_rate_limited",
      "iNaturalist is limiting requests. Try again in a minute.",
      503,
      true,
    );
  }
  if (!response.ok) {
    throw new NewCountySpeciesError(
      "inat_request_failed",
      `iNaturalist returned HTTP ${response.status}. Retry the request in a moment.`,
      502,
      true,
    );
  }
  let payload;
  try {
    payload = await response.json();
  } catch (_error) {
    throw new NewCountySpeciesError(
      "inat_malformed_response",
      "iNaturalist returned an unexpected response. Retry the request.",
      502,
      true,
    );
  }
  if (!Array.isArray(payload?.results)) {
    throw new NewCountySpeciesError(
      "inat_malformed_response",
      "iNaturalist returned an unexpected response. Retry the request.",
      502,
      true,
    );
  }
  return payload;
}

function urlWith(params) {
  const url = new URL(INAT_API);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return url;
}

function observationCandidate(observation) {
  const taxon = observation?.taxon;
  const id = Number(taxon?.id);
  if (!Number.isSafeInteger(id) || id <= 0 || taxon?.rank !== "species") return null;
  if (!validDate(observation?.observed_on)) return null;
  const observationId = Number(observation?.id);
  if (!Number.isSafeInteger(observationId) || observationId <= 0) return null;
  const scientificName = typeof taxon.name === "string" ? taxon.name.trim() : "";
  if (!scientificName) return null;
  const commonName = taxon.preferred_common_name || taxon.english_common_name || null;
  return {
    taxonId: id,
    scientificName,
    commonName: typeof commonName === "string" && commonName.trim() ? commonName.trim() : null,
    firstObservationDate: observation.observed_on,
    observer: observation?.user?.login || observation?.user?.name || "Unknown observer",
    observationUrl: `https://www.inaturalist.org/observations/${observationId}`,
    observationId,
  };
}

function earlier(left, right) {
  return left.firstObservationDate < right.firstObservationDate
    || (left.firstObservationDate === right.firstObservationDate && left.observationId < right.observationId);
}

export async function fetchPeriodSpecies(query, options = {}) {
  const species = new Map();
  let idAbove = 0;
  while (true) {
    const payload = await fetchPage(urlWith({
      ...qualifyingParams(query),
      d1: query.dateFrom,
      d2: query.dateTo,
      per_page: String(PAGE_SIZE),
      order: "asc",
      order_by: "id",
      id_above: String(idAbove),
    }), options);
    if (payload.results.length === 0) break;
    for (const observation of payload.results) {
      const candidate = observationCandidate(observation);
      if (!candidate) continue;
      const current = species.get(candidate.taxonId);
      if (!current || earlier(candidate, current)) species.set(candidate.taxonId, candidate);
    }
    const lastId = Number(payload.results.at(-1)?.id);
    if (!Number.isSafeInteger(lastId) || lastId <= idAbove) {
      throw new NewCountySpeciesError(
        "inat_malformed_response",
        "iNaturalist returned an invalid observation page. Retry the request.",
        502,
        true,
      );
    }
    idAbove = lastId;
  }
  return [...species.values()];
}

export async function hasEarlierObservation(query, taxonId, options = {}) {
  const payload = await fetchPage(urlWith({
    ...qualifyingParams(query),
    taxon_id: String(taxonId),
    d2: previousDate(query.dateFrom),
    per_page: "1",
    order: "asc",
    order_by: "observed_on",
  }), options);
  return payload.results.length > 0;
}

async function filterSequential(values, predicate) {
  const kept = [];
  for (const value of values) {
    if (await predicate(value)) kept.push(value);
  }
  return kept;
}

export async function detectNewCountySpecies(query, options = {}) {
  const requestOptions = {
    ...options,
    pacer: options.pacer ?? createRequestPacer(),
  };
  const candidates = await fetchPeriodSpecies(query, requestOptions);
  const species = await filterSequential(
    candidates,
    async (candidate) => !(await hasEarlierObservation(query, candidate.taxonId, requestOptions)),
  );
  species.sort((left, right) => (
    left.firstObservationDate.localeCompare(right.firstObservationDate)
      || left.scientificName.localeCompare(right.scientificName)
      || left.taxonId - right.taxonId
  ));
  return {
    query,
    totalNewSpecies: species.length,
    species: species.map(({ observationId, ...speciesRecord }) => speciesRecord),
  };
}

function response(payload, status = 200, requestMethod = "GET", cacheable = false) {
  const headers = new Headers({
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Accept, Content-Type",
    "Cache-Control": cacheable
      ? `public, max-age=${RESULT_CACHE_SECONDS}, s-maxage=${RESULT_CACHE_SECONDS}, stale-while-revalidate=86400`
      : "no-store",
    "Content-Type": "application/json; charset=utf-8",
    "X-Content-Type-Options": "nosniff",
  });
  return new Response(requestMethod === "HEAD" ? null : JSON.stringify(payload), { status, headers });
}

export async function handleNewCountySpecies(context) {
  const method = context.request.method;
  if (method === "OPTIONS") return response(null, 204, method);
  if (method !== "GET" && method !== "HEAD") {
    const result = response({
      error: { code: "method_not_allowed", message: "Use GET, HEAD, or OPTIONS." },
    }, 405, method);
    result.headers.set("Allow", "GET, HEAD, OPTIONS");
    return result;
  }
  try {
    const cache = method === "GET" ? globalThis.caches?.default : null;
    if (cache) {
      const cached = await cache.match(context.request);
      if (cached) return cached;
    }
    const query = normalizeQuery(new URL(context.request.url).searchParams);
    const payload = await detectNewCountySpecies(query);
    const result = response(payload, 200, method, true);
    if (cache) {
      try {
        await cache.put(context.request, result.clone());
      } catch (_error) {
        // A cache miss must never prevent a successful, rate-limited result.
      }
    }
    return result;
  } catch (error) {
    const known = error instanceof NewCountySpeciesError;
    return response({
      error: {
        code: known ? error.code : "internal_error",
        message: known ? error.message : "The county-species detector could not complete the request.",
        retryable: known ? error.retryable : true,
      },
    }, known ? error.status : 500, method);
  }
}
