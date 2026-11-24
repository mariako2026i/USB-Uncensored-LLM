// Installable interface. Keep chat text, auth codes and recordings out of the cache.
self.addEventListener('fetch', (event) => {
  if (event.request.mode === 'navigate') event.respondWith(fetch(event.request));
});
