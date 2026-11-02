// מקליט בקשות המקווה — תוסף לכרום. רץ לבד בכל כרטיסייה של prod.מקווה.com (גם בלקוח שנפתח בכרטיסייה חדשה).
// כל הכרטיסיות כותבות לאותה רשימה (נשמרת בדפדפן בלבד), ומכל כרטיסייה אפשר להוריד את הכל לקובץ אחד.
// מוסתרים: טוקן, סיסמאות, מספרי זהות, טלפון, מייל, פרטי כרטיס, תמונות פנים, תשובת חברת האשראי. הכניסה (Account) לא נרשמת.
(() => {
  if (window.__mkCapExt) return;
  window.__mkCapExt = true;

  const KEY = '__mikveh_capture_log', TAGKEY = '__mikveh_capture_tag', MAXN = 900;
  const SENS = /password|passwd|pwd|personalId|idNumber|^tz$|zeout|token|authorization|cardSerial|faceImage|creditCard|cardNumber|cvv|cvc|tokef|lastNum|phone|mobile|email|mail$|paymentResponse/i;
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
  function parse(t) {
    if (t == null || t === '') return t == null ? null : '';
    try { return clean(JSON.parse(t)); } catch (e) { return String(t).slice(0, MAXSTR); }
  }
  function cleanUrl(u) {
    try {
      const x = new URL(u, location.href);
      for (const k of [...x.searchParams.keys()]) if (SENS.test(k)) x.searchParams.set(k, '[הוסתר]');
      return x.toString();
    } catch (e) { return String(u); }
  }

  let full = false;
  function add(method, url, body, status, resp) {
    let path = '';
    try { path = new URL(url, location.href).pathname; } catch (e) { path = String(url); }
    if (/\.(js|css|png|jpe?g|gif|svg|woff2?|ttf|ico|map|html|json)$/i.test(path)) return;
    if (/\/Account\/?$/i.test(path)) return;
    if (HIDE_RESP.test(path)) resp = '"[הוסתר]"';
    const log = ls.get(KEY, []);
    if (log.length >= MAXN) { full = true; refresh(); return; }
    log.push({
      n: log.length + 1,
      time: new Date().toLocaleTimeString('he-IL'),
      tab: TAB,
      screen: location.hash || location.pathname,
      tag: ls.get(TAGKEY, ''),
      method: String(method || 'GET').toUpperCase(),
      url: cleanUrl(url),
      status: status,
      body: typeof body === 'string' ? parse(body) : (body ? '[גוף שאינו טקסט]' : null),
      response: parse(resp)
    });
    if (!ls.set(KEY, log)) full = true;
    refresh();
  }

  // XHR
  const XO = XMLHttpRequest.prototype.open, XS = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__mk = { m: m, u: u }; return XO.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) {
    const x = this;
    if (x.__mk) x.addEventListener('loadend', () => {
      let r;
      try {
        r = (x.responseType === '' || x.responseType === 'text') ? x.responseText
          : x.responseType === 'json' ? JSON.stringify(x.response) : '[' + x.responseType + ']';
      } catch (e) { r = null; }
      try { add(x.__mk.m, x.__mk.u, b, x.status, r); } catch (e) {}
    });
    return XS.apply(this, arguments);
  };

  // fetch
  const F = window.fetch;
  window.fetch = async function (input, init) {
    const res = await F.apply(this, arguments);
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || String(input);
      const m = (init && init.method) || (input && input.method) || 'GET';
      const b = init && init.body;
      res.clone().text().then(t => add(m, url, b, res.status, t)).catch(() => {});
    } catch (e) {}
    return res;
  };

  // חלון קטן — רק בחלון הראשי (לא בתוך מסגרות)
  let cnt, warn, tagIn;
  function refresh() {
    if (!cnt) return;
    cnt.textContent = ls.get(KEY, []).length;
    warn.style.display = full ? 'block' : 'none';
    if (document.activeElement !== tagIn) tagIn.value = ls.get(TAGKEY, '');
  }
  function panel() {
    if (window.top !== window || !document.body) return;
    const box = document.createElement('div');
    box.dir = 'rtl';
    box.style.cssText = 'position:fixed;bottom:16px;left:16px;z-index:2147483647;background:#fff;color:#111;border:2px solid #d93025;border-radius:10px;padding:10px 12px;font:14px Arial,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.25);width:270px';
    box.innerHTML =
      '<div style="font-weight:bold;margin-bottom:6px">🔴 מקליט המקווה <span style="font-weight:normal;color:#666">(כל הכרטיסיות)</span></div>' +
      '<div style="margin-bottom:4px">מה אני עושה עכשיו:</div>' +
      '<input id="mkTag" placeholder="למשל: שילמתי 10 ש&quot;ח במזומן" style="width:100%;box-sizing:border-box;padding:4px;margin-bottom:6px">' +
      '<div style="margin-bottom:6px">נרשמו: <b id="mkCnt">0</b> בקשות</div>' +
      '<div id="mkWarn" style="display:none;color:#d93025;margin-bottom:6px">הרשימה מלאה — הורד קובץ ולחץ "נקה"</div>' +
      '<button id="mkDl" style="padding:5px 10px;margin-left:4px">⬇ הורד קובץ</button>' +
      '<button id="mkClr" style="padding:5px 10px;margin-left:4px">נקה</button>' +
      '<button id="mkMin" style="padding:5px 10px">_</button>';
    document.body.appendChild(box);
    cnt = box.querySelector('#mkCnt'); warn = box.querySelector('#mkWarn'); tagIn = box.querySelector('#mkTag');
    tagIn.addEventListener('input', e => ls.set(TAGKEY, e.target.value.trim()));
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
      const blob = new Blob([JSON.stringify({ at: d.toISOString(), requests: ls.get(KEY, []) }, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
    };
    window.addEventListener('storage', e => { if (e.key === KEY || e.key === TAGKEY) refresh(); });
    refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', panel); else panel();
})();
