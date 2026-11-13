// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Offline cache for kiosk devices: when the internet is gone, the kiosk page still opens
// (e.g. after the tablet reloads or restarts). Votes are kept by kiosk.js and sent later.
// Browsers run service workers only on HTTPS (and localhost).
const CACHE = "tapinion-kiosk-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(["/static/htmx.min.js", "/static/kiosk.js", "/static/style.css"])).catch(() => {})
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  const kiosk = url.pathname.startsWith("/k/");
  const asset = url.pathname.startsWith("/static/") || url.pathname.startsWith("/branding/");
  if (!kiosk && !asset) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        // keep only working kiosk screens, never the PIN page
        const keep = res.ok && (asset || res.headers.get("X-Kiosk-State") === "unlocked" || url.pathname.endsWith("/form"));
        if (keep) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(kiosk ? url.origin + url.pathname : req, copy));
        }
        return res;
      })
      .catch(() =>
        caches.open(CACHE).then((c) =>
          c.match(kiosk ? url.origin + url.pathname : req).then((hit) => hit || c.match(req, { ignoreSearch: true }))
        ).then((hit) => hit || Response.error())
      )
  );
});
