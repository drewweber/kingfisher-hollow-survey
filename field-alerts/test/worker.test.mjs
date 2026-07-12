import assert from "node:assert/strict";
import test from "node:test";

import worker, { runPoll } from "../src/index.mjs";
import { InatClient } from "../src/inat-client.mjs";

class MemoryStorage {
  constructor(initial = {}) {
    this.values = new Map(Object.entries(initial));
  }

  async get(key) {
    return this.values.get(key);
  }

  async put(key, value) {
    if (typeof key === "object") {
      for (const [entryKey, entryValue] of Object.entries(key)) this.values.set(entryKey, entryValue);
      return;
    }
    this.values.set(key, value);
  }
}

const configEnv = {
  NTFY_TOPIC: "private-test-topic",
  CHECK_API_KEY: "private-test-key",
  INAT_REQUEST_PAUSE_MS: "0",
};

function moth(id, taxonId) {
  return {
    id,
    updated_at: "2026-07-10T12:00:00Z",
    taxon: {
      id: taxonId,
      name: "Examplea regionalis",
      preferred_common_name: "Example Moth",
      rank: "species",
      ancestor_ids: [47157],
    },
  };
}

function response(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

test("iNaturalist fetch is invoked without borrowing the client as this", async () => {
  function cloudflareStyleFetch() {
    assert.equal(this, undefined);
    return response({ total_results: 4 });
  }
  const client = new InatClient(cloudflareStyleFetch);
  assert.equal(await client.count({ taxon_id: 123 }), 4);
});

test("identification context finds same-genus moths recorded in the region", async () => {
  const calls = [];
  const fetchFn = async (url) => {
    const parsed = new URL(url);
    calls.push(parsed);
    if (parsed.pathname.endsWith("/taxa/212342")) {
      return response({ results: [{
        id: 212342,
        rank: "species",
        ancestors: [
          { id: 47155, name: "Tortricidae", rank: "family" },
          { id: 124620, name: "Acleris", rank: "genus" },
        ],
      }] });
    }
    if (parsed.pathname.endsWith("/observations/species_counts")) {
      return response({ results: [
        { count: 14, taxon: { id: 212349, name: "Acleris robinsoniana", preferred_common_name: "Robinson's Acleris Moth", rank: "species" } },
        { count: 1, taxon: { id: 212342, name: "Acleris maximana", rank: "species" } },
      ] });
    }
    throw new Error(`Unexpected URL: ${url}`);
  };
  const client = new InatClient(fetchFn);
  const context = await client.identificationContext(212342, {
    propertyLat: 42.2744,
    propertyLng: -76.4926,
    regionRadiusKm: 80,
    requestPauseMs: 0,
  });
  assert.equal(context.genusName, "Acleris");
  assert.equal(context.familyName, "Tortricidae");
  assert.deepEqual(context.regionalCandidates.map((item) => item.scientificName), ["Acleris robinsoniana"]);
  assert.equal(calls[1].searchParams.get("radius"), "80");
});

test("first poll quietly establishes a baseline", async () => {
  const storage = new MemoryStorage();
  const fetchFn = async (url) => {
    assert.match(String(url), /api\.inaturalist\.org/);
    return response({ results: [moth(10, 990001)] });
  };
  const result = await runPoll(storage, configEnv, fetchFn);
  assert.equal(result.bootstrapped, 1);
  assert.equal(result.alerts, 0);
  assert.ok(await storage.get("initialized-at"));
});

test("new possible state first sends one red ntfy alert", async () => {
  const storage = new MemoryStorage({ "initialized-at": "2026-07-10T11:00:00Z" });
  const observation = moth(11, 990002);
  let ntfyCalls = 0;
  let countCalls = 0;
  const fetchFn = async (url, init = {}) => {
    const parsed = new URL(url);
    if (parsed.hostname === "ntfy.sh") {
      ntfyCalls += 1;
      assert.equal(init.headers.priority, "5");
      return new Response("ok", { status: 200 });
    }
    if (parsed.pathname.endsWith("/observations") && parsed.searchParams.get("per_page") === "30") {
      return response({ results: [observation] });
    }
    countCalls += 1;
    if (parsed.searchParams.get("place_id") === "48") return response({ total_results: 1 });
    if (parsed.searchParams.get("place_id") === "653") return response({ total_results: 1 });
    if (parsed.searchParams.get("radius") === "80") return response({ total_results: 8 });
    throw new Error(`Unexpected URL: ${url}`);
  };

  const first = await runPoll(storage, configEnv, fetchFn);
  const second = await runPoll(storage, configEnv, fetchFn);
  assert.equal(first.alerts, 1);
  assert.equal(second.alerts, 0);
  assert.equal(ntfyCalls, 1);
  assert.equal(countCalls, 3);
});

test("notable alert includes AI comparison against regional congeners", async () => {
  const storage = new MemoryStorage({ "initialized-at": "2026-07-10T11:00:00Z" });
  const observation = moth(13, 990003);
  observation.taxon.name = "Acleris maximana";
  let notificationBody = "";
  let aiCalls = 0;
  const env = {
    ...configEnv,
    AI: {
      async run() {
        aiCalls += 1;
        return { response: JSON.stringify({
          comparisons: [{
            scientific_name: "Acleris robinsoniana",
            difference: "Target: narrow terminal fascia; alternative: broad dark terminal field.",
          }],
          photo_priorities: ["Capture the terminal fascia and costa square-on in one frame."],
          limitation: "Worn moths may require expert examination.",
        }) };
      },
    },
  };
  const fetchFn = async (url, init = {}) => {
    const parsed = new URL(url);
    if (parsed.hostname === "ntfy.sh") {
      notificationBody = init.body;
      return new Response("ok", { status: 200 });
    }
    if (parsed.pathname.endsWith("/observations") && parsed.searchParams.get("per_page") === "30") {
      return response({ results: [observation] });
    }
    if (parsed.pathname.endsWith("/taxa/990003")) {
      return response({ results: [{ ancestors: [
        { id: 47155, name: "Tortricidae", rank: "family" },
        { id: 124620, name: "Acleris", rank: "genus" },
      ] }] });
    }
    if (parsed.pathname.endsWith("/observations/species_counts")) {
      return response({ results: [{
        count: 14,
        taxon: {
          id: 212349,
          name: "Acleris robinsoniana",
          preferred_common_name: "Robinson's Acleris Moth",
          rank: "species",
        },
      }] });
    }
    if (parsed.searchParams.get("place_id") === "48") return response({ total_results: 1 });
    if (parsed.searchParams.get("place_id") === "653") return response({ total_results: 1 });
    if (parsed.searchParams.get("radius") === "80") return response({ total_results: 1 });
    throw new Error(`Unexpected URL: ${url}`);
  };

  const result = await runPoll(storage, env, fetchFn);
  assert.equal(result.alerts, 1);
  assert.equal(aiCalls, 1);
  assert.match(notificationBody, /RULE OUT:/);
  assert.match(notificationBody, /Robinson's Acleris Moth/);
  assert.match(notificationBody, /DECISIVE PHOTOS:/);
});

test("iNaturalist throttling does not suppress AI lookalike guidance", async () => {
  const storage = new MemoryStorage({ "initialized-at": "2026-07-10T11:00:00Z" });
  const observation = moth(14, 990004);
  observation.taxon.name = "Sigela brauneata";
  let notificationBody = "";
  let aiCalls = 0;
  const env = {
    ...configEnv,
    AI: {
      async run(_model, input) {
        aiCalls += 1;
        assert.match(input.messages[1].content, /Genus: Sigela/);
        return { response: {
          comparisons: [{
            scientific_name: "Eupithecia miserulata",
            difference: "Target: the forewing postmedial line is evenly scalloped; alternative: the line bends sharply at the costa.",
          }],
          photo_priorities: ["Capture the entire forewing postmedial line square-on from costa to inner margin."],
          limitation: "A worn moth may still require expert examination.",
        } };
      },
    },
  };
  const fetchFn = async (url, init = {}) => {
    const parsed = new URL(url);
    if (parsed.hostname === "ntfy.sh") {
      notificationBody = init.body;
      return new Response("ok", { status: 200 });
    }
    if (parsed.pathname.endsWith("/observations") && parsed.searchParams.get("per_page") === "30") {
      return response({ results: [observation] });
    }
    if (parsed.pathname.endsWith("/taxa/990004")) return response({}, 429);
    if (parsed.searchParams.get("place_id") === "48") return response({ total_results: 1 });
    if (parsed.searchParams.get("place_id") === "653") return response({ total_results: 1 });
    if (parsed.searchParams.get("radius") === "80") return response({ total_results: 1 });
    throw new Error(`Unexpected URL: ${url}`);
  };

  const result = await runPoll(storage, env, fetchFn);
  assert.equal(result.alerts, 1);
  assert.equal(aiCalls, 1);
  assert.match(notificationBody, /Eupithecia miserulata/);
  assert.match(notificationBody, /forewing postmedial line/);
});

test("known KH taxa skip all rarity count calls", async () => {
  const storage = new MemoryStorage({ "initialized-at": "2026-07-10T11:00:00Z" });
  const fetchFn = async (url) => {
    const parsed = new URL(url);
    if (parsed.searchParams.get("per_page") === "30") {
      return response({ results: [moth(12, 83860)] });
    }
    throw new Error(`Known taxon unexpectedly caused another request: ${url}`);
  };
  const result = await runPoll(storage, configEnv, fetchFn);
  assert.equal(result.skippedKnown, 1);
  assert.equal(result.assessed, 0);
});

test("manual checker rejects an incorrect access key before reaching state", async () => {
  const env = {
    CHECK_API_KEY: "correct-key",
    ALERT_STATE: {
      idFromName: () => "id",
      get: () => ({ fetch: () => { throw new Error("should not be called"); } }),
    },
  };
  const request = new Request("https://alerts.example/api/check", {
    method: "POST",
    headers: { authorization: "Bearer wrong-key" },
    body: "{}",
  });
  const result = await worker.fetch(request, env);
  assert.equal(result.status, 401);
});

test("checker page has labelled controls and a live status region", async () => {
  const result = await worker.fetch(new Request("https://alerts.example/"), {});
  const html = await result.text();
  assert.match(html, /<label[^>]+for="observation"/);
  assert.match(html, /role="status"/);
  assert.match(html, /Check observation/);
});
