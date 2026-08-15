# Kingfisher Hollow Field Targets PWA

## Goal

Provide a phone-installable field guide for every target currently shown in the
survey's moth, butterfly, and dragonfly/damselfly gap lists. After one complete
online load, the target list, finding guidance, identification guidance,
reference photographs, filters, and detail views must work in airplane mode.

The existing survey is not converted into a PWA and its generated root document
must remain functionally unchanged. The guide build records the newly generated
root document's hash and fails if it mutates that file. Independent report runs
are not byte-comparable because Plotly assigns fresh random chart element IDs.

## Scope

`all targets` means targets derived from the three existing public gap analyses
in the same database snapshot:

- up to 50 moths selected for the current two-week/month window, with a
  conservative local host-guild signal used as a secondary ranking factor;
- 30 butterflies ranked by nearby records;
- 30 dragonflies and damselflies ranked by nearby records.

The much larger unfiltered regional gap pool is not bundled. Butterfly and
odonate membership follows the public selectors directly. Moths start with a
larger seasonal candidate slice so a defensible local guild signal can promote
a species that falls just below the regional-frequency top 50.

## Requirements

1. Generate target membership from `analyze.moth_county_gap`,
   `analyze.butterfly_gap`, and `analyze.odonate_gap`. Keep regional frequency
   as the moth baseline, then allow recent Kingfisher Hollow moths sharing an
   exact, sourced larval-host genus to boost a seasonal candidate.
2. Give every target common and scientific names, seasonal context, habitat and
   method tags, explicit daylight and/or dusk-night survey periods, a reason to
   look, finding guidance, identification evidence to photograph, named
   regional comparisons where available, and an explicit ID limitation. Only
   show a comparison after it has been deliberately vetted as a plausible
   confusion species. For each field-separable pair, name the visible character
   and state what that character looks like on both species. If an ordinary
   field view cannot resolve the pair, say so and name the genus, species group,
   or other higher level at which it should be reported.
3. Treat family-level guidance as an evidence protocol, not as a sourced
   species diagnosis. Never invent a field mark when the local database does
   not contain a vetted diagnostic key.
4. Bundle a local Creative Commons image for every target, with creator,
   source, license, license URL, and checksum. All-rights-reserved and unknown
   licenses fail the release.
5. Keep all application code, styles, data, icons, and required photographs on
   the same origin. Do not depend on CDNs, Google Fonts, iNaturalist, or an AI
   model for offline use.
6. Support common/scientific-name search, group filtering, an always-visible
   survey-period control, habitat, method, and local-flight-signal filtering,
   target details, browser back, keyboard navigation, and preserved list
   position. Daylight includes active adults and explicit methods such as
   flushing, beating, or leaf-mine searches; a generic host-search fallback
   does not make every nocturnal moth a daytime target.
7. When dusk-night is selected, use a persisted low-light red and black theme
   with dimmed target thumbnails and restrained identification imagery. Apply
   that preference before styles load so reopening the installed app does not
   produce a bright flash. Any-time and daylight views retain the standard
   field theme.
8. Display `Ready offline` only after the service worker verifies every release
   asset. Preserve the previous complete release when an update is interrupted.
9. Keep the package below 75 MB and expose the data date, guidance revision,
   target counts, download progress, and cache-repair state.
10. Register the worker only from `/field/service-worker.js` with `/field/`
   scope. It must never control `/`, the survey's external assets, or
   `/api/update`.
11. A missing target, required guidance field, image, attribution, approved
    license, or service-worker asset fails the build.

## Architecture

The guide is a separate static application deployed beside the survey at
`https://survey.kingfisher-hollow.com/field/`.

- `src/field_guide.py` reads the same SQLite snapshot and selectors as the
  report, enriches licensed image metadata through a persistent cache, and
  generates `public/field/`.
- `src/field_guidance.py` owns conservative family and group evidence
  protocols and the survey-period rules. Butterflies and most odonates are
  daylight targets; darners include dusk; moths are nocturnal unless known
  day-flying behavior or a named daylight detection method supports another
  period.
