import { handleObservationSearch } from "../../../src/social_export_runtime.mjs";

export function onRequest(context) {
  return handleObservationSearch(context);
}
