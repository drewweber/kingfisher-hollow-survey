# Kingfisher Hollow Field Alerts

This Cloudflare Worker watches Drew Weber's moth observations in the Kingfisher
Hollow iNaturalist project once per minute. It sends an ntfy phone notification
when a new or newly identified species crosses the field-documentation threshold:

- **Red:** possible first iNaturalist record for New York State or within 80 km
  of Kingfisher Hollow. The regional search includes well-covered Tompkins County
  and nearby northern Pennsylvania.
- **Yellow:** possible first iNaturalist record for Tioga County, with earlier
  records elsewhere in the region.
- **No rarity alert:** new only to Kingfisher Hollow or already recorded in
  Tioga County.

The label is deliberately "possible ... iNaturalist first." It is an immediate
prompt to take better photographs, not a final rarity claim. Museum specimens,
MPG, BAMONA, BugGuide, GBIF, and other sources still matter.

## How it works

- A one-minute Cloudflare Cron Trigger reads the project's most recently updated
  moth observations, so later identification changes are checked too.
- A Durable Object remembers handled observation/taxon combinations and prevents
  duplicate alerts.
- The bundled KH moth roster avoids regional API lookups for familiar species.
- New taxa receive three parallel iNaturalist counts: Tioga County, New York
  State, and an 80 km radius around the property.
- For a notable taxon, the Worker retrieves same-genus moths documented within
  80 km and asks Workers AI for a conservative field comparison. The phone alert
  names up to three plausible lookalikes, the external differences to check, and
  the exact photographs needed to separate them. Guidance is cached per taxon;
  if AI or the comparison lookup is unavailable, the alert falls back to the
  established family-level evidence checklist rather than delaying the rarity alert.
- The root page is a phone-friendly manual checker. Paste an iNaturalist URL to
  assess it immediately rather than waiting for the next scheduled poll.

This is independent of the survey report rebuild and does not trigger GitHub
Actions.

## Local setup

```sh
cd field-alerts
cp .dev.vars.example .dev.vars
npm install
npm test
npm run dev
```

Open the local URL printed by Wrangler. Scheduled polling can be tested with the
Wrangler scheduled-test URL printed in the terminal.

Regenerate the bundled known-moth baseline after a local data sync:

```sh
npm run build:known
```

## One-time Cloudflare setup

Deploy the Worker, then add its private values as Cloudflare Worker secrets:

```sh
npm run deploy
npx wrangler secret put CHECK_API_KEY
npx wrangler secret put NTFY_TOPIC
```

If the ntfy topic is reserved or self-hosted with authentication, also set:

```sh
npx wrangler secret put NTFY_TOKEN
```

Install the ntfy app on the phone and subscribe to the exact `NTFY_TOPIC`. Use a
long, unguessable topic name if using the public ntfy service.

After deployment, the first scheduled run establishes a quiet baseline and does
not send old observations. Use the manual checker to verify delivery immediately.

## Configuration

Non-secret defaults live in `wrangler.jsonc`. Runtime secrets are:

- `CHECK_API_KEY`: required by the manual checker endpoint.
- `NTFY_TOPIC`: private ntfy topic receiving red/yellow alerts.
- `NTFY_TOKEN`: optional authorization for a reserved or self-hosted topic.

The `AI` binding is declared in `wrangler.jsonc` and uses
`@cf/openai/gpt-oss-120b` only for notable new taxa and manual checks. No
additional API key is required; Workers AI usage is billed through Cloudflare.

`GET /api/health` reports whether the two required secrets are present without
revealing them.
