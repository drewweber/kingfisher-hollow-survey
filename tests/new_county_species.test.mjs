import assert from "node:assert/strict";
import test from "node:test";

import {
  createRequestPacer,
  detectNewCountySpecies,
  normalizeQuery,
} from "../src/new_county_species_runtime.mjs";
import { onRequest } from "../functions/api/new-county-species.js";

function speciesCount(taxonId, name, commonName = null, count = 1) {
  return {
    taxon: { id: taxonId, rank: "species", name, preferred_common_name: commonName },
    count,
  };
}

function observationRecord(speciesTaxonId, observationId, observedOn = "2026-07-15", taxon = {}) {
  return {
    id: observationId,
    uri: `https://www.inaturalist.org/observations/${observationId}`,
    observed_on: observedOn,
    taxon: {
      id: speciesTaxonId,
      rank: "species",
      min_species_taxon_id: speciesTaxonId,
      ...taxon,
    },
  };
}

test("detector compares the selected-period and prior species lists", async () => {
  const calls = [];
  const query = normalizeQuery(new URLSearchParams({
    place_id: "653", d1: "2026-07-01", d2: "2026-07-31", include_casual: "false",
  }));
  const fetchImpl = async (url, init) => {
    const params = new URL(url).searchParams;
    calls.push(new URL(url));
    assert.match(init.headers["User-Agent"], /KingfisherHollowCountySpeciesDetector/);
    const path = new URL(url).pathname;
    if (path === "/v2/observations/species_counts") {
      if (params.get("d1")) return Response.json({
        total_results: 2,
        results: [
          speciesCount(11, "Newus species", "New Species", 2),
          speciesCount(22, "Oldus species", null, 5),
        ],
      });
      assert.equal(params.get("taxon_id"), "11,22");
      return Response.json({
        total_results: 1,
        results: [speciesCount(22, "Oldus species", null, 25)],
      });
    }
    assert.equal(path, "/v2/observations");
    assert.equal(params.get("taxon_id"), "11");
    assert.equal(params.get("order_by"), "observed_on");
    assert.match(params.get("fields"), /min_species_taxon_id/);
    assert.match(params.get("fields"), /uri/);
    return Response.json({
      total_results: 1,
      results: [observationRecord(11, 991, "2026-07-12", {
        id: 111,
        rank: "subspecies",
      })],
    });
  };
  const result = await detectNewCountySpecies(query, {
    fetchImpl,
    pacer: { beforeRequest: async () => {} },
  });
  assert.equal(result.totalNewSpecies, 1);
  assert.deepEqual(result.species, [{
    taxonId: 11,
    scientificName: "Newus species",
    commonName: "New Species",
    periodObservationCount: 2,
    recordUrl: "https://www.inaturalist.org/observations/991",
    recordObservedOn: "2026-07-12",
  }]);
  assert.deepEqual(result.meta, {
    source: "iNaturalist v2 species counts and observations",
    upstreamRequests: 3,
  });
  assert.equal(calls[0].searchParams.get("per_page"), "500");
  assert.equal(calls[0].searchParams.get("verifiable"), "true");
  assert.equal(calls[0].searchParams.get("hrank"), "species");
  assert.equal(calls[0].searchParams.get("ttl"), "300");
  assert.match(calls[0].searchParams.get("fields"), /preferred_common_name/);
  assert.equal(calls.length, 3);
  assert.equal(calls[0].searchParams.get("d1"), "2026-07-01");
  assert.equal(calls[0].searchParams.get("d2"), "2026-07-31");
  assert.equal(calls[1].searchParams.get("d1"), null);
  assert.equal(calls[1].searchParams.get("d2"), "2026-06-30");
  assert.equal(calls[2].searchParams.get("d1"), "2026-07-01");
  assert.equal(calls[2].searchParams.get("d2"), "2026-07-31");
});

test("browser-direct mode omits the forbidden User-Agent header and skips history for an empty period", async () => {
  const query = normalizeQuery(new URLSearchParams({
    place_id: "653", d1: "2026-07-01", d2: "2026-07-01", include_casual: "false",
  }));
  let calls = 0;
  const result = await detectNewCountySpecies(query, {
    fetchImpl: async (url, init) => {
      calls += 1;
      assert.equal(init.headers["User-Agent"], undefined);
      assert.equal(init.credentials, "omit");
      assert.equal(init.cache, "default");
      assert.equal(new URL(url).hostname, "api.inaturalist.org");
      return Response.json({ total_results: 0, results: [] });
    },
    pacer: { beforeRequest: async () => {} },
    sendUserAgent: false,
  });
  assert.equal(calls, 1);
  assert.equal(result.totalNewSpecies, 0);
  assert.equal(result.meta.upstreamRequests, 1);
});

