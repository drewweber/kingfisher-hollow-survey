import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";

import {
  __resetForTests,
  handleEndpoint,
  handleNotFound,
} from "../src/public_api_runtime.mjs";
import {
  API_DOCS_HTML,
  OPENAPI_DOCUMENT,
  handleContract,
} from "../src/public_api_contract.mjs";
import { onRequest as catchAllRoute } from "../functions/api/[[path]].js";
import { onRequest as observationsRoute } from "../functions/api/observations.js";


const fixture = {
  schema_version: 1,
  dataset: "kingfisher-hollow-moths",
  generated_at: "2026-07-17T12:00:00Z",
  timezone: "America/New_York",
  data_version: "fixture123456789",
  observations: [
    {
      observation_id: 105,
      taxon_id: 1,
      scientific_name: "Actias luna",
      common_name: "Luna Moth",
      order: "Lepidoptera",
      family: "Saturniidae",
      rank: "species",
      observed_on: "2026-06-11",
      observed_at: "2026-06-11T22:14:00-04:00",
      inat_url: "https://www.inaturalist.org/observations/105",
    },
    {
      observation_id: 104,
      taxon_id: 1,
      scientific_name: "Actias luna",
      common_name: "Luna Moth",
      order: "Lepidoptera",
      family: "Saturniidae",
      rank: "species",
      observed_on: "2026-06-11",
      observed_at: "2026-06-11T21:00:00-04:00",
      inat_url: "https://www.inaturalist.org/observations/104",
    },
    {
      observation_id: 103,
      taxon_id: 1,
      scientific_name: "Actias luna",
      common_name: "Luna Moth",
      order: "Lepidoptera",
      family: "Saturniidae",
      rank: "species",
      observed_on: "2026-06-12",
      observed_at: "2026-06-12T01:30:00-04:00",
      inat_url: "https://www.inaturalist.org/observations/103",
    },
    {
      observation_id: 102,
      taxon_id: 2,
      scientific_name: "Antheraea polyphemus",
      common_name: "Polyphemus Moth",
      order: "Lepidoptera",
      family: "Saturniidae",
      rank: "species",
      observed_on: "2025-08-19",
      observed_at: "2025-08-19T23:10:00-04:00",
      inat_url: "https://www.inaturalist.org/observations/102",
    },
    {
      observation_id: 101,
      taxon_id: 3,
      scientific_name: "Xestia c-nigrum",
      common_name: null,
      order: "Lepidoptera",
      family: "Noctuidae",
      rank: "species",
      observed_on: "2026-06-11",
      observed_at: "2026-06-11T20:00:00-04:00",
      inat_url: "https://www.inaturalist.org/observations/101",
    },
    // A repeated iNaturalist ID must never inflate counts.
    {
      observation_id: 105,
      taxon_id: 1,
      scientific_name: "Actias luna",
      common_name: "Duplicate Luna Moth",
      order: "Lepidoptera",
      family: "Saturniidae",
      rank: "species",
      observed_on: "2026-06-10",
      observed_at: "2026-06-10T20:00:00-04:00",
      inat_url: "https://www.inaturalist.org/observations/105",
    },
  ],
};

function context(path, { method = "GET", headers = {}, snapshot = fixture, limiter = null } = {}) {
  const env = {
    ASSETS: {
      fetch: async () => new Response(JSON.stringify(snapshot), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    },
  };
  if (limiter) env.API_RATE_LIMITER = limiter;
  return {
    request: new Request(`https://survey.kingfisher-hollow.com${path}`, { method, headers }),
    env,
  };
}

async function json(response) {
  return JSON.parse(await response.text());
}

beforeEach(() => {
  __resetForTests();
});

test("observations filter, sort, paginate, and expose only stable public fields", async () => {
  const response = await observationsRoute(context(
    "/api/observations?family=saturniidae&year=2026&limit=2&offset=1",
  ));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("access-control-allow-origin"), "*");
  assert.equal(response.headers.get("x-total-count"), "3");
  const body = await json(response);
  assert.equal(body.count, 3);
  assert.equal(body.next_offset, null);
  assert.deepEqual(body.results.map((row) => row.observation_id), [105, 104]);
  assert.equal(body.results[0].rank, "species");
  assert.equal("latitude" in body.results[0], false);
  assert.equal("user_login" in body.results[0], false);
});

