const INAT_SPECIES_COUNTS_API = "https://api.inaturalist.org/v2/observations/species_counts";
const INAT_OBSERVATIONS_API = "https://api.inaturalist.org/v2/observations";
const SPECIES_COUNT_PAGE_SIZE = 500;
const HISTORY_BATCH_SIZE = 300;
const OBSERVATION_PAGE_SIZE = 200;
const OBSERVATION_BATCH_MAX_TAXA = 180;
const OBSERVATION_BATCH_MAX_EXPECTED_RECORDS = 180;
const MAX_OBSERVATION_BATCHES = 8;
const MAX_PERIOD_SPECIES = 2_000;
const MAX_PERIOD_PAGES = MAX_PERIOD_SPECIES / SPECIES_COUNT_PAGE_SIZE;
const MAX_ATTEMPTS = 2;
const MAX_AUTOMATIC_RETRY_DELAY_MS = 10_000;
const INAT_REQUEST_INTERVAL_MS = 1_100;
const INAT_USER_AGENT = "KingfisherHollowCountySpeciesDetector/1.0 (+https://survey.kingfisher-hollow.com/tools/new-county-species/)";
const RESULT_CACHE_SECONDS = 60 * 60;
const RESULT_CACHE_VERSION = "record-links-v2";
const SPECIES_FIELDS = "(count:!t,taxon:(id:!t,rank:!t,name:!t,preferred_common_name:!t))";
const HISTORY_FIELDS = "(taxon:(id:!t,rank:!t))";
const OBSERVATION_FIELDS = "(uri:!t,observed_on:!t,taxon:(min_species_taxon_id:!t))";

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

function validatedObservationUrl(value) {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:"
      || url.hostname !== "www.inaturalist.org"
      || url.username || url.password || url.port || url.search || url.hash
      || !/^\/observations\/\d+\/?$/.test(url.pathname)) {
      return null;
    }
    return url.toString();
  } catch (_error) {
    return null;
  }
}

function previousDate(value) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString().slice(0, 10);
}

function retryDelay(response, attempt) {
  const retryAfter = Number(response?.headers?.get("retry-after"));
  if (Number.isFinite(retryAfter) && retryAfter > 0) return retryAfter * 1_000;
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
    // species_counts normalizes finer IDs to taxon.min_species_taxon_id. hrank
    // keeps subspecies observations while the returned buckets remain species.
    hrank: "species",
    ...(query.includeCasual ? {} : { verifiable: "true" }),
  };
}

