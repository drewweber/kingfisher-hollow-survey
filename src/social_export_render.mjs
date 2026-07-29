import {
  PRESETS,
  SocialExportError,
  errorResponse,
  fetchMatchingObservations,
  groupObservations,
  normalizeQuery,
  normalizeSettings,
  selectExportSpecies,
  validateInatPhotoUrl,
} from "./social_export_runtime.mjs";

const encoder = new TextEncoder();

const THEMES = Object.freeze({
  "kingfisher-quiet": {
    background: "#e9ede8",
    ink: "#102820",
    muted: "#53665e",
    accent: "#5b8fa8",
    leaf: "#8ec8b1",
    tileGap: "#102820",
    label: "rgba(8, 24, 19, .86)",
    labelInk: "#ffffff",
  },
  "midnight-sheet": {
    background: "#0d221c",
    ink: "#f4f5ef",
    muted: "#a7b8b0",
    accent: "#8ec8b1",
    leaf: "#5b8fa8",
    tileGap: "#071510",
    label: "rgba(4, 15, 12, .88)",
    labelInk: "#ffffff",
  },
  "field-note": {
    background: "#e7e2d4",
    ink: "#263128",
    muted: "#6e756c",
    accent: "#a6563c",
    leaf: "#66785e",
    tileGap: "#263128",
    label: "rgba(28, 36, 29, .87)",
    labelInk: "#ffffff",
  },
});

function xml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function estimatedTextWidth(value, fontSize) {
  let units = 0;
  for (const character of String(value)) {
    if (/\s/.test(character)) units += 0.31;
    else if (/[ilI1'.,:;]/.test(character)) units += 0.29;
    else if (/[MW@%&]/.test(character)) units += 0.88;
    else if (/[A-Z]/.test(character)) units += 0.64;
    else units += 0.53;
  }
  return units * fontSize;
}

function truncateToWidth(value, maximumWidth, fontSize) {
  const text = String(value ?? "").trim();
  if (estimatedTextWidth(text, fontSize) <= maximumWidth) return text;
  const ellipsisWidth = estimatedTextWidth("…", fontSize);
  let fitted = "";
  for (const character of text) {
    if (estimatedTextWidth(`${fitted}${character}`, fontSize) + ellipsisWidth > maximumWidth) {
      break;
    }
    fitted += character;
  }
  return `${fitted.trimEnd()}…`;
}

export function wrapCommonName(value, maximumWidth, fontSize) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (!text) return ["Unresolved taxon"];
  if (estimatedTextWidth(text, fontSize) <= maximumWidth) return [text];

  const words = text.split(" ");
  let firstLine = "";
  let splitIndex = 0;
  while (splitIndex < words.length - 1) {
    const candidate = firstLine
      ? `${firstLine} ${words[splitIndex]}`
      : words[splitIndex];
    if (estimatedTextWidth(candidate, fontSize) > maximumWidth) break;
    firstLine = candidate;
    splitIndex += 1;
  }
  if (!firstLine) {
    firstLine = truncateToWidth(words[0], maximumWidth, fontSize);
    splitIndex = 1;
  }
  const secondLine = truncateToWidth(
    words.slice(splitIndex).join(" "),
    maximumWidth,
    fontSize,
  );
  return secondLine ? [firstLine, secondLine] : [firstLine];
}

function bytesToBase64(bytes) {
  let binary = "";
  const block = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += block) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + block));
  }
  return btoa(binary);
}

function imageDataUrl(bytes, contentType) {
  const mime = /^image\/(jpeg|png|webp)$/i.test(contentType || "")
    ? contentType.split(";")[0]
    : "image/jpeg";
  return `data:${mime};base64,${bytesToBase64(bytes)}`;
}

function coverWing(theme, width, height) {
  const centerX = width * 0.72;
  const centerY = height * 0.52;
  const scale = width / 1080;
  return `
    <g transform="translate(${centerX} ${centerY}) scale(${scale})" fill="none"
      stroke="${theme.accent}" stroke-linecap="round" opacity=".26">
      <path d="M0 -8 C 125 -220, 270 -230, 304 -126 C 326 -57, 253 15, 71 18"
        stroke-width="5"/>
      <path d="M0 8 C 128 220, 272 230, 304 126 C 326 57, 253 -15, 71 -18"
        stroke-width="5"/>
      <path d="M14 -2 C 108 -145, 211 -162, 274 -113 M14 2 C 108 145, 211 162, 274 113"
        stroke-width="2"/>
      <path d="M56 -36 C 133 -61, 199 -59, 254 -20 M56 36 C 133 61, 199 59, 254 20"
        stroke-width="2"/>
      <circle cx="232" cy="-100" r="23" stroke-width="3"/>
      <circle cx="232" cy="100" r="23" stroke-width="3"/>
      <path d="M0 -20 L0 20 M-13 -5 L0 -24 L13 -5 M-12 7 L0 25 L12 7" stroke-width="5"/>
    </g>`;
}

