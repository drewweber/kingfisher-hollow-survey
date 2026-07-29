const INAT_API = "https://api.inaturalist.org/v1";
const INAT_OBSERVATION = "https://www.inaturalist.org/observations/";
const API_USER_AGENT = "Kingfisher-Hollow-Social-Export/1.0 (survey.kingfisher-hollow.com)";
const CACHE_TTL_SECONDS = 30 * 60;
const MAX_API_RESULTS = 10_000;
const API_PAGE_SIZE = 200;
const INAT_MAX_ATTEMPTS = 3;
const BUTTERFLY_TAXON_ID = 47224;
const inFlightInatPages = new Map();

export const TAXON_GROUPS = Object.freeze({
  moths: { label: "Moths", taxonId: 47157, excludeTaxonId: BUTTERFLY_TAXON_ID },
  butterflies: { label: "Butterflies", taxonId: BUTTERFLY_TAXON_ID },
  birds: { label: "Birds", taxonId: 3 },
  fungi: { label: "Fungi", taxonId: 47170 },
  plants: { label: "Plants", taxonId: 47126 },
  amphibians: { label: "Amphibians", taxonId: 20978 },
  reptiles: { label: "Reptiles", taxonId: 26036 },
  mammals: { label: "Mammals", taxonId: 40151 },
  insects: { label: "Insects", taxonId: 47158 },
  arachnids: { label: "Arachnids", taxonId: 47119 },
  mollusks: { label: "Mollusks", taxonId: 47115 },
});

export const PRESETS = Object.freeze({
  "national-moth-week-2026": {
    id: "national-moth-week-2026",
    label: "National Moth Week 2026",
    dateFrom: "2026-07-18",
    dateTo: "2026-07-26",
    taxonGroup: "moths",
    observer: "drewweber",
    outputFormat: "instagram-square",
    gridSize: "5x4",
    maximumSlides: 10,
    includeCover: true,
    includeSpeciesLabels: true,
    includeUnresolvedTaxa: false,
    theme: "kingfisher-quiet",
    fillToMaximumSlides: true,
    fileStem: "moth-week-2026",
    cover: {
      title: "NATIONAL MOTH WEEK",
      place: "Kingfisher Hollow",
      dates: "July 18–26, 2026",
      credit: "Photos by Drew Weber",
    },
  },
});

const SUPPORTED_RANKS = new Set([
  "species",
  "subspecies",
  "variety",
  "form",
  "hybrid",
]);
const SPECIES_OR_LOWER_RANKS = new Set([
  "species",
  "subspecies",
  "variety",
  "form",
]);
const ALLOWED_PHOTO_HOSTS = new Set([
  "static.inaturalist.org",
  "inaturalist-open-data.s3.amazonaws.com",
]);

