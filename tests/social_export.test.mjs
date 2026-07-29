import assert from "node:assert/strict";
import test from "node:test";

import {
  PRESETS,
  applyPhotoScores,
  fetchMatchingObservations,
  groupObservations,
  normalizeQuery,
  normalizeSettings,
  selectExportSpecies,
} from "../src/social_export_runtime.mjs";
import {
  analyzePixels,
  scorePhotoBatch,
} from "../src/social_export_scoring.mjs";
import {
  buildExport,
  coverSlideSvg,
  createSlidePlan,
  createZip,
  gridSlideSvg,
  wrapCommonName,
} from "../src/social_export_render.mjs";
import {
  createManifest as createBrowserManifest,
  createZipBlob,
} from "../social-export/browser-export.js";

function photo(id, dimensions = { width: 2400, height: 1800 }) {
  return {
    id,
    url: `https://inaturalist-open-data.s3.amazonaws.com/photos/${id}/medium.jpg`,
    original_dimensions: dimensions,
    attribution: `© drewweber, some rights reserved`,
    license_code: "cc-by-nc",
  };
}

function observation({
  id,
  taxonId,
  speciesId = taxonId,
  rank = "species",
  ancestors = [],
  photos = [photo(id * 10)],
  qualityGrade = "needs_id",
}) {
  return {
    id,
    observed_on: "2026-07-20",
    quality_grade: qualityGrade,
    faves_count: 0,
    user: { login: "drewweber" },
    taxon: {
      id: taxonId,
      parent_id: speciesId,
      rank,
      name: rank === "subspecies" ? "Actias luna minor" : `Species ${speciesId}`,
      preferred_common_name: rank === "subspecies" ? "Minor Luna Moth" : `Common ${speciesId}`,
      ancestor_ids: ancestors,
    },
    photos,
  };
}

const mothQuery = normalizeQuery({
  dateFrom: "2026-07-18",
  dateTo: "2026-07-26",
  taxonGroup: "moths",
  observer: "drewweber",
  includeUnresolvedTaxa: false,
});

test("National Moth Week preset normalizes to ten square 5x4 slides", () => {
  const preset = PRESETS["national-moth-week-2026"];
  const query = normalizeQuery(preset);
  const settings = normalizeSettings(preset, query);
  assert.deepEqual(query, mothQuery);
  assert.equal(settings.width, 1080);
  assert.equal(settings.height, 1080);
  assert.equal(settings.gridSize, "5x4");
  assert.equal(settings.gridColumns, 5);
  assert.equal(settings.gridRows, 4);
  assert.equal(settings.maximumSlides, 10);
  assert.equal(settings.fillToMaximumSlides, true);
  assert.equal(settings.fileStem, "moth-week-2026");
});

test("moth grouping excludes Papilionoidea and ignores unresolved taxa", () => {
  const grouped = groupObservations([
    observation({ id: 1, taxonId: 101 }),
    observation({ id: 2, taxonId: 202, ancestors: [47157, 47224] }),
    observation({ id: 3, taxonId: 303, rank: "genus" }),
  ], mothQuery);
  assert.equal(grouped.species.length, 1);
  assert.equal(grouped.species[0].taxonId, 101);
  assert.equal(grouped.summary.excludedButterflyCount, 1);
  assert.equal(grouped.summary.unresolvedCount, 1);
});

test("subspecies display is preserved while the parent species remains unique", () => {
  const grouped = groupObservations([
    observation({ id: 1, taxonId: 400, speciesId: 400, rank: "species" }),
    observation({ id: 2, taxonId: 401, speciesId: 400, rank: "subspecies" }),
  ], mothQuery);
  assert.equal(grouped.species.length, 1);
  assert.equal(grouped.species[0].speciesKey, "species:400");
  assert.equal(grouped.species[0].rank, "subspecies");
  assert.equal(grouped.species[0].scientificName, "Actias luna minor");
  assert.equal(grouped.species[0].candidates.length, 2);
});

test("iNaturalist pagination uses 200 records per request and follows all pages", async () => {
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(new URL(url).searchParams);
    const page = Number(new URL(url).searchParams.get("page"));
    const results = page === 1
      ? Array.from({ length: 200 }, (_, index) => ({ id: index + 1 }))
      : [{ id: 201 }];
    return new Response(JSON.stringify({ total_results: 201, results }), {
      headers: { "content-type": "application/json" },
    });
  };
  const results = await fetchMatchingObservations(mothQuery, {
    fetchImpl,
    cache: null,
    delay: async () => {},
  });
  assert.equal(results.length, 201);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].get("per_page"), "200");
  assert.equal(calls[0].get("photos"), "true");
  assert.equal(calls[0].get("user_id"), "drewweber");
});

