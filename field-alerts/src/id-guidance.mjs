export const ID_GUIDANCE_MODEL = "@cf/openai/gpt-oss-120b";

const GUIDANCE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    comparisons: {
      type: "array",
      maxItems: 3,
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          scientific_name: { type: "string" },
          difference: { type: "string" },
        },
        required: ["scientific_name", "difference"],
      },
    },
    photo_priorities: {
      type: "array",
      maxItems: 3,
      items: { type: "string" },
    },
    limitation: { type: "string" },
  },
  required: ["comparisons", "photo_priorities", "limitation"],
};

const clean = (value, maxLength = 280) => String(value || "").trim().slice(0, maxLength);

function candidateLines(context) {
  if (!context.regionalCandidates?.length) {
    return "No same-genus species were returned by the 80 km iNaturalist comparison. Name another alternative only if it is a well-established Southern Tier New York lookalike.";
  }
  return context.regionalCandidates
    .map((candidate) => {
      const common = candidate.commonName ? ` / ${candidate.commonName}` : "";
      return `- ${candidate.scientificName}${common}: ${candidate.count} regional observations`;
    })
    .join("\n");
}

export function identificationPrompt(observation, context) {
  const taxon = observation.taxon || {};
  const common = taxon.preferred_common_name || "no common name";
  const observed = observation.observed_on || observation.time_observed_at || "date unavailable";
  return `You are a conservative eastern North American moth identification specialist helping a field photographer while the live moth may still be available.

Current iNaturalist identification: ${taxon.name} (${common})
Observed: ${observed}, Kingfisher Hollow, Tioga County, New York
Genus: ${context.genusName || "unavailable"}
Family: ${context.familyName || "unavailable"}

Same-genus species documented within 80 km:
${candidateLines(context)}

Return a rapid comparison guide, not a final identification.

For comparisons, choose at most three species that are genuinely confusable as adults in this region. Prefer the supplied regional list. If that list is non-empty, do not name a species outside it. For each, state one concise external difference in the form “Target: X; alternative: Y.” Name the exact mark or structure and where it occurs. Do not rely on vague overall color, size, habitat, or host plant unless it is truly diagnostic.

For photo_priorities, give at most three decisive photographs tied directly to those differences. Name the exact structure, wing region, line, spot, fringe, palp, antenna, hindwing, abdomen segment, or terminal feature that must be visible. Do not repeat generic advice such as “take dorsal and side views.”

If adults cannot be separated reliably from photographs, say so plainly in limitation and name the evidence required, such as genitalia, DNA, larval host association, or expert examination. Omit any comparison you cannot describe confidently. Never invent a mark.`;
}

function parseModelResponse(response) {
  const value = response?.response
    ?? response?.choices?.[0]?.message?.parsed
    ?? response?.choices?.[0]?.message?.content
    ?? response?.choices?.[0]?.text
    ?? response?.output_text
    ?? response;
  if (value && typeof value === "object") return value;
  if (typeof value !== "string") throw new Error("Identification model returned no structured text.");
  const json = value.trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/, "");
  try {
    return JSON.parse(json);
  } catch {
    const start = json.indexOf("{");
    const end = json.lastIndexOf("}");
    if (start === -1 || end <= start) throw new Error("Identification model returned no JSON object.");
    return JSON.parse(json.slice(start, end + 1));
  }
}

function sanitizeGuidance(raw, context) {
  const candidates = new Map(
    (context.regionalCandidates || []).map((candidate) => [
      candidate.scientificName.toLowerCase(),
      candidate,
    ]),
  );
  const restrictToCandidates = candidates.size > 0;
  const comparisons = [];
  for (const item of Array.isArray(raw?.comparisons) ? raw.comparisons : []) {
    const scientificName = clean(item?.scientific_name, 100);
    const difference = clean(item?.difference);
    if (!scientificName || !difference) continue;
    const candidate = candidates.get(scientificName.toLowerCase());
    if (restrictToCandidates && !candidate) continue;
    const label = candidate?.commonName
      ? `${candidate.commonName} (${candidate.scientificName})`
      : scientificName;
    comparisons.push({ scientificName, label, difference });
    if (comparisons.length === 3) break;
  }
  const photoPriorities = (Array.isArray(raw?.photo_priorities) ? raw.photo_priorities : [])
    .map((item) => clean(item))
    .filter(Boolean)
    .slice(0, 3);
  const limitation = clean(raw?.limitation, 320);
  if (!comparisons.length && !photoPriorities.length && !limitation) return null;
  return {
    comparisons,
    photoPriorities,
    limitation: limitation || "Rapid comparison only; retain the original files for expert review.",
    model: ID_GUIDANCE_MODEL,
  };
}

export async function generateIdentificationGuidance(ai, observation, context) {
  if (!ai?.run) return null;
  const response = await ai.run(ID_GUIDANCE_MODEL, {
    messages: [
      {
        role: "system",
        content: "Return only the requested JSON identification guide. Be conservative and omit any comparison whose visible diagnostic difference you do not know.",
      },
      { role: "user", content: identificationPrompt(observation, context) },
    ],
    response_format: {
      type: "json_schema",
      json_schema: GUIDANCE_SCHEMA,
    },
    temperature: 0,
    max_tokens: 1800,
  });
  return sanitizeGuidance(parseModelResponse(response), context);
}