test("history checks are batched instead of making one request per species", async () => {
  const query = normalizeQuery(new URLSearchParams({
    place_id: "653", d1: "2026-07-01", d2: "2026-07-31", include_casual: "false",
  }));
  const historyBatchSizes = [];
  const recordBatchSizes = [];
  const periodResults = Array.from({ length: 301 }, (_, index) => (
    speciesCount(index + 1, `Species ${index + 1}`)
  ));
  const result = await detectNewCountySpecies(query, {
    fetchImpl: async (url) => {
      const path = new URL(url).pathname;
      const params = new URL(url).searchParams;
      if (path.endsWith("/species_counts") && params.get("d1")) {
        return Response.json({ total_results: periodResults.length, results: periodResults });
      }
      const taxonIds = params.get("taxon_id").split(",").map(Number);
      if (path.endsWith("/species_counts")) {
        historyBatchSizes.push(taxonIds.length);
        return Response.json({ total_results: 0, results: [] });
      }
      recordBatchSizes.push(taxonIds.length);
      return Response.json({
        total_results: taxonIds.length,
        results: taxonIds.map((taxonId) => observationRecord(taxonId, 10_000 + taxonId)),
      });
    },
    pacer: { beforeRequest: async () => {} },
  });
  assert.equal(result.totalNewSpecies, 301);
  assert.deepEqual(historyBatchSizes, [300, 1]);
  assert.deepEqual(recordBatchSizes, [180, 121]);
  assert.equal(result.meta.upstreamRequests, 5);
});

test("record lookups isolate high-volume species and map infrataxa to parent species", async () => {
  const query = normalizeQuery(new URLSearchParams({
    place_id: "653", d1: "2026-07-01", d2: "2026-07-31", include_casual: "false",
  }));
  const recordRequests = [];
  const periodResults = [
    speciesCount(1, "Species one", null, 181),
    speciesCount(2, "Species two", null, 100),
    speciesCount(3, "Species three", null, 80),
  ];
  const result = await detectNewCountySpecies(query, {
    fetchImpl: async (url) => {
      const path = new URL(url).pathname;
      const params = new URL(url).searchParams;
      if (path.endsWith("/species_counts") && params.get("d1")) {
        return Response.json({ total_results: periodResults.length, results: periodResults });
      }
      if (path.endsWith("/species_counts")) {
        return Response.json({ total_results: 0, results: [] });
      }
      const taxonIds = params.get("taxon_id").split(",").map(Number);
      recordRequests.push({ perPage: Number(params.get("per_page")), taxonIds });
      return Response.json({
        total_results: taxonIds.length,
        results: taxonIds.map((taxonId) => observationRecord(
          taxonId,
          20_000 + taxonId,
          "2026-07-20",
          taxonId === 2 ? { id: 222, rank: "subspecies" } : {},
        )),
      });
    },
    pacer: { beforeRequest: async () => {} },
  });
  assert.deepEqual(recordRequests, [
    { perPage: 1, taxonIds: [1] },
    { perPage: 200, taxonIds: [2, 3] },
  ]);
  assert.deepEqual(result.species.map((species) => species.recordUrl), [
    "https://www.inaturalist.org/observations/20001",
    "https://www.inaturalist.org/observations/20003",
    "https://www.inaturalist.org/observations/20002",
  ]);
});

test("record lookup budget is enforced before any evidence requests", async () => {
  const query = normalizeQuery(new URLSearchParams({
    place_id: "653", d1: "2026-07-01", d2: "2026-07-31", include_casual: "false",
  }));
  const periodResults = Array.from({ length: 9 }, (_, index) => (
    speciesCount(index + 1, `Species ${index + 1}`, null, 181)
  ));
  let evidenceRequests = 0;
  await assert.rejects(detectNewCountySpecies(query, {
    fetchImpl: async (url) => {
      const path = new URL(url).pathname;
      const params = new URL(url).searchParams;
      if (path.endsWith("/species_counts") && params.get("d1")) {
        return Response.json({ total_results: periodResults.length, results: periodResults });
      }
      if (path.endsWith("/species_counts")) {
        return Response.json({ total_results: 0, results: [] });
      }
      evidenceRequests += 1;
      return Response.json({ total_results: 0, results: [] });
    },
    pacer: { beforeRequest: async () => {} },
  }), (error) => error.code === "inat_record_lookup_too_broad"
    && error.status === 422 && !error.retryable);
  assert.equal(evidenceRequests, 0);
});