export class SocialExportError extends Error {
  constructor(code, message, status = 400, retryable = false) {
    super(message);
    this.name = "SocialExportError";
    this.code = code;
    this.status = status;
    this.retryable = retryable;
  }
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function cleanText(value, maximumLength = 100) {
  if (typeof value !== "string") return "";
  return value.trim().replace(/\s+/g, " ").slice(0, maximumLength);
}

function isIsoDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function inclusiveDayCount(dateFrom, dateTo) {
  return Math.floor(
    (Date.parse(`${dateTo}T00:00:00Z`) - Date.parse(`${dateFrom}T00:00:00Z`))
      / 86_400_000,
  ) + 1;
}

export function normalizeQuery(raw) {
  const input = asObject(raw);
  const dateFrom = cleanText(input.dateFrom, 10);
  const dateTo = cleanText(input.dateTo, 10);
  const observer = cleanText(input.observer, 40).toLowerCase();
  const taxonGroup = cleanText(input.taxonGroup, 30).toLowerCase();

  if (!isIsoDate(dateFrom) || !isIsoDate(dateTo)) {
    throw new SocialExportError(
      "invalid_date",
      "Choose a valid start and end date.",
    );
  }
  if (dateFrom > dateTo) {
    throw new SocialExportError(
      "invalid_date_range",
      "The start date must be on or before the end date.",
    );
  }
  if (inclusiveDayCount(dateFrom, dateTo) > 366) {
    throw new SocialExportError(
      "date_range_too_large",
      "Choose a date range of one year or less.",
    );
  }
  if (!/^[a-z0-9_]{1,40}$/.test(observer)) {
    throw new SocialExportError(
      "invalid_observer",
      "Enter a valid iNaturalist username.",
    );
  }
  if (!TAXON_GROUPS[taxonGroup]) {
    throw new SocialExportError(
      "invalid_taxon_group",
      "Choose one of the supported taxon groups.",
    );
  }

  return {
    dateFrom,
    dateTo,
    observer,
    taxonGroup,
    includeUnresolvedTaxa: input.includeUnresolvedTaxa === true,
  };
}

export function normalizeSettings(raw, query) {
  const input = asObject(raw);
  const outputFormat = input.outputFormat === "instagram-story"
    ? "instagram-story"
    : "instagram-square";
  const requestedGrid = cleanText(input.gridSize || input.gridLayout, 20)
    .toLowerCase()
    .replace("×", "x");
  const gridLayout = ["3x3", "4x4", "5x4", "5x5"].includes(requestedGrid)
    ? requestedGrid
    : [3, 4, 5].includes(Number(requestedGrid))
      ? `${Number(requestedGrid)}x${Number(requestedGrid)}`
      : "4x4";
  const [gridColumns, gridRows] = gridLayout.split("x").map(Number);
  const maximumSlides = Math.min(20, Math.max(1, Number(input.maximumSlides) || 10));
  const preset = PRESETS[cleanText(input.presetId || input.id, 60)] || null;
  const theme = ["kingfisher-quiet", "midnight-sheet", "field-note"].includes(input.theme)
    ? input.theme
    : "kingfisher-quiet";

  return {
    presetId: preset?.id || null,
    outputFormat,
    width: 1080,
    height: outputFormat === "instagram-story" ? 1920 : 1080,
    gridSize: gridLayout,
    gridLayout,
    gridColumns,
    gridRows,
    maximumSlides,
    includeCover: input.includeCover !== false,
    includeSpeciesLabels: input.includeSpeciesLabels !== false,
    theme,
    fillToMaximumSlides: preset?.fillToMaximumSlides === true
      || input.fillToMaximumSlides === true,
    fileStem: preset?.fileStem || defaultFileStem(query),
    cover: preset?.cover || {
      title: `${TAXON_GROUPS[query.taxonGroup].label.toUpperCase()} AT KINGFISHER HOLLOW`,
      place: "Kingfisher Hollow",
      dates: `${query.dateFrom}–${query.dateTo}`,
      credit: `Photos by ${query.observer}`,
    },
  };
}

function defaultFileStem(query) {
  const group = query.taxonGroup.replace(/[^a-z0-9]+/g, "-");
  return `${group}-${query.dateFrom}-${query.dateTo}`;
}

function hasTaxonId(taxon, targetId) {
  if (!taxon || !targetId) return false;
  if (Number(taxon.id) === targetId) return true;
  if (Array.isArray(taxon.ancestor_ids)) {
    return taxon.ancestor_ids.some((id) => Number(id) === targetId);
  }
  if (Array.isArray(taxon.ancestors)) {
    return taxon.ancestors.some((ancestor) => Number(ancestor?.id ?? ancestor) === targetId);
  }
  return false;
}

function speciesIdentity(taxon) {
  const rank = cleanText(taxon?.rank, 30).toLowerCase();
  if (rank === "species") {
    return { speciesId: Number(taxon.id), displayTaxon: taxon };
  }
  if (SPECIES_OR_LOWER_RANKS.has(rank)) {
    const ancestors = Array.isArray(taxon.ancestors) ? taxon.ancestors : [];
    const speciesAncestor = [...ancestors].reverse().find(
      (ancestor) => cleanText(ancestor?.rank, 30).toLowerCase() === "species",
    );
    const speciesId = Number(speciesAncestor?.id || taxon.parent_id || taxon.id);
    return { speciesId, displayTaxon: taxon };
  }
  return { speciesId: Number(taxon?.id), displayTaxon: taxon };
}

function photoUrlAtSize(url, size) {
  if (typeof url !== "string") return "";
  return url.replace(
    /\/(square|small|medium|large|original)\.([a-z0-9]+)(?:\?.*)?$/i,
    `/${size}.$2`,
  );
}

export function validateInatPhotoUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || !ALLOWED_PHOTO_HOSTS.has(url.hostname)) {
      throw new Error("host");
    }
    if (!/^\/photos\/\d+\//.test(url.pathname)) {
      throw new Error("path");
    }
    return url.toString();
  } catch (_error) {
    throw new SocialExportError(
      "invalid_photo_url",
      "A selected photo did not come from iNaturalist.",
    );
  }
}