async function fetchPage(url, {
  fetchImpl = fetch,
  delay = wait,
  pacer,
  sendUserAgent = true,
  onRequest,
} = {}) {
  let response;
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
    try {
      await pacer?.beforeRequest();
      onRequest?.({ url: String(url), attempt: attempt + 1 });
      const headers = { Accept: "application/json" };
      if (sendUserAgent) headers["User-Agent"] = INAT_USER_AGENT;
      response = await fetchImpl(url, {
        cache: "default",
        credentials: "omit",
        headers,
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
    if (response.status >= 500 && attempt < MAX_ATTEMPTS - 1) {
      const delayMs = retryDelay(response, attempt);
      if (delayMs <= MAX_AUTOMATIC_RETRY_DELAY_MS) {
        await delay(delayMs);
        continue;
      }
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

function urlWith(path, params) {
  const url = new URL(path);
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, Array.isArray(value) ? value.join(",") : value);
  }
  return url;
}

function speciesCandidate(result) {
  const taxon = result?.taxon;
  const id = Number(taxon?.id);
  if (!Number.isSafeInteger(id) || id <= 0 || taxon?.rank !== "species") return null;
  const scientificName = typeof taxon.name === "string" ? taxon.name.trim() : "";
  if (!scientificName) return null;
  const commonName = taxon.preferred_common_name || taxon.english_common_name || null;
  const periodObservationCount = Number(result?.count);
  return {
    taxonId: id,
    scientificName,
    commonName: typeof commonName === "string" && commonName.trim() ? commonName.trim() : null,
    periodObservationCount: Number.isSafeInteger(periodObservationCount) && periodObservationCount > 0
      ? periodObservationCount
      : 0,
  };
}

export async function fetchPeriodSpecies(query, options = {}) {
  const species = new Map();
  options.onProgress?.({ phase: "period", message: "Fetching species recorded in the selected period…" });
  for (let page = 1; page <= MAX_PERIOD_PAGES; page += 1) {
    const payload = await fetchPage(urlWith(INAT_SPECIES_COUNTS_API, {
      ...qualifyingParams(query),
      d1: query.dateFrom,
      d2: query.dateTo,
      per_page: String(SPECIES_COUNT_PAGE_SIZE),
      page: String(page),
      ttl: "300",
      fields: SPECIES_FIELDS,
    }), options);
    const total = Number(payload.total_results);
    if (Number.isSafeInteger(total) && total > MAX_PERIOD_SPECIES) {
      throw new NewCountySpeciesError(
        "inat_species_list_too_broad",
        "The selected period contains more than 2,000 species. Use a shorter period.",
        422,
        false,
      );
    }
    for (const result of payload.results) {
      const candidate = speciesCandidate(result);
      if (!candidate) continue;
      species.set(candidate.taxonId, candidate);
    }
    if (payload.results.length < SPECIES_COUNT_PAGE_SIZE
      || (Number.isSafeInteger(total) && page * SPECIES_COUNT_PAGE_SIZE >= total)) {
      return [...species.values()];
    }
  }

  throw new NewCountySpeciesError(
    "inat_species_list_too_broad",
    "The selected period contains too many species for an immediate check. Use a shorter period.",
    422,
    false,
  );
}

function taxonBatches(taxonIds) {
  const batches = [];
  for (let index = 0; index < taxonIds.length; index += HISTORY_BATCH_SIZE) {
    batches.push(taxonIds.slice(index, index + HISTORY_BATCH_SIZE));
  }
  return batches;
}

export async function fetchHistoricalSpeciesTaxonIds(query, taxonIds, options = {}) {
  const historicTaxonIds = new Set();
  const batches = taxonBatches(taxonIds);
  options.onProgress?.({
    phase: "history",
    message: `Checking prior records for ${taxonIds.length.toLocaleString()} period species…`,
  });

  for (const batch of batches) {
    const payload = await fetchPage(urlWith(INAT_SPECIES_COUNTS_API, {
      ...qualifyingParams(query),
      d2: previousDate(query.dateFrom),
      taxon_id: batch,
      per_page: String(SPECIES_COUNT_PAGE_SIZE),
      page: "1",
      ttl: "300",
      fields: HISTORY_FIELDS,
    }), options);
    if (Number(payload.total_results) > SPECIES_COUNT_PAGE_SIZE) {
      throw new NewCountySpeciesError(
        "inat_malformed_response",
        "iNaturalist returned more historical taxa than were requested.",
        502,
        true,
      );
    }
    for (const result of payload.results) {
      const id = Number(result?.taxon?.id);
      if (Number.isSafeInteger(id) && id > 0 && result?.taxon?.rank === "species") {
        historicTaxonIds.add(id);
      }
    }
  }
  return historicTaxonIds;
}

function observationRecordBatches(species) {
  const batches = [];
  let current = [];
  let expectedRecords = 0;
  const flush = () => {
    if (current.length === 0) return;
    batches.push({
      species: current,
      perPage: OBSERVATION_PAGE_SIZE,
    });
    current = [];
    expectedRecords = 0;
  };

  for (const candidate of [...species].sort((left, right) => left.taxonId - right.taxonId)) {
    const candidateRecords = Math.max(1, candidate.periodObservationCount);
    if (candidateRecords > OBSERVATION_BATCH_MAX_EXPECTED_RECORDS) {
      flush();
      batches.push({ species: [candidate], perPage: 1 });
      continue;
    }
    if (current.length >= OBSERVATION_BATCH_MAX_TAXA
      || expectedRecords + candidateRecords > OBSERVATION_BATCH_MAX_EXPECTED_RECORDS) {
      flush();
    }
    current.push(candidate);
    expectedRecords += candidateRecords;
  }
  flush();
  return batches;
}

async function fetchObservationRecordBatches(query, batches, options, records) {
  for (const batch of batches) {
    const requestedTaxonIds = new Set(batch.species.map((candidate) => candidate.taxonId));
    const payload = await fetchPage(urlWith(INAT_OBSERVATIONS_API, {
      ...qualifyingParams(query),
      d1: query.dateFrom,
      d2: query.dateTo,
      taxon_id: [...requestedTaxonIds],
      order: "asc",
      order_by: "observed_on",
      per_page: String(batch.perPage),
      page: "1",
      ttl: "300",
      fields: OBSERVATION_FIELDS,
    }), options);
    for (const result of payload.results) {
      const taxon = result?.taxon;
      const speciesTaxonId = Number(taxon?.min_species_taxon_id);
      const recordUrl = validatedObservationUrl(result?.uri);
      if (!recordUrl || !requestedTaxonIds.has(speciesTaxonId)
        || records.has(speciesTaxonId)) {
        continue;
      }
      records.set(speciesTaxonId, {
        recordUrl,
        recordObservedOn: validDate(result?.observed_on) ? result.observed_on : null,
      });
    }
  }
}

export async function fetchObservationRecords(query, species, options = {}) {
  const records = new Map();
  if (species.length === 0) return records;
  options.onProgress?.({
    phase: "records",
    message: `Finding an iNaturalist record for ${species.length.toLocaleString()} new species…`,
  });

  const batches = observationRecordBatches(species);
  if (batches.length > MAX_OBSERVATION_BATCHES) {
    throw new NewCountySpeciesError(
      "inat_record_lookup_too_broad",
      "The result needs too many record lookups for an immediate check. Use a shorter period.",
      422,
      false,
    );
  }
  await fetchObservationRecordBatches(query, batches, options, records);
  const missing = species.filter((candidate) => !records.has(candidate.taxonId));
  if (missing.length > 0) {
    throw new NewCountySpeciesError(
      "inat_record_lookup_inconsistent",
      "iNaturalist changed while the detector was linking records. Retry the search.",
      502,
      true,
    );
  }
  return records;
}

export async function detectNewCountySpecies(query, options = {}) {
  let upstreamRequests = 0;
  const callerOnRequest = options.onRequest;
  const requestOptions = {
    ...options,
    pacer: options.pacer ?? createRequestPacer(),
    onRequest: (details) => {
      upstreamRequests += 1;
      callerOnRequest?.(details);
    },
  };
  const candidates = await fetchPeriodSpecies(query, requestOptions);
  const candidateTaxonIds = candidates
    .map((candidate) => candidate.taxonId)
    .sort((left, right) => left - right);
  const historicTaxonIds = candidates.length === 0
    ? new Set()
    : await fetchHistoricalSpeciesTaxonIds(
      query,
      candidateTaxonIds,
      requestOptions,
    );
  const newSpecies = candidates.filter((candidate) => !historicTaxonIds.has(candidate.taxonId));
  const records = await fetchObservationRecords(query, newSpecies, requestOptions);
  const species = newSpecies.map((candidate) => ({
    ...candidate,
    ...records.get(candidate.taxonId),
  }));
  species.sort((left, right) => (
    left.scientificName.localeCompare(right.scientificName)
      || left.taxonId - right.taxonId
  ));
  return {
    query,
    totalNewSpecies: species.length,
    species,
    meta: {
      source: "iNaturalist v2 species counts and observations",
      upstreamRequests,
    },
  };
}

function response(payload, status = 200, requestMethod = "GET", cacheable = false) {
  const headers = new Headers({
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Accept, Content-Type",
    "Cache-Control": cacheable
      ? `public, max-age=${RESULT_CACHE_SECONDS}, s-maxage=${RESULT_CACHE_SECONDS}`
      : "no-store",
    "Content-Type": "application/json; charset=utf-8",
    "X-Content-Type-Options": "nosniff",
  });
  const body = requestMethod === "HEAD" || status === 204 ? null : JSON.stringify(payload);
  return new Response(body, { status, headers });
}

function resultCacheRequest(request, query) {
  const url = new URL(request.url);
  url.search = new URLSearchParams({
    place_id: String(query.placeId),
    d1: query.dateFrom,
    d2: query.dateTo,
    include_casual: String(query.includeCasual),
    _result_schema: RESULT_CACHE_VERSION,
  });
  return new Request(url.toString(), { method: "GET" });
}

export async function handleNewCountySpecies(context) {
  const method = context.request.method;
  if (method === "OPTIONS") return response(null, 204, method);
  if (method === "HEAD") return response(null, 204, method);
  if (method !== "GET") {
    const result = response({
      error: { code: "method_not_allowed", message: "Use GET, HEAD, or OPTIONS." },
    }, 405, method);
    result.headers.set("Allow", "GET, HEAD, OPTIONS");
    return result;
  }
  try {
    const query = normalizeQuery(new URL(context.request.url).searchParams);
    const cache = globalThis.caches?.default;
    const cacheRequest = cache ? resultCacheRequest(context.request, query) : null;
    if (cache) {
      const cached = await cache.match(cacheRequest);
      if (cached) return cached;
    }
    const payload = await detectNewCountySpecies(query);
    const result = response(payload, 200, method, true);
    if (cache) {
      try {
        await cache.put(cacheRequest, result.clone());
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
