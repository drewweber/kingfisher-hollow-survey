const encoder = new TextEncoder();

const THEMES = Object.freeze({
  "kingfisher-quiet": {
    background: "#e9ede8",
    ink: "#102820",
    muted: "#53665e",
    accent: "#5b8fa8",
    label: "rgba(8, 24, 19, .86)",
    labelInk: "#ffffff",
  },
  "midnight-sheet": {
    background: "#0d221c",
    ink: "#f4f5ef",
    muted: "#a7b8b0",
    accent: "#8ec8b1",
    label: "rgba(4, 15, 12, .88)",
    labelInk: "#ffffff",
  },
  "field-note": {
    background: "#e7e2d4",
    ink: "#263128",
    muted: "#6e756c",
    accent: "#a6563c",
    label: "rgba(28, 36, 29, .87)",
    labelInk: "#ffffff",
  },
});

function proxyPhotoUrl(url) {
  return `/api/social-export/photo?url=${encodeURIComponent(url)}`;
}

function selectedCandidate(group) {
  return group.candidates.find((candidate) => candidate.photoId === group.selectedPhotoId)
    || group.candidates[0];
}

function canvasBlob(canvas) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Safari could not encode one of the PNG slides."));
    }, "image/png");
  });
}

async function loadPhoto(candidate) {
  const image = new Image();
  image.decoding = "async";
  image.src = proxyPhotoUrl(candidate.renderUrl);
  try {
    if (typeof image.decode === "function") {
      await image.decode();
    } else {
      await new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = reject;
      });
    }
  } catch (_error) {
    throw new Error(
      `Photo ${candidate.photoId} could not be loaded for rendering. Retry the export.`,
    );
  }
  return image;
}

function drawCoverWing(context, theme, width, height) {
  const scale = width / 1080;
  context.save();
  context.translate(width * 0.72, height * 0.52);
  context.scale(scale, scale);
  context.globalAlpha = 0.26;
  context.strokeStyle = theme.accent;
  context.lineCap = "round";
  context.lineWidth = 5;
  context.beginPath();
  context.moveTo(0, -8);
  context.bezierCurveTo(125, -220, 270, -230, 304, -126);
  context.bezierCurveTo(326, -57, 253, 15, 71, 18);
  context.moveTo(0, 8);
  context.bezierCurveTo(128, 220, 272, 230, 304, 126);
  context.bezierCurveTo(326, 57, 253, -15, 71, -18);
  context.stroke();
  context.lineWidth = 3;
  context.beginPath();
  context.arc(232, -100, 23, 0, Math.PI * 2);
  context.arc(232, 100, 23, 0, Math.PI * 2);
  context.stroke();
  context.restore();
}

function drawSlideNumber(context, theme, width, height, slideNumber, x = width - 55) {
  context.fillStyle = theme.muted;
  context.font = "400 18px Inter, sans-serif";
  context.textAlign = "right";
  context.textBaseline = "alphabetic";
  context.fillText(String(slideNumber).padStart(2, "0"), x, height - 34);
}

function drawCover(context, settings, speciesCount, slideNumber) {
  const theme = THEMES[settings.theme] || THEMES["kingfisher-quiet"];
  const { width, height, cover } = settings;
  const portrait = height > width;
  const left = portrait ? 84 : 76;
  const top = portrait ? 300 : 180;
  const titleSize = portrait ? 94 : 82;
  const titleWords = cover.title.split(" ");

  context.fillStyle = theme.background;
  context.fillRect(0, 0, width, height);
  drawCoverWing(context, theme, width, height);
  context.strokeStyle = theme.accent;
  context.lineWidth = 8;
  context.beginPath();
  context.moveTo(left, top - 62);
  context.lineTo(left + 82, top - 62);
  context.stroke();

  context.textAlign = "left";
  context.textBaseline = "alphabetic";
  context.fillStyle = theme.ink;
  context.font = `700 ${titleSize}px Inter, sans-serif`;
  context.fillText(titleWords.slice(0, 2).join(" "), left, top);
  context.fillText(titleWords.slice(2).join(" "), left, top + titleSize * 1.02);

  context.font = `600 ${portrait ? 54 : 46}px "Playfair Display", serif`;
  context.fillText(cover.place, left, top + titleSize * 2.45);
  context.fillStyle = theme.muted;
  context.font = `400 ${portrait ? 31 : 27}px Inter, sans-serif`;
  context.fillText(cover.dates, left, top + titleSize * 3.08);

  const footerY = height - (portrait ? 280 : 150);
  context.fillStyle = theme.ink;
  context.font = `600 ${portrait ? 32 : 27}px Inter, sans-serif`;
  context.fillText(`${speciesCount.toLocaleString("en-US")} species featured`, left, footerY);
  context.fillStyle = theme.muted;
  context.font = `400 ${portrait ? 27 : 23}px Inter, sans-serif`;
  context.fillText(cover.credit, left, footerY + (portrait ? 54 : 46));
  drawSlideNumber(context, theme, width, height, slideNumber);
}

