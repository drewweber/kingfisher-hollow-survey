import { buildAssessment, buildKnownAssessment, isMothObservation, parseObservationId, SPECIES_RANKS } from "./alert-core.mjs";
import { runtimeConfig } from "./config.mjs";
import { InatClient } from "./inat-client.mjs";
import { generateIdentificationGuidance } from "./id-guidance.mjs";
import { KNOWN_MOTH_IDS } from "./known-moths.mjs";
import { sendNtfy } from "./notifier.mjs";
import { checkerPage } from "./ui.mjs";

const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  },
});

const observationKey = (id) => `observation:${id}`;
const knownTaxonKey = (id) => `known-taxon:${id}`;
const alertKey = (taxonId, level) => `alert:${taxonId}:${level}`;
const guidanceKey = (taxonId) => `identification-guidance:v1:${taxonId}`;

function stateStub(env) {
  const id = env.ALERT_STATE.idFromName("kingfisher-hollow");
  return env.ALERT_STATE.get(id);
}

function observationState(observation) {
  return {
    taxonId: observation.taxon?.id || null,
    taxonRank: observation.taxon?.rank || null,
    updatedAt: observation.updated_at || null,
  };
}

export async function assessObservation(observation, config, client) {
  if (!isMothObservation(observation, config)) {
    throw new Error("That observation is not a moth in the Kingfisher Hollow project.");
  }
  if (!observation.taxon) {
    return buildAssessment(observation, { county: 0, state: 0, regional: 0 }, config);
  }
  if (!SPECIES_RANKS.has(observation.taxon.rank)) {
    return buildAssessment(observation, { county: 0, state: 0, regional: 0 }, config);
  }
  const totals = await client.countsForTaxon(observation.taxon.id, config);
  return buildAssessment(observation, totals, config);
}

async function addIdentificationGuidance(storage, env, client, observation, assessment, config) {
  const taxonId = observation.taxon?.id;
  if (!taxonId || !SPECIES_RANKS.has(observation.taxon?.rank) || !env.AI?.run) return assessment;
  const key = guidanceKey(taxonId);
  try {
    let identification = await storage.get(key);
    if (!identification) {
      const context = await client.identificationContext(taxonId, config);
      identification = await generateIdentificationGuidance(env.AI, observation, context);
      if (identification) await storage.put(key, identification);
    }
    return identification ? { ...assessment, identification } : assessment;
  } catch (error) {
    console.error("Identification guidance unavailable", error);
    return assessment;
  }
}

async function recordHandled(storage, observation, assessment, notificationSent) {
  await storage.put(observationKey(observation.id), observationState(observation));
  if (observation.taxon?.id && SPECIES_RANKS.has(observation.taxon.rank)) {
    await storage.put(knownTaxonKey(observation.taxon.id), true);
    if (notificationSent && assessment?.actionable) {
      await storage.put(alertKey(observation.taxon.id, assessment.level), Date.now());
    }
  }
}

export async function runPoll(storage, env, fetchFn = fetch) {
  const config = runtimeConfig(env);
  if (!config.ntfyTopic) {
    return { ok: false, skipped: "ntfy-not-configured" };
  }

  const client = new InatClient(fetchFn);
  const observations = await client.recentMoths(config);
  const initialized = await storage.get("initialized-at");
  if (!initialized) {
    const baseline = { "initialized-at": new Date().toISOString() };
    for (const observation of observations) {
      baseline[observationKey(observation.id)] = observationState(observation);
    }
    await storage.put(baseline);
    return { ok: true, bootstrapped: observations.length, assessed: 0, alerts: 0 };
  }

  let assessed = 0;
  let alerts = 0;
  let skippedKnown = 0;
  for (const observation of [...observations].reverse()) {
    const current = observationState(observation);
    const previous = await storage.get(observationKey(observation.id));
    if (previous?.taxonId === current.taxonId) continue;

    if (!isMothObservation(observation, config) || !observation.taxon) {
      await storage.put(observationKey(observation.id), current);
      continue;
    }

    if (!SPECIES_RANKS.has(observation.taxon.rank)) {
      await storage.put(observationKey(observation.id), current);
      continue;
    }

    const alreadyKnown = KNOWN_MOTH_IDS.has(observation.taxon.id)
      || await storage.get(knownTaxonKey(observation.taxon.id));
    if (alreadyKnown) {
      skippedKnown += 1;
      await storage.put(observationKey(observation.id), current);
      continue;
    }

    let assessment = await assessObservation(observation, config, client);
    assessed += 1;
    let notificationSent = false;
    if (assessment.actionable) {
      assessment = await addIdentificationGuidance(storage, env, client, observation, assessment, config);
      const previousAlert = await storage.get(alertKey(observation.taxon.id, assessment.level));
      const cooldownMs = config.alertCooldownDays * 24 * 60 * 60 * 1000;
      if (!previousAlert || Date.now() - Number(previousAlert) > cooldownMs) {
        await sendNtfy(assessment, config, fetchFn);
        notificationSent = true;
        alerts += 1;
      }
    }
    await recordHandled(storage, observation, assessment, notificationSent);
  }
  return { ok: true, checked: observations.length, assessed, alerts, skippedKnown };
}

