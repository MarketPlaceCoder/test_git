const CACHE = "research-pwa-v1";
const ASSETS = [
  "./",
  "./index.html",
  "./style.css",
  "./main.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(e.request).catch(()=>caches.match(e.request))
    );
  } else {
    e.respondWith(
      caches.match(e.request).then(res => res || fetch(e.request))
    );
  }
});

