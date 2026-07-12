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

`all targets` means the complete output of the three existing public target
selectors in the same database snapshot:

- up to 50 moths selected for the current two-week/month window;
- 30 butterflies ranked by nearby records;
- 30 dragonflies and damselflies ranked by nearby records.

The much larger unfiltered regional gap pool is not bundled in v1. The build
records target IDs and counts, so tests can prove parity with the public survey.

## Requirements

1. Generate target membership from `analyze.moth_county_gap`,
   `analyze.butterfly_gap`, and `analyze.odonate_gap` without copying or changing
   their ranking behavior.
2. Give every target common and scientific names, seasonal context, habitat and
   method tags, a reason to look, finding guidance, identification evidence to
   photograph, named regional comparisons where available, and an explicit ID
   limitation.
3. Treat family-level guidance as an evidence protocol, not as a sourced
   species diagnosis. Never invent a field mark when the local database does
   not contain a vetted diagnostic key.
4. Bundle a local Creative Commons image for every target, with creator,
   source, license, license URL, and checksum. All-rights-reserved and unknown
   licenses fail the release.
5. Keep all application code, styles, data, icons, and required photographs on
   the same origin. Do not depend on CDNs, Google Fonts, iNaturalist, or an AI
   model for offline use.
6. Support common/scientific-name search, group filtering, habitat and method
   filtering, target details, browser back, keyboard navigation, and preserved
   list position.
7. Display `Ready offline` only after the service worker verifies every release
   asset. Preserve the previous complete release when an update is interrupted.
8. Keep the package below 75 MB and expose the data date, guidance revision,
   target counts, download progress, and cache-repair state.
9. Register the worker only from `/field/service-worker.js` with `/field/`
   scope. It must never control `/`, the survey's external assets, or
   `/api/update`.
10. A missing target, required guidance field, image, attribution, approved
    license, or service-worker asset fails the build.

## Architecture

The guide is a separate static application deployed beside the survey at
`https://survey.kingfisher-hollow.com/field/`.

- `src/field_guide.py` reads the same SQLite snapshot and selectors as the
  report, enriches licensed image metadata through a persistent cache, and
  generates `public/field/`.
- `src/field_guidance.py` owns conservative family and group evidence
  protocols.
- `field-guide/app/` owns the dependency-free phone interface.
- `field-guide/service-worker.js` is a scoped template populated with the
  complete versioned asset manifest.
- `report.py` writes `public/index.html` first, then builds the sibling guide.
  It does not add markup, registration code, or links to the survey.

A separate origin would provide even stronger operational isolation, but it
would require another Pages project, DNS record, token, and workflow. The
path-scoped deployment meets the immediate acceptance criteria while retaining
a strict browser-enforced service-worker boundary. Moving the generated folder
to a dedicated origin later does not require rewriting the app.

## Release Plan

1. Build and validate structured target records and licensed local media.
2. Build the mobile interface, manifest, icons, and scoped service worker.
3. Add unit tests for selector parity, complete guidance, media rights, service
   worker scope, package completeness, and unchanged root survey output.
4. Run the full report build and compare the root document hash.
5. Browser-test desktop and phone layouts, then reload the installed guide with
   networking disabled and exhaustively open all target records.
6. Push only after local acceptance passes; watch the GitHub Actions deployment
   and verify both the live survey and `/field/`.

## Acceptance

- Every target selected in that build is present exactly once.
- Every target opens offline with finding help, ID help, evidence checklist,
  image, and attribution.
- Search and every group/filter control work after a cold offline reload.
- No required offline flow makes a request to another origin.
- The service worker's asset manifest contains every local target image and
  cannot control a URL outside `/field/`.
- The field-guide build leaves the exact `public/index.html` bytes written
  immediately before it untouched; the report build fails if the hash changes.
- The guide fits 320-430 px phone widths without overlap and supports keyboard
  and screen-reader navigation.