function fittedLine(context, text, maximumWidth) {
  if (context.measureText(text).width <= maximumWidth) return text;
  let fitted = "";
  for (const character of text) {
    if (context.measureText(`${fitted}${character}…`).width > maximumWidth) break;
    fitted += character;
  }
  return `${fitted.trimEnd()}…`;
}

function wrapCommonName(context, value, maximumWidth) {
  const text = String(value || "Unresolved taxon").replace(/\s+/g, " ").trim();
  if (context.measureText(text).width <= maximumWidth) return [text];
  const words = text.split(" ");
  let firstLine = "";
  let splitIndex = 0;
  while (splitIndex < words.length - 1) {
    const candidate = firstLine
      ? `${firstLine} ${words[splitIndex]}`
      : words[splitIndex];
    if (context.measureText(candidate).width > maximumWidth) break;
    firstLine = candidate;
    splitIndex += 1;
  }
  if (!firstLine) {
    firstLine = fittedLine(context, words[0], maximumWidth);
    splitIndex = 1;
  }
  const secondLine = fittedLine(context, words.slice(splitIndex).join(" "), maximumWidth);
  return secondLine ? [firstLine, secondLine] : [firstLine];
}

function drawCoverPhoto(context, image, x, y, size, rotation) {
  const angle = (Number(rotation) || 0) * Math.PI / 180;
  const scale = Math.max(size / image.naturalWidth, size / image.naturalHeight);
  const drawWidth = image.naturalWidth * scale;
  const drawHeight = image.naturalHeight * scale;
  context.save();
  context.beginPath();
  context.rect(x, y, size, size);
  context.clip();
  context.translate(x + size / 2, y + size / 2);
  context.rotate(angle);
  context.drawImage(image, -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight);
  context.restore();
}

function drawLabel(context, item, x, y, tileSize, labelHeight, theme) {
  const commonSize = tileSize < 175 ? 15 : tileSize < 245 ? 17 : 22;
  const lineHeight = Math.round(commonSize * 1.1);
  context.fillStyle = theme.label;
  context.fillRect(x, y, tileSize, labelHeight);
  context.fillStyle = theme.labelInk;
  context.font = `650 ${commonSize}px Inter, sans-serif`;
  context.textAlign = "left";
  context.textBaseline = "middle";
  const lines = wrapCommonName(
    context,
    item.commonName || item.scientificName,
    tileSize - 20,
  );
  const centerY = y + labelHeight / 2;
  const firstY = lines.length === 1 ? centerY : centerY - lineHeight / 2;
  lines.forEach((line, index) => {
    context.fillText(line, x + 10, firstY + index * lineHeight);
  });
}

