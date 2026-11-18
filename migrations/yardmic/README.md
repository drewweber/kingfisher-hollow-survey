# YardMic snapshot storage

Provision a D1 database for production and a separate database for previews.
Bind each to the corresponding Cloudflare Pages environment as `YARDMIC_DB`.
Apply `0001_snapshots.sql`, then `0002_recent_dates.sql` once per database before
deploying. Existing encrypted Pages variables must be preserved. The release
workflow checks for the production binding and encrypted YardMic key.

Only normalized, validated detection dates and their provenance are saved.
Recent and historical snapshots have independent refresh leases. Recent records
are checked at most once every two minutes, history every six hours; a new date
can refresh sooner. Failed requests back off from two to fifteen minutes.
Concurrent refreshes are fenced by a thirty-second lease and transactional writes.

Saved evidence is eligible for display for thirty days from its original
estimated source time. Failed retries do not renew that deadline. Recent-hour
records remain attached to one source snapshot. Historical dates can be
reconciled from separate successful responses, retaining each date's timestamp;
whole-day corrections replace prior detections rather than unioning them.
Completed recent dates preserve later corrections when a history request is
unavailable across midnight. Physical saved rows may remain after their display
deadline until replaced or cleaned during subsequent successful refreshes.

Edge cache is an additional fallback, subject to eviction. It is not durable
storage. A new database can adopt an existing validated edge snapshot with its
original timestamps. If neither storage nor the upstream has usable evidence,
the page hides the affected panels and keeps the independent eBird content.

The page polls while visible and retains open disclosures, chart position and
focus. It shows dated saved records during errors and accepts validated recovery
without reloading. It never requests visitor microphone or audio access.

References: [Pages bindings](https://developers.cloudflare.com/pages/functions/bindings/),
[D1 transactions](https://developers.cloudflare.com/d1/worker-api/d1-database/),
[D1 limits](https://developers.cloudflare.com/d1/platform/limits/).
