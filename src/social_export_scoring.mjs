import {
  SocialExportError,
  errorResponse,
  jsonResponse,
  validateInatPhotoUrl,
} from "./social_export_runtime.mjs";

const MAX_PHOTOS_PER_BATCH = 24;

function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

function luminance(red, green, blue) {
  return (red * 0.2126 + green * 0.7152 + blue * 0.0722) / 255;
}

function pixelLuminance(pixels, width, x, y) {
  const offset = (y * width + x) * 4;
  return luminance(pixels[offset], pixels[offset + 1], pixels[offset + 2]);
}

function perceptualHash(luma, width, height) {
  const cells = [];
  for (let cellY = 0; cellY < 8; cellY += 1) {
    for (let cellX = 0; cellX < 8; cellX += 1) {
      const x0 = Math.floor(cellX * width / 8);
      const x1 = Math.max(x0 + 1, Math.floor((cellX + 1) * width / 8));
      const y0 = Math.floor(cellY * height / 8);
      const y1 = Math.max(y0 + 1, Math.floor((cellY + 1) * height / 8));
      let total = 0;
      let count = 0;
      for (let y = y0; y < y1; y += 1) {
        for (let x = x0; x < x1; x += 1) {
          total += luma[y * width + x];
          count += 1;
        }
      }
      cells.push(total / Math.max(1, count));
    }
  }
  const average = cells.reduce((total, value) => total + value, 0) / cells.length;
  return cells.map((value) => value >= average ? "1" : "0").join("");
}

export function analyzePixels(pixels, width, height) {
  if (!(pixels instanceof Uint8Array) || width < 8 || height < 8
      || pixels.length < width * height * 4) {
    throw new Error("Invalid image pixels");
  }

  const count = width * height;
  const luma = new Float32Array(count);
  let total = 0;
  let clipped = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const value = pixelLuminance(pixels, width, x, y);
      luma[y * width + x] = value;
      total += value;
      if (value < 0.025 || value > 0.975) clipped += 1;
    }
  }
  const mean = total / count;
  let variance = 0;
  for (const value of luma) variance += (value - mean) ** 2;
  const standardDeviation = Math.sqrt(variance / count);

  let gradientTotal = 0;
  let gradientCount = 0;
  let centerGradient = 0;
  let centerCount = 0;
  let borderGradient = 0;
  let borderCount = 0;
  const borderX = Math.max(2, Math.floor(width * 0.1));
  const borderY = Math.max(2, Math.floor(height * 0.1));
  const centerX0 = Math.floor(width * 0.2);
  const centerX1 = Math.ceil(width * 0.8);
  const centerY0 = Math.floor(height * 0.2);
  const centerY1 = Math.ceil(height * 0.8);

  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const index = y * width + x;
      const gx = luma[index + 1] - luma[index - 1];
      const gy = luma[index + width] - luma[index - width];
      const gradient = Math.sqrt(gx * gx + gy * gy);
      gradientTotal += gradient;
      gradientCount += 1;
      if (x >= centerX0 && x < centerX1 && y >= centerY0 && y < centerY1) {
        centerGradient += gradient;
        centerCount += 1;
      }
      if (x < borderX || x >= width - borderX || y < borderY || y >= height - borderY) {
        borderGradient += gradient;
        borderCount += 1;
      }
    }
  }

  const averageGradient = gradientTotal / Math.max(1, gradientCount);
  const centerDensity = centerGradient / Math.max(1, centerCount);
  const borderDensity = borderGradient / Math.max(1, borderCount);
  const clippedRatio = clipped / count;
  const exposure = clamp01(
    1 - Math.abs(mean - 0.52) / 0.52 - clippedRatio * 1.7,
  );
  const contrast = clamp01(standardDeviation / 0.24);
  const sharpness = clamp01((averageGradient - 0.015) / 0.14);
  const subjectOccupancy = clamp01(
    0.35 + (centerDensity / Math.max(0.006, averageGradient) - 0.82) * 0.7,
  );
  const obstruction = clamp01(
    (borderDensity / Math.max(0.008, centerDensity) - 0.72) * 0.7
      + clippedRatio * 0.7,
  );

  return {
    sharpness: Math.round(sharpness * 1_000) / 1_000,
    exposure: Math.round(exposure * 1_000) / 1_000,
    contrast: Math.round(contrast * 1_000) / 1_000,
    subjectOccupancy: Math.round(subjectOccupancy * 1_000) / 1_000,
    obstruction: Math.round(obstruction * 1_000) / 1_000,
    perceptualHash: perceptualHash(luma, width, height),
  };
}