test("an unsafe record URI fails instead of returning an unlinked species", async () => {
  const query = normalizeQuery(new URLSearchParams({
    place_id: "653", d1: "2026-07-01", d2: "2026-07-31", include_casual: "false",
  }));
  let calls = 0;
  await assert.rejects(detectNewCountySpecies(query, {
    fetchImpl: async (url) => {
      calls += 1;
      const path = new URL(url).pathname;
      const params = new URL(url).searchParams;
      if (path.endsWith("/species_counts") && params.get("d1")) {
        return Response.json({ total_results: 1, results: [speciesCount(11, "Missing record")] });
      }
      if (path.endsWith("/species_counts")) {
        return Response.json({ total_results: 0, results: [] });
      }
      return Response.json({
        total_results: 1,
        results: [{
          ...observationRecord(11, 99),
          uri: "https://attacker@www.inaturalist.org/observations/99?redirect=1#bad",
        }],
      });
    },
    pacer: { beforeRequest: async () => {} },
  }), (error) => error.code === "inat_record_lookup_inconsistent" && error.retryable);
  assert.equal(calls, 3);
});

test("overly broad periods stop after the first aggregate response", async () => {
  const query = normalizeQuery(new URLSearchParams({
    place_id: "653", d1: "2026-01-01", d2: "2026-07-31", include_casual: "false",
  }));
  let calls = 0;
  await assert.rejects(detectNewCountySpecies(query, {
    fetchImpl: async () => {
      calls += 1;
      return Response.json({ total_results: 2001, results: [] });
    },
    pacer: { beforeRequest: async () => {} },
  }), (error) => error.code === "inat_species_list_too_broad");
  assert.equal(calls, 1);
});

test("rate-limit responses are not automatically retried", async () => {
  const query = normalizeQuery(new URLSearchParams({
    place_id: "653", d1: "2026-07-01", d2: "2026-07-31", include_casual: "false",
  }));
  let calls = 0;
  const delays = [];
  await assert.rejects(detectNewCountySpecies(query, {
    delay: async (milliseconds) => { delays.push(milliseconds); },
    fetchImpl: async () => {
      calls += 1;
      return new Response(null, { status: 429, headers: { "Retry-After": "60" } });
    },
    pacer: { beforeRequest: async () => {} },
  }), (error) => error.code === "inat_rate_limited");
  assert.equal(calls, 1);
  assert.deepEqual(delays, []);
});

test("iNaturalist requests are paced at roughly one per second", async () => {
  const delays = [];
  const pacer = createRequestPacer({
    now: () => 0,
    delay: async (milliseconds) => { delays.push(milliseconds); },
  });
  await pacer.beforeRequest();
  await pacer.beforeRequest();
  await pacer.beforeRequest();
  assert.deepEqual(delays, [1100, 2200]);
});

test("query validation rejects unsafe IDs, inverted dates, and invalid casual settings", () => {
  assert.throws(() => normalizeQuery(new URLSearchParams({ place_id: "0", d1: "2026-01-01", d2: "2026-01-01" })), /place ID/);
  assert.throws(() => normalizeQuery(new URLSearchParams({ place_id: "1", d1: "2026-02-01", d2: "2026-01-01" })), /on or before/);
  assert.throws(() => normalizeQuery(new URLSearchParams({ place_id: "1", d1: "2026-01-01", d2: "2026-01-01", include_casual: "maybe" })), /true or false/);
});

test("route exposes a read-only, structured validation error", async () => {
  const response = await onRequest({ request: new Request("https://survey.example/api/new-county-species?place_id=wrong&d1=2026-01-01&d2=2026-01-02") });
  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), {
    error: { code: "invalid_place_id", message: "place_id must be a positive iNaturalist place ID.", retryable: false },
  });
  assert.equal(response.headers.get("access-control-allow-origin"), "*");
});

test("HEAD is a metadata-only response and never starts an iNaturalist lookup", async () => {
  const response = await onRequest({
    request: new Request("https://survey.example/api/new-county-species?place_id=653&d1=2026-01-01&d2=2026-01-02", {
      method: "HEAD",
    }),
  });
  assert.equal(response.status, 204);
  assert.equal(await response.text(), "");
  assert.equal(response.headers.get("access-control-allow-methods"), "GET, HEAD, OPTIONS");
});

test("route serves a cached completed detector result without contacting iNaturalist", async () => {
  const previousCaches = globalThis.caches;
  let matchedCacheUrl;
  globalThis.caches = {
    default: {
      match: async (request) => {
        matchedCacheUrl = new URL(request.url);
        return Response.json({ cached: true });
      },
    },
  };
  try {
    const response = await onRequest({ request: new Request("https://survey.example/api/new-county-species?nonce=123&d2=2026-01-02&place_id=653&d1=2026-01-01") });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { cached: true });
    assert.equal(matchedCacheUrl.searchParams.get("_result_schema"), "record-links-v2");
    assert.equal(matchedCacheUrl.searchParams.get("include_casual"), "false");
    assert.equal(matchedCacheUrl.searchParams.get("nonce"), null);
    assert.deepEqual([...matchedCacheUrl.searchParams.keys()], [
      "place_id", "d1", "d2", "include_casual", "_result_schema",
    ]);
  } finally {
    globalThis.caches = previousCaches;
  }
});