- `src/moth_guilds.py` combines a 14-day property activity window with a
  checked-in reduction of the Natural History Museum HOSTS dataset. Exact
  shared host genera can change moth order; very broad feeders and unknown
  associations cannot.
- `src/refresh_moth_hosts.py` refreshes that compact reference index
  occasionally. It is deliberately excluded from nightly automation.
- `field-guide/app/` owns the dependency-free phone interface.
- `field-guide/service-worker.js` is a scoped template populated with the
  complete versioned asset manifest.
- `report.py` writes the survey's static page set first, then builds the
  sibling guide. It does not add markup, registration code, or links to the
  survey.

A separate origin would provide even stronger operational isolation, but it
would require another Pages project, DNS record, token, and workflow. The
path-scoped deployment meets the immediate acceptance criteria while retaining
a strict browser-enforced service-worker boundary. Moving the generated folder
to a dedicated origin later does not require rewriting the app.

Refresh the checked-in host index when the seasonal pool or taxonomy changes
substantially:

```sh
.venv/bin/python src/refresh_moth_hosts.py
```

The command queries the reference source for a bounded seasonal/recent set and
writes `data/reference/moth-hosts.json`. Normal report builds read that local
file and make no HOSTS network requests.

## Update Lifecycle

1. The survey workflow syncs the current iNaturalist property roster into
   SQLite.
2. `report.py` rebuilds the three gap selectors and writes a new
   `/field/targets.json`. A species already present in the matching property
   table is excluded before target ranking. Moth candidates are first limited
   to the regional seasonal pool, then reranked using recent shared-host guilds.
3. The field-guide builder hashes the data, app sources, and complete asset
   manifest into a new release version. Cloudflare Pages deploys that release
   with the survey.
4. On each online app launch, the installed guide checks the service-worker
   script without using the HTTP cache. A changed worker downloads and verifies
   the complete new release before deleting the previous cache.
5. When the new worker takes control, the open app refreshes its visible target
   data. Browsers that support `WindowClient.navigate` also reload the installed
   window once, which upgrades sessions still running older app code.

The guide therefore does not change at the moment an observation is submitted.
It changes after the next successful data sync and deployment. When offline, it
deliberately retains the last complete release rather than showing a partial
update.

## Release Plan

1. Build and validate structured target records and licensed local media.
2. Build the mobile interface, manifest, icons, and scoped service worker.
3. Add unit tests for candidate sourcing, target counts, complete guidance,
   media rights, service-worker scope, package completeness, and unchanged root
   survey output.
4. Run the full report build and compare the root document hash.
5. Browser-test desktop and phone layouts, then reload the installed guide with
   networking disabled and exhaustively open all target records.
6. Push only after local acceptance passes; watch the GitHub Actions deployment
   and verify both the live survey and `/field/`.

## Acceptance

- Every target selected in that build is present exactly once.
- Every target opens offline with finding help, ID help, evidence checklist,
  image, and attribution.
- Comparison species are limited to vetted confusion pairs; no arbitrary
  same-family fallback is presented as a lookalike.
- Every field-separable comparison names visible traits for both species.
  Comparisons that cannot be resolved from an ordinary field view explicitly
  name the higher taxonomic level to report and do not invent a difference
  list.
- Search and every group/filter control work after a cold offline reload.
- Dusk-night selection immediately changes the interface and browser chrome to
  the low-light theme, survives a cold offline reload without a bright startup
  state, and returns to the standard theme when another period is selected.
- No required offline flow makes a request to another origin.
- The service worker's asset manifest contains every local target image and
  cannot control a URL outside `/field/`.
- The field-guide build leaves every generated survey page byte-for-byte
  untouched; the report build fails if any page hash changes.
- The guide fits 320-430 px phone widths without overlap and supports keyboard
  and screen-reader navigation.
