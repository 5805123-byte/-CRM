// Service worker — installable app, always-fresh UI, and עבודה בלי אינטרנט.
// Network-first with HTTP-cache bypass so updates show immediately; cache is only an offline fallback.
const CACHE = 'kc-crm-v570';
const SHARE_CACHE = 'kc-shared';   // קבצים שהגיעו דרך "שיתוף" (וואטסאפ/גלריה) — לא נמחק בעדכון גרסה
const DATA_CACHE = 'kc-data';      // העותק האחרון של הנתונים, לשימוש בלי רשת
const SHELL = ['/', '/index.html', '/app.js', '/manifest.json', '/logo.png', '/kc-logo.png', '/icon-192.png', '/icon-512.png'];

/* ---------- תור השינויים שנעשו בלי רשת ----------
   מאיר: "איך אני עושה שה-CRM יעבוד גם אופליין, גם כשאין wifi".
   כל שמירה שנכשלת מחוסר רשת נשמרת כאן לפי הסדר, ונשלחת לשרת ברגע
   שהחיבור חוזר — כך שום תיקון לא הולך לאיבוד. */
const DBN = 'kc-out', STORE = 'q';
function idb() {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DBN, 1);
    r.onupgradeneeded = () => r.result.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}
function tx(db, mode) { return db.transaction(STORE, mode).objectStore(STORE); }
function done(req) { return new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error); }); }
async function qAll() { const db = await idb(); return done(tx(db, 'readonly').getAll()); }
async function qAdd(rec) { const db = await idb(); return done(tx(db, 'readwrite').add(rec)); }
async function qDel(id) { const db = await idb(); return done(tx(db, 'readwrite').delete(id)); }
async function qPut(rec) { const db = await idb(); return done(tx(db, 'readwrite').put(rec)); }
async function qCount() { try { return (await qAll()).length; } catch (e) { return 0; } }

async function tell(msg) {
  const cs = await self.clients.matchAll({ includeUncontrolled: true, type: 'window' });
  for (const c of cs) { try { c.postMessage(msg); } catch (e) {} }
}

// מזהה זמני שניתן לרשומה חדשה שנוצרה בלי רשת. שלילי, כדי שלא יתנגש
// לעולם במזהה אמיתי מהשרת.
let TMP = -Date.now();
const nextTmp = () => --TMP;

// אחרי שהשרת נתן מזהה אמיתי לרשומה שנוצרה אופליין — מחליפים את המזהה
// הזמני בכל מה שעדיין ממתין בתור ומתייחס אליה
function swapId(rec, from, to) {
  const f = String(from), t = String(to);
  rec.url = rec.url.replace(new RegExp('/' + f.replace('-', '\\-') + '$'), '/' + t);
  if (rec.body) {
    try {
      const o = JSON.parse(rec.body);
      let hit = false;
      for (const k of Object.keys(o)) {
        if (String(o[k]) === f) { o[k] = to; hit = true; }
      }
      if (hit) rec.body = JSON.stringify(o);
    } catch (e) {}
  }
  return rec;
}

let replaying = false;
async function replay() {
  if (replaying) return;
  replaying = true;
  try {
    let items = await qAll();
    items.sort((a, b) => a.id - b.id);
    let sent = 0, failed = 0;
    for (const it of items) {
      let r;
      try {
        r = await fetch(it.url, {
          method: it.method,
          headers: { 'Content-Type': 'application/json' },
          body: it.body || undefined
        });
      } catch (e) { break; }              // אין רשת — עוצרים ומנסים בפעם הבאה
      if (!r.ok && r.status >= 500) break;  // תקלת שרת — לא מאבדים, ננסה שוב
      if (r.ok && it.tmp) {
        let real = null;
        try { real = (await r.clone().json()).id; } catch (e) {}
        if (real != null) {
          // מתקנים גם את הרשימה שרצה כאן ולא רק את מה ששמור במכשיר —
          // אחרת השמירות הבאות בתור היו ממשיכות לפנות למזהה הזמני
          for (const x of items) {
            if (x.id > it.id) { swapId(x, it.tmp, real); await qPut(x); }
          }
        }
      }
      await qDel(it.id);
      if (r.ok) sent++; else failed++;
    }
    const left = await qCount();
    if (sent || failed || left === 0) await tell({ kc: 'synced', sent, failed, left });
    return { sent, failed, left };
  } finally { replaying = false; }
}

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
      .then(ks => Promise.all(ks.filter(k => k !== CACHE && k !== SHARE_CACHE && k !== DATA_CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
      .then(() => replay().catch(() => {}))
  );
});
self.addEventListener('message', e => {
  const d = e.data || {};
  if (d.kc === 'sync') e.waitUntil(replay().catch(() => {}));
  if (d.kc === 'pending') e.waitUntil(qCount().then(n => tell({ kc: 'pending', n })));
});
self.addEventListener('sync', e => { if (e.tag === 'kc-sync') e.waitUntil(replay().catch(() => {})); });

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
  // שמירה בלי רשת — נכנסת לתור ותישלח כשהחיבור יחזור
  if (e.request.method !== 'GET' && url.pathname.startsWith('/api/')) {
    e.respondWith((async () => {
      const body = await e.request.clone().text().catch(() => '');
      try {
        const r = await fetch(e.request);
        if (r.status < 500) { replay().catch(() => {}); return r; }
        throw new Error('server');
      } catch (err) {
        // POST פותח רשומה חדשה, ולכן צריך מזהה שהמסך יוכל לעבוד איתו
        // עד שהשרת ייתן את האמיתי
        const tmp = e.request.method === 'POST' ? nextTmp() : null;
        try {
          await qAdd({ url: url.pathname + url.search, method: e.request.method, body, tmp, at: Date.now() });
        } catch (e2) {
          return new Response(JSON.stringify({ ok: false, offline: true, error: 'queue' }),
            { status: 503, headers: { 'Content-Type': 'application/json' } });
        }
        tell({ kc: 'queued', n: await qCount() });
        const out = { ok: true, queued: true };
        if (tmp != null) out.id = tmp;
        return new Response(JSON.stringify(out),
          { status: 200, headers: { 'Content-Type': 'application/json', 'X-KC-Queued': '1' } });
      }
    })());
    return;
  }
  if (e.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/')) {
    // נתונים חיים כשיש רשת; בלי רשת — העותק האחרון שנשמר, כדי שהכרטיסים
    // יהיו זמינים גם בלי wifi
    e.respondWith((async () => {
      try {
        const r = await fetch(e.request);
        if (r.ok) { const copy = r.clone(); caches.open(DATA_CACHE).then(c => c.put(url.pathname + url.search, copy)); }
        return r;
      } catch (err) {
        const c = await caches.open(DATA_CACHE);
        const hit = await c.match(url.pathname + url.search);
        if (hit) {
          const h = new Headers(hit.headers);
          h.set('X-KC-Offline', '1');
          h.delete('ETag');                     // שלא ייחשב כתשובה טרייה
          // הגוף שנשמר הוא כבר מפוענח; אסור להשאיר כותרות שמתארות דחיסה
          h.delete('Content-Encoding'); h.delete('Content-Length');
          return new Response(await hit.blob(), { status: 200, headers: h });
        }
        return new Response(JSON.stringify({ offline: true }),
          { status: 503, headers: { 'Content-Type': 'application/json' } });
      }
    })());
    return;
  }
  // Network-first, bypassing the browser HTTP cache so a new deploy is picked up at once.
  e.respondWith(
    fetch(e.request, { cache: 'no-store' })
      .then(res => { const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return res; })
      .catch(() => caches.match(e.request).then(r => r || caches.match('/')))
  );
});