async function drawGrid(context, settings, species, slideNumber, onProgress) {
  const theme = THEMES[settings.theme] || THEMES["kingfisher-quiet"];
  const { width, height, gridColumns, gridRows } = settings;
  const gap = gridColumns >= 5 ? 6 : 8;
  const outer = 36;
  const labelHeight = settings.includeSpeciesLabels
    ? (gridRows === 5 ? 44 : gridRows === 4 ? 48 : 56)
    : 0;
  const horizontalTileSize = Math.floor(
    (width - outer * 2 - gap * (gridColumns - 1)) / gridColumns,
  );
  const verticalTileSize = Math.floor(
    (height - outer * 2 - gap * (gridRows - 1) - labelHeight * gridRows) / gridRows,
  );
  const tileSize = Math.min(horizontalTileSize, verticalTileSize);
  const cellHeight = tileSize + labelHeight;
  const gridWidth = tileSize * gridColumns + gap * (gridColumns - 1);
  const gridHeight = cellHeight * gridRows + gap * (gridRows - 1);
  const gridX = Math.floor((width - gridWidth) / 2);
  const gridY = Math.floor((height - gridHeight) / 2);

  context.fillStyle = theme.background;
  context.fillRect(0, 0, width, height);
  const loaded = [];
  for (let index = 0; index < species.length; index += 1) {
    const item = species[index];
    onProgress?.(index + 1, species.length);
    loaded.push({
      item,
      image: await loadPhoto(selectedCandidate(item)),
    });
  }

  const capacity = gridColumns * gridRows;
  for (let index = 0; index < capacity; index += 1) {
    const row = Math.floor(index / gridColumns);
    const column = index % gridColumns;
    const x = gridX + column * (tileSize + gap);
    const y = gridY + row * (cellHeight + gap);
    const loadedItem = loaded[index];
    if (!loadedItem) {
      context.fillStyle = theme.ink;
      context.globalAlpha = 0.075;
      context.fillRect(x, y, tileSize, tileSize);
      context.globalAlpha = 1;
      continue;
    }
    drawCoverPhoto(
      context,
      loadedItem.image,
      x,
      y,
      tileSize,
      loadedItem.item.rotation,
    );
    if (settings.includeSpeciesLabels) {
      drawLabel(
        context,
        loadedItem.item,
        x,
        y + tileSize,
        tileSize,
        labelHeight,
        theme,
      );
    }
  }
  drawSlideNumber(context, theme, width, height, slideNumber, gridX + gridWidth);
  for (const loadedItem of loaded) loadedItem.image.src = "";
}

function createSlidePlan(species, settings) {
  const capacity = settings.gridColumns * settings.gridRows;
  const maximumGridSlides = Math.max(
    0,
    settings.maximumSlides - (settings.includeCover ? 1 : 0),
  );
  const requestedGridSlides = settings.presetId === "national-moth-week-2026"
    ? maximumGridSlides
    : Math.min(maximumGridSlides, Math.ceil(species.length / capacity));
  const plan = [];
  let slideNumber = 1;
  if (settings.includeCover) {
    plan.push({ type: "cover", slideNumber });
    slideNumber += 1;
  }
  for (let index = 0; index < requestedGridSlides; index += 1) {
    plan.push({
      type: "grid",
      slideNumber,
      species: species.slice(index * capacity, (index + 1) * capacity),
    });
    slideNumber += 1;
  }
  return plan;
}

function normalizedSettings(raw, query) {
  const outputFormat = raw.outputFormat === "instagram-story"
    ? "instagram-story"
    : "instagram-square";
  const preset = raw.presetId === "national-moth-week-2026";
  return {
    ...raw,
    width: 1080,
    height: outputFormat === "instagram-story" ? 1920 : 1080,
    fileStem: preset
      ? "moth-week-2026"
      : `${query.taxonGroup}-${query.dateFrom}-${query.dateTo}`,
    cover: preset
      ? {
        title: "NATIONAL MOTH WEEK",
        place: "Kingfisher Hollow",
        dates: "July 18–26, 2026",
        credit: "Photos by Drew Weber",
      }
      : {
        title: `${query.taxonGroup.toUpperCase()} AT KINGFISHER HOLLOW`,
        place: "Kingfisher Hollow",
        dates: `${query.dateFrom}–${query.dateTo}`,
        credit: `Photos by ${query.observer}`,
      },
  };
}

