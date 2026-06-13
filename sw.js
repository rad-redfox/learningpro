const CACHE = 'learningpro-v2';
const ASSETS = ['/', '/index.html', '/manifest.json', '/icon.svg',
  'https://fonts.googleapis.com/css2?family=Fredoka+One&family=Nunito:wght@400;600;700&display=swap'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  // Only handle GET. Let POST/others (the /api/* calls) pass straight to the network.
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Never intercept API calls.
  if (url.pathname.startsWith('/api/') || url.hostname.includes('anthropic.com')) return;

  // Network-first: always try fresh (so new deploys show up immediately),
  // fall back to cache only when offline.
  e.respondWith(
    fetch(req)
      .then(res => {
        if (res && res.status === 200 && (res.type === 'basic' || res.type === 'cors')) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(req, clone)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then(c => c || caches.match('/index.html')))
  );
});
