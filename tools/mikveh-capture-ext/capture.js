// מקליט בקשות המקווה — תוסף לכרום (גרסה 2). רץ לבד בכל כרטיסייה של prod.מקווה.com (גם בלקוח שנפתח בכרטיסייה חדשה).
// כל הכרטיסיות כותבות לאותה רשימה (נשמרת בדפדפן בלבד), ומכל כרטיסייה אפשר להוריד את הכל לקובץ אחד.
// מוסתרים: טוקן, סיסמאות, מספרי זהות, טלפון, מייל, פרטי כרטיס, תמונות פנים, תשובת חברת האשראי. הכניסה (Account) לא נרשמת.
// 🎥 גרסה 2 — מאיר: "צפייה מרחוק במסך המכונה, וגם ללחוץ על כפתורים — זה נראה לי וידאו, תשכלל שיקלוט יותר":
//   • WebSocket (חיבור חי): הכתובת, פתיחה / סגירה, ההודעות הראשונות שמגיעות (טקסט או סוג הקובץ הבינארי), וכל מה שנשלח
//     (לחיצה על כפתור במסך המרוחק נשלחת בדרך כלל כך)
//   • WebRTC (וידאו חי): שרתי החיבור (בלי סיסמאות), סוג הווידאו (קודק), ערוצי נתונים ומה שנשלח בהם
//   • EventSource, תמונות / וידאו / מסגרות שנטענות (רק הכתובת והגודל — בלי התוכן)
//   • כפתור "📸 מה יש בדף" — אילו iframe / video / img / canvas יש עכשיו בדף (כתובת וגודל)
//   • גם בתוך מסגרת מאתר אחר (למשל המסך המרוחק) — נשלח לחלון הראשי ונשמר באותה רשימה
(() => {
  if (window.__mkCapExt) return;

  const MK_HOST = /(^|\.)xn--8dbba8a7b\.com$/i;
  const IS_TOP = window.top === window;
  // רצים רק בכרטיסייה של המקווה: בחלון הראשי שלה, או במסגרת שנמצאת בתוכה
  let inMk = MK_HOST.test(location.hostname);
  if (!IS_TOP && !inMk) {
    try { inMk = [...(location.ancestorOrigins || [])].some(o => MK_HOST.test(new URL(o).hostname)); } catch (e) {}
  }
  if (!inMk) return;
  window.__mkCapExt = true;
  const MK_FRAME = MK_HOST.test(location.hostname);   // מסגרת מאותו אתר — כותבת ישר; מאתר אחר — שולחת לחלון הראשי

  const KEY = '__mikveh_capture_log', TAGKEY = '__mikveh_capture_tag', MAXN = 1500;
  const SENS = /password|passwd|pwd|personalId|idNumber|^tz$|zeout|token|authorization|cardSerial|faceImage|creditCard|cardNumber|cvv|cvc|tokef|lastNum|phone|mobile|email|mail$|paymentResponse|credential|secret|apikey|api_key|sessionid|cookie/i;
  const HIDE_RESP = /GetAllPasswords|GetFaceImages|\/CreditCard\//i;
  const MAXARR = 3, MAXSTR = 300;
  const TAB = Math.random().toString(36).slice(2, 6);

  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } }
  };

  function clean(v, d = 0) {
    if (d > 10) return '…';
    if (Array.isArray(v)) {
      const a = v.slice(0, MAXARR).map(x => clean(x, d + 1));
      if (v.length > MAXARR) a.push('… ועוד ' + (v.length - MAXARR) + ' רשומות');
      return a;
    }
    if (v && typeof v === 'object') {
      const o = {};
      for (const k in v) o[k] = SENS.test(k) ? '[הוסתר]' : clean(v[k], d + 1);
      return o;
    }
    if (typeof v === 'string' && v.length > MAXSTR) return v.slice(0, MAXSTR) + '…';
    return v;
  }
  // טקסט חופשי (הודעות בחיבור חי): מסתירים "token=…", "password: …" וכו'
  function scrub(t) {
    return String(t).replace(/(token|password|passwd|pwd|authorization|secret|apikey|api_key|credential|bearer)(["'\s]*[:=]\s*["']?|\s+)[^"'&\s,;}]+/gi, '$1$2[הוסתר]');
  }
  function parse(t) {
    if (t == null || t === '') return t == null ? null : '';
    try { return clean(JSON.parse(t)); } catch (e) { return scrub(String(t)).slice(0, MAXSTR); }
  }
  function cleanUrl(u) {
    try {
      const x = new URL(u, location.href);
      for (const k of [...x.searchParams.keys()]) if (SENS.test(k)) x.searchParams.set(k, '[הוסתר]');
      if (x.username || x.password) { x.username = '[הוסתר]'; x.password = ''; }
      if (/^(blob|data):/i.test(x.protocol)) return x.protocol + '…';
      return x.toString();
    } catch (e) { return String(u).slice(0, 200); }
  }
  // סוג קובץ בינארי לפי הבייטים הראשונים — כדי לדעת אם זה וידאו, תמונות או מסך מרוחק (VNC)
  function sniff(u8) {
    const h = [...u8.slice(0, 12)].map(b => b.toString(16).padStart(2, '0')).join(' ');
    const s = String.fromCharCode(...u8.slice(0, 12));
    let kind = '';
    if (u8[0] === 0xff && u8[1] === 0xd8) kind = 'JPEG (תמונה)';
    else if (u8[0] === 0x89 && s.slice(1, 4) === 'PNG') kind = 'PNG (תמונה)';
    else if (s.slice(0, 4) === 'RIFF' && s.slice(8, 12) === 'WEBP') kind = 'WEBP (תמונה)';
    else if (s.startsWith('RFB ')) kind = 'VNC (מסך מרוחק)';
    else if (u8[0] === 0x1a && u8[1] === 0x45 && u8[2] === 0xdf && u8[3] === 0xa3) kind = 'WebM/MKV (וידאו)';
    else if (s.slice(4, 8) === 'ftyp' || s.slice(4, 8) === 'moof' || s.slice(4, 8) === 'mdat') kind = 'MP4 (וידאו)';
    else if (u8[0] === 0 && u8[1] === 0 && (u8[2] === 1 || (u8[2] === 0 && u8[3] === 1))) kind = 'H.264/H.265 (וידאו גולמי)';
    else if (u8[0] === 0x47) kind = 'MPEG-TS? (וידאו)';
    else if (u8[0] === 0x1f && u8[1] === 0x8b) kind = 'GZIP';
    return { size: u8.length, format: kind || 'לא מזוהה', head: h };
  }
  function binInfo(d) {
    try {
      if (d instanceof ArrayBuffer) return sniff(new Uint8Array(d));
      if (ArrayBuffer.isView(d)) return sniff(new Uint8Array(d.buffer, d.byteOffset, d.byteLength));
      if (typeof Blob !== 'undefined' && d instanceof Blob) return { size: d.size, format: 'Blob ' + (d.type || ''), head: '' };
    } catch (e) {}
    return { size: 0, format: typeof d, head: '' };
  }

  let full = false;
  function store(entry) {
    const log = ls.get(KEY, []);
    if (log.length >= MAXN) { full = true; refresh(); return; }
    entry.n = log.length + 1;
    log.push(entry);
    if (!ls.set(KEY, log)) full = true;
    refresh();
  }
  function push(entry) {
    entry.time = new Date().toLocaleTimeString('he-IL');
    entry.tab = TAB;
    entry.frame = IS_TOP ? '' : (location.host || location.protocol);
    entry.screen = (IS_TOP || MK_FRAME) ? (location.hash || location.pathname) : '';
    if (IS_TOP || MK_FRAME) { entry.tag = ls.get(TAGKEY, ''); store(entry); }
    else { try { window.top.postMessage({ __mkcap: entry }, '*'); } catch (e) {} }
  }
  // החלון הראשי מקבל רשומות ממסגרות מאתר אחר
  if (IS_TOP) window.addEventListener('message', e => {
    const d = e.data && e.data.__mkcap;
    if (!d || typeof d !== 'object' || typeof d.kind !== 'string') return;
    d.tag = ls.get(TAGKEY, ''); d.from = e.origin;
    store(d);
  });

  function add(method, url, body, status, resp) {
    let path = '';
    try { path = new URL(url, location.href).pathname; } catch (e) { path = String(url); }
    if (/\.(js|css|png|jpe?g|gif|svg|woff2?|ttf|ico|map|html|json)$/i.test(path)) return;
    if (/\/Account\/?$/i.test(path)) return;
    if (HIDE_RESP.test(path)) resp = '"[הוסתר]"';
    push({
      kind: 'http',
      method: String(method || 'GET').toUpperCase(),
      url: cleanUrl(url),
      status: status,
      body: typeof body === 'string' ? parse(body) : (body ? '[גוף שאינו טקסט]' : null),
      response: typeof resp === 'string' ? parse(resp) : resp
    });
  }

  // ---------- XHR ----------
  const XO = XMLHttpRequest.prototype.open, XS = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__mk = { m: m, u: u }; return XO.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) {
    const x = this;
    if (x.__mk) x.addEventListener('loadend', () => {
      let r;
      try {
        r = (x.responseType === '' || x.responseType === 'text') ? x.responseText
          : x.responseType === 'json' ? JSON.stringify(x.response)
          : (x.response ? '[' + x.responseType + '] ' + JSON.stringify(binInfo(x.response)) : '[' + x.responseType + ']');
      } catch (e) { r = null; }
      try { add(x.__mk.m, x.__mk.u, b, x.status, r); } catch (e) {}
    });
    return XS.apply(this, arguments);
  };

  // ---------- fetch ----------
  const F = window.fetch;
  window.fetch = async function (input, init) {
    const res = await F.apply(this, arguments);
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || String(input);
      const m = (init && init.method) || (input && input.method) || 'GET';
      const b = init && init.body;
      const ct = (res.headers.get('content-type') || '').toLowerCase();
      if (/video|image|octet-stream|multipart\/x-mixed-replace/.test(ct)) {
        // זרם וידאו / תמונות — לא קוראים את התוכן (יכול להיות אינסופי), רק מה זה
        add(m, url, b, res.status, '[' + ct + ']');
      } else res.clone().text().then(t => add(m, url, b, res.status, t)).catch(() => {});
    } catch (e) {}
    return res;
  };

  // ---------- WebSocket — חיבור חי ----------
  const WS = window.WebSocket;
  if (WS) {
    let wsN = 0;
    const MKWS = function (url, protocols) {
      const ws = protocols === undefined ? new WS(url) : new WS(url, protocols);
      const id = 'ws' + (++wsN) + '-' + TAB;
      const st = { inN: 0, outN: 0, inBytes: 0, outBytes: 0, kinds: {}, opened: Date.now() };
      push({ kind: 'ws-open', ws: id, url: cleanUrl(url), protocols: protocols ? String(protocols) : '' });
      ws.addEventListener('open', () => push({ kind: 'ws-connected', ws: id, protocol: ws.protocol || '', binaryType: ws.binaryType }));
      ws.addEventListener('message', ev => {
        st.inN++;
        const d = ev.data;
        let info;
        if (typeof d === 'string') { info = { text: parse(d) }; st.inBytes += d.length; st.kinds.text = (st.kinds.text || 0) + 1; }
        else { info = binInfo(d); st.inBytes += info.size || 0; st.kinds[info.format] = (st.kinds[info.format] || 0) + 1; }
        // ה-15 הראשונות — במלואן (מקוצר); אחר כך רק ספירה (וידאו שולח הרבה)
        if (st.inN <= 15) push(Object.assign({ kind: 'ws-in', ws: id, i: st.inN }, info));
      });
      const S0 = ws.send;
      ws.send = function (d) {
        st.outN++;
        let info;
        if (typeof d === 'string') { info = { text: parse(d) }; st.outBytes += d.length; }
        else { info = binInfo(d); st.outBytes += info.size || 0; }
        // מה שנשלח — כמעט תמיד לחיצות / פקודות; נרשם עד 300 לכל חיבור
        if (st.outN <= 300) push(Object.assign({ kind: 'ws-out', ws: id, i: st.outN }, info));
        return S0.apply(this, arguments);
      };
      const sum = () => push({ kind: 'ws-summary', ws: id, seconds: Math.round((Date.now() - st.opened) / 1000), in: st.inN, inKB: Math.round(st.inBytes / 1024), out: st.outN, outKB: Math.round(st.outBytes / 1024), types: st.kinds });
      const tm = setInterval(() => { if (ws.readyState === 1 && st.inN > 15) sum(); }, 15000);
      ws.addEventListener('close', ev => { clearInterval(tm); sum(); push({ kind: 'ws-closed', ws: id, code: ev.code, reason: scrub(ev.reason || '') }); });
      ws.addEventListener('error', () => push({ kind: 'ws-error', ws: id }));
      return ws;
    };
    MKWS.prototype = WS.prototype;
    ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach(k => { try { MKWS[k] = WS[k]; } catch (e) {} });
    window.WebSocket = MKWS;
  }

  // ---------- EventSource ----------
  const ES = window.EventSource;
  if (ES) {
    const MKES = function (url, cfg) {
      const es = new ES(url, cfg);
      let n = 0;
      push({ kind: 'sse-open', url: cleanUrl(url) });
      es.addEventListener('message', ev => { if (++n <= 15) push({ kind: 'sse-in', i: n, text: parse(ev.data) }); });
      return es;
    };
    MKES.prototype = ES.prototype;
    window.EventSource = MKES;
  }

  // ---------- WebRTC — וידאו חי ----------
  const sdpSum = sdp => {
    const L = String(sdp || '').split(/\r?\n/);
    const out = { media: [], codecs: [] };
    L.forEach(l => {
      if (l.startsWith('m=')) out.media.push(l.slice(2).split(' ').slice(0, 3).join(' '));
      const m = l.match(/^a=rtpmap:\d+ ([^/]+)/); if (m && !out.codecs.includes(m[1])) out.codecs.push(m[1]);
    });
    return out;   // בלי ice-pwd / ufrag / fingerprint — לא נשמרים
  };
  const PC = window.RTCPeerConnection;
  if (PC) {
    let pcN = 0;
    const MKPC = function (cfg) {
      const pc = new PC(cfg);
      const id = 'rtc' + (++pcN) + '-' + TAB;
      push({ kind: 'rtc-new', rtc: id, iceServers: ((cfg && cfg.iceServers) || []).map(s => ({ urls: [].concat(s.urls || s.url || []).map(cleanUrl), username: s.username ? '[הוסתר]' : undefined, credential: s.credential ? '[הוסתר]' : undefined })) });
      ['setLocalDescription', 'setRemoteDescription'].forEach(fn => {
        const o = pc[fn];
        pc[fn] = function (d) { try { if (d && d.sdp) push({ kind: 'rtc-' + (fn === 'setLocalDescription' ? 'local' : 'remote'), rtc: id, type: d.type, sdp: sdpSum(d.sdp) }); } catch (e) {} return o.apply(this, arguments); };
      });
      pc.addEventListener('connectionstatechange', () => push({ kind: 'rtc-state', rtc: id, state: pc.connectionState }));
      pc.addEventListener('track', ev => push({ kind: 'rtc-track', rtc: id, track: ev.track && ev.track.kind, label: ev.track && ev.track.label }));
      const wireDC = (dc, how) => {
        push({ kind: 'rtc-datachannel', rtc: id, how: how, label: dc.label, protocol: dc.protocol || '' });
        let n = 0, o = 0;
        dc.addEventListener('message', ev => { if (++n <= 15) push(Object.assign({ kind: 'dc-in', rtc: id, label: dc.label, i: n }, typeof ev.data === 'string' ? { text: parse(ev.data) } : binInfo(ev.data))); });
        const S0 = dc.send;
        dc.send = function (d) { if (++o <= 300) push(Object.assign({ kind: 'dc-out', rtc: id, label: dc.label, i: o }, typeof d === 'string' ? { text: parse(d) } : binInfo(d))); return S0.apply(this, arguments); };
      };
      const CD = pc.createDataChannel;
      pc.createDataChannel = function () { const dc = CD.apply(this, arguments); try { wireDC(dc, 'נפתח מהדף'); } catch (e) {} return dc; };
      pc.addEventListener('datachannel', ev => { try { wireDC(ev.channel, 'נפתח מהצד השני'); } catch (e) {} });
      return pc;
    };
    MKPC.prototype = PC.prototype;
    try { Object.keys(PC).forEach(k => { MKPC[k] = PC[k]; }); MKPC.generateCertificate = PC.generateCertificate; } catch (e) {}
    window.RTCPeerConnection = MKPC;
  }

  // ---------- תמונות / וידאו / מסגרות שנטענות (רק כתובת וגודל) ----------
  try {
    const seen = {};
    new PerformanceObserver(list => {
      list.getEntries().forEach(en => {
        if (!/img|video|iframe|frame|other|css|link|beacon|xmlhttprequest|fetch/.test(en.initiatorType)) return;
        let key = en.name;
        try { const u = new URL(en.name); key = u.origin + u.pathname.replace(/\d{3,}/g, '#'); } catch (e) {}
        // אותו נתיב שחוזר הרבה (תמונה שמתרעננת) — נרשם פעם ראשונה ואחר כך כל 20 פעמים
        seen[key] = (seen[key] || 0) + 1;
        if (!/img|video|iframe|frame|other/.test(en.initiatorType)) return;
        if (seen[key] === 1 || seen[key] % 20 === 0) push({ kind: 'resource', type: en.initiatorType, url: cleanUrl(en.name), times: seen[key], kb: Math.round((en.transferSize || en.encodedBodySize || 0) / 1024), ms: Math.round(en.duration) });
      });
    }).observe({ type: 'resource', buffered: true });
  } catch (e) {}

  // ---------- 📸 מה יש בדף עכשיו ----------
  function snapshot() {
    const box = el => { const r = el.getBoundingClientRect(); return Math.round(r.width) + '×' + Math.round(r.height); };
    const out = [];
    document.querySelectorAll('iframe,frame').forEach(f => out.push({ tag: f.tagName.toLowerCase(), src: cleanUrl(f.src || f.getAttribute('src') || ''), size: box(f), title: f.title || '' }));
    document.querySelectorAll('video').forEach(v => out.push({ tag: 'video', src: (v.currentSrc || v.src) ? cleanUrl(v.currentSrc || v.src) : '', live: !!v.srcObject, stream: v.srcObject ? (v.srcObject.constructor && v.srcObject.constructor.name) : '', size: box(v), video: v.videoWidth + '×' + v.videoHeight, playing: !v.paused }));
    document.querySelectorAll('img').forEach(i => { const r = i.getBoundingClientRect(); if (r.width >= 200 && r.height >= 120) out.push({ tag: 'img', src: cleanUrl(i.currentSrc || i.src || ''), size: box(i), natural: i.naturalWidth + '×' + i.naturalHeight }); });
    document.querySelectorAll('canvas').forEach(c => { const r = c.getBoundingClientRect(); if (r.width >= 200 && r.height >= 120) out.push({ tag: 'canvas', size: box(c), pixels: c.width + '×' + c.height, id: c.id || '', cls: String(c.className || '').slice(0, 60) }); });
    document.querySelectorAll('object,embed').forEach(o => out.push({ tag: o.tagName.toLowerCase(), src: cleanUrl(o.data || o.src || ''), size: box(o) }));
    return out;
  }
  if (!IS_TOP) window.addEventListener('message', e => {
    if (e.data && e.data.__mksnap) push({ kind: 'snapshot', where: location.host, items: snapshot() });
  });

  // ---------- חלון קטן — רק בחלון הראשי ----------
  let cnt, warn, tagIn;
  function refresh() {
    if (!cnt) return;
    cnt.textContent = ls.get(KEY, []).length;
    warn.style.display = full ? 'block' : 'none';
    if (document.activeElement !== tagIn) tagIn.value = ls.get(TAGKEY, '');
  }
  function panel() {
    if (!IS_TOP || !document.body || !MK_HOST.test(location.hostname)) return;
    const box = document.createElement('div');
    box.dir = 'rtl';
    box.style.cssText = 'position:fixed;bottom:16px;left:16px;z-index:2147483647;background:#fff;color:#111;border:2px solid #d93025;border-radius:10px;padding:10px 12px;font:14px Arial,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.25);width:280px';
    box.innerHTML =
      '<div style="font-weight:bold;margin-bottom:6px">🔴 מקליט המקווה <span style="font-weight:normal;color:#666">(גרסה 2 · כל הכרטיסיות)</span></div>' +
      '<div style="margin-bottom:4px">מה אני עושה עכשיו:</div>' +
      '<input id="mkTag" placeholder="למשל: לחצתי צפייה מרחוק" style="width:100%;box-sizing:border-box;padding:4px;margin-bottom:6px">' +
      '<div style="margin-bottom:6px">נרשמו: <b id="mkCnt">0</b> רשומות</div>' +
      '<div id="mkWarn" style="display:none;color:#d93025;margin-bottom:6px">הרשימה מלאה — הורד קובץ ולחץ "נקה"</div>' +
      '<button id="mkSnap" style="padding:5px 8px;margin:0 0 6px 4px" title="אילו מסגרות / וידאו / תמונות / קנבס יש עכשיו בדף">📸 מה יש בדף</button><br>' +
      '<button id="mkDl" style="padding:5px 10px;margin-left:4px">⬇ הורד קובץ</button>' +
      '<button id="mkClr" style="padding:5px 10px;margin-left:4px">נקה</button>' +
      '<button id="mkMin" style="padding:5px 10px">_</button>';
    document.body.appendChild(box);
    cnt = box.querySelector('#mkCnt'); warn = box.querySelector('#mkWarn'); tagIn = box.querySelector('#mkTag');
    tagIn.addEventListener('input', e => ls.set(TAGKEY, e.target.value.trim()));
    box.querySelector('#mkSnap').onclick = () => {
      push({ kind: 'snapshot', where: location.host, items: snapshot().filter(x => !(x.tag === 'img' && /^data/.test(x.src))) });
      // גם המסגרות שבתוך הדף (אם התוסף רץ בהן)
      document.querySelectorAll('iframe,frame').forEach(f => { try { f.contentWindow.postMessage({ __mksnap: 1 }, '*'); } catch (e) {} });
      const b = box.querySelector('#mkSnap'); b.textContent = '✓ נרשם'; setTimeout(() => { b.textContent = '📸 מה יש בדף'; }, 1500);
    };
    box.querySelector('#mkClr').onclick = () => {
      if (confirm('למחוק את כל מה שנרשם?')) { ls.set(KEY, []); ls.set(TAGKEY, ''); full = false; refresh(); }
    };
    let small = false;
    box.querySelector('#mkMin').onclick = () => {
      small = !small;
      [...box.children].forEach((c, i) => { if (i > 0 && c.id !== 'mkMin') c.style.display = small ? 'none' : ''; });
      box.querySelector('#mkMin').style.display = '';
      if (small) box.appendChild(box.querySelector('#mkMin')); else refresh();
    };
    box.querySelector('#mkDl').onclick = () => {
      const d = new Date(), p = n => String(n).padStart(2, '0');
      const name = 'mikveh-capture-' + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '-' + p(d.getHours()) + p(d.getMinutes()) + '.json';
      const blob = new Blob([JSON.stringify({ at: d.toISOString(), version: 2, requests: ls.get(KEY, []) }, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
    };
    window.addEventListener('storage', e => { if (e.key === KEY || e.key === TAGKEY) refresh(); });
    refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', panel); else panel();
})();