export class AlertState {
  constructor(ctx, env) {
    this.storage = ctx.storage;
    this.env = env;
  }

  async fetch(request) {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/poll" && request.method === "POST") {
        return json(await runPoll(this.storage, this.env));
      }
      if (url.pathname === "/check" && request.method === "POST") {
        const body = await request.json();
        const observationId = parseObservationId(body.observation);
        const config = runtimeConfig(this.env);
        const client = new InatClient();
        const observation = await client.projectObservation(observationId, config);
        if (!observation) {
          return json({ ok: false, error: "That observation is not currently included in the Kingfisher Hollow project." }, 404);
        }
        const taxonId = observation.taxon?.id;
        const alreadyKnown = taxonId && (
          KNOWN_MOTH_IDS.has(taxonId) || await this.storage.get(knownTaxonKey(taxonId))
        );
        let assessment = alreadyKnown
          ? buildKnownAssessment(observation)
          : await assessObservation(observation, config, client);
        assessment = await addIdentificationGuidance(
          this.storage, this.env, client, observation, assessment, config,
        );
        let notificationSent = false;
        if (body.notify && assessment.actionable) {
          await sendNtfy(assessment, config);
          notificationSent = true;
        }
        await recordHandled(this.storage, observation, assessment, notificationSent);
        return json({ ok: true, assessment, notificationSent });
      }
      return json({ ok: false, error: "Not found." }, 404);
    } catch (error) {
      console.error(error);
      return json({ ok: false, error: error.message || "Field check failed." }, 502);
    }
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") {
      return new Response(checkerPage(), {
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "public, max-age=300",
          "content-security-policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
          "referrer-policy": "no-referrer",
          "x-content-type-options": "nosniff",
          "x-frame-options": "DENY",
        },
      });
    }
    if (request.method === "GET" && url.pathname === "/api/health") {
      return json({
        ok: true,
        ntfyConfigured: Boolean(env.NTFY_TOPIC),
        checkerConfigured: Boolean(env.CHECK_API_KEY),
        identificationGuidanceConfigured: Boolean(env.AI),
      });
    }
    if (request.method === "GET" && url.pathname === "/favicon.ico") {
      return new Response(null, { status: 204 });
    }
    if (request.method === "POST" && url.pathname === "/api/check") {
      if (!env.CHECK_API_KEY) return json({ ok: false, error: "The checker access key is not configured." }, 503);
      if (request.headers.get("authorization") !== `Bearer ${env.CHECK_API_KEY}`) {
        return json({ ok: false, error: "Access key not accepted." }, 401);
      }
      return stateStub(env).fetch("https://alert-state.internal/check", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: await request.text(),
      });
    }
    return json({ ok: false, error: "Not found." }, 404);
  },

  async scheduled(_controller, env, ctx) {
    ctx.waitUntil((async () => {
      const response = await stateStub(env).fetch("https://alert-state.internal/poll", { method: "POST" });
      if (!response.ok) console.error("Field alert poll failed", await response.text());
      else console.log("Field alert poll", await response.text());
    })());
  },
};
