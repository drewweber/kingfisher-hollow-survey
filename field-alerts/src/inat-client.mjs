const BASE_URL = "https://api.inaturalist.org/v1";

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export class InatClient {
  constructor(fetchFn = fetch) {
    // Cloudflare's global fetch throws "Illegal invocation" when it is later
    // called as an object method (this.fetchFn). Wrap it so the original
    // function is always invoked without a borrowed `this` value.
    this.fetchFn = (...args) => fetchFn(...args);
  }

  async request(path, params = {}, options = {}) {
    const url = new URL(`${BASE_URL}/${path.replace(/^\//, "")}`);
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }

    const attempts = Math.max(1, Number(options.attempts) || 4);
    let lastError;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);
      try {
        const response = await this.fetchFn(url, {
          headers: { "user-agent": "kingfisher-hollow-field-alerts" },
          signal: controller.signal,
        });
        if (response.ok) return await response.json();
        if (response.status !== 429 && response.status < 500) {
          throw new Error(`iNaturalist returned HTTP ${response.status}.`);
        }
        const retryAfter = Number.parseInt(response.headers.get("retry-after") || "", 10);
        lastError = new Error(`iNaturalist temporarily returned HTTP ${response.status}.`);
        if (attempt < attempts - 1) {
          await wait(Number.isFinite(retryAfter)
            ? Math.min(retryAfter * 1000, 30000)
            : [2000, 5000, 10000, 20000][attempt]);
        }
      } catch (error) {
        lastError = error;
        if (attempt < attempts - 1) await wait([1000, 3000, 7000][attempt] || 10000);
      } finally {
        clearTimeout(timeout);
      }
    }
    throw lastError || new Error("iNaturalist request failed.");
  }

  async recentMoths(config) {
    const data = await this.request("observations", {
      project_id: config.projectId,
      user_login: config.username,
      taxon_id: config.lepidopteraTaxonId,
      without_taxon_id: config.butterflyTaxonId,
      order_by: "updated_at",
      order: "desc",
      per_page: config.recentLimit,
    });
    return data.results || [];
  }

  async projectObservation(observationId, config) {
    const data = await this.request("observations", {
      id: observationId,
      project_id: config.projectId,
      per_page: 1,
    });
    return data.results?.[0] || null;
  }

  async count(params) {
    const data = await this.request("observations", { ...params, per_page: 0 });
    return Number(data.total_results || 0);
  }

  async countsForTaxon(taxonId, config) {
    // iNaturalist explicitly discourages bursts. These only run for a taxon
    // that is new to KH, so a short serial pause is cheap and avoids 429s.
    const state = await this.count({ taxon_id: taxonId, place_id: config.statePlaceId });
    if (config.requestPauseMs) await wait(config.requestPauseMs);
    const regional = await this.count({
      taxon_id: taxonId,
      lat: config.propertyLat,
      lng: config.propertyLng,
      radius: config.regionRadiusKm,
    });
    if (config.requestPauseMs) await wait(config.requestPauseMs);
    const county = await this.count({ taxon_id: taxonId, place_id: config.countyPlaceId });
    return { county, state, regional };
  }

  async identificationContext(taxonId, config) {
    // This context enriches an alert but must never delay it through a long
    // retry cycle. The caller falls back to model knowledge if iNaturalist is
    // temporarily throttling requests.
    const details = await this.request(`taxa/${taxonId}`, {}, { attempts: 1 });
    const taxon = details.results?.[0] || {};
    const ancestors = taxon.ancestors || [];
    const genus = ancestors.find((ancestor) => ancestor.rank === "genus")
      || (taxon.rank === "genus" ? taxon : null);
    const family = ancestors.find((ancestor) => ancestor.rank === "family") || null;
    if (!genus?.id) {
      return {
        genusName: genus?.name || "",
        familyName: family?.name || "",
        regionalCandidates: [],
      };
    }
    if (config.requestPauseMs) await wait(config.requestPauseMs);
    const counts = await this.request("observations/species_counts", {
      taxon_id: genus.id,
      lat: config.propertyLat,
      lng: config.propertyLng,
      radius: config.regionRadiusKm,
      per_page: 30,
    }, { attempts: 1 });
    const regionalCandidates = (counts.results || [])
      .filter((entry) => entry.taxon?.id !== taxonId && SPECIES_RANKS_FOR_CONTEXT.has(entry.taxon?.rank))
      .map((entry) => ({
        taxonId: entry.taxon.id,
        scientificName: entry.taxon.name,
        commonName: entry.taxon.preferred_common_name || "",
        count: Number(entry.count || 0),
      }))
      .slice(0, 20);
    return {
      genusName: genus.name || "",
      familyName: family?.name || "",
      regionalCandidates,
    };
  }
}

const SPECIES_RANKS_FOR_CONTEXT = new Set([
  "species", "subspecies", "variety", "form", "hybrid", "subvariety", "subform",
]);
