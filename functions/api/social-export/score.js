import { handlePhotoScoring } from "../../../src/social_export_scoring.mjs";

export function onRequest(context) {
  return handlePhotoScoring(context);
}
