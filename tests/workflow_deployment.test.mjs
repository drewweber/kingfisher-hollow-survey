import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

const workflow = readFileSync(
  new URL("../.github/workflows/update.yml", import.meta.url),
  "utf8",
);
const bindingStep = workflow.split("- name: Verify Pages update bindings")[1]?.split("\n      - name:")[0];
const filter = bindingStep?.match(/\| jq -er '([\s\S]*?)'/)?.[1];
assert.ok(filter, "The production binding gate must contain an executable jq filter");

const sentinel = "test-secret-value-must-never-appear";
const secret = { type: "secret_text", value: sentinel };
const complete = { UPDATE_TRIGGER_KEY: secret, GITHUB_DISPATCH_TOKEN: secret };

for (const [name, response, accepted] of [
  ["missing result", { success: true }, false],
  ["empty bindings", { success: true, result: { deployment_configs: { production: { env_vars: {} } } } }, false],
  ["missing trigger key", { success: true, result: { deployment_configs: { production: { env_vars: { GITHUB_DISPATCH_TOKEN: secret } } } } }, false],
  ["missing dispatch token", { success: true, result: { deployment_configs: { production: { env_vars: { UPDATE_TRIGGER_KEY: secret } } } } }, false],
  ["plaintext binding", { success: true, result: { deployment_configs: { production: { env_vars: { ...complete, UPDATE_TRIGGER_KEY: { type: "plain_text", value: sentinel } } } } } }, false],
  ["API failure", { success: false, result: { deployment_configs: { production: { env_vars: complete } } } }, false],
  ["both encrypted bindings", { success: true, result: { deployment_configs: { production: { env_vars: complete } } } }, true],
  // Cloudflare does not return stored secret values: metadata is not runtime proof.
  ["encrypted metadata without values", { success: true, result: { deployment_configs: { production: { env_vars: { UPDATE_TRIGGER_KEY: { type: "secret_text" }, GITHUB_DISPATCH_TOKEN: { type: "secret_text" } } } } } }, true],
]) {
  test(`Pages binding gate ${accepted ? "accepts" : "rejects"} ${name} without revealing values`, () => {
    const result = spawnSync("jq", ["-er", filter], { input: JSON.stringify(response), encoding: "utf8" });
    assert.ifError(result.error);
    assert.equal(result.status === 0, accepted);
    assert.doesNotMatch(result.stdout + result.stderr, new RegExp(sentinel));
    assert.equal(result.stdout.trim(), accepted ? "Pages update binding metadata is configured; runtime verification is still required." : "");
  });
}