export function createManifest(query, settings, slides, generatedAt = new Date().toISOString()) {
  const photos = [];
  for (const slide of slides) {
    if (slide.type !== "grid") continue;
    slide.species.forEach((item, tileIndex) => {
      const selected = selectedCandidate(item);
      photos.push({
        filename: `${settings.fileStem}-${String(slide.slideNumber).padStart(2, "0")}.png`,
        slide: slide.slideNumber,
        tile: tileIndex + 1,
        species_key: item.speciesKey,
        common_name: item.commonName,
        scientific_name: item.scientificName,
        taxon_rank: item.rank,
        taxon_id: item.taxonId,
        observation_id: selected.observationId,
        observation_url: selected.observationUrl,
        photo_id: selected.photoId,
        photo_url: selected.originalUrl,
        rotation_degrees: Number(item.rotation) || 0,
        photographer: query.observer,
        attribution: selected.attribution,
        license_code: selected.licenseCode,
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
      renderer: "browser-canvas",
      output_format: settings.outputFormat,
      width: settings.width,
      height: settings.height,
      grid_size: settings.gridSize,
      slide_count: slides.length,
      include_cover: settings.includeCover,
      include_species_labels: settings.includeSpeciesLabels,
      theme: settings.theme,
    },
    species_featured: photos.length,
    photos,
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
      item.observation_url,
      "",
    );
  }
  return lines.join("\n");
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

export async function createZipBlob(files, now = new Date()) {
  const localParts = [];
  const centralParts = [];
  const timestamp = dosDateTime(now);
  let offset = 0;

  for (const file of files) {
    const name = encoder.encode(file.name);
    const dataBlob = file.data instanceof Blob
      ? file.data
      : new Blob([typeof file.data === "string" ? encoder.encode(file.data) : file.data]);
    const bytes = new Uint8Array(await dataBlob.arrayBuffer());
    const checksum = crc32(bytes);
    const localHeader = concatBytes([
      littleEndian32(0x04034b50),
      littleEndian16(20),
      littleEndian16(0x0800),
      littleEndian16(0),
      littleEndian16(timestamp.time),
      littleEndian16(timestamp.date),
      littleEndian32(checksum),
      littleEndian32(dataBlob.size),
      littleEndian32(dataBlob.size),
      littleEndian16(name.length),
      littleEndian16(0),
      name,
    ]);
    localParts.push(localHeader, dataBlob);
    centralParts.push(concatBytes([
      littleEndian32(0x02014b50),
      littleEndian16(20),
      littleEndian16(20),
      littleEndian16(0x0800),
      littleEndian16(0),
      littleEndian16(timestamp.time),
      littleEndian16(timestamp.date),
      littleEndian32(checksum),
      littleEndian32(dataBlob.size),
      littleEndian32(dataBlob.size),
      littleEndian16(name.length),
      littleEndian16(0),
      littleEndian16(0),
      littleEndian16(0),
      littleEndian16(0),
      littleEndian32(0),
      littleEndian32(offset),
      name,
    ]));
    offset += localHeader.length + dataBlob.size;
    bytes.fill(0);
    await new Promise((resolve) => setTimeout(resolve, 0));
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
  return new Blob([...localParts, central, end], { type: "application/zip" });
}

export async function renderCarouselZip(query, rawSettings, species, onProgress) {
  const settings = normalizedSettings(rawSettings, query);
  await Promise.all([
    document.fonts.load("700 82px Inter"),
    document.fonts.load('600 46px "Playfair Display"'),
  ]);
  await document.fonts.ready;

  const slides = createSlidePlan(species, settings);
  const files = [];
  const canvas = document.createElement("canvas");
  canvas.width = settings.width;
  canvas.height = settings.height;
  const context = canvas.getContext("2d", { alpha: false });
  if (!context) throw new Error("This browser cannot create the export canvas.");

  for (let index = 0; index < slides.length; index += 1) {
    const slide = slides[index];
    onProgress?.({
      phase: "render",
      slide: index + 1,
      slideCount: slides.length,
      photo: 0,
      photoCount: slide.species?.length || 0,
    });
    context.clearRect(0, 0, settings.width, settings.height);
    if (slide.type === "cover") {
      drawCover(context, settings, species.length, slide.slideNumber);
    } else {
      await drawGrid(context, settings, slide.species, slide.slideNumber, (photo, photoCount) => {
        onProgress?.({
          phase: "render",
          slide: index + 1,
          slideCount: slides.length,
          photo,
          photoCount,
        });
      });
    }
    files.push({
      name: `${settings.fileStem}-${String(slide.slideNumber).padStart(2, "0")}.png`,
      data: await canvasBlob(canvas),
    });
    await new Promise((resolve) => requestAnimationFrame(() => resolve()));
  }

  const manifest = createManifest(query, settings, slides);
  files.push({
    name: "attribution.json",
    data: `${JSON.stringify(manifest, null, 2)}\n`,
  });
  files.push({
    name: "attribution.txt",
    data: attributionText(manifest),
  });
  onProgress?.({ phase: "package", slideCount: slides.length });
  const zip = await createZipBlob(files);
  canvas.width = 1;
  canvas.height = 1;
  return {
    zip,
    filename: `${settings.fileStem}.zip`,
    slideCount: slides.length,
    manifest,
  };
}
