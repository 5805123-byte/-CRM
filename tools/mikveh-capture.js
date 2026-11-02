// מקליט בקשות — מסך הניהול של המקווה (prod.מקווה.com/adminUi)
// מדביקים בקונסול (F12 → Console) אחרי הכניסה למסך הניהול. מופיע חלון קטן בפינה.
// מקליט כל קריאה של המסך לשרת: כתובת, שיטה, גוף, ודוגמה מהתשובה (עד 3 רשומות מכל רשימה).
// מוסתרים אוטומטית: טוקן, סיסמה, מספר זהות, טלפון, מייל, פרטי כרטיס, תמונות פנים. הכניסה (Account) לא נרשמת בכלל.
// לא שולח שום דבר לשום מקום — רק מוריד קובץ JSON למחשב.
(() => {
  if (window.__mkCap) { window.__mkCap.style.display = 'block'; return; }

  const LOG = [];
  let tag = '';
  const SENS = /password|passwd|pwd|personalId|idNumber|^tz$|token|authorization|cardSerial|faceImage|creditCard|cardNumber|cvv|cvc|phone|mobile|email/i;
  const MAXARR = 3, MAXSTR = 300;

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
    if (t == null) return null;
    try { return clean(JSON.parse(t)); } catch (e) { return String(t).slice(0, MAXSTR); }
  }
  function cleanUrl(u) {
    try {
      const x = new URL(u, location.href);
      for (const k of [...x.searchParams.keys()]) if (SENS.test(k)) x.searchParams.set(k, '[הוסתר]');
      return x.toString();
    } catch (e) { return String(u); }
  }

  function add(method, url, body, status, resp) {
    let path = '';
    try { path = new URL(url, location.href).pathname; } catch (e) { path = String(url); }
    if (/\.(js|css|png|jpe?g|gif|svg|woff2?|ttf|ico|map|html)$/i.test(path)) return;
    if (/\/Account\/?$/i.test(path)) return; // הכניסה עצמה — לא נרשמת
    LOG.push({
      n: LOG.length + 1,
      time: new Date().toLocaleTimeString('he-IL'),
      tag: tag,
      method: String(method || 'GET').toUpperCase(),
      url: cleanUrl(url),
      status: status,
      body: typeof body === 'string' ? parse(body) : (body ? '[גוף שאינו טקסט]' : null),
      response: parse(resp)
    });
    cnt.textContent = LOG.length;
  }

  // XHR (המסך שלהם בנוי ב-Angular — עובד דרך XHR)
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
      add(x.__mk.m, x.__mk.u, b, x.status, r);
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

  // חלון קטן
  const box = document.createElement('div');
  box.dir = 'rtl';
  box.style.cssText = 'position:fixed;bottom:16px;left:16px;z-index:2147483647;background:#fff;color:#111;border:2px solid #1a73e8;border-radius:10px;padding:10px 12px;font:14px Arial,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.25);width:260px';
  box.innerHTML =
    '<div style="font-weight:bold;margin-bottom:6px">🔴 מקליט בקשות המקווה</div>' +
    '<div style="margin-bottom:4px">מה אני בודק עכשיו:</div>' +
    '<input id="mkTag" placeholder="למשל: תשלומים של לקוח כהן" style="width:100%;box-sizing:border-box;padding:4px;margin-bottom:6px">' +
    '<div style="margin-bottom:8px">נרשמו: <b id="mkCnt">0</b> בקשות</div>' +
    '<button id="mkDl" style="padding:5px 10px;margin-left:4px">⬇ הורד קובץ</button>' +
    '<button id="mkClr" style="padding:5px 10px;margin-left:4px">נקה</button>' +
    '<button id="mkHide" style="padding:5px 10px">הסתר</button>';
  document.body.appendChild(box);
  window.__mkCap = box;
  const cnt = box.querySelector('#mkCnt');
  box.querySelector('#mkTag').addEventListener('input', e => { tag = e.target.value.trim(); });
  box.querySelector('#mkClr').onclick = () => { LOG.length = 0; cnt.textContent = '0'; };
  box.querySelector('#mkHide').onclick = () => { box.style.display = 'none'; };
  box.querySelector('#mkDl').onclick = () => {
    const d = new Date(), p = n => String(n).padStart(2, '0');
    const name = 'mikveh-capture-' + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '-' + p(d.getHours()) + p(d.getMinutes()) + '.json';
    const blob = new Blob([JSON.stringify({ page: location.href, at: d.toISOString(), requests: LOG }, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  };
  console.log('%cמקליט המקווה פועל — אל תרענן את הדף', 'color:#1a73e8;font-weight:bold');
})();
