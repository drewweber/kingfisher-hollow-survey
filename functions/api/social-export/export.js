import { handleExport } from "../../../src/social_export_render.mjs";

export function onRequest(context) {
  return handleExport(context);
}