function metadataPhotoScore(photo, observation) {
  const dimensions = asObject(photo.original_dimensions);
  const width = Math.max(0, Number(dimensions.width) || 0);
  const height = Math.max(0, Number(dimensions.height) || 0);
  const shortEdge = Math.min(width, height);
  const resolution = Math.min(1, Math.log2(Math.max(1, shortEdge)) / 11);
  const researchBonus = observation.quality_grade === "research" ? 2.5 : 0;
  const favoriteBonus = Math.min(3, Math.log2(1 + Math.max(0, observation.faves_count || 0)));
  return Math.round((38 + resolution * 34 + researchBonus + favoriteBonus) * 100) / 100;
}

function normalizedPhoto(photo, observation) {
  const canonicalUrl = validateInatPhotoUrl(photo.url);
  const dimensions = asObject(photo.original_dimensions);
  return {
    photoId: Number(photo.id),
    observationId: Number(observation.id),
    observationUrl: `${INAT_OBSERVATION}${Number(observation.id)}`,
    observedOn: cleanText(observation.observed_on, 10),
    url: canonicalUrl,
    thumbnailUrl: photoUrlAtSize(canonicalUrl, "small"),
    renderUrl: photoUrlAtSize(canonicalUrl, "medium"),
    originalUrl: photoUrlAtSize(canonicalUrl, "original"),
    width: Math.max(0, Number(dimensions.width) || 0),
    height: Math.max(0, Number(dimensions.height) || 0),
    attribution: cleanText(photo.attribution, 300)
      || `© ${cleanText(observation.user?.login, 40)}`,
    licenseCode: cleanText(photo.license_code, 30) || null,
    qualityGrade: cleanText(observation.quality_grade, 30) || "needs_id",
    favorites: Math.max(0, Number(observation.faves_count) || 0),
    metadataScore: metadataPhotoScore(photo, observation),
    score: metadataPhotoScore(photo, observation),
    metrics: null,
  };
}

function chooseDisplayTaxon(current, candidate) {
  if (!current) return candidate;
  const currentRank = cleanText(current.rank, 30).toLowerCase();
  const candidateRank = cleanText(candidate.rank, 30).toLowerCase();
  if (currentRank === "species" && SPECIES_OR_LOWER_RANKS.has(candidateRank)
      && candidateRank !== "species") {
    return candidate;
  }
  return current;
}

