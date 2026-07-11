const integer = (value, fallback) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const number = (value, fallback) => {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export function runtimeConfig(env = {}) {
  return {
    projectId: integer(env.INAT_PROJECT_ID, 249580),
    username: env.INAT_USERNAME || "drewweber",
    countyPlaceId: integer(env.INAT_COUNTY_PLACE_ID, 653),
    statePlaceId: integer(env.INAT_STATE_PLACE_ID, 48),
    lepidopteraTaxonId: integer(env.INAT_LEPIDOPTERA_TAXON_ID, 47157),
    butterflyTaxonId: integer(env.INAT_BUTTERFLY_TAXON_ID, 47224),
    propertyLat: number(env.KH_LATITUDE, 42.2744),
    propertyLng: number(env.KH_LONGITUDE, -76.4926),
    regionRadiusKm: number(env.REGION_RADIUS_KM, 80),
    recentLimit: integer(env.RECENT_OBSERVATION_LIMIT, 30),
    requestPauseMs: integer(env.INAT_REQUEST_PAUSE_MS, 1100),
    alertCooldownDays: integer(env.ALERT_COOLDOWN_DAYS, 7),
    ntfyServer: (env.NTFY_SERVER || "https://ntfy.sh").replace(/\/$/, ""),
    ntfyTopic: env.NTFY_TOPIC || "",
    ntfyToken: env.NTFY_TOKEN || "",
  };
}
