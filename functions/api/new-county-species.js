import { handleNewCountySpecies } from "../../src/new_county_species_runtime.mjs";

export function onRequest(context) {
  return handleNewCountySpecies(context);
}
