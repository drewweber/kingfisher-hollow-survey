import { handleYardmic } from "../../src/yardmic_runtime.mjs";

export function onRequest(context) {
  return handleYardmic(context);
}
