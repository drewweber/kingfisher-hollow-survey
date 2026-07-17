import { handleContract } from "../../src/public_api_contract.mjs";
import { handleNotFound } from "../../src/public_api_runtime.mjs";

export function onRequest(context) {
  const pathname = new URL(context.request.url).pathname;
  if (pathname === "/api" || pathname === "/api/") {
    return handleContract("index", context);
  }
  return handleNotFound(context);
}
