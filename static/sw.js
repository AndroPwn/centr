// centr Service Worker
//
// Goal: once a phone has loaded this page ONE time (e.g. while connected to
// a neighbor's hotspot), the app shell must keep working with zero network
// at all — no Wi-Fi, no hotspot, nothing. That's the whole point of a
// "post-blackout" app.
//
// Strategy:
//   - App shell (HTML/CSS/JS/manifest/icons): cache-first, so it loads
//     instantly and works fully offline once cached.
//   - /api/* and /download/*: NEVER cache. These are either live mesh data
//     (which must always be current, not stale) or a large binary download.
//     If the bridge process on this device isn't reachable, we fail
//     gracefully instead of serving stale/wrong data.

const CACHE_NAME = "centr-shell-v2";

const APP_SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Live/dynamic endpoints: network-only, with a graceful JSON failure
  // instead of a broken fetch() throwing in the page.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/download/")) {
    event.respondWith(
      fetch(req).catch(
        () =>
          new Response(
            JSON.stringify({ ok: false, error: "This device's bridge node is unreachable right now." }),
            { status: 503, headers: { "Content-Type": "application/json" } }
          )
      )
    );
    return;
  }

  // App shell: cache-first, falling back to network, falling back to the
  // cached index.html for any unknown navigation (so refreshing while
  // offline never shows a browser error page).
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req)
        .then((response) => {
          if (response && response.status === 200 && req.method === "GET") {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
          }
          return response;
        })
        .catch(() => caches.match("/index.html"));
    })
  );
});