export function coverSlideSvg(settings, speciesCount, slideNumber = 1) {
  const theme = THEMES[settings.theme] || THEMES["kingfisher-quiet"];
  const { width, height, cover } = settings;
  const portrait = height > width;
  const left = portrait ? 84 : 76;
  const top = portrait ? 300 : 180;
  const titleSize = portrait ? 94 : 82;
  const displayCount = `${speciesCount.toLocaleString("en-US")} species featured`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"
    viewBox="0 0 ${width} ${height}">
    <rect width="${width}" height="${height}" fill="${theme.background}"/>
    ${coverWing(theme, width, height)}
    <line x1="${left}" y1="${top - 62}" x2="${left + 82}" y2="${top - 62}"
      stroke="${theme.accent}" stroke-width="8"/>
    <text x="${left}" y="${top}" fill="${theme.ink}" font-family="Inter, sans-serif"
      font-size="${titleSize}" font-weight="700">
      <tspan x="${left}" dy="0">${xml(cover.title.split(" ").slice(0, 2).join(" "))}</tspan>
      <tspan x="${left}" dy="${titleSize * 1.02}">${xml(cover.title.split(" ").slice(2).join(" "))}</tspan>
    </text>
    <text x="${left}" y="${top + titleSize * 2.45}" fill="${theme.ink}"
      font-family="Playfair Display, serif" font-size="${portrait ? 54 : 46}"
      font-weight="600">${xml(cover.place)}</text>
    <text x="${left}" y="${top + titleSize * 3.08}" fill="${theme.muted}"
      font-family="Inter, sans-serif" font-size="${portrait ? 31 : 27}">
      ${xml(cover.dates)}
    </text>
    <g transform="translate(${left} ${height - (portrait ? 280 : 150)})">
      <text fill="${theme.ink}" font-family="Inter, sans-serif" font-size="${portrait ? 32 : 27}"
        font-weight="600">${xml(displayCount)}</text>
      <text y="${portrait ? 54 : 46}" fill="${theme.muted}" font-family="Inter, sans-serif"
        font-size="${portrait ? 27 : 23}">${xml(cover.credit)}</text>
    </g>
    <text x="${width - 55}" y="${height - 45}" text-anchor="end" fill="${theme.muted}"
      font-family="Inter, sans-serif" font-size="18">${String(slideNumber).padStart(2, "0")}</text>
  </svg>`;
}

function tileLabel(species, x, y, tileSize, labelHeight, theme) {
  const commonSize = tileSize < 175 ? 15 : tileSize < 245 ? 17 : 22;
  const lineHeight = Math.round(commonSize * 1.1);
  const lines = wrapCommonName(
    species.commonName || species.scientificName,
    tileSize - 20,
    commonSize,
  );
  const centerY = y + labelHeight / 2;
  const firstY = lines.length === 1 ? centerY : centerY - lineHeight / 2;
  return `
    <rect x="${x}" y="${y}" width="${tileSize}" height="${labelHeight}"
      fill="${theme.label}"/>
    <text x="${x + 10}" y="${firstY}" dominant-baseline="middle"
      fill="${theme.labelInk}" font-family="Inter, sans-serif" font-size="${commonSize}"
      font-weight="650">${lines.map((line, index) => (
        `<tspan x="${x + 10}" y="${firstY + index * lineHeight}">${xml(line)}</tspan>`
      )).join("")}</text>`;
}

export function gridSlideSvg(settings, species, photoData, slideNumber) {
  const theme = THEMES[settings.theme] || THEMES["kingfisher-quiet"];
  const {
    width,
    height,
    gridColumns = 4,
    gridRows = 4,
  } = settings;
  const gap = gridColumns >= 5 ? 6 : 8;
  const portrait = height > width;
  const outer = 36;
  const labelHeight = settings.includeSpeciesLabels
    ? (gridRows === 5 ? 44 : gridRows === 4 ? 48 : 56)
    : 0;
  const horizontalTileSize = Math.floor(
    (width - outer * 2 - gap * (gridColumns - 1)) / gridColumns,
  );
  const verticalTileSize = Math.floor(
    (
      height
      - outer * 2
      - gap * (gridRows - 1)
      - labelHeight * gridRows
    ) / gridRows,
  );
  const tileSize = Math.min(horizontalTileSize, verticalTileSize);
  const cellHeight = tileSize + labelHeight;
  const gridWidth = tileSize * gridColumns + gap * (gridColumns - 1);
  const gridHeight = cellHeight * gridRows + gap * (gridRows - 1);
  const gridX = Math.floor((width - gridWidth) / 2);
  const gridY = Math.floor((height - gridHeight) / 2);
  const clips = [];
  const tiles = [];
  const photoById = new Map(photoData.map((photo) => [photo.photoId, photo]));
  const capacity = gridColumns * gridRows;

  for (let index = 0; index < capacity; index += 1) {
    const row = Math.floor(index / gridColumns);
    const column = index % gridColumns;
    const x = gridX + column * (tileSize + gap);
    const y = gridY + row * (cellHeight + gap);
    const item = species[index];
    if (!item) {
      tiles.push(`<rect x="${x}" y="${y}" width="${tileSize}" height="${tileSize}"
        fill="${theme.ink}" opacity=".075"/>
        ${settings.includeSpeciesLabels
          ? `<rect x="${x}" y="${y + tileSize}" width="${tileSize}" height="${labelHeight}"
              fill="${theme.label}" opacity=".22"/>`
          : ""}`);
      continue;
    }
    const photo = photoById.get(item.selectedPhoto.photoId);
    const centerX = x + tileSize / 2;
    const centerY = y + tileSize / 2;
    const rotation = Number(item.rotation) || 0;
    const clipId = `tile-${slideNumber}-${index}`;
    clips.push(`<clipPath id="${clipId}"><rect x="${x}" y="${y}"
      width="${tileSize}" height="${tileSize}"/></clipPath>`);
    tiles.push(`
      <image href="${photo.dataUrl}" x="${x}" y="${y}"
        width="${tileSize}" height="${tileSize}"
        preserveAspectRatio="xMidYMid slice"
        transform="rotate(${rotation} ${centerX} ${centerY})"
        clip-path="url(#${clipId})"/>
      ${settings.includeSpeciesLabels
        ? tileLabel(item, x, y + tileSize, tileSize, labelHeight, theme)
        : ""}`);
  }

  const storyHeading = portrait
    ? `<text x="${gridX}" y="${gridY - 55}" fill="${theme.ink}" font-family="Inter, sans-serif"
        font-size="25" font-weight="650">${xml(settings.cover.title)}</text>`
    : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"
    viewBox="0 0 ${width} ${height}">
    <defs>${clips.join("")}</defs>
    <rect width="${width}" height="${height}" fill="${theme.background}"/>
    ${storyHeading}
    ${tiles.join("")}
    <text x="${gridX + gridWidth}" y="${height - 14}" text-anchor="end" fill="${theme.muted}"
      font-family="Inter, sans-serif" font-size="18">${String(slideNumber).padStart(2, "0")}</text>
  </svg>`;
}

