const CACHE_NAME = "kater-shell-v3";

const SHELL_FILES = [
  "/",
  "/style.css",
  "/app.js",
  "/manifest.json",
  "/icon.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API-запросы всегда идут в сеть — чат не кэшируем.
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // Сеть в приоритете, кэш — только офлайн-страховка. Раньше было наоборот
  // (cache-first) и дважды подряд ловили баг: поправили app.js, забыли
  // поднять CACHE_NAME — старые установленные PWA молча получали устаревший
  // код без единой ошибки. Теперь свежая версия подтягивается сама, пока
  // есть сеть, а версия кэша нужна только для офлайн-режима.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
