const CACHE_NAME = "harbor-signal-v2";
const CORE_ASSETS = [
  "/logger.js",
  "/map.js",
  "/manifest.webmanifest",
  "/images/harbor-signal.png",
  "/images/ingrid-portrait.jpg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(CORE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const acceptsHtml = event.request.headers.get("accept")?.includes("text/html");
  const sameOrigin = new URL(event.request.url).origin === self.location.origin;
  if (event.request.mode === "navigate" || acceptsHtml || sameOrigin) {
    event.respondWith(networkFirst(event.request));
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request);
    })
  );
});

function networkFirst(request) {
  return fetch(request)
    .then((response) => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
      }
      return response;
    })
    .catch(() => caches.match(request).then((cached) => cached || caches.match("/")));
}