test("iNaturalist rate limits are retried using Retry-After before surfacing an error", async () => {
  let calls = 0;
  const delays = [];
  const results = await fetchMatchingObservations(mothQuery, {
    cache: null,
    delay: async (milliseconds) => delays.push(milliseconds),
    fetchImpl: async () => {
      calls += 1;
      if (calls === 1) {
        return new Response(null, {
          status: 429,
          headers: { "retry-after": "2" },
        });
      }
      return new Response(JSON.stringify({
        total_results: 1,
        results: [{ id: 1 }],
      }), {
        headers: { "content-type": "application/json" },
      });
    },
  });
  assert.equal(calls, 2);
  assert.deepEqual(delays, [2_000]);
  assert.equal(results.length, 1);
});

test("malformed successful iNaturalist responses are retried before use", async () => {
  let calls = 0;
  const delays = [];
  const results = await fetchMatchingObservations(mothQuery, {
    cache: null,
    delay: async (milliseconds) => delays.push(milliseconds),
    fetchImpl: async () => {
      calls += 1;
      if (calls === 1) {
        return new Response("<?xml version=\"1.0\"?><Error>temporary</Error>", {
          headers: { "content-type": "application/xml" },
        });
      }
      return new Response(JSON.stringify({
        total_results: 1,
        results: [{ id: 1 }],
      }), {
        headers: { "content-type": "application/json" },
      });
    },
  });
  assert.equal(calls, 2);
  assert.deepEqual(delays, [1_000]);
  assert.equal(results.length, 1);
});

test("pixel analysis returns bounded visual-quality metrics and a stable hash", () => {
  const width = 32;
  const height = 32;
  const pixels = new Uint8Array(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const offset = (y * width + x) * 4;
      const value = (Math.floor(x / 2) + Math.floor(y / 2)) % 2 ? 230 : 25;
      pixels.set([value, value, value, 255], offset);
    }
  }
  const metrics = analyzePixels(pixels, width, height);
  for (const key of ["sharpness", "exposure", "contrast", "subjectOccupancy", "obstruction"]) {
    assert.ok(metrics[key] >= 0 && metrics[key] <= 1, `${key} is bounded`);
  }
  assert.match(metrics.perceptualHash, /^[01]{64}$/);
  assert.ok(metrics.sharpness > 0.5);
});

test("photo scoring batches tolerate an individual image-analysis failure", async () => {
  const results = await scorePhotoBatch([
    { photoId: 1, url: "https://static.inaturalist.org/photos/1/small.jpg" },
    { photoId: 2, url: "https://static.inaturalist.org/photos/2/small.jpg" },
  ], {
    analyzeImpl: async (item) => {
      if (item.photoId === 2) throw new Error("broken image");
      return {
        photoId: item.photoId,
        sharpness: 1,
        exposure: 1,
        contrast: 1,
        subjectOccupancy: 1,
        obstruction: 0,
        perceptualHash: "0".repeat(64),
      };
    },
  });
  assert.equal(results[0].sharpness, 1);
  assert.match(results[1].error, /broken image/);
});

test("automatic scoring penalizes a near-identical lower-quality candidate", () => {
  const grouped = groupObservations([
    observation({
      id: 1,
      taxonId: 101,
      photos: [photo(11), photo(12, { width: 1800, height: 1400 })],
    }),
  ], mothQuery);
  const scored = applyPhotoScores(grouped.species, [
    {
      photoId: 11,
      sharpness: .9,
      exposure: .9,
      contrast: .8,
      subjectOccupancy: .8,
      obstruction: .1,
      perceptualHash: "0".repeat(64),
    },
    {
      photoId: 12,
      sharpness: .85,
      exposure: .85,
      contrast: .75,
      subjectOccupancy: .75,
      obstruction: .15,
      perceptualHash: `${"0".repeat(63)}1`,
    },
  ]);
  assert.equal(scored[0].candidates[0].photoId, 11);
  assert.equal(scored[0].candidates[1].nearDuplicate, true);
});

