import { API_VERSION } from "./public_api_runtime.mjs";


const parameter = (name) => ({ $ref: `#/components/parameters/${name}` });
const jsonResponse = (schema) => ({
  description: "Successful JSON response. Set format=csv for CSV output.",
  content: {
    "application/json": { schema },
    "text/csv": { schema: { type: "string" } },
  },
});
const commonErrors = {
  "400": { $ref: "#/components/responses/BadRequest" },
  "405": { $ref: "#/components/responses/MethodNotAllowed" },
  "429": { $ref: "#/components/responses/RateLimited" },
  "503": { $ref: "#/components/responses/DataUnavailable" },
};

export const OPENAPI_DOCUMENT = {
  openapi: "3.1.0",
  info: {
    title: "Kingfisher Hollow Moth Survey API",
    version: API_VERSION,
    description: [
      "Public, read-only access to moth observations recorded at Kingfisher Hollow.",
      "A night is a distinct America/New_York calendar date represented by observed_on.",
      "Name and family filters are case-insensitive exact matches. Multiple filters use AND semantics.",
    ].join(" "),
  },
  servers: [{ url: "https://survey.kingfisher-hollow.com" }],
  tags: [
    { name: "Observations", description: "Observation-level iNaturalist records." },
    { name: "Species", description: "Species summaries derived from matching observations." },
    { name: "Nights", description: "One row per matching local calendar date." },
    { name: "Stats", description: "Aggregate counts and date range." },
  ],
  paths: {
    "/api/observations": {
      get: {
        tags: ["Observations"],
        summary: "List moth observations",
        parameters: [
          parameter("TaxonId"), parameter("Family"), parameter("ScientificName"),
          parameter("DateFrom"), parameter("DateTo"), parameter("Year"),
          parameter("Limit"), parameter("Offset"), parameter("Format"),
        ],
        responses: {
          "200": jsonResponse({ $ref: "#/components/schemas/ObservationCollection" }),
          ...commonErrors,
        },
      },
    },
    "/api/species": {
      get: {
        tags: ["Species"],
        summary: "List recorded moth species with occurrence summaries",
        parameters: [
          parameter("TaxonId"), parameter("Family"), parameter("ScientificName"),
          parameter("CommonName"), parameter("DateFrom"), parameter("DateTo"),
          parameter("Year"), parameter("Limit"), parameter("Offset"),
          parameter("Format"),
        ],
        responses: {
          "200": jsonResponse({ $ref: "#/components/schemas/SpeciesCollection" }),
          ...commonErrors,
        },
      },
    },
    "/api/nights": {
      get: {
        tags: ["Nights"],
        summary: "List local dates with matching moth observations",
        parameters: [
          parameter("TaxonId"), parameter("Family"), parameter("DateFrom"),
          parameter("DateTo"), parameter("Year"), parameter("Limit"),
          parameter("Offset"), parameter("Format"),
        ],
        responses: {
          "200": jsonResponse({ $ref: "#/components/schemas/NightCollection" }),
          ...commonErrors,
        },
      },
    },
    "/api/stats": {
      get: {
        tags: ["Stats"],
        summary: "Return aggregate moth occurrence statistics",
        parameters: [
          parameter("TaxonId"), parameter("Family"), parameter("DateFrom"),
          parameter("DateTo"), parameter("Year"), parameter("Format"),
        ],
        responses: {
          "200": jsonResponse({ $ref: "#/components/schemas/Stats" }),
          ...commonErrors,
        },
      },
    },
  },
  components: {
    parameters: {
      TaxonId: {
        name: "taxon_id", in: "query",
        description: "Exact positive iNaturalist taxon ID.",
        schema: { type: "integer", minimum: 1 },
      },
      Family: {
        name: "family", in: "query",
        description: "Case-insensitive exact scientific family name, such as Saturniidae.",
        schema: { type: "string", minLength: 1, maxLength: 200 },
      },
      ScientificName: {
        name: "scientific_name", in: "query",
        description: "Case-insensitive exact scientific species name.",
        schema: { type: "string", minLength: 1, maxLength: 200 },
      },
      CommonName: {
        name: "common_name", in: "query",
        description: "Case-insensitive exact common name.",
        schema: { type: "string", minLength: 1, maxLength: 200 },
      },
      DateFrom: {
        name: "date_from", in: "query",
        description: "Inclusive local start date.",
        schema: { type: "string", format: "date" },
      },
      DateTo: {
        name: "date_to", in: "query",
        description: "Inclusive local end date.",
        schema: { type: "string", format: "date" },
      },
      Year: {
        name: "year", in: "query",
        description: "Four-digit observation year. Intersects with date_from and date_to when combined.",
        schema: { type: "integer", minimum: 1900, maximum: 2100 },
      },
      Limit: {
        name: "limit", in: "query",
        description: "Maximum rows returned in this page.",
        schema: { type: "integer", minimum: 1, maximum: 500, default: 100 },
      },
      Offset: {
        name: "offset", in: "query",
        description: "Zero-based result offset.",
        schema: { type: "integer", minimum: 0, default: 0 },
      },
      Format: {
        name: "format", in: "query",
        description: "Response format.",
        schema: { type: "string", enum: ["json", "csv"], default: "json" },
      },
    },
    schemas: {
      Observation: {
        type: "object",
        required: [
          "observation_id", "taxon_id", "scientific_name", "common_name", "order",
          "family", "rank", "observed_on", "observed_at", "inat_url",
        ],
        properties: {
          observation_id: { type: "integer" },
          taxon_id: { type: "integer" },
          scientific_name: { type: "string" },
          common_name: { type: ["string", "null"] },
          order: { type: "string", example: "Lepidoptera" },
          family: { type: "string", example: "Saturniidae" },
          rank: { type: "string", example: "species" },
          observed_on: { type: "string", format: "date" },
          observed_at: { type: "string", format: "date-time" },
          inat_url: { type: "string", format: "uri" },
        },
      },
      Species: {
        type: "object",
        required: [
          "taxon_id", "scientific_name", "common_name", "order", "family", "rank",
          "observation_count", "night_count", "first_seen", "last_seen",
        ],
        properties: {
          taxon_id: { type: "integer" },
          scientific_name: { type: "string" },
          common_name: { type: ["string", "null"] },
          order: { type: "string" },
          family: { type: "string" },
          rank: { type: "string" },
          observation_count: { type: "integer", minimum: 1 },
          night_count: { type: "integer", minimum: 1 },
          first_seen: { type: "string", format: "date" },
          last_seen: { type: "string", format: "date" },
        },
      },
      Night: {
        type: "object",
        required: ["date", "observation_count", "species_count", "families"],
        properties: {
          date: { type: "string", format: "date" },
          observation_count: { type: "integer", minimum: 1 },
          species_count: { type: "integer", minimum: 1 },
          families: { type: "array", items: { type: "string" } },
        },
      },
      Stats: {
        type: "object",
        required: [
          "observation_count", "species_count", "night_count",
          "first_observation_date", "last_observation_date", "generated_at",
          "timezone", "data_version",
        ],
        properties: {
          observation_count: { type: "integer", minimum: 0 },
          species_count: { type: "integer", minimum: 0 },
          night_count: { type: "integer", minimum: 0 },
          first_observation_date: { type: ["string", "null"], format: "date" },
          last_observation_date: { type: ["string", "null"], format: "date" },
          generated_at: { type: "string", format: "date-time" },
          timezone: { type: "string", const: "America/New_York" },
          data_version: { type: "string" },
        },
      },
      CollectionMetadata: {
        type: "object",
        required: [
          "count", "limit", "offset", "next_offset", "results", "generated_at",
          "timezone", "data_version",
        ],
        properties: {
          count: { type: "integer", minimum: 0 },
          limit: { type: "integer", minimum: 1, maximum: 500 },
          offset: { type: "integer", minimum: 0 },
          next_offset: { type: ["integer", "null"], minimum: 0 },
          generated_at: { type: "string", format: "date-time" },
          timezone: { type: "string" },
          data_version: { type: "string" },
        },
      },
      ObservationCollection: {
        allOf: [
          { $ref: "#/components/schemas/CollectionMetadata" },
          { type: "object", properties: { results: { type: "array", items: { $ref: "#/components/schemas/Observation" } } } },
        ],
      },
      SpeciesCollection: {
        allOf: [
          { $ref: "#/components/schemas/CollectionMetadata" },
          { type: "object", properties: { results: { type: "array", items: { $ref: "#/components/schemas/Species" } } } },
        ],
      },
      NightCollection: {
        allOf: [
          { $ref: "#/components/schemas/CollectionMetadata" },
          { type: "object", properties: { results: { type: "array", items: { $ref: "#/components/schemas/Night" } } } },
        ],
      },
      Error: {
        type: "object",
        required: ["error", "message"],
        properties: {
          error: { type: "string", example: "invalid_date_from" },
          message: { type: "string", example: "date_from must use YYYY-MM-DD format" },
        },
      },
    },
    responses: {
      BadRequest: {
        description: "Invalid or unsupported query parameter.",
        content: { "application/json": { schema: { $ref: "#/components/schemas/Error" } } },
      },
      MethodNotAllowed: {
        description: "The API is read-only.",
        content: { "application/json": { schema: { $ref: "#/components/schemas/Error" } } },
      },
      RateLimited: {
        description: "The request rate was exceeded.",
        content: { "application/json": { schema: { $ref: "#/components/schemas/Error" } } },
      },
      DataUnavailable: {
        description: "The generated survey snapshot could not be loaded.",
        content: { "application/json": { schema: { $ref: "#/components/schemas/Error" } } },
      },
    },
  },
};

