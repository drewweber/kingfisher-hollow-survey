const VERSION = __VERSION__;
const CACHE_VERSION = __CACHE_VERSION__;
const CACHE_NAME = `kh-field-${CACHE_VERSION}`;
const CACHE_PREFIX = "kh-field-";
const ASSETS = __ASSETS__;

const absolute = (path) => new URL(path, self.registration.scope).toString();
const cacheKey = (asset) => {
  const url = new URL(asset.path, self.registration.scope);
  url.searchParams.set("v", asset.sha256);
  return url.toString();
};

async function responseSha256(response) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await response.clone().arrayBuffer(),
  );
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function cacheOne(cache, asset) {
  const key = cacheKey(asset);
  if (await cache.match(key)) return;
  const reusable = await caches.match(key);
  if (reusable) {
    await cache.put(key, reusable);
    return;
  }
  const url = absolute(asset.path);
  const response = await fetch(url, { cache: "no-cache" });
  if (!response.ok) throw new Error(`Could not cache ${asset.path}: ${response.status}`);
  if (await responseSha256(response) !== asset.sha256) {
    throw new Error(`Asset changed while preparing offline access: ${asset.path}`);
  }
  await cache.put(key, response);
}

async function prepareOffline() {
  const cache = await caches.open(CACHE_NAME);
  let complete = 0;
  for (const asset of ASSETS) {
    await cacheOne(cache, asset);
    complete += 1;
    const clients = await self.clients.matchAll({ includeUncontrolled: true });
    for (const client of clients) {
      client.postMessage({ type: "OFFLINE_PROGRESS", complete, total: ASSETS.length });
    }
  }
  return verifyOffline();
}

async function verifyOffline() {
  const cache = await caches.open(CACHE_NAME);
  const missing = [];
  for (const asset of ASSETS) {
    if (!(await cache.match(cacheKey(asset)))) missing.push(asset.path);
  }
  return { ready: missing.length === 0, missing };
}

async function broadcastStatus(target) {
  const status = await verifyOffline();
  target.postMessage({
    type: "OFFLINE_STATUS",
    version: VERSION,
    ready: status.ready,
    missing: status.missing.length,
    total: ASSETS.length,
  });
}

self.addEventListener("install", (event) => {
  event.waitUntil(prepareOffline().then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const status = await verifyOffline();
    if (!status.ready) return;
    const names = await caches.keys();
    await Promise.all(names
      .filter((name) => name.startsWith(CACHE_PREFIX) && name !== CACHE_NAME)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
    const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of clients) {
      if (!client.url.startsWith(self.registration.scope)) continue;
      client.navigate(client.url).catch(() => {
        // The app's controllerchange handler still refreshes targets when
        // WindowClient.navigate is unavailable on the installed browser.
      });
    }
  })());
});

self.addEventListener("message", (event) => {
  if (!event.source) return;
  if (event.data?.type === "OFFLINE_STATUS") {
    event.waitUntil(broadcastStatus(event.source));
  }
  if (event.data?.type === "PREPARE_OFFLINE") {
    event.waitUntil(prepareOffline()
      .then(() => broadcastStatus(event.source))
      .catch((error) => event.source.postMessage({
        type: "OFFLINE_ERROR",
        message: error?.message || "Offline download failed",
      })));
  }
});

self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  const scopeUrl = new URL(self.registration.scope);
  if (requestUrl.origin !== scopeUrl.origin || !requestUrl.pathname.startsWith(scopeUrl.pathname)) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(event.request, { ignoreSearch: true });
    if (cached) return cached;
    try {
      const response = await fetch(event.request);
      if (response.ok && event.request.method === "GET") {
        await cache.put(event.request, response.clone());
      }
      return response;
    } catch (error) {
      if (event.request.mode === "navigate") {
        const app = await cache.match(absolute("./index.html"), { ignoreSearch: true });
        if (app) return app;
      }
      throw error;
    }
  })());
});
