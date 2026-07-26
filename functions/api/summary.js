import { handleSummary } from "../../src/public_api_runtime.mjs";

export function onRequest(context) {
  return handleSummary(context);
}
