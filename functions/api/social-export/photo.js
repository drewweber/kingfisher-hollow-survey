import {
  SocialExportError,
  errorResponse,
  validateInatPhotoUrl,
} from "../../../src/social_export_runtime.mjs";

const PHOTO_CACHE_SECONDS = 7 * 24 * 60 * 60;
const MAX_PHOTO_BYTES = 10_000_000;

function cacheKey(requestUrl, photoUrl) {
  const source = new URL(photoUrl);
  const key = new URL("/__social-export-cache/photo", requestUrl);
  key.searchParams.set("source", `${source.hostname}${source.pathname}`);
  return new Request(key);
}

export async function onRequest(context) {
  if (!["GET", "HEAD"].includes(context.request.method)) {
    return errorResponse(new SocialExportError(
      "method_not_allowed",
      "Use GET to retrieve a reviewed iNaturalist photo.",
      405,
    ));
  }

  try {
    const requestUrl = new URL(context.request.url);
    const photoUrl = validateInatPhotoUrl(requestUrl.searchParams.get("url"));
    const cache = globalThis.caches?.default || null;
    const key = cacheKey(requestUrl, photoUrl);
    const cached = cache ? await cache.match(key) : null;
    if (cached) {
      return context.request.method === "HEAD"
        ? new Response(null, { status: cached.status, headers: cached.headers })
        : cached;
    }

    const upstream = await fetch(photoUrl, {
      redirect: "manual",
      headers: {
        Accept: "image/jpeg,image/png,image/webp",
        "User-Agent": "Kingfisher-Hollow-Social-Export/1.0 (survey.kingfisher-hollow.com)",
      },
    });
    if (!upstream.ok) {
      throw new SocialExportError(
        "photo_download_failed",
        "A reviewed iNaturalist photo could not be downloaded. Retry the export.",
        502,
        true,
      );
    }
    const contentType = upstream.headers.get("content-type") || "";
    const contentLength = Number(upstream.headers.get("content-length")) || 0;
    if (!/^image\/(jpeg|png|webp)(?:;|$)/i.test(contentType)) {
      throw new SocialExportError(
        "invalid_photo_response",
        "iNaturalist returned an unexpected photo response. Retry the export.",
        502,
        true,
      );
    }
    if (contentLength > MAX_PHOTO_BYTES) {
      throw new SocialExportError(
        "photo_too_large",
        "One selected photo is too large to render safely. Choose another photo.",
      );
    }

    const headers = new Headers({
      "Content-Type": contentType,
      "Cache-Control": `public, max-age=${PHOTO_CACHE_SECONDS}, immutable`,
      "X-Content-Type-Options": "nosniff",
    });
    if (contentLength) headers.set("Content-Length", String(contentLength));
    const response = new Response(upstream.body, {
      status: 200,
      headers,
    });
    if (cache) context.waitUntil(cache.put(key, response.clone()));
    return context.request.method === "HEAD"
      ? new Response(null, { status: 200, headers })
      : response;
  } catch (error) {
    console.error("Social export photo proxy failed", error);
    return errorResponse(error);
  }
}