export const API_DOCS_HTML = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kingfisher Hollow Moth Survey API</title>
  <meta name="description" content="Public read-only API documentation for Kingfisher Hollow moth observations.">
  <style>
    :root { color-scheme: light; --ink:#17231f; --muted:#64706b; --line:#d7dfdb; --green:#216b59; --paper:#f7f9f8; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); background:var(--paper); font:16px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    header,main,footer { width:min(920px,calc(100% - 32px)); margin-inline:auto; }
    header { padding:56px 0 28px; border-bottom:1px solid var(--line); }
    h1,h2 { font-family:Georgia,"Times New Roman",serif; letter-spacing:0; }
    h1 { margin:0 0 12px; font-size:4rem; line-height:1.05; }
    h2 { margin:44px 0 12px; font-size:1.65rem; }
    p { max-width:72ch; }
    a { color:var(--green); text-underline-offset:3px; }
    nav { display:flex; flex-wrap:wrap; gap:18px; margin-top:24px; }
    code,pre { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
    code { font-size:.9em; }
    p code,.note code { overflow-wrap:anywhere; word-break:break-word; }
    pre { overflow:auto; padding:16px; background:#fff; border:1px solid var(--line); border-radius:6px; font-size:.86rem; }
    table { width:100%; border-collapse:collapse; background:#fff; }
    th,td { padding:12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
    th { font-size:.78rem; text-transform:uppercase; color:var(--muted); }
    .note { padding:16px 18px; border-left:3px solid var(--green); background:#fff; }
    footer { margin-top:56px; padding:24px 0 48px; border-top:1px solid var(--line); color:var(--muted); }
    @media (max-width:640px) { header { padding-top:32px; } h1 { font-size:2.35rem; } th,td { padding:10px 8px; } table { font-size:.88rem; } }
  </style>
</head>
<body>
  <header>
    <p>Kingfisher Hollow Biodiversity Survey</p>
    <h1>Moth Survey API</h1>
    <p>Public, read-only occurrence data for moths documented on the 30-acre Kingfisher Hollow property in Tioga County, New York.</p>
    <nav aria-label="API links">
      <a href="/api/openapi.json">OpenAPI schema</a>
      <a href="/">Survey site</a>
      <a href="https://www.inaturalist.org/projects/kingfisher-hollow-biodiversity-survey">iNaturalist project</a>
    </nav>
  </header>
  <main>
    <h2>Endpoints</h2>
    <table>
      <thead><tr><th>Endpoint</th><th>Returns</th></tr></thead>
      <tbody>
        <tr><td><a href="/api/observations"><code>/api/observations</code></a></td><td>Observation-level records with dates and iNaturalist links.</td></tr>
        <tr><td><a href="/api/species"><code>/api/species</code></a></td><td>Species totals, distinct date counts, and first and last dates.</td></tr>
        <tr><td><a href="/api/nights"><code>/api/nights</code></a></td><td>One row per local calendar date with matching records.</td></tr>
        <tr><td><a href="/api/stats"><code>/api/stats</code></a></td><td>Observation, species, and distinct-date totals.</td></tr>
      </tbody>
    </table>

    <h2>Filtering</h2>
    <p>Filters use AND semantics. Family and species names are case-insensitive exact matches. Dates use <code>YYYY-MM-DD</code> and are inclusive. The <code>year</code> filter intersects with explicit date bounds.</p>
    <pre><code>GET /api/stats?family=Saturniidae
GET /api/observations?family=Saturniidae&amp;date_from=2026-06-01&amp;limit=25
GET /api/species?scientific_name=Actias%20luna
GET /api/nights?taxon_id=47919&amp;year=2026</code></pre>

    <h2>Dates and nights</h2>
    <p class="note">A night is a distinct <code>observed_on</code> date in <code>America/New_York</code>. It is not a formal trapping-session record. Records with the same iNaturalist observation ID are counted once.</p>

    <h2>Pagination and CSV</h2>
    <p>Collection endpoints default to 100 rows. Use <code>limit</code> and <code>offset</code>; the maximum page size is 500. Add <code>format=csv</code> to any data endpoint for CSV output.</p>
    <pre><code>GET /api/observations?limit=500&amp;offset=500&amp;format=csv</code></pre>

    <h2>Errors and caching</h2>
    <p>Errors use stable JSON fields: <code>{"error":"invalid_date_from","message":"date_from must use YYYY-MM-DD format"}</code>. Responses include CORS, cache validators, pagination headers, and rate-limit headers. The dataset refreshes when the public survey rebuilds.</p>
  </main>
  <footer>API version ${API_VERSION}. No authentication is required. Exact coordinates and observer details are not exposed.</footer>
</body>
</html>`;

const CONTRACT_CACHE = "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800";

function contractHash(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

function contractHeaders(contentType, etag) {
  return new Headers({
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Accept, Content-Type, If-None-Match",
    "Access-Control-Max-Age": "86400",
    "Cache-Control": CONTRACT_CACHE,
    "Content-Type": contentType,
    "ETag": etag,
    "X-API-Version": API_VERSION,
    "X-Content-Type-Options": "nosniff",
  });
}

export function handleContract(kind, context) {
  const method = context.request.method.toUpperCase();
  if (method === "OPTIONS") {
    const headers = contractHeaders("text/plain; charset=utf-8", `W/"api-${kind}-${API_VERSION}"`);
    return new Response(null, { status: 204, headers });
  }
  if (!new Set(["GET", "HEAD"]).has(method)) {
    const headers = contractHeaders("application/json; charset=utf-8", `W/"api-${kind}-${API_VERSION}"`);
    headers.set("Cache-Control", "no-store");
    headers.set("Allow", "GET, HEAD, OPTIONS");
    return new Response(JSON.stringify({
      error: "method_not_allowed",
      message: "This public API is read-only; use GET, HEAD, or OPTIONS.",
    }), { status: 405, headers });
  }

  let body;
  let contentType;
  if (kind === "openapi") {
    body = JSON.stringify(OPENAPI_DOCUMENT);
    contentType = "application/json; charset=utf-8";
  } else if (kind === "docs") {
    body = API_DOCS_HTML;
    contentType = "text/html; charset=utf-8";
  } else {
    body = JSON.stringify({
      name: "Kingfisher Hollow Moth Survey API",
      version: API_VERSION,
      dataset: "kingfisher-hollow-moths",
      timezone: "America/New_York",
      documentation: "/api/docs",
      openapi: "/api/openapi.json",
      endpoints: ["/api/observations", "/api/species", "/api/nights", "/api/stats"],
    });
    contentType = "application/json; charset=utf-8";
  }
  const etag = `W/"api-${kind}-${contractHash(body)}"`;
  const headers = contractHeaders(contentType, etag);
  if (context.request.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers });
  }
  return new Response(method === "HEAD" ? null : body, { status: 200, headers });
}