export function createSlidePlan(species, settings) {
  const capacity = settings.gridColumns * settings.gridRows;
  const maximumGridSlides = Math.max(
    0,
    settings.maximumSlides - (settings.includeCover ? 1 : 0),
  );
  const neededGridSlides = Math.ceil(species.length / capacity);
  const gridSlideCount = settings.fillToMaximumSlides
    ? maximumGridSlides
    : Math.min(maximumGridSlides, neededGridSlides);
  const plan = [];
  let slideNumber = 1;
  if (settings.includeCover) {
    plan.push({ type: "cover", slideNumber });
    slideNumber += 1;
  }
  for (let index = 0; index < gridSlideCount; index += 1) {
    plan.push({
      type: "grid",
      slideNumber,
      species: species.slice(index * capacity, (index + 1) * capacity),
    });
    slideNumber += 1;
  }
  return plan;
}

async function fetchPhotoData(items, fetchImpl) {
  return Promise.all(items.map(async (item) => {
    const url = validateInatPhotoUrl(item.selectedPhoto.renderUrl);
    const response = await fetchImpl(url, {
      headers: { Accept: "image/jpeg,image/png,image/webp" },
      cf: { cacheEverything: true, cacheTtl: 604_800 },
    });
    if (!response.ok) {
      throw new SocialExportError(
        "photo_download_failed",
        `iNaturalist photo ${item.selectedPhoto.photoId} could not be downloaded. Retry the export.`,
        502,
        true,
      );
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length > 8_000_000) {
      throw new SocialExportError(
        "photo_too_large",
        "One selected photo is too large to render safely. Choose another photo.",
      );
    }
    return {
      photoId: item.selectedPhoto.photoId,
      dataUrl: imageDataUrl(bytes, response.headers.get("content-type")),
    };
  }));
}