export function groupObservations(rawObservations, query) {
  const config = TAXON_GROUPS[query.taxonGroup];
  const grouped = new Map();
  let observationCount = 0;
  let photoCount = 0;
  let excludedButterflyCount = 0;
  let unresolvedCount = 0;

  for (const observation of rawObservations) {
    const taxon = observation?.taxon;
    const photos = Array.isArray(observation?.photos) ? observation.photos : [];
    if (!taxon || photos.length === 0) continue;
    if (config.excludeTaxonId && hasTaxonId(taxon, config.excludeTaxonId)) {
      excludedButterflyCount += 1;
      continue;
    }
    const rank = cleanText(taxon.rank, 30).toLowerCase();
    const resolved = SUPPORTED_RANKS.has(rank);
    if (!resolved && !query.includeUnresolvedTaxa) {
      unresolvedCount += 1;
      continue;
    }

    const { speciesId, displayTaxon } = speciesIdentity(taxon);
    if (!Number.isSafeInteger(speciesId) || speciesId <= 0) continue;
    const speciesKey = resolved ? `species:${speciesId}` : `taxon:${Number(taxon.id)}`;
    if (!grouped.has(speciesKey)) {
      grouped.set(speciesKey, {
        speciesKey,
        speciesId: resolved ? speciesId : null,
        taxonId: Number(taxon.id),
        rank,
        displayTaxon,
        candidates: [],
        observationIds: new Set(),
      });
    }
    const group = grouped.get(speciesKey);
    group.displayTaxon = chooseDisplayTaxon(group.displayTaxon, displayTaxon);
    group.observationIds.add(Number(observation.id));
    observationCount += 1;

    for (const photo of photos) {
      if (!Number.isSafeInteger(Number(photo.id)) || Number(photo.id) <= 0) continue;
      try {
        group.candidates.push(normalizedPhoto(photo, observation));
        photoCount += 1;
      } catch (_error) {
        // Ignore non-iNaturalist media URLs rather than allowing an export-time SSRF.
      }
    }
  }

  const species = [...grouped.values()].map((group) => {
    const taxon = group.displayTaxon;
    const candidatesById = new Map();
    for (const candidate of group.candidates) {
      const previous = candidatesById.get(candidate.photoId);
      if (!previous || candidate.metadataScore > previous.metadataScore) {
        candidatesById.set(candidate.photoId, candidate);
      }
    }
    const candidates = [...candidatesById.values()].sort(
      (left, right) => right.score - left.score || left.photoId - right.photoId,
    );
    return {
      speciesKey: group.speciesKey,
      speciesId: group.speciesId,
      taxonId: Number(taxon.id),
      rank: cleanText(taxon.rank, 30).toLowerCase(),
      commonName: cleanText(
        taxon.preferred_common_name || taxon.english_common_name,
        140,
      ) || null,
      scientificName: cleanText(taxon.name, 160) || "Unresolved taxon",
      observationCount: group.observationIds.size,
      selectedPhotoId: candidates[0]?.photoId || null,
      candidates,
    };
  }).filter((group) => group.candidates.length > 0);

  species.sort((left, right) => (
    (left.commonName || left.scientificName).localeCompare(
      right.commonName || right.scientificName,
      "en",
      { sensitivity: "base" },
    )
  ));

  return {
    species,
    summary: {
      observationCount,
      speciesCount: species.length,
      photoCount,
      excludedButterflyCount,
      unresolvedCount,
    },
  };
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function cacheKeyFor(url) {
  return new Request(url.toString(), {
    headers: { Accept: "application/json" },
  });
}

function retryDelayMilliseconds(response, attempt) {
  const retryAfter = response.headers.get("retry-after");
  if (retryAfter) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds) && seconds >= 0) {
      return Math.min(15_000, Math.max(1_000, seconds * 1_000));
    }
    const date = Date.parse(retryAfter);
    if (Number.isFinite(date)) {
      return Math.min(15_000, Math.max(1_000, date - Date.now()));
    }
  }
  return [2_000, 5_000][attempt] || 5_000;
}

