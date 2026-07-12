import assert from "node:assert/strict";
import test from "node:test";

import {
  generateIdentificationGuidance,
  identificationPrompt,
} from "../src/id-guidance.mjs";
import { notificationFor } from "../src/alert-core.mjs";

const observation = {
  id: 123,
  observed_on: "2026-04-04",
  taxon: {
    id: 212342,
    name: "Acleris maximana",
    preferred_common_name: "",
    rank: "species",
  },
};

const context = {
  genusName: "Acleris",
  familyName: "Tortricidae",
  regionalCandidates: [
    {
      taxonId: 212349,
      scientificName: "Acleris robinsoniana",
      commonName: "Robinson's Acleris Moth",
      count: 14,
    },
    {
      taxonId: 212345,
      scientificName: "Acleris nivisellana",
      commonName: "Snowy-shouldered Acleris Moth",
      count: 39,
    },
  ],
};

test("identification prompt supplies the target and regional candidate set", () => {
  const prompt = identificationPrompt(observation, context);
  assert.match(prompt, /Acleris maximana/);
  assert.match(prompt, /Acleris robinsoniana/);
  assert.match(prompt, /within 80 km/i);
  assert.match(prompt, /Do not repeat generic advice/i);
});

test("structured guidance keeps regional candidates and exact field differences", async () => {
  const ai = {
    async run(_model, input) {
      assert.equal(input.temperature, 0);
      assert.equal(input.response_format.type, "json_schema");
      assert.equal(input.response_format.json_schema.type, "object");
      assert.equal(input.response_format.json_schema.schema, undefined);
      return {
        response: JSON.stringify({
          comparisons: [
            {
              scientific_name: "Acleris robinsoniana",
              difference: "Target: terminal fascia remains narrow at the costa; alternative: the dark terminal field expands broadly toward the costa.",
            },
            {
              scientific_name: "Inventeda ficta",
              difference: "This invented species must be discarded.",
            },
          ],
          photo_priorities: [
            "Photograph the forewing apex and terminal fascia square-on, with the costa in focus.",
            "Photograph the head and labial palps in strict side profile.",
          ],
          limitation: "A worn individual may still require expert examination.",
        }),
      };
    },
  };
  const guidance = await generateIdentificationGuidance(ai, observation, context);
  assert.equal(guidance.comparisons.length, 1);
  assert.match(guidance.comparisons[0].label, /Robinson's Acleris/);
  assert.match(guidance.comparisons[0].difference, /terminal fascia/);
  assert.equal(guidance.photoPriorities.length, 2);
});

test("notification replaces generic angles with lookalikes and decisive photographs", () => {
  const notification = notificationFor({
    level: "red",
    headline: "Possible regional iNaturalist first",
    species: "Acleris maximana",
    scientificName: "Acleris maximana",
    observationUrl: "https://www.inaturalist.org/observations/123",
    priorCounts: { county: 0, regional: 0, state: 8 },
    evidence: ["Generic dorsal photograph"],
    caveat: "Rapid screen only.",
    identification: {
      comparisons: [{
        label: "Robinson's Acleris Moth (Acleris robinsoniana)",
        difference: "Target: narrow terminal fascia; alternative: broad terminal field.",
      }],
      photoPriorities: ["Capture the terminal fascia and costa in one square-on frame."],
      limitation: "Worn moths may require expert examination.",
    },
  });
  assert.match(notification.message, /RULE OUT:/);
  assert.match(notification.message, /Acleris robinsoniana/);
  assert.match(notification.message, /DECISIVE PHOTOS:/);
  assert.doesNotMatch(notification.message, /Generic dorsal photograph/);
});