async function loadFontBuffers(context) {
  if (!context.env?.ASSETS?.fetch) return [];
  const paths = [
    "/assets/fonts/inter-latin-wght-normal.woff2",
    "/assets/fonts/playfair-display-latin-wght-normal.woff2",
    "/assets/fonts/playfair-display-latin-wght-italic.woff2",
  ];
  const buffers = [];
  for (const path of paths) {
    const response = await context.env.ASSETS.fetch(new URL(path, context.request.url));
    if (response.ok) buffers.push(new Uint8Array(await response.arrayBuffer()));
  }
  return buffers;
}

async function rasterizeSvg(svg, fontBuffers) {
  const { Resvg } = await import("@cf-wasm/resvg/workers");
  const renderer = await Resvg.create(svg, {
    background: "rgba(0,0,0,0)",
    fitTo: { mode: "original" },
    imageRendering: 0,
    textRendering: 1,
    font: {
      fontBuffers,
      loadSystemFonts: false,
      defaultFontFamily: "Inter",
      sansSerifFamily: "Inter",
      serifFamily: "Playfair Display",
    },
  });
  let rendered;
  try {
    rendered = renderer.render();
    return rendered.asPng();
  } finally {
    rendered?.free();
    renderer.free();
  }
}

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function littleEndian16(value) {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff]);
}

function littleEndian32(value) {
  return new Uint8Array([
    value & 0xff,
    (value >>> 8) & 0xff,
    (value >>> 16) & 0xff,
    (value >>> 24) & 0xff,
  ]);
}

function concatBytes(parts) {
  const size = parts.reduce((total, part) => total + part.length, 0);
  const combined = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    combined.set(part, offset);
    offset += part.length;
  }
  return combined;
}

function dosDateTime(date = new Date()) {
  const year = Math.max(1980, date.getUTCFullYear());
  return {
    date: ((year - 1980) << 9) | ((date.getUTCMonth() + 1) << 5) | date.getUTCDate(),
    time: (date.getUTCHours() << 11) | (date.getUTCMinutes() << 5)
      | Math.floor(date.getUTCSeconds() / 2),
  };
}

export function createZip(files, now = new Date()) {
  const localParts = [];
  const centralParts = [];
  const timestamp = dosDateTime(now);
  let offset = 0;

  for (const file of files) {
    const name = encoder.encode(file.name);
    const data = file.data instanceof Uint8Array ? file.data : encoder.encode(String(file.data));
    const checksum = crc32(data);
    const localHeader = concatBytes([
      littleEndian32(0x04034b50),
      littleEndian16(20),
      littleEndian16(0x0800),
      littleEndian16(0),
      littleEndian16(timestamp.time),
      littleEndian16(timestamp.date),
      littleEndian32(checksum),
      littleEndian32(data.length),
      littleEndian32(data.length),
      littleEndian16(name.length),
      littleEndian16(0),
      name,
    ]);
    localParts.push(localHeader, data);
    const centralHeader = concatBytes([
      littleEndian32(0x02014b50),
      littleEndian16(20),
      littleEndian16(20),
      littleEndian16(0x0800),
      littleEndian16(0),
      littleEndian16(timestamp.time),
      littleEndian16(timestamp.date),
      littleEndian32(checksum),
      littleEndian32(data.length),
      littleEndian32(data.length),
      littleEndian16(name.length),
      littleEndian16(0),
      littleEndian16(0),
      littleEndian16(0),
      littleEndian16(0),
      littleEndian32(0),
      littleEndian32(offset),
      name,
    ]);
    centralParts.push(centralHeader);
    offset += localHeader.length + data.length;
  }

  const central = concatBytes(centralParts);
  const end = concatBytes([
    littleEndian32(0x06054b50),
    littleEndian16(0),
    littleEndian16(0),
    littleEndian16(files.length),
    littleEndian16(files.length),
    littleEndian32(central.length),
    littleEndian32(offset),
    littleEndian16(0),
  ]);
  return concatBytes([...localParts, central, end]);
}