async function fetchInatPage(url, {
  fetchImpl,
  cache,
  executionContext,
  delay,
}) {
  const key = cacheKeyFor(url);
  if (cache) {
    const cached = await cache.match(key);
    if (cached) return cached.json();
  }

  const inFlightKey = url.toString();
  if (inFlightInatPages.has(inFlightKey)) {
    return inFlightInatPages.get(inFlightKey);
  }

  const request = (async () => {
    let response;
    for (let attempt = 0; attempt < INAT_MAX_ATTEMPTS; attempt += 1) {
      try {
        response = await fetchImpl(url, {
          headers: {
            Accept: "application/json",
            "User-Agent": API_USER_AGENT,
          },
          cf: {
            cacheEverything: true,
            cacheTtl: CACHE_TTL_SECONDS,
          },
        });
      } catch (_error) {
        throw new SocialExportError(
          "inat_unavailable",
          "iNaturalist could not be reached. Check the connection and try again.",
          502,
          true,
        );
      }
      if (response.status !== 429) break;
      if (attempt < INAT_MAX_ATTEMPTS - 1) {
        await delay(retryDelayMilliseconds(response, attempt));
      }
    }
    if (response.status === 429) {
      throw new SocialExportError(
        "inat_rate_limited",
        "iNaturalist is still limiting requests after automatic retries. Try again in a minute.",
        503,
        true,
      );
    }
    if (!response.ok) {
      throw new SocialExportError(
        "inat_request_failed",
        `iNaturalist returned HTTP ${response.status}. Retry the request in a moment.`,
        502,
        true,
      );
    }
    const payload = await response.json();
    if (!payload || !Array.isArray(payload.results)) {
      throw new SocialExportError(
        "inat_malformed_response",
        "iNaturalist returned an unexpected response. Retry the request.",
        502,
        true,
      );
    }
    if (cache) {
      const cachedResponse = new Response(JSON.stringify(payload), {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": `public, max-age=${CACHE_TTL_SECONDS}`,
        },
      });
      const put = cache.put(key, cachedResponse);
      if (executionContext?.waitUntil) executionContext.waitUntil(put);
      else await put;
    }
    return payload;
  })();

  inFlightInatPages.set(inFlightKey, request);
  try {
    return await request;
  } finally {
    inFlightInatPages.delete(inFlightKey);
  }
}

export async function fetchMatchingObservations(
  query,
  {
    fetchImpl = fetch,
    cache = globalThis.caches?.default || null,
    executionContext = null,
    delay = wait,
  } = {},
) {
  const config = TAXON_GROUPS[query.taxonGroup];
  const results = [];
  let page = 1;
  let totalResults = null;

  while (totalResults === null || results.length < totalResults) {
    const url = new URL(`${INAT_API}/observations`);
    url.searchParams.set("user_id", query.observer);
    url.searchParams.set("d1", query.dateFrom);
    url.searchParams.set("d2", query.dateTo);
    url.searchParams.set("taxon_id", String(config.taxonId));
    url.searchParams.set("photos", "true");
    url.searchParams.set("per_page", String(API_PAGE_SIZE));
    url.searchParams.set("page", String(page));
    url.searchParams.set("order", "asc");
    url.searchParams.set("order_by", "id");
    url.searchParams.set("locale", "en");
    url.searchParams.set("preferred_place_id", "1");

    const payload = await fetchInatPage(url, {
      fetchImpl,
      cache,
      executionContext,
      delay,
    });
    totalResults = Math.min(Number(payload.total_results) || 0, MAX_API_RESULTS);
    results.push(...payload.results);
    if (payload.results.length < API_PAGE_SIZE || results.length >= totalResults) break;
    if (results.length >= MAX_API_RESULTS) {
      throw new SocialExportError(
        "too_many_observations",
        "This search has more than 10,000 observations. Choose a shorter date range.",
      );
    }
    page += 1;
    await delay(1_000);
  }

  return results.slice(0, totalResults ?? results.length);
}

export function jsonResponse(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...extraHeaders,
    },
  });
}

export function errorResponse(error) {
  const known = error instanceof SocialExportError;
  return jsonResponse({
    error: {
      code: known ? error.code : "internal_error",
      message: known
        ? error.message
        : "The export tool hit an unexpected error. Retry the request.",
      retryable: known ? error.retryable : true,
    },
  }, known ? error.status : 500);
}

export async function handleObservationSearch(context) {
  if (context.request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        Allow: "POST, OPTIONS",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
      },
    });
  }
  if (context.request.method !== "POST") {
    return errorResponse(new SocialExportError(
      "method_not_allowed",
      "Use POST to search observations.",
      405,
    ));
  }
  try {
    const query = normalizeQuery(await context.request.json());
    const observations = await fetchMatchingObservations(query, {
      executionContext: context,
    });
    const grouped = groupObservations(observations, query);
    return jsonResponse({
      schemaVersion: 1,
      query,
      ...grouped,
    });
  } catch (error) {
    return errorResponse(error);
  }
}

