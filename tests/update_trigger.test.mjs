import assert from "node:assert/strict";
import { test } from "node:test";
import { onRequestPost } from "../functions/api/update.js";

const key = "dummy-private-update-key";
const token = "dummy-private-github-token";

function request(providedKey = "") {
  return new Request("https://example.com/api/update", {
    method: "POST",
    headers: { "x-kh-update-key": providedKey },
  });
}

for (const [name, env, expectedStates] of [
  ["both absent", {}, { UPDATE_TRIGGER_KEY: "missing", GITHUB_DISPATCH_TOKEN: "missing" }],
  ["empty trigger key", { UPDATE_TRIGGER_KEY: "", GITHUB_DISPATCH_TOKEN: token }, { UPDATE_TRIGGER_KEY: "empty", GITHUB_DISPATCH_TOKEN: "present" }],
  ["empty GitHub token", { UPDATE_TRIGGER_KEY: key, GITHUB_DISPATCH_TOKEN: "" }, { UPDATE_TRIGGER_KEY: "present", GITHUB_DISPATCH_TOKEN: "empty" }],
  ["null token", { UPDATE_TRIGGER_KEY: key, GITHUB_DISPATCH_TOKEN: null }, { UPDATE_TRIGGER_KEY: "present", GITHUB_DISPATCH_TOKEN: "missing" }],
  ["invalid type alongside missing token", { UPDATE_TRIGGER_KEY: { secret: key } }, { UPDATE_TRIGGER_KEY: "invalid_type", GITHUB_DISPATCH_TOKEN: "missing" }],
]) {
  test(`unconfigured update (${name}) logs only binding states and never dispatches`, async (t) => {
    const logs = [];
    let calls = 0;
    t.mock.method(console, "error", (...args) => logs.push(args));
    t.mock.method(globalThis, "fetch", async () => {
      calls++;
      return new Response(null, { status: 204 });
    });
    const response = await onRequestPost({ request: request(key), env });
    assert.equal(response.status, 503);
    assert.equal(calls, 0);
    assert.equal(logs.length, 1);
    assert.equal(logs[0].length, 1);
    assert.deepEqual(JSON.parse(logs[0][0]), {
      event: "survey_update_configuration_missing",
      bindings: expectedStates,
    });
    const body = await response.json();
    assert.equal(body.error, "Update trigger is not configured.");
    assert.equal(body.bindings, undefined);
    for (const secret of [key, token]) {
      assert.ok(!JSON.stringify(logs).includes(secret));
      assert.ok(!JSON.stringify(body).includes(secret));
    }
  });
}

test("configured update rejects absent and wrong keys without GitHub requests or logs", async (t) => {
  const log = t.mock.method(console, "error", () => {});
  const network = t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 204 }));
  for (const supplied of ["", "wrong-key"]) {
    const response = await onRequestPost({ request: request(supplied), env: { UPDATE_TRIGGER_KEY: key, GITHUB_DISPATCH_TOKEN: token } });
    assert.equal(response.status, 401);
  }
  assert.equal(network.mock.callCount(), 0);
  assert.equal(log.mock.callCount(), 0);
});

test("authorized update dispatches the intended workflow without logging credentials", async (t) => {
  const log = t.mock.method(console, "error", () => {});
  const network = t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "https://api.github.com/repos/drewweber/kingfisher-hollow-survey/actions/workflows/update.yml/dispatches");
    assert.equal(options.method, "POST");
    assert.equal(options.headers.authorization, `Bearer ${token}`);
    assert.deepEqual(JSON.parse(options.body), { ref: "main", inputs: { refresh_scope: "daily" } });
    return new Response(null, { status: 204 });
  });
  const response = await onRequestPost({ request: request(key), env: { UPDATE_TRIGGER_KEY: key, GITHUB_DISPATCH_TOKEN: token } });
  assert.equal(response.status, 202);
  assert.equal(network.mock.callCount(), 1);
  assert.equal(log.mock.callCount(), 0);
  assert.equal((await response.json()).ok, true);
});
