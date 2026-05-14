const CACHE_NAME = "harbor-signal-v1";
const CORE_ASSETS = [
  "/",
  "/map/",
  "/timeline/",
  "/vessels/",
  "/signal/",
  "/logger/",
  "/logger.js",
  "/images/harbor-signal.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)));
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    caches.match(event.request).then((cached) => {
      return cached || fetch(event.request);
    })
  );
});
