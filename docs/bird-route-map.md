# Bird route-use map

The Birds page displays an owner-approved public aggregate: 5 m cell polygons and the number of distinct acquired eBird checklist routes touching each cell. It reads `data/bird-route-use-5m.json`; it never opens the private GPS archive during a site build.

The snapshot contains 628 acquired routes from an inventory of 686 checklists through November 18, 2026. The 58 unresolved exports include 46 missing and 12 flagged checklists. Missing exports are unknown coverage, not evidence of no route or no visit. This snapshot refresh is independent of the site's regular iNaturalist sync.

Each checklist contributes at most one count to each touched cell, regardless of point spacing, repeat passes, or duplicate export files. The analysis includes cell-boundary touches and disconnects 24 edges longer than 100 m while retaining measured endpoints. The local spherical equirectangular grid has approximately 5 m cells; positional GPS error can exceed that width. Without verified point timestamps, the map describes route-use frequency, not time spent. It does not describe bird abundance or individual bird locations.

Colors use a logarithmic scale: `log(count) / log(maximum)`, from one checklist to the highest cell count. This gives lower counts more color separation without changing the underlying totals. Legend labels and cell details show raw checklist counts; the current legend labels 1, 5, 20, 100 and 468 at their logarithmic positions. A snapshot whose maximum is one uses a single color and one legend label.

## Refresh

1. Refresh and reconcile the private checklist inventory, originals, acquisition logs, and route revisions. Revalidate retained checklists: an existing ID does not establish an unchanged route. If eBird exposes no reliable modification signal, record the resulting limitation instead of claiming changed-only export support.
2. Re-run the private route analysis with the prior `methods.json` as the fixed grid origin, preserving alignment across snapshots.
3. Run the exporter with explicit private input paths and a **new** output filename:

   ```sh
   python3 tools/export_bird_route_cells.py --grid PATH/grid-5m.json --methods PATH/methods.json --inventory PATH/inventory.json --output PATH/new-public-cells.json
   ```

4. Review the aggregate and its coverage metadata, then approve replacement of `data/bird-route-use-5m.json`. Build and test through the normal report pipeline. The exporter refuses to overwrite existing files.

Only the strictly allowlisted aggregate may be copied into the survey repository. Keep original GPX/KML, route linework, checklist memberships, source paths, per-checklist dates, logs and full method/projection records in the private archive. The loader rejects extra fields before generating the map.

## Browser rendering

The map uses native SVG polygons over OpenStreetMap raster tiles with visible attribution. It requires neither WebGL nor a new installed dependency. The JavaScript loads only on Birds. Buttons, keyboard controls and a checkbox support pan, zoom, reset and overlay visibility. The public page requests only the currently visible map tiles, using ordinary browser caching and referrer behavior; no offline download or tile prefetch is implemented. Only aggregate cell geometry/counts and summary coverage are embedded in the page.

The owner approved making the 5 m home-route aggregate public on November 18, 2026. That approval does not cover publishing the raw archive.
