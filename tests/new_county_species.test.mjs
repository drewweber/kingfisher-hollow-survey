import assert from "node:assert/strict";
import test from "node:test";

import {
  createRequestPacer,
  detectNewCountySpecies,
  normalizeQuery,
} from "../src/new_county_species_runtime.mjs";
import { onRequest } from "../functions/api/new-county-species.js";

function observation(id, taxonId, observedOn, name, commonName = null) {
  return {
    id,
    observed_on: observedOn,
    user: { login: `observer-${id}` },
    taxon: { id: taxonId, rank: "species", name, preferred_common_name: commonName },
  };
}

test("detector deduplicates species, keeps the first period record, and excludes taxa with prior records", async () => {
  const calls = [];
  const query = normalizeQuery(new URLSearchParams({
    place_id: "653", d1: "2026-07-01", d2: "2026-07-31", include_casual: "false",
  }));
  const fetchImpl = async (url, init) => {
    const params = new URL(url).searchParams;
    calls.push(new URL(url));
    assert.match(init.headers["User-Agent"], /KingfisherHollowCountySpeciesDetector/);
    if (params.get("d1")) {
      if (params.get("id_above") === "0") return Response.json({ results: [
        observation(10, 11, "2026-07-12", "Newus species", "New Species"),
        observation(11, 11, "2026-07-03", "Newus species", "New Species"),
        observation(12, 22, "2026-07-08", "Oldus species"),
      ] });
      return Response.json({ results: [] });
    }
    assert.equal(new URL(url).pathname, "/v1/observations/species_counts");
    return Response.json({
      total_results: 1,
      results: [{ taxon: { id: 22, rank: "species" } }],
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
    firstObservationDate: "2026-07-03",
    observer: "observer-11",
    observationUrl: "https://www.inaturalist.org/observations/11",
  }]);
  assert.equal(calls[0].searchParams.get("per_page"), "200");
  assert.equal(calls[0].searchParams.get("id_above"), "0");
  assert.equal(calls[0].searchParams.get("verifiable"), "true");
  const historyCalls = calls.filter((url) => url.pathname.endsWith("/species_counts"));
  assert.equal(historyCalls.length, 1);
  assert.equal(historyCalls[0].searchParams.get("per_page"), "500");
  assert.equal(historyCalls[0].searchParams.get("page"), "1");
  assert.equal(historyCalls[0].searchParams.get("d2"), "2026-06-30");
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