function manifestFor(query, settings, species, slides, generatedAt) {
  const placements = [];
  for (const slide of slides) {
    if (slide.type !== "grid") continue;
    slide.species.forEach((item, tileIndex) => {
      placements.push({
        filename: `${settings.fileStem}-${String(slide.slideNumber).padStart(2, "0")}.png`,
        slide: slide.slideNumber,
        tile: tileIndex + 1,
        species_key: item.speciesKey,
        common_name: item.commonName,
        scientific_name: item.scientificName,
        taxon_rank: item.rank,
        taxon_id: item.taxonId,
        observation_id: item.selectedPhoto.observationId,
        observation_url: item.selectedPhoto.observationUrl,
        photo_id: item.selectedPhoto.photoId,
        photo_url: item.selectedPhoto.originalUrl,
        rotation_degrees: item.rotation,
        photographer: query.observer,
        attribution: item.selectedPhoto.attribution,
        license_code: item.selectedPhoto.licenseCode,
      });
    });
  }
  return {
    schema_version: 1,
    generated_at: generatedAt,
    source: "iNaturalist API",
    query: {
      observer: query.observer,
      date_from: query.dateFrom,
      date_to: query.dateTo,
      taxon_group: query.taxonGroup,
      include_unresolved_taxa: query.includeUnresolvedTaxa,
      photo_required: true,
    },
    export: {
      output_format: settings.outputFormat,
      width: settings.width,
      height: settings.height,
      grid_size: settings.gridLayout,
      slide_count: slides.length,
      include_cover: settings.includeCover,
      include_species_labels: settings.includeSpeciesLabels,
      theme: settings.theme,
    },
    species_featured: species.length,
    photos: placements,
  };
}

function attributionText(manifest) {
  const lines = [
    "Kingfisher Hollow social-media export",
    `Generated: ${manifest.generated_at}`,
    `Observer / photographer: ${manifest.query.observer}`,
    `Dates: ${manifest.query.date_from} through ${manifest.query.date_to}`,
    "Source: iNaturalist",
    "",
  ];
  for (const item of manifest.photos) {
    lines.push(
      `${item.filename} · tile ${item.tile}`,
      `${item.common_name || item.scientific_name} · ${item.scientific_name}`,
      `${item.attribution}${item.license_code ? ` · ${item.license_code}` : ""}`,
      `${item.observation_url}`,
      "",
    );
  }
  return lines.join("\n");
}

export async function buildExport(
  context,
  body,
  {
    fetchImpl = fetch,
    rasterize = rasterizeSvg,
  } = {},
) {
  const preset = PRESETS[String(body?.settings?.presetId || "")] || null;
  const query = normalizeQuery({ ...(preset || {}), ...body?.query });
  const settings = normalizeSettings({ ...(preset || {}), ...body?.settings }, query);
  const observations = await fetchMatchingObservations(query, {
    fetchImpl,
    executionContext: context,
  });
  const grouped = groupObservations(observations, query);
  const species = selectExportSpecies(
    grouped.species,
    body?.selections,
    settings,
  );
  if (species.length === 0) {
    throw new SocialExportError(
      "no_selected_species",
      "Choose at least one species photo before exporting.",
    );
  }

  const slides = createSlidePlan(species, settings);
  if (slides.length === 0) {
    throw new SocialExportError(
      "no_slides",
      "Increase the maximum slide count or include a cover slide.",
    );
  }
  const fontBuffers = await loadFontBuffers(context);
  const files = [];

  for (const slide of slides) {
    let svg;
    if (slide.type === "cover") {
      svg = coverSlideSvg(settings, species.length, slide.slideNumber);
    } else {
      const photoData = await fetchPhotoData(slide.species, fetchImpl);
      svg = gridSlideSvg(settings, slide.species, photoData, slide.slideNumber);
    }
    const png = await rasterize(svg, fontBuffers);
    if (!(png instanceof Uint8Array) || png.length < 100) {
      throw new SocialExportError(
        "render_failed",
        "A slide could not be rendered. Retry the export.",
        500,
        true,
      );
    }
    files.push({
      name: `${settings.fileStem}-${String(slide.slideNumber).padStart(2, "0")}.png`,
      data: png,
    });
  }

  const generatedAt = new Date().toISOString();
  const manifest = manifestFor(query, settings, species, slides, generatedAt);
  files.push({
    name: "attribution.json",
    data: `${JSON.stringify(manifest, null, 2)}\n`,
  });
  files.push({
    name: "attribution.txt",
    data: attributionText(manifest),
  });

  return {
    zip: createZip(files),
    filename: `${settings.fileStem}.zip`,
    slideCount: slides.length,
    manifest,
  };
}

export async function handleExport(context) {
  if (context.request.method !== "POST") {
    return errorResponse(new SocialExportError(
      "method_not_allowed",
      "Use POST to export the carousel.",
      405,
    ));
  }
  try {
    const result = await buildExport(context, await context.request.json());
    return new Response(result.zip, {
      status: 200,
      headers: {
        "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename="${result.filename}"`,
        "Content-Length": String(result.zip.length),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-Slide-Count": String(result.slideCount),
      },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
