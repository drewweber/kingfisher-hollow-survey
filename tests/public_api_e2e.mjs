import assert from "node:assert/strict";
import { test } from "node:test";

import { API_VERSION } from "../src/public_api_runtime.mjs";


const BASE_URL = (process.env.API_BASE_URL || "http://127.0.0.1:8788").replace(/\/$/, "");
const MAX_RESPONSE_MS = 2_000;

async function fetchResponse(path, init = {}) {
  const started = performance.now();
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "user-agent": "Kingfisher-Hollow-API-acceptance/1.0",
      ...(init.headers || {}),
    },
  });
  const elapsed = performance.now() - started;
  return { response, elapsed };
}

async function fetchJson(path, expectedStatus = 200, init = {}) {
  const { response, elapsed } = await fetchResponse(path, init);
  assert.equal(response.status, expectedStatus, `${path} returned HTTP ${response.status}`);
  assert.match(response.headers.get("content-type") || "", /^application\/json/);
  assert.equal(response.headers.get("set-cookie"), null);
  const body = await response.json();
  return { body, response, elapsed };
}

async function waitForDeployment() {
  let lastVersion = null;
  for (let attempt = 0; attempt < 12; attempt += 1) {
    try {
      const { body } = await fetchJson(`/api?deployment_probe=${Date.now()}`);
      lastVersion = body.version;
      if (lastVersion === API_VERSION) return;
    } catch (_error) {
      // Cloudflare's custom domain can take a few seconds to switch deployments.
    }
    await new Promise((resolve) => setTimeout(resolve, 5_000));
  }
  assert.fail(`Expected API version ${API_VERSION}; received ${lastVersion || "no response"}`);
}

await waitForDeployment();

test("family statistics return filtered counts and local-date bounds", async () => {
  const { body, response, elapsed } = await fetchJson("/api/stats?family=Saturniidae");
  assert.ok(elapsed < MAX_RESPONSE_MS, `stats took ${Math.round(elapsed)} ms`);
  assert.deepEqual(body.filters, { family: "Saturniidae" });
  for (const field of ["observation_count", "species_count", "night_count"]) {
    assert.equal(typeof body[field], "number");
  }
  for (const field of ["first_observation_date", "last_observation_date"]) {
    assert.ok(body[field] === null || /^\d{4}-\d{2}-\d{2}$/.test(body[field]));
  }
  assert.equal(response.headers.get("access-control-allow-origin"), "*");
});

