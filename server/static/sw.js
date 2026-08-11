// Service worker — installable app, always-fresh UI.
// Network-first with HTTP-cache bypass so updates show immediately; cache is only an offline fallback.
const CACHE = 'kc-crm-v266';
const SHARE_CACHE = 'kc-shared';   // קבצים שהגיעו דרך "שיתוף" (וואטסאפ/גלריה) — לא נמחק בעדכון גרסה
const SHELL = ['/', '/index.html', '/app.js', '/manifest.json', '/logo.png', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(SHELL.map(u => new Request(u, { cache: 'reload' }))))
      .then(() => self.skipWaiting())
  );
});
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(ks => Promise.all(ks.filter(k => k !== CACHE && k !== SHARE_CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // שיתוף מוואטסאפ/גלריה אל תוך האפליקציה — שומרים את הקבצים ופותחים את מסך השיוך
  if (e.request.method === 'POST' && url.pathname === '/share-target') {
    e.respondWith((async () => {
      try {
        const fd = await e.request.formData();
        const files = fd.getAll('files').filter(f => f && f.size);
        const c = await caches.open(SHARE_CACHE);
        for (const k of await c.keys()) await c.delete(k);      // ניקוי שיתוף קודם
        let i = 0;
        for (const f of files) {
          await c.put(new Request('/__shared__/' + (i++) + '/' + encodeURIComponent(f.name || 'file')),
                      new Response(f, { headers: { 'Content-Type': f.type || 'application/octet-stream' } }));
        }
        const txt = (fd.get('text') || fd.get('title') || '').toString();
        if (txt) await c.put(new Request('/__shared_text__'), new Response(txt));
      } catch (err) { /* אם משהו נכשל — עדיין נפתח את האפליקציה */ }
      return Response.redirect('/?share=1', 303);
    })());
    return;
  }
  if (e.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/')) {                 // always live data
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }
  // Network-first, bypassing the browser HTTP cache so a new deploy is picked up at once.
  e.respondWith(
    fetch(e.request, { cache: 'no-store' })
      .then(res => { const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return res; })
      .catch(() => caches.match(e.request).then(r => r || caches.match('/')))
  );
});
