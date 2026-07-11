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
