export const SPECIES_RANKS = new Set([
  "species",
  "subspecies",
  "variety",
  "form",
  "hybrid",
  "subvariety",
  "subform",
]);

export function parseObservationId(value) {
  const match = String(value || "").trim().match(/(?:observations\/)?(\d+)(?:\/?(?:[?#].*)?)?$/);
  if (!match) {
    throw new Error("Enter a valid iNaturalist observation URL or observation number.");
  }
  return Number.parseInt(match[1], 10);
}

export function isMothObservation(observation, config) {
  const taxon = observation?.taxon;
  if (!taxon) return false;
  const ancestors = new Set(taxon.ancestor_ids || []);
  const isLepidoptera = taxon.id === config.lepidopteraTaxonId || ancestors.has(config.lepidopteraTaxonId);
  const isButterfly = taxon.id === config.butterflyTaxonId || ancestors.has(config.butterflyTaxonId);
  return isLepidoptera && !isButterfly;
}

export function classifyRarity({ statePrior, regionalPrior, countyPrior }) {
  const stateFirst = statePrior === 0;
  const regionalFirst = regionalPrior === 0;
  const countyFirst = countyPrior === 0;

  if (stateFirst || regionalFirst) {
    return { level: "red", stateFirst, regionalFirst, countyFirst };
  }
  if (countyFirst) {
    return { level: "yellow", stateFirst, regionalFirst, countyFirst };
  }
  return { level: "none", stateFirst, regionalFirst, countyFirst };
}

function priorCount(total) {
  // The live iNaturalist result includes the observation being assessed.
  return Math.max(0, Number(total || 0) - 1);
}

function taxonLabel(taxon) {
  return taxon.preferred_common_name || taxon.name || "Unresolved moth";
}

function evidenceProfile(taxon) {
  const scientific = taxon?.name || "";
  const common = taxon?.preferred_common_name || "";
  const combined = `${scientific} ${common}`.toLowerCase();

  if (scientific.startsWith("Catocala ") || combined.includes("underwing")) {
    return [
      "Sharp dorsal photograph with the forewings closed naturally",
      "Both hindwings fully exposed; their color and band shape are essential",
      "Side and underside views without handling away diagnostic scales",
      "A ruler or other scale reference",
      "Exact habitat, light type, time, and nearby oak, hickory, willow, or other likely host",
    ];
  }

  if (/sphinx|hawkmoth|hawk moth/.test(combined)) {
    return [
      "Sharp dorsal and side views showing the entire wing and body shape",
      "Hindwing exposed if it can be done without damaging the moth",
      "Close view of antennae, thorax, and abdomen markings",
      "A ruler or other scale reference",
      "Exact habitat, light type, time, and nearby likely host plants",
    ];
  }

  if (scientific.startsWith("Acronicta ") || combined.includes("dagger moth")) {
    return [
      "Several sharply focused dorsal photographs at slightly different exposures",
      "Side view, hindwing if visible, and a close view of the abdomen",
      "Antennae and face photographed head-on or obliquely",
      "A ruler or other scale reference",
      "Exact habitat, light type, time, and nearby host plants; retain the original full-resolution files",
    ];
  }

  if (/tortrix|leafroller|leaf-roller|leaf miner|leaf-miner|mompha|coleophora|gelechi|micro moth|micromoth/.test(combined)) {
    return [
      "Multiple magnified dorsal photographs with the wing pattern square to the camera",
      "Side and head views showing palps and antennae",
      "A millimeter ruler or another precise scale reference",
      "Photograph the leaf mine, case, feeding sign, or host plant when present",
      "Exact habitat, light type, and time; keep the identification provisional if photographs are insufficient",
    ];
  }

  if (/prominent|kitten|furcula|datana/.test(combined)) {
    return [
      "Sharp dorsal view showing both forewings without glare",
      "Side profile showing thorax, abdomen, and resting posture",
      "Hindwing exposed if practical",
      "A ruler or other scale reference",
      "Exact habitat, light type, time, and nearby hardwood host plants",
    ];
  }

  return [
    "Several sharp dorsal photographs at different exposures",
    "Side view plus hindwing and underside if practical",
    "Close views of antennae, face, thorax, and abdomen tip",
    "A ruler or other scale reference",
    "Exact habitat, light type, time, and nearby host plants; retain the original full-resolution files",
  ];
}

function headlineFor(classification) {
  if (classification.level === "yellow") return "Possible Tioga County iNaturalist first";
  if (classification.stateFirst && classification.regionalFirst) {
    return "Possible New York and regional iNaturalist first";
  }
  if (classification.stateFirst) return "Possible New York iNaturalist first";
  if (classification.regionalFirst) return "Possible regional iNaturalist first";
  return "Previously documented in Tioga County";
}

export function buildAssessment(observation, totals, config) {
  const taxon = observation.taxon || {};
  const species = taxonLabel(taxon);
  const scientificName = taxon.name || "";
  const observationUrl = `https://www.inaturalist.org/observations/${observation.id}`;

  if (!SPECIES_RANKS.has(taxon.rank)) {
    return {
      level: "unresolved",
      actionable: false,
      headline: "Identification is not yet at species level",
      species,
      scientificName,
      observationId: observation.id,
      observationUrl,
      reasons: ["Rarity cannot be assessed reliably until the observation has a species-level identification."],
      evidence: evidenceProfile(taxon),
      priorCounts: null,
      caveat: "Keep photographing it. A later identification change will be checked automatically.",
    };
  }

  const priorCounts = {
    state: priorCount(totals.state),
    regional: priorCount(totals.regional),
    county: priorCount(totals.county),
  };
  const classification = classifyRarity({
    statePrior: priorCounts.state,
    regionalPrior: priorCounts.regional,
    countyPrior: priorCounts.county,
  });
  const reasons = [];
  if (classification.stateFirst) reasons.push("No earlier iNaturalist observations found in New York State.");
  if (classification.regionalFirst) {
    reasons.push(`No earlier iNaturalist observations found within ${config.regionRadiusKm} km of Kingfisher Hollow, including Tompkins County and nearby northern Pennsylvania.`);
  }
  if (classification.level === "yellow") {
    reasons.push("No earlier iNaturalist observations found in Tioga County, but the species is documented elsewhere in the region.");
  }
  if (classification.level === "none") {
    reasons.push("Earlier iNaturalist observations already exist in Tioga County.");
  }

  return {
    level: classification.level,
    actionable: classification.level === "red" || classification.level === "yellow",
    headline: headlineFor(classification),
    species,
    scientificName,
    observationId: observation.id,
    observationUrl,
    reasons,
    evidence: evidenceProfile(taxon),
    priorCounts,
    flags: classification,
    caveat: "This is a rapid iNaturalist screening result, not a final rarity determination. Historical specimens and other databases may contain additional records.",
  };
}

export function buildKnownAssessment(observation) {
  const taxon = observation.taxon || {};
  return {
    level: "none",
    actionable: false,
    headline: "Already documented at Kingfisher Hollow",
    species: taxonLabel(taxon),
    scientificName: taxon.name || "",
    observationId: observation.id,
    observationUrl: `https://www.inaturalist.org/observations/${observation.id}`,
    reasons: ["This taxon is already in the Kingfisher Hollow moth roster, so it cannot be a new county, regional, or state record from this observation."],
    evidence: evidenceProfile(taxon),
    priorCounts: null,
    caveat: "No rarity alert is needed. Additional photographs can still help if the identification is uncertain or later changes.",
  };
}

export function notificationFor(assessment) {
  const name = assessment.scientificName
    ? `${assessment.species} (${assessment.scientificName})`
    : assessment.species;
  const prefix = assessment.level === "red" ? "RED" : "YELLOW";
  const counts = assessment.priorCounts
    ? `Earlier records: Tioga ${assessment.priorCounts.county}; 80 km region ${assessment.priorCounts.regional}; New York ${assessment.priorCounts.state}.`
    : "";
  return {
    title: `${prefix}: ${assessment.headline}`,
    message: [
      name,
      counts,
      "Photograph more before release:",
      ...assessment.evidence.slice(0, 4).map((item) => `- ${item}`),
      assessment.caveat,
    ].filter(Boolean).join("\n"),
    priority: assessment.level === "red" ? "5" : "3",
    tags: assessment.level === "red" ? "rotating_light,camera" : "warning,camera",
    click: assessment.observationUrl,
  };
}