export function hammingDistance(left, right) {
  if (typeof left !== "string" || typeof right !== "string" || left.length !== right.length) {
    return Number.POSITIVE_INFINITY;
  }
  let distance = 0;
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) distance += 1;
  }
  return distance;
}

export function applyPhotoScores(species, metricResults) {
  const metricsByPhoto = new Map(
    metricResults.map((result) => [Number(result.photoId), result]),
  );
  const scored = species.map((group) => {
    const candidates = group.candidates.map((candidate) => {
      const analysis = metricsByPhoto.get(candidate.photoId);
      if (!analysis || analysis.error) return candidate;
      const score = Math.max(0, Math.min(100,
        candidate.metadataScore * 0.42
        + analysis.sharpness * 18
        + analysis.exposure * 13
        + analysis.contrast * 10
        + analysis.subjectOccupancy * 12
        + (1 - analysis.obstruction) * 5
      ));
      return {
        ...candidate,
        score: Math.round(score * 100) / 100,
        metrics: analysis,
      };
    });
    candidates.sort((left, right) => right.score - left.score || left.photoId - right.photoId);
    for (let index = 1; index < candidates.length; index += 1) {
      const candidate = candidates[index];
      const similarBetter = candidates.slice(0, index).some((better) => (
        hammingDistance(candidate.metrics?.perceptualHash, better.metrics?.perceptualHash) <= 5
      ));
      if (similarBetter) {
        candidate.score = Math.max(0, Math.round((candidate.score - 8) * 100) / 100);
        candidate.nearDuplicate = true;
      }
    }
    candidates.sort((left, right) => right.score - left.score || left.photoId - right.photoId);
    return {
      ...group,
      candidates,
      selectedPhotoId: candidates[0]?.photoId || null,
    };
  });

  const selectedHashes = [];
  const selectionOrder = [...scored].sort((left, right) => (
    right.candidates[0].score - left.candidates[0].score
    || left.speciesKey.localeCompare(right.speciesKey)
  ));
  for (const group of selectionOrder) {
    const distinct = group.candidates.find((candidate) => {
      const hash = candidate.metrics?.perceptualHash;
      return hash && selectedHashes.every(
        (selectedHash) => hammingDistance(hash, selectedHash) > 5,
      );
    });
    const selected = distinct || group.candidates[0];
    group.selectedPhotoId = selected.photoId;
    if (selected.metrics?.perceptualHash) {
      selectedHashes.push(selected.metrics.perceptualHash);
    }
  }
  return scored;
}

export function selectExportSpecies(species, selections, settings) {
  const requested = new Map(
    Array.isArray(selections)
      ? selections.map((selection) => [
        cleanText(selection?.speciesKey, 80),
        {
          photoId: Number(selection?.photoId),
          rotation: ((Math.round(Number(selection?.rotation || 0) / 90) * 90) % 360 + 360) % 360,
        },
      ])
      : [],
  );
  const uniqueSpecies = new Set();
  const verified = [];
  for (const group of species) {
    const selection = requested.get(group.speciesKey);
    if (!selection?.photoId || uniqueSpecies.has(group.speciesKey)) continue;
    const photo = group.candidates.find((candidate) => candidate.photoId === selection.photoId);
    if (!photo) {
      throw new SocialExportError(
        "photo_not_in_query",
        "A selected photo no longer belongs to the requested iNaturalist results. Refresh the review.",
        409,
        true,
      );
    }
    uniqueSpecies.add(group.speciesKey);
    verified.push({
      ...group,
      selectedPhoto: photo,
      rotation: selection.rotation,
    });
  }

  const gridSlides = Math.max(0, settings.maximumSlides - (settings.includeCover ? 1 : 0));
  const capacity = gridSlides * settings.gridColumns * settings.gridRows;
  return verified.slice(0, capacity);
}
