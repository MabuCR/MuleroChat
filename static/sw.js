// MuleroChat Service Worker — offline fallback basico
const CACHE = "mulerochat-v1";
const OFFLINE_URL = "/offline";

// Al instalar: pre-cachear la pagina de offline
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(["/", "/offline"]))
  );
  self.skipWaiting();
});

// Al activar: limpiar caches viejos
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: primero red, si falla offline fallback
self.addEventListener("fetch", (event) => {
  // WebSockets no se cachean
  if (event.request.url.includes("/ws/")) return;
  // Requests de API no se cachean
  if (event.request.url.includes("/api/")) return;

  event.respondWith(
    fetch(event.request).catch(() =>
      caches.match(event.request).then((cached) => cached || caches.match(OFFLINE_URL))
    )
  );
});
