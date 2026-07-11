import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAssessment,
  buildKnownAssessment,
  classifyRarity,
  notificationFor,
  parseObservationId,
} from "../src/alert-core.mjs";
import { runtimeConfig } from "../src/config.mjs";

const config = runtimeConfig({});

function observation(overrides = {}) {
  return {
    id: 123456,
    taxon: {
      id: 900001,
      name: "Catocala testata",
      preferred_common_name: "Test Underwing",
      rank: "species",
      ancestor_ids: [47157],
    },
    ...overrides,
  };
}

test("parses observation numbers and iNaturalist URLs", () => {
  assert.equal(parseObservationId("378352635"), 378352635);
  assert.equal(
    parseObservationId("https://www.inaturalist.org/observations/378352635?locale=en"),
    378352635,
  );
  assert.throws(() => parseObservationId("not an observation"), /valid iNaturalist/);
});

test("red is reserved for possible state or regional firsts", () => {
  assert.equal(classifyRarity({ statePrior: 0, regionalPrior: 9, countyPrior: 0 }).level, "red");
  assert.equal(classifyRarity({ statePrior: 50, regionalPrior: 0, countyPrior: 0 }).level, "red");
});

test("county-only first is yellow", () => {
  const result = classifyRarity({ statePrior: 120, regionalPrior: 18, countyPrior: 0 });
  assert.equal(result.level, "yellow");
  assert.equal(result.countyFirst, true);
  assert.equal(result.regionalFirst, false);
});

test("existing Tioga record produces no rarity alert", () => {
  assert.equal(classifyRarity({ statePrior: 120, regionalPrior: 18, countyPrior: 2 }).level, "none");
});

test("assessment subtracts the current observation from live totals", () => {
  const assessment = buildAssessment(observation(), { state: 1, regional: 1, county: 1 }, config);
  assert.equal(assessment.level, "red");
  assert.deepEqual(assessment.priorCounts, { state: 0, regional: 0, county: 0 });
  assert.match(assessment.evidence.join(" "), /hindwings fully exposed/i);
});

test("coarse identifications remain unresolved and do not claim rarity", () => {
  const coarse = observation({
    taxon: {
      id: 47157,
      name: "Lepidoptera",
      preferred_common_name: "Butterflies and Moths",
      rank: "order",
      ancestor_ids: [47157],
    },
  });
  const assessment = buildAssessment(coarse, { state: 0, regional: 0, county: 0 }, config);
  assert.equal(assessment.level, "unresolved");
  assert.equal(assessment.actionable, false);
});

test("known KH taxa return immediately without invented regional counts", () => {
  const assessment = buildKnownAssessment(observation());
  assert.equal(assessment.level, "none");
  assert.equal(assessment.priorCounts, null);
  assert.match(assessment.headline, /Already documented/);
});

test("Acleris and pug alerts request the small details needed for review", () => {
  const acleris = buildAssessment(observation({
    taxon: {
      id: 212342,
      name: "Acleris maximana",
      preferred_common_name: "",
      rank: "species",
      ancestor_ids: [47157],
    },
  }), { state: 1, regional: 1, county: 1 }, config);
  assert.match(acleris.evidence.join(" "), /millimeter ruler/i);
  assert.match(acleris.evidence.join(" "), /palps and antennae/i);

  const pug = buildAssessment(observation({
    taxon: {
      id: 338318,
      name: "Sigela brauneata",
      preferred_common_name: "Brown False Pug",
      rank: "species",
      ancestor_ids: [47157],
    },
  }), { state: 1, regional: 1, county: 1 }, config);
  assert.match(pug.evidence.join(" "), /fringe pattern/i);
  assert.match(pug.evidence.join(" "), /full-resolution image/i);
});

test("notification requests immediate evidence without claiming confirmed rarity", () => {
  const assessment = buildAssessment(observation(), { state: 1, regional: 1, county: 1 }, config);
  const notification = notificationFor(assessment);
  assert.match(notification.title, /^RED:/);
  assert.match(notification.message, /Photograph more before release/);
  assert.match(notification.message, /not a final rarity determination/);
});
