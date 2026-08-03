import {
  detectNewCountySpecies,
  normalizeQuery,
} from "./new-county-species-runtime.js?v=__ASSET_VERSION__";

const form = document.querySelector("#detector-form");
const results = document.querySelector("#results");
const button = document.querySelector("#run-detector");
const status = document.querySelector("#search-status");
const errorBox = document.querySelector("#search-error");
const rows = document.querySelector("#result-rows");
const empty = document.querySelector("#empty-results");
const total = document.querySelector("#result-total");
const summary = document.querySelector("#result-summary");
const CLIENT_CACHE_NAME = "kh-new-county-species-v2";
const FRESH_CACHE_MS = 5 * 60 * 1_000;
const STALE_CACHE_MS = 24 * 60 * 60 * 1_000;
const REQUEST_INTERVAL_MS = 1_100;
const PACER_STORAGE_KEY = "khInatApiNextRequestAt";

function validRecordUrl(value) {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:"
      && url.hostname === "www.inaturalist.org"
      && !url.username && !url.password && !url.port && !url.search && !url.hash
      && /^\/observations\/\d+\/?$/.test(url.pathname);
  } catch (_error) {
    return false;
  }
}

function isoDateToday() {
  return new Date().toISOString().slice(0, 10);
}

function daysAgo(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

document.querySelector("#date-from").value = daysAgo(30);
document.querySelector("#date-to").value = isoDateToday();

function clearError() {
  errorBox.hidden = true;
  errorBox.querySelector("p").textContent = "";
}

function showError(message) {
  errorBox.querySelector("p").textContent = message;
  errorBox.hidden = false;
}

function cacheRequest(query) {
  const url = new URL("/_client-cache/new-county-species", window.location.origin);
  url.search = new URLSearchParams({
    place_id: String(query.placeId),
    d1: query.dateFrom,
    d2: query.dateTo,
    include_casual: String(query.includeCasual),
  });
  return new Request(url);
}

async function readCachedResult(query, maxAge) {
  if (!globalThis.caches) return null;
  try {
    const cache = await globalThis.caches.open(CLIENT_CACHE_NAME);
    const response = await cache.match(cacheRequest(query));
    if (!response) return null;
    const entry = await response.json();
    const age = Date.now() - Number(entry?.cachedAt);
    if (!Number.isFinite(age) || age < 0 || age > maxAge || !Array.isArray(entry?.payload?.species)
      || entry.payload.species.some((species) => (
        !validRecordUrl(species?.recordUrl)
      ))) {
      return null;
    }
    return { age, payload: entry.payload };
  } catch (_error) {
    return null;
  }
}

async function cacheResult(query, payload) {
  if (!globalThis.caches) return;
  try {
    const cache = await globalThis.caches.open(CLIENT_CACHE_NAME);
    await cache.put(cacheRequest(query), Response.json({ cachedAt: Date.now(), payload }));
  } catch (_error) {
    // Cache availability must never prevent a successful lookup.
  }
}

function queryLockName(query) {
  return [
    "kh-new-county-species",
    query.placeId,
    query.dateFrom,
    query.dateTo,
    query.includeCasual,
  ].join(":");
}

async function withQueryLock(query, callback) {
  if (!navigator.locks?.request) return callback();
  return navigator.locks.request(queryLockName(query), callback);
}

function createBrowserRequestPacer() {
  let inMemoryNextRequestAt = 0;
  return {
    async beforeRequest() {
      const schedule = async () => {
        const now = Date.now();
        let storedNextRequestAt = 0;
        try {
          storedNextRequestAt = Number(localStorage.getItem(PACER_STORAGE_KEY)) || 0;
        } catch (_error) {
          // The in-memory clock still protects this tab when storage is unavailable.
        }
        const scheduled = Math.max(now, storedNextRequestAt, inMemoryNextRequestAt);
        if (scheduled > now) {
          await new Promise((resolve) => setTimeout(resolve, scheduled - now));
        }
        const nextRequestAt = Date.now() + REQUEST_INTERVAL_MS;
        inMemoryNextRequestAt = nextRequestAt;
        try {
          localStorage.setItem(PACER_STORAGE_KEY, String(nextRequestAt));
        } catch (_error) {
          // The in-memory clock still protects this tab when storage is unavailable.
        }
      };
      if (navigator.locks?.request) {
        await navigator.locks.request("kh-inaturalist-api-pacer", schedule);
      } else {
        await schedule();
      }
    },
  };
}

function textCell(value, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = value;
  return cell;
}

function renderResults(payload) {
  rows.replaceChildren();
  const count = payload.totalNewSpecies;
  total.textContent = count.toLocaleString();
  total.setAttribute("aria-label", `${count.toLocaleString()} new species`);
  summary.textContent = `${count.toLocaleString()} species newly recorded in iNaturalist for place ${payload.query.placeId} from ${payload.query.dateFrom} through ${payload.query.dateTo}.`;
  empty.hidden = count !== 0;
  for (const species of payload.species) {
    const row = document.createElement("tr");
    const speciesCell = document.createElement("td");
    const common = document.createElement("strong");
    common.textContent = species.commonName || species.scientificName;
    const scientific = document.createElement("em");
    scientific.textContent = species.scientificName;
    const recordLink = document.createElement("a");
    recordLink.className = "record-link";
    recordLink.href = species.recordUrl;
    recordLink.target = "_blank";
    recordLink.rel = "noopener noreferrer";
    recordLink.textContent = "View iNaturalist record ↗";
    recordLink.setAttribute(
      "aria-label",
      `View the iNaturalist record for ${species.commonName || species.scientificName} (opens in a new tab)`,
    );
    speciesCell.append(common, scientific, recordLink);
    row.append(
      speciesCell,
      textCell(species.periodObservationCount.toLocaleString(), "tabular"),
    );
    rows.append(row);
  }
  results.hidden = false;
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  results.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  results.hidden = true;
  const placeId = document.querySelector("#place-id").value;
  const dateFrom = document.querySelector("#date-from").value;
  const dateTo = document.querySelector("#date-to").value;
  const includeCasual = document.querySelector("#include-casual").checked;
  const params = new URLSearchParams({ place_id: placeId, d1: dateFrom, d2: dateTo, include_casual: String(includeCasual) });
  let query;
  try {
    query = normalizeQuery(params);
  } catch (error) {
    showError(error.message || "Check the place ID and date range.");
    status.textContent = "";
    return;
  }

  button.disabled = true;
  const startedAt = Date.now();
  try {
    const fresh = await readCachedResult(query, FRESH_CACHE_MS);
    if (fresh) {
      renderResults(fresh.payload);
      status.textContent = "Loaded instantly from this browser’s recent-search cache.";
      return;
    }

    const search = await withQueryLock(query, async () => {
      const coalesced = await readCachedResult(query, FRESH_CACHE_MS);
      if (coalesced) return { cacheHit: true, payload: coalesced.payload };
      const payload = await detectNewCountySpecies(query, {
        pacer: createBrowserRequestPacer(),
        sendUserAgent: false,
        onProgress: ({ message }) => { status.textContent = message; },
      });
      await cacheResult(query, payload);
      return { cacheHit: false, payload };
    });
    const { cacheHit, payload } = search;
    renderResults(payload);
    if (cacheHit) {
      status.textContent = "Loaded instantly from a matching search completed in another tab.";
    } else {
      const elapsed = ((Date.now() - startedAt) / 1_000).toFixed(1);
      const requests = payload.meta?.upstreamRequests ?? 0;
      status.textContent = `Search complete in ${elapsed}s using ${requests} iNaturalist request${requests === 1 ? "" : "s"}.`;
    }
  } catch (error) {
    const stale = await readCachedResult(query, STALE_CACHE_MS);
    if (stale) {
      renderResults(stale.payload);
      const minutesOld = Math.max(1, Math.round(stale.age / 60_000));
      showError(`iNaturalist is temporarily unavailable. Showing this browser’s cached result from ${minutesOld.toLocaleString()} minutes ago.`);
      status.textContent = "Cached result shown.";
    } else {
      showError(error.message || "The detector could not complete the request. Please try again.");
      status.textContent = "";
    }
  } finally {
    button.disabled = false;
  }
});
