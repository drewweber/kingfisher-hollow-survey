import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

test("Pages deployment uses Cloudflare's production command", () => {
  const workflow = readFileSync(
    new URL("../.github/workflows/update.yml", import.meta.url),
    "utf8",
  );

  assert.match(
    workflow,
    /wrangler pages deploy public --project-name=kingfisher-survey --commit-dirty=true/,
  );
  assert.doesNotMatch(workflow, /wrangler pages deploy[^\n]*--branch=/);

  assert.match(workflow, /Verify Pages update bindings/);
  assert.match(workflow, /UPDATE_TRIGGER_KEY/);
  assert.match(workflow, /GITHUB_DISPATCH_TOKEN/);
});