test("combined biodiversity summary returns pollable integer totals", async () => {
  const { body, response, elapsed } = await fetchJson("/api/summary");
  assert.ok(elapsed < MAX_RESPONSE_MS, `summary took ${Math.round(elapsed)} ms`);
  for (const field of ["birds", "moths", "totalSpecies"]) {
    assert.equal(Number.isInteger(body[field]), true);
    assert.ok(body[field] >= 0);
  }
  assert.ok(body.totalSpecies >= body.birds);
  assert.ok(body.totalSpecies >= body.moths);
  assert.match(body.updatedAt, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
  assert.match(response.headers.get("cache-control") || "", /max-age=300/);
  assert.equal(response.headers.get("access-control-allow-origin"), "*");
});

test("recorded Saturniidae species contain required occurrence summaries", async () => {
  const { body, elapsed } = await fetchJson("/api/species?family=Saturniidae&limit=500");
  assert.ok(elapsed < MAX_RESPONSE_MS, `species took ${Math.round(elapsed)} ms`);
  assert.equal(body.count, body.results.length);
  assert.equal(body.total, body.results.length);
  assert.equal(new Set(body.results.map((row) => row.taxon_id)).size, body.results.length);
  for (const row of body.results) {
    assert.equal(row.family, "Saturniidae");
    assert.equal(typeof row.observation_count, "number");
    assert.equal(typeof row.night_count, "number");
    assert.match(row.first_seen, /^\d{4}-\d{2}-\d{2}$/);
    assert.match(row.last_seen, /^\d{4}-\d{2}-\d{2}$/);
  }
});

test("an unrecorded Imperial Moth returns an explicit empty collection", async () => {
  const { body } = await fetchJson(
    "/api/observations?scientific_name=Eacles%20imperialis",
  );
  assert.equal(body.count, 0);
  assert.equal(body.total, 0);
  assert.deepEqual(body.results, []);
});

test("a Luna Moth result links to the same iNaturalist observation ID", async () => {
  const { body, elapsed } = await fetchJson(
    "/api/observations?scientific_name=Actias%20luna&limit=1",
  );
  assert.ok(elapsed < MAX_RESPONSE_MS, `observations took ${Math.round(elapsed)} ms`);
  assert.ok(body.total >= 1, "Actias luna should be present in the current survey data");
  const observation = body.results[0];
  assert.equal(
    observation.inat_url,
    `https://www.inaturalist.org/observations/${observation.observation_id}`,
  );

  const exact = await fetchJson(
    `/api/observations?observation_id=${observation.observation_id}`,
  );
  assert.equal(exact.body.total, 1);
  assert.equal(exact.body.results[0].observation_id, observation.observation_id);
});

test("Saturniidae night totals agree across aggregate and collection endpoints", async () => {
  const stats = await fetchJson("/api/stats?family=Saturniidae");
  const nights = await fetchJson("/api/nights?family=Saturniidae&limit=500");
  const observations = await fetchJson("/api/observations?family=Saturniidae&limit=1");
  const species = await fetchJson("/api/species?family=Saturniidae&limit=500");
  assert.equal(stats.body.night_count, nights.body.total);
  assert.equal(stats.body.observation_count, observations.body.total);
  assert.equal(stats.body.species_count, species.body.total);
  assert.equal(new Set(nights.body.results.map((row) => row.date)).size, nights.body.total);
});

test("OpenAPI exposes exactly five GPT Action operations", async () => {
  const { body } = await fetchJson("/api/openapi.json");
  assert.equal(body.openapi, "3.1.0");
  assert.deepEqual(body.servers, [{ url: "https://survey.kingfisher-hollow.com" }]);
  assert.deepEqual(body.security, []);
  const operationIds = Object.values(body.paths).map((path) => path.get.operationId).sort();
  assert.deepEqual(operationIds, [
    "getBiodiversitySummary",
    "getSurveyStats",
    "listObservationNights",
    "listObservations",
    "listSpecies",
  ]);
  for (const path of Object.values(body.paths)) {
    for (const parameter of path.get.parameters || []) {
      assert.equal(typeof parameter.name, "string");
      assert.equal(parameter.in, "query");
      assert.equal(parameter.$ref, undefined);
      assert.equal(typeof parameter.schema, "object");
    }
  }
});

test("documentation is actionable and all public operations are read-only", async () => {
  const { response } = await fetchResponse("/api/docs");
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") || "", /^text\/html/);
  const docs = await response.text();
  assert.match(docs, /href="\/api\/stats\?family=Saturniidae"/);
  assert.match(docs, /Use the Kingfisher Hollow Survey API for every question/);
  assert.match(docs, /\/api\/openapi\.json/);

  for (const path of [
    "/api", "/api/summary", "/api/species", "/api/observations", "/api/nights", "/api/stats",
    "/api/openapi.json", "/api/docs",
  ]) {
    for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
      const result = await fetchJson(path, 405, { method });
      assert.equal(result.body.error, "method_not_allowed");
    }
  }
  const invalid = await fetchJson("/api/observations?date_from=07-16-2026", 400);
  assert.equal(invalid.body.error, "invalid_date");
  const unknown = await fetchJson("/api/not-a-route", 404);
  assert.equal(unknown.body.error, "not_found");
  const preflight = await fetchResponse("/api/stats", { method: "OPTIONS" });
  assert.equal(preflight.response.status, 204);
  assert.equal(preflight.response.headers.get("access-control-allow-origin"), "*");
});
