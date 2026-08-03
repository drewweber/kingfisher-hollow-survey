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

test("detector compares the selected-period and prior species lists", async () => {
  const calls = [];
  const query = normalizeQuery(new URLSearchParams({
    place_id: "653", d1: "2026-07-01", d2: "2026-07-31", include_casual: "false",
  }));
  const fetchImpl = async (url, init) => {
    const params = new URL(url).searchParams;
    calls.push(new URL(url));
    assert.match(init.headers["User-Agent"], /KingfisherHollowCountySpeciesDetector/);
    assert.equal(new URL(url).pathname, "/v2/observations/species_counts");
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
  }]);
  assert.deepEqual(result.meta, {
    source: "iNaturalist v2 observation species counts",
    upstreamRequests: 2,
  });
  assert.equal(calls[0].searchParams.get("per_page"), "500");
  assert.equal(calls[0].searchParams.get("verifiable"), "true");
  assert.equal(calls[0].searchParams.get("hrank"), "species");
  assert.equal(calls[0].searchParams.get("ttl"), "300");
  assert.match(calls[0].searchParams.get("fields"), /preferred_common_name/);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].searchParams.get("d1"), "2026-07-01");
  assert.equal(calls[0].searchParams.get("d2"), "2026-07-31");
  assert.equal(calls[1].searchParams.get("d1"), null);
  assert.equal(calls[1].searchParams.get("d2"), "2026-06-30");
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
  const periodResults = Array.from({ length: 301 }, (_, index) => (
    speciesCount(index + 1, `Species ${index + 1}`)
  ));
  const result = await detectNewCountySpecies(query, {
    fetchImpl: async (url) => {
      const params = new URL(url).searchParams;
      if (params.get("d1")) {
        return Response.json({ total_results: periodResults.length, results: periodResults });
      }
      historyBatchSizes.push(params.get("taxon_id").split(",").length);
      return Response.json({ total_results: 0, results: [] });
    },
    pacer: { beforeRequest: async () => {} },
  });
  assert.equal(result.totalNewSpecies, 301);
  assert.deepEqual(historyBatchSizes, [300, 1]);
  assert.equal(result.meta.upstreamRequests, 3);
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
  globalThis.caches = {
    default: {
      match: async () => Response.json({ cached: true }),
    },
  };
  try {
    const response = await onRequest({ request: new Request("https://survey.example/api/new-county-species?place_id=653&d1=2026-01-01&d2=2026-01-02") });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { cached: true });
  } finally {
    globalThis.caches = previousCaches;
  }
});