test("species summarize distinct local dates and first and last sightings", async () => {
  const response = await handleEndpoint("species", context("/api/species?taxon_id=1"));
  const body = await json(response);
  assert.equal(body.count, 1);
  assert.deepEqual(body.results[0], {
    taxon_id: 1,
    scientific_name: "Actias luna",
    common_name: "Luna Moth",
    order: "Lepidoptera",
    family: "Saturniidae",
    rank: "species",
    observation_count: 3,
    night_count: 2,
    first_seen: "2026-06-11",
    last_seen: "2026-06-12",
  });
});

test("species common-name filtering is case-insensitive and preserves null names", async () => {
  let response = await handleEndpoint(
    "species",
    context("/api/species?common_name=luna%20moth"),
  );
  let body = await json(response);
  assert.equal(body.count, 1);
  assert.equal(body.results[0].taxon_id, 1);

  __resetForTests();
  response = await handleEndpoint("species", context("/api/species?family=Noctuidae"));
  body = await json(response);
  assert.equal(body.results[0].common_name, null);
});

test("nights return one row per local date with unique families and species", async () => {
  const response = await handleEndpoint(
    "nights",
    context("/api/nights?family=Saturniidae&limit=10"),
  );
  const body = await json(response);
  assert.equal(body.count, 3);
  assert.deepEqual(body.results.map((row) => row.date), [
    "2026-06-12", "2026-06-11", "2025-08-19",
  ]);
  assert.deepEqual(body.results[1], {
    date: "2026-06-11",
    observation_count: 2,
    species_count: 1,
    families: ["Saturniidae"],
  });
});

test("stats use stable fields and do not count duplicate observation IDs", async () => {
  let response = await handleEndpoint("stats", context("/api/stats"));
  let body = await json(response);
  assert.equal(body.observation_count, 5);
  assert.equal(body.species_count, 3);
  assert.equal(body.night_count, 3);
  assert.equal(body.first_observation_date, "2025-08-19");
  assert.equal(body.last_observation_date, "2026-06-12");

  __resetForTests();
  response = await handleEndpoint(
    "stats",
    context("/api/stats?family=SATURNIIDAE&year=2026"),
  );
  body = await json(response);
  assert.equal(body.observation_count, 3);
  assert.equal(body.species_count, 1);
  assert.equal(body.night_count, 2);
});

test("empty stats keep the same field names and use null date bounds", async () => {
  const response = await handleEndpoint(
    "stats",
    context("/api/stats?taxon_id=999999"),
  );
  const body = await json(response);
  assert.equal(body.observation_count, 0);
  assert.equal(body.species_count, 0);
  assert.equal(body.night_count, 0);
  assert.equal(body.first_observation_date, null);
  assert.equal(body.last_observation_date, null);
});

test("invalid parameters return clear stable errors", async (t) => {
  const cases = [
    ["/api/observations?date_from=06-11-2026", "invalid_date_from"],
    ["/api/observations?date_from=2026-06-12&date_to=2026-06-11", "invalid_date_range"],
    ["/api/observations?limit=501", "invalid_limit"],
    ["/api/observations?taxon_id=abc", "invalid_taxon_id"],
    ["/api/observations?format=xml", "invalid_format"],
    ["/api/observations?year=02026", "invalid_year"],
    ["/api/observations?station=pond", "unknown_parameter"],
    ["/api/observations?year=2026&year=2025", "duplicate_parameter"],
  ];
  for (const [path, code] of cases) {
    await t.test(code, async () => {
      __resetForTests();
      const response = await handleEndpoint("observations", context(path));
      assert.equal(response.status, 400);
      const body = await json(response);
      assert.equal(body.error, code);
      assert.equal(typeof body.message, "string");
    });
  }
});

test("CSV output uses declared fields and pagination headers", async () => {
  const response = await handleEndpoint(
    "observations",
    context("/api/observations?taxon_id=1&limit=1&format=csv"),
  );
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type"), /^text\/csv/);
  assert.equal(response.headers.get("x-total-count"), "3");
  const body = await response.text();
  assert.match(body, /^observation_id,taxon_id,scientific_name/);
  assert.match(body, /Actias luna/);
  assert.equal(body.trim().split("\r\n").length, 2);
});