test("automatic choices avoid repeating a near-identical image across species", () => {
  const grouped = groupObservations([
    observation({ id: 1, taxonId: 101, photos: [photo(11)] }),
    observation({ id: 2, taxonId: 102, photos: [photo(21), photo(22)] }),
  ], mothQuery);
  const metric = (photoId, hash, sharpness) => ({
    photoId,
    sharpness,
    exposure: .9,
    contrast: .8,
    subjectOccupancy: .8,
    obstruction: .1,
    perceptualHash: hash,
  });
  const scored = applyPhotoScores(grouped.species, [
    metric(11, "0".repeat(64), .95),
    metric(21, `${"0".repeat(63)}1`, .9),
    metric(22, "1".repeat(64), .8),
  ]);
  const selections = new Map(scored.map((group) => [group.speciesKey, group.selectedPhotoId]));
  assert.equal(selections.get("species:101"), 11);
  assert.equal(selections.get("species:102"), 22);
});

test("the preset creates exactly ten 5x4 slides and readable square SVGs", () => {
  const settings = normalizeSettings(PRESETS["national-moth-week-2026"], mothQuery);
  const grouped = groupObservations(
    Array.from({ length: 144 }, (_, index) => observation({
      id: index + 1,
      taxonId: 1_000 + index,
    })),
    mothQuery,
  );
  const selected = selectExportSpecies(
    grouped.species,
    grouped.species.map((group) => ({
      speciesKey: group.speciesKey,
      photoId: group.selectedPhotoId,
    })),
    settings,
  );
  const plan = createSlidePlan(selected, settings);
  assert.equal(plan.length, 10);
  assert.deepEqual(plan.map((slide) => slide.slideNumber), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.match(coverSlideSvg(settings, 144), /width="1080" height="1080"/);

  const gridSpecies = plan[1].species;
  const svg = gridSlideSvg(
    settings,
    gridSpecies,
    gridSpecies.map((group) => ({
      photoId: group.selectedPhoto.photoId,
      dataUrl: "data:image/jpeg;base64,AA==",
    })),
    2,
  );
  assert.match(svg, /font-size="(?:1[6-9]|2[0-3])"/);
  assert.match(svg, /preserveAspectRatio="xMidYMid slice"/);
  assert.match(svg, /height="48"\s+fill=/);
  assert.doesNotMatch(svg, /font-style="italic"/);
  assert.doesNotMatch(svg, /rank|leaderboard/i);
});

test("a labeled 5x4 set can use Instagram's 20-slide limit for 380 species", () => {
  const settings = normalizeSettings({
    ...PRESETS["national-moth-week-2026"],
    maximumSlides: 20,
  }, mothQuery);
  const grouped = groupObservations(
    Array.from({ length: 400 }, (_, index) => observation({
      id: index + 1,
      taxonId: 2_000 + index,
    })),
    mothQuery,
  );
  const selected = selectExportSpecies(
    grouped.species,
    grouped.species.map((group) => ({
      speciesKey: group.speciesKey,
      photoId: group.selectedPhotoId,
    })),
    settings,
  );
  const plan = createSlidePlan(selected, settings);
  assert.equal(selected.length, 380);
  assert.equal(plan.length, 20);
  assert.equal(plan.filter((slide) => slide.type === "grid").length, 19);
});

test("common-name labels wrap to two fitted lines without adding scientific names", () => {
  assert.deepEqual(
    wrapCommonName("American Plum Borer Moth", 150, 17),
    ["American Plum", "Borer Moth"],
  );
  const longLabel = wrapCommonName(
    "Extraordinarily Long Tentiform Blotchminer Moth",
    125,
    17,
  );
  assert.equal(longLabel.length, 2);
  assert.match(longLabel[1], /…$/);
});

test("photo rotation is normalized and carried into the square-fill SVG and manifest", async () => {
  const settings = normalizeSettings({
    ...PRESETS["national-moth-week-2026"],
    maximumSlides: 2,
  }, mothQuery);
  const grouped = groupObservations([
    observation({ id: 88, taxonId: 808, photos: [photo(880)] }),
  ], mothQuery);
  const selected = selectExportSpecies(grouped.species, [{
    speciesKey: "species:808",
    photoId: 880,
    rotation: 91,
  }], settings);
  assert.equal(selected[0].rotation, 90);
  const svg = gridSlideSvg(settings, selected, [{
    photoId: 880,
    dataUrl: "data:image/jpeg;base64,AA==",
  }], 2);
  assert.match(svg, /rotate\(90 /);

  const fixture = observation({ id: 88, taxonId: 808, photos: [photo(880)] });
  const result = await buildExport({
    request: new Request("https://survey.kingfisher-hollow.com/api/social-export/export"),
    env: { ASSETS: { fetch: async () => new Response(null, { status: 404 }) } },
  }, {
    query: mothQuery,
    settings: {
      ...PRESETS["national-moth-week-2026"],
      presetId: "national-moth-week-2026",
      maximumSlides: 2,
    },
    selections: [{ speciesKey: "species:808", photoId: 880, rotation: 90 }],
  }, {
    fetchImpl: async (url) => {
      if (new URL(url).hostname === "api.inaturalist.org") {
        return new Response(JSON.stringify({ total_results: 1, results: [fixture] }), {
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(new Uint8Array([0xff, 0xd8, 0xff, 0xd9]), {
        headers: { "content-type": "image/jpeg" },
      });
    },
    rasterize: async () => new Uint8Array(128).fill(3),
  });
  assert.equal(result.manifest.photos[0].rotation_degrees, 90);
});

test("ZIP output uses valid local, central, and end records", () => {
  const zip = createZip([
    { name: "moth-week-2026-01.png", data: new Uint8Array([1, 2, 3]) },
    { name: "attribution.txt", data: "credit" },
  ], new Date("2026-07-29T12:00:00Z"));
  const view = new DataView(zip.buffer, zip.byteOffset, zip.byteLength);
  assert.equal(view.getUint32(0, true), 0x04034b50);
  assert.equal(view.getUint32(zip.length - 22, true), 0x06054b50);
  assert.equal(view.getUint16(zip.length - 12, true), 2);
  assert.match(new TextDecoder().decode(zip), /moth-week-2026-01\.png/);
  assert.match(new TextDecoder().decode(zip), /attribution\.txt/);
});

test("browser export creates valid ZIP records and observer-owned attribution", async () => {
  const settings = normalizeSettings({
    ...PRESETS["national-moth-week-2026"],
    maximumSlides: 2,
  }, mothQuery);
  const grouped = groupObservations([
    observation({ id: 91, taxonId: 909, photos: [photo(910)] }),
  ], mothQuery);
  grouped.species[0].rotation = 90;
  const slides = [
    { type: "cover", slideNumber: 1 },
    { type: "grid", slideNumber: 2, species: grouped.species },
  ];
  const manifest = createBrowserManifest(
    mothQuery,
    settings,
    slides,
    "2026-07-29T12:00:00.000Z",
  );
  assert.equal(manifest.export.renderer, "browser-canvas");
  assert.equal(manifest.photos[0].photographer, "drewweber");
  assert.equal(manifest.photos[0].rotation_degrees, 90);

  const zipBlob = await createZipBlob([
    { name: "moth-week-2026-01.png", data: new Blob([new Uint8Array([1, 2, 3])]) },
    { name: "attribution.json", data: JSON.stringify(manifest) },
  ], new Date("2026-07-29T12:00:00Z"));
  const zip = new Uint8Array(await zipBlob.arrayBuffer());
  const view = new DataView(zip.buffer, zip.byteOffset, zip.byteLength);
  assert.equal(view.getUint32(0, true), 0x04034b50);
  assert.equal(view.getUint32(zip.length - 22, true), 0x06054b50);
  assert.match(new TextDecoder().decode(zip), /moth-week-2026-01\.png/);
  assert.match(new TextDecoder().decode(zip), /browser-canvas/);
});

test("complete export re-verifies the selected iNaturalist photo and names ten PNG files", async () => {
  const fixture = observation({ id: 77, taxonId: 707, photos: [photo(770)] });
  const fetchImpl = async (url) => {
    const parsed = new URL(url);
    if (parsed.hostname === "api.inaturalist.org") {
      return new Response(JSON.stringify({ total_results: 1, results: [fixture] }), {
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(new Uint8Array([0xff, 0xd8, 0xff, 0xd9]), {
      headers: { "content-type": "image/jpeg" },
    });
  };
  const context = {
    request: new Request("https://survey.kingfisher-hollow.com/api/social-export/export"),
    env: { ASSETS: { fetch: async () => new Response(null, { status: 404 }) } },
  };
  const result = await buildExport(context, {
    query: mothQuery,
    settings: { ...PRESETS["national-moth-week-2026"], presetId: "national-moth-week-2026" },
    selections: [{ speciesKey: "species:707", photoId: 770 }],
  }, {
    fetchImpl,
    rasterize: async () => new Uint8Array(128).fill(7),
  });
  assert.equal(result.filename, "moth-week-2026.zip");
  assert.equal(result.slideCount, 10);
  const zipText = new TextDecoder().decode(result.zip);
  for (let slide = 1; slide <= 10; slide += 1) {
    assert.match(zipText, new RegExp(`moth-week-2026-${String(slide).padStart(2, "0")}\\.png`));
  }
  assert.match(zipText, /attribution\.json/);
  assert.match(zipText, /attribution\.txt/);
  assert.equal(result.manifest.photos[0].photographer, "drewweber");
});
