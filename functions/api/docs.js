import { handleContract } from "../../src/public_api_contract.mjs";

export function onRequest(context) {
  return handleContract("docs", context);
}