test("OPTIONS, HEAD, and non-read methods behave explicitly", async () => {
  let response = await handleEndpoint(
    "observations",
    context("/api/observations", { method: "OPTIONS" }),
  );
  assert.equal(response.status, 204);
  assert.equal(response.headers.get("access-control-allow-methods"), "GET, HEAD, OPTIONS");

  __resetForTests();
  response = await handleEndpoint(
    "observations",
    context("/api/observations", { method: "HEAD" }),
  );
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "");

  response = await handleEndpoint(
    "observations",
    context("/api/observations", { method: "POST" }),
  );
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "GET, HEAD, OPTIONS");
  assert.equal((await json(response)).error, "method_not_allowed");
});

test("ETag validators return 304 for an unchanged representation", async () => {
  const first = await handleEndpoint("stats", context("/api/stats?family=Saturniidae"));
  const etag = first.headers.get("etag");
  assert.ok(etag);

  const second = await handleEndpoint(
    "stats",
    context("/api/stats?family=Saturniidae", { headers: { "if-none-match": etag } }),
  );
  assert.equal(second.status, 304);
  assert.equal(await second.text(), "");
});

test("a configured Cloudflare limiter can reject requests with JSON 429", async () => {
  const limiter = { limit: async () => ({ success: false }) };
  const response = await handleEndpoint(
    "stats",
    context("/api/stats", { limiter }),
  );
  assert.equal(response.status, 429);
  assert.equal(response.headers.get("retry-after"), "60");
  assert.equal((await json(response)).error, "rate_limited");
});

test("the in-memory fallback limiter rejects the 121st request per client and endpoint", async () => {
  const options = { headers: { "cf-connecting-ip": "203.0.113.12" } };
  for (let count = 0; count < 120; count += 1) {
    const response = await handleEndpoint("stats", context("/api/stats", options));
    assert.equal(response.status, 200);
  }
  const response = await handleEndpoint("stats", context("/api/stats", options));
  assert.equal(response.status, 429);
  assert.equal((await json(response)).error, "rate_limited");
});

test("unknown API paths return a CORS-enabled JSON 404", async () => {
  const response = handleNotFound(context("/api/not-a-route"));
  assert.equal(response.status, 404);
  assert.equal(response.headers.get("access-control-allow-origin"), "*");
  assert.equal((await json(response)).error, "not_found");
});

test("the Pages catch-all preserves the API landing route", async () => {
  let response = catchAllRoute(context("/api"));
  assert.equal(response.status, 200);
  assert.equal((await json(response)).name, "Kingfisher Hollow Moth Survey API");

  response = catchAllRoute(context("/api/not-a-route"));
  assert.equal(response.status, 404);
  assert.equal((await json(response)).error, "not_found");
});

test("missing data snapshot returns a clear 503 response", async () => {
  const broken = context("/api/stats");
  broken.env.ASSETS.fetch = async () => new Response("missing", { status: 404 });
  const originalError = console.error;
  console.error = () => {};
  try {
    const response = await handleEndpoint("stats", broken);
    assert.equal(response.status, 503);
    assert.equal((await json(response)).error, "data_unavailable");
  } finally {
    console.error = originalError;
  }
});

test("OpenAPI and human documentation describe every public endpoint", async () => {
  for (const path of ["/api/observations", "/api/species", "/api/nights", "/api/stats"]) {
    assert.ok(OPENAPI_DOCUMENT.paths[path]);
    assert.ok(OPENAPI_DOCUMENT.paths[path].get.responses["200"].content["text/csv"]);
    assert.match(API_DOCS_HTML, new RegExp(path.replaceAll("/", "\\/")));
  }
  const openapiResponse = handleContract("openapi", context("/api/openapi.json"));
  assert.equal(openapiResponse.status, 200);
  assert.equal((await json(openapiResponse)).openapi, "3.1.0");

  const docsResponse = handleContract("docs", context("/api/docs"));
  assert.equal(docsResponse.status, 200);
  assert.match(docsResponse.headers.get("content-type"), /^text\/html/);
  assert.match(await docsResponse.text(), /America\/New_York/);
});