async function analyzePhoto(photo, fetchImpl) {
  const url = validateInatPhotoUrl(photo.url);
  const response = await fetchImpl(url, {
    headers: { Accept: "image/jpeg,image/png,image/webp" },
    cf: {
      cacheEverything: true,
      cacheTtl: 86_400,
    },
  });
  if (!response.ok) {
    throw new Error(`Photo returned HTTP ${response.status}`);
  }
  if (Number(response.headers.get("content-length") || 0) > 5_000_000) {
    throw new Error("Photo is too large to inspect safely");
  }

  const { PhotonImage } = await import("@cf-wasm/photon/workerd");
  const image = PhotonImage.new_from_byteslice(new Uint8Array(await response.arrayBuffer()));
  try {
    const width = image.get_width();
    const height = image.get_height();
    if (width * height > 1_500_000) {
      throw new Error("Photo dimensions are too large to inspect safely");
    }
    return {
      photoId: Number(photo.photoId),
      width,
      height,
      ...analyzePixels(image.get_raw_pixels(), width, height),
    };
  } finally {
    image.free();
  }
}

async function mapConcurrent(items, concurrency, mapper) {
  const results = new Array(items.length);
  let index = 0;
  async function worker() {
    while (index < items.length) {
      const current = index;
      index += 1;
      results[current] = await mapper(items[current], current);
    }
  }
  await Promise.all(
    Array.from({ length: Math.min(concurrency, items.length) }, () => worker()),
  );
  return results;
}

export async function scorePhotoBatch(
  photos,
  { fetchImpl = fetch, analyzeImpl = analyzePhoto } = {},
) {
  if (!Array.isArray(photos) || photos.length === 0 || photos.length > MAX_PHOTOS_PER_BATCH) {
    throw new SocialExportError(
      "invalid_photo_batch",
      `Send between 1 and ${MAX_PHOTOS_PER_BATCH} photos per scoring request.`,
    );
  }
  const normalized = photos.map((photo) => ({
    photoId: Number(photo?.photoId),
    url: validateInatPhotoUrl(photo?.url),
  }));
  if (normalized.some((photo) => !Number.isSafeInteger(photo.photoId) || photo.photoId <= 0)) {
    throw new SocialExportError(
      "invalid_photo_batch",
      "The photo batch contains an invalid photo ID.",
    );
  }

  return mapConcurrent(normalized, 4, async (photo) => {
    try {
      return await analyzeImpl(photo, fetchImpl);
    } catch (error) {
      return {
        photoId: photo.photoId,
        error: cleanAnalysisError(error),
      };
    }
  });
}

function cleanAnalysisError(error) {
  const message = typeof error?.message === "string"
    ? error.message.replace(/\s+/g, " ").slice(0, 160)
    : "Photo analysis failed";
  return message || "Photo analysis failed";
}

export async function handlePhotoScoring(context) {
  if (context.request.method !== "POST") {
    return errorResponse(new SocialExportError(
      "method_not_allowed",
      "Use POST to score photos.",
      405,
    ));
  }
  try {
    const body = await context.request.json();
    const results = await scorePhotoBatch(body?.photos);
    return jsonResponse({ schemaVersion: 1, results });
  } catch (error) {
    return errorResponse(error);
  }
}
