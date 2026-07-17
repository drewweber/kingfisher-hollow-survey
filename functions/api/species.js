import { handleEndpoint } from "../../src/public_api_runtime.mjs";

export function onRequest(context) {
  return handleEndpoint("species", context);
}
