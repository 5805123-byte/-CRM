# -*- coding: utf-8 -*-
"""חיבור למערכת המקווה (prod.מקווה.com — המערכת של מקווה לייביש עוזר, מועדון 2087).

מאיר: "צריך לחבר את מערכת המקווה". הכניסה: POST /Account עם שם משתמש, סיסמה ומספר
מועדון → טוקן (Bearer) שתקף כיום. כל שאר הבקשות נשלחות עם הטוקן. כשהוא פג (או חוזר 401)
נכנסים מחדש לבד.

הפרטים לחיבור — ב-Render בלבד (לא בקוד, לא בקובץ ולא בהודעות):
    MIKVEH_USER   שם המשתמש (yemot)
    MIKVEH_PASS   הסיסמה
אופציונלי:
    MIKVEH_CLUB   מספר המועדון (ברירת מחדל 2087)
    MIKVEH_BASE   כתובת אחרת
"""
import datetime
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PROD = 'https://prod.xn--8dbba8a7b.com/'          # prod.מקווה.com
CLUB_DEFAULT = '2087'
UA = 'KollelChatzosCRM/1.0 (+mikveh)'
LAST = {'at': '', 'ok': None, 'error': '', 'method': ''}
_TOK = {'token': '', 'exp': 0.0, 'club_id': ''}
_LOCK = threading.Lock()


def _env(k):
    return (os.environ.get(k) or '').strip()


def configured():
    return bool(_env('MIKVEH_USER') and _env('MIKVEH_PASS'))


def base():
    b = _env('MIKVEH_BASE') or PROD
    return b if b.endswith('/') else b + '/'


def club():
    return _env('MIKVEH_CLUB') or CLUB_DEFAULT


def _note(ok, err, method):
    LAST.update(at=time.strftime('%Y-%m-%d %H:%M'), ok=ok, error=err, method=method)


def _http(method, path, body=None, query=None, token='', timeout=45):
    """בקשה אחת בלי טיפול בטוקן. מחזיר (קוד, JSON או טקסט)."""
    url = base() + path.lstrip('/')
    if query:
        url += '?' + urllib.parse.urlencode({k: v for k, v in query.items() if v not in (None, '')})
    data = json.dumps(body).encode('utf-8') if body is not None else None
    hdr = {'Accept': 'application/json, text/plain, */*', 'User-Agent': UA}
    if data is not None:
        hdr['Content-Type'] = 'application/json'
    if token:
        hdr['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, raw = r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return 0, str(e)
    try:
        out = json.loads(raw) if raw.strip() else {}
    except ValueError:
        out = raw
    return code, out


def _exp_ts(res):
    """מתי הטוקן פג — expiredTime מהתשובה (UTC), ואם אין — 12 שעות."""
    s = str((res or {}).get('expiredTime') or '')[:19]
    try:
        return datetime.datetime.strptime(s, '%Y-%m-%dT%H:%M:%S').replace(
            tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return time.time() + 12 * 3600


def login(force=False):
    """טוקן תקף. נכנס מחדש רק כשצריך (חצי שעה לפני שפג)."""
    with _LOCK:
        if not force and _TOK['token'] and _TOK['exp'] - time.time() > 1800:
            return _TOK['token']
        if not configured():
            raise RuntimeError('המקווה לא מוגדר — חסרים MIKVEH_USER ו-MIKVEH_PASS ב-Render')
        code, res = _http('POST', 'Account', {'username': _env('MIKVEH_USER'), 'password': _env('MIKVEH_PASS'),
                                              'externalClubId': club()})
        tok = res.get('token') if isinstance(res, dict) else ''
        if code != 200 or not tok:
            err = 'כניסה נכשלה (%s): %s' % (code, (res.get('message') or res.get('title') or '')
                                             if isinstance(res, dict) else str(res)[:160])
            _note(False, err, 'Account')
            raise RuntimeError(err)
        _TOK.update(token=tok, exp=_exp_ts(res), club_id=res.get('clubId') or '')
        return tok


def call(method, path, body=None, query=None, timeout=45):
    """בקשה עם הטוקן. 401 → כניסה מחדש ועוד ניסיון אחד. השגיאה נשמרת ב-LAST למסך הבדיקה."""
    try:
        tok = login()
    except RuntimeError as e:
        return 0, str(e)
    code, out = _http(method, path, body, query, tok, timeout)
    if code == 401:
        try:
            tok = login(force=True)
        except RuntimeError as e:
            return 0, str(e)
        code, out = _http(method, path, body, query, tok, timeout)
    ok = 200 <= code < 300
    err = ''
    if not ok:
        err = (out.get('message') or out.get('title') or '') if isinstance(out, dict) else str(out)[:200]
        err = '%s %s' % (code, err)
    _note(ok, err, path)
    return code, out


def get(path, query=None):
    code, out = call('GET', path, query=query)
    if code != 200:
        raise RuntimeError('המקווה %s: %s' % (path, LAST.get('error') or code))
    return out


# ---------- משיכה ----------

def current_club():
    """פרטי המועדון (שם, כתובת, רישיונות, מסוף הסליקה)."""
    return get('Club/GetCurrent')


def check():
    """לבדיקת המערכת: (תקין?, הסבר)."""
    if not configured():
        return False, 'לא מוגדר — חסרים MIKVEH_USER ו-MIKVEH_PASS ב-Render'
    try:
        c = current_club()
    except Exception as e:
        return False, str(e)[:200]
    return True, 'מחובר · %s (מועדון %s) · %s רישיונות' % (
        (c.get('name') or '').strip(), c.get('externalClubId') or club(), c.get('licancesAmount') or 0)


# ---------- פעולות מתוך ה-CRM (בלי סנכרון — הכל חי מול המקווה) ----------
# מאיר: "אני לא רוצה לסנכרן, אלא לבצע פעולות דרך ה-CRM, למשל עדכון קבוצה, ולשלוח לו הודעה
# במיידי דרך הטלפון שזה עודכן". שום דבר מהמקווה לא נשמר אצלנו; מספרי זהות / סיסמאות
# של הלקוחות (password, personalId) לא יוצאים מהשרת אל המסך.
_HIDE = ('password', 'personalId', 'cardSerial', 'faceImages')


def _items(res):
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        for k in ('items', 'data', 'result', 'clients', 'list'):
            if isinstance(res.get(k), list):
                return res[k]
    return []


_GR = {'at': 0.0, 'rows': None}


def groups(fresh=False):
    """הקבוצות הפעילות (בלי מחוקות), לפי השם. זיכרון של 10 דקות — הן כמעט לא משתנות."""
    if not fresh and _GR['rows'] is not None and time.time() - _GR['at'] < 600:
        return _GR['rows']
    out = []
    hid = set()
    for g in _items(get('Group')):
        if g.get('isDeleted'):
            continue
        # מאיר: "תסתיר מהמערכת את משתמש מזדמן ואת קבוצת מזדמן" — הקבוצה הכללית של המקווה (type=2)
        if g.get('type') == 2 or (g.get('name') or '').strip().startswith('['):
            hid.add(g.get('id'))
            _GR.setdefault('hidden_names', {})[g.get('id')] = (g.get('name') or '').strip()
            continue
        out.append({'id': g.get('id'), 'name': (g.get('name') or '').strip(), 'color': g.get('color') or '',
                    'price': (g.get('subscriptionPrice') or 0) / 100.0 if g.get('subscriptionPrice') is not None else None})
    out.sort(key=lambda g: g['name'])
    _GR.update(at=time.time(), rows=out, hidden=hid)
    return out


def hidden_groups():
    if _GR['rows'] is None:
        groups()
    return _GR.get('hidden') or set()


def visible(c):
    """לא מציגים את "[משתמש מזדמן]" ואת מי שבקבוצת המזדמנים הכללית."""
    return c.get('groupId') not in hidden_groups() and not (c.get('firstName') or '').strip().startswith('[')


def slim(c):
    """לקוח בשביל המסך — בלי הפרטים הרגישים."""
    return {'id': c.get('id'), 'code': c.get('clientCode'), 'first': (c.get('firstName') or '').strip(),
            'last': (c.get('lastName') or '').strip(), 'phone': (c.get('phone') or '').strip(),
            'email': c.get('email') or '', 'group': c.get('groupId') or '', 'type': c.get('type'),
            'parent': c.get('parentId') or '', 'sub_end': c.get('subscriptionEndDate') or '',
            'sub_start': c.get('subscriptionStartDate') or '', 'last_in': c.get('lastEntrance') or '',
            'lic_exp': c.get('licenceExp') or '', 'balance': c.get('balance'), 'last_balance': c.get('lastBalance'),
            'temp_balance': c.get('tempBalance'), 'finger': bool(c.get('hasFingerPrint')),
            'pay_method': bool(c.get('hasPaymentMethod')), 'blocked': bool(c.get('isBlocked')),
            'block_reason': c.get('blockReason') or '', 'remark': c.get('remark') or '',
            'message': c.get('message') or '', 'sons': len(c.get('sons') or []),
            # מחיר אישי ללקוח, אם המקווה מחזיר כזה (באגורות, כמו מחיר הקבוצה). בלי — מחיר הקבוצה
            'price': next(((c.get(k) or 0) / 100.0 for k in ('subscriptionPrice', 'specialPrice', 'customPrice', 'price')
                           if isinstance(c.get(k), (int, float)) and c.get(k)), None)}


_CL = {'at': 0.0, 'rows': None}


def clients(fresh=False):
    """כל הלקוחות (GET /Client). זיכרון של 2 דקות בלבד — לא נשמר בבסיס הנתונים."""
    if not fresh and _CL['rows'] is not None and time.time() - _CL['at'] < 120:
        return _CL['rows']
    rows = [c for c in _items(get('Client')) if not c.get('isDeleted')]
    _CL.update(at=time.time(), rows=rows)
    return rows


# מאיר: "שמעבירים קבוצה ללקוח לוקח זמן עד שהשרת עונה… למה באמת לוקח לו הרבה זמן?" — כל העברה
# הייתה: כל הקבוצות + ניסיון ללקוח בודד + (כשאין) כל רשימת הלקוחות + העדכון, אחד אחרי השני.
# עכשיו: הקבוצות בזיכרון; הלקוח נטען כבר כשפותחים את הכרטיס (prefetch) ונשמר דקה וחצי;
# אם אין במקווה קריאה ללקוח בודד — זוכרים את זה ולא מנסים שוב. TIMES — כמה לקח כל שלב.
_ONE = {}
TIMES = {}


def client(cid, max_age=0):
    """הלקוח המלא כמו שהמקווה מחזיר (כולל הבנים) — בשביל העדכון.
    מאיר: "באתר של המקווה… אחרי זה הוא טוען את הלקוח" — GET /GetClientFull/{id} (זו הקריאה של
    המסך שלהם; ‏Client/{id} לא קיימת אצלם, ולכן כל העברה חיכתה לה ואז משכה את כל הרשימה → 502)."""
    hit = _ONE.get(str(cid))
    if max_age and hit and time.time() - hit[0] < max_age:
        return dict(hit[1])
    code, res = call('GET', 'GetClientFull/%s' % cid, timeout=20)
    if code == 200 and isinstance(res, dict) and res.get('id'):
        _ONE[str(cid)] = (time.time(), res)
        return dict(res)
    # גיבוי בלבד — מהרשימה. חסרים בה clubId / externalClubId, ו-createdAt הוא שעת הבקשה;
    # מתקנים כדי לא לדרוס במקווה מועדון / תאריך פתיחה.
    for c in clients(fresh=False):
        if str(c.get('id')) == str(cid):
            c = dict(c)
            c.pop('hasPaymentMethod', None)
            c.pop('createdAt', None)
            c['clubId'] = c.get('clubId') or _TOK.get('club_id') or None
            c['externalClubId'] = c.get('externalClubId') or int(club())
            return c
    raise RuntimeError('הלקוח לא נמצא במקווה')


def update_client(cid, changes):
    """PATCH /Client/{id} — כמו המסך של המקווה: שולחים את כל הלקוח, עם השינוי בלבד."""
    t0 = time.time()
    obj = dict(client(cid, max_age=90))
    t1 = time.time()
    obj.update(changes)
    obj.setdefault('faceImages', [])          # כמו המסך של המקווה
    code, res = call('PATCH', 'Client/%s' % cid, body=obj, timeout=30)
    t2 = time.time()
    TIMES.update(at=time.strftime('%Y-%m-%d %H:%M:%S'), load_ms=int((t1 - t0) * 1000), patch_ms=int((t2 - t1) * 1000))
    if code != 200:
        raise RuntimeError('העדכון במקווה נכשל: %s' % (LAST.get('error') or code))
    _ONE.pop(str(cid), None)
    if isinstance(res, dict) and _CL['rows'] is not None:
        # הרשימה בזיכרון מתעדכנת במקום — בלי למשוך שוב את כל הלקוחות
        for i, c in enumerate(_CL['rows']):
            if str(c.get('id')) == str(cid):
                _CL['rows'][i] = dict(c, **{k: v for k, v in res.items() if k in ('groupId', 'updatedAt')})
    return res if isinstance(res, dict) else obj


def balance(cid):
    """היתרה של הלקוח — ישירות מ-GetClientFull (בלי הגיבוי שמושך את כל הרשימה — זה מה שלקח דקה):
    balance, ואם אין — lastBalance (כמו הקוביה במסך). באגורות."""
    _ONE.pop(str(cid), None)
    code, c = call('GET', 'GetClientFull/%s' % cid, timeout=15)
    if code != 200 or not isinstance(c, dict):
        raise RuntimeError('קריאת הלקוח מהמקווה נכשלה: %s' % (LAST.get('error') or code))
    _ONE[str(cid)] = (time.time(), c)
    for k in ('balance', 'lastBalance'):
        v = c.get(k)
        if v is not None:
            try:
                return int(round(float(v)))
            except (TypeError, ValueError):
                pass
    return 0


def add_credit(cid, amount):
    """מה שכפתור "הוספת יתרה" / "הפחתת יתרה" במסך המקווה עושה (addCreditById → POST addCredit/{id} {amount}).
    הסכום באגורות (נבדק: 15 → ₪0.15). סכום שלילי = הפחתה."""
    code, res = call('POST', 'addCredit/%s' % cid, body={'amount': amount}, timeout=30)
    if not (200 <= code < 300):
        raise RuntimeError('עדכון היתרה במקווה נכשל: %s' % (LAST.get('error') or code))
    _ONE.pop(str(cid), None)
    return res


def ui_service_urls():
    """אבחון: הבסיס (this.url) של כל שירות במסך הניהול, עם שמות הפונקציות שלו — כדי לדעת תחת איזה נתיב
    יושבות קריאות כמו getBalance. קריאה בלבד של קבצי ה-JS."""
    root = base() + 'adminUi/'
    req = urllib.request.Request(root, headers={'User-Agent': UA})
    html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace')
    out = []
    for src in re.findall(r'<script[^>]+src="([^"]+\.js)"', html)[:12]:
        try:
            js = urllib.request.urlopen(urllib.request.Request(urllib.parse.urljoin(root, src), headers={'User-Agent': UA}), timeout=30).read(6_000_000).decode('utf-8', 'replace')
        except Exception:
            continue
        for m in re.finditer(r'this\.url\s*=\s*(`[^`]{1,200}`|[^,;}]{1,160})', js):
            seg = js[m.end():m.end() + 2500]
            fns = re.findall(r'(\w+)\([^)]{0,40}\)\{return this\.http\.(?:get|post|put|patch|delete)\(`\$\{this\.url\}/([^`]+)`', seg)
            if fns:
                out.append('%s\n    ' % m.group(1).strip() + '\n    '.join('%s → %s' % (f, p) for f, p in fns[:40]))
    for m in re.finditer(r'(apiUrl|baseUrl|serverUrl|apiBase)\s*[:=]\s*["\'`]([^"\'`]{4,160})', html):
        out.append('%s = %s' % (m.group(1), m.group(2)))
    return out


def set_group(cid, group_id):
    return update_client(cid, {'groupId': group_id})


# ---------- מחירים ----------
# מאיר: "שאם אני לוחץ על הקוביה של מחיר שאוכל לשנות את המחיר… ושמכאן אוכל לשנות מחירים".
# המחיר במקווה שמור בקבוצה (subscriptionPrice, באגורות). אם ללקוח יש שדה מחיר משלו — גם אותו.
_PRICE_RE = re.compile(r'price|discount|cost|fee|amount', re.I)
_NOT_PRICE = ('balance', 'lastBalance', 'tempBalance')


def price_fields(cid):
    """שדות מחיר שיש ללקוח עצמו במקווה (מספרים בלבד) — כדי לדעת אם אפשר מחיר אישי."""
    c = client(cid, max_age=60)
    return {k: v for k, v in c.items() if _PRICE_RE.search(k) and k not in _NOT_PRICE
            and (v is None or isinstance(v, (int, float))) and not isinstance(v, bool)}


# ---------- חידוש אוטומטי ----------
# מאיר: "איך אני מבטל הוראת קבע של לקוח מקווה שרוצה לבטל — שלא יהיה חידוש מנוי אוטומטי. יש את זה באתר של
# המקווה". השם המדויק של השדה אצלם לא ידוע מראש — מחפשים שדה כן/לא של חידוש / חיוב אוטומטי אצל הלקוח
_RENEW_RE = re.compile(r'renew|recurr|autoCharge|autoPay|auto_?pay|autoRenew|standing|isAuto|automatic|subscriptionAuto|charge', re.I)

# מאיר (צילום מהאתר של המקווה, "פעולות אוטומטיות"): ☑ חידוש רישיון · ☑ חידוש תוקף מנוי · ☐ הוספת יתרת פעימות —
# "אני רוצה שזה יהיה פה בדיוק כמו באתר שלהם". מחפשים לכל אחת את השדה כן/לא שלה אצל הלקוח (גם בתוך אובייקט פנימי)
AUTO_ACTIONS = (
    ('licence', 'חידוש רישיון', re.compile(r'licen|licanc|lisen|lics', re.I)),
    ('sub', 'חידוש תוקף מנוי', re.compile(r'subscri|valid|expir|member|tokef', re.I)),
    ('balance', 'הוספת יתרת פעימות', re.compile(r'balanc|pulse|beat|entr|punch|ticket|credit|peim|amount', re.I)),
)
_AUTO_RE = re.compile(r'auto|renew|recur|refill|top_?up|extend|add', re.I)


def _flat_bools(c):
    """כל שדות הכן/לא של הלקוח (כולל 0/1), גם רמה אחת פנימה: {'a': v, 'obj.b': v}"""
    out = {}
    for k, v in c.items():
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, bool):
                    out['%s.%s' % (k, k2)] = v2
    return out


def _key_list(c):
    """שמות השדות בלבד (בלי ערכים) — כדי שאפשר יהיה לחבר שדה שלא זוהה"""
    out = []
    for k, v in c.items():
        t = type(v).__name__
        out.append('%s:%s' % (k, t))
        if isinstance(v, dict):
            out += ['%s.%s:%s' % (k, k2, type(v2).__name__) for k2, v2 in v.items()]
        elif isinstance(v, list) and v and not isinstance(v[0], dict) and re.search(r'auto|action|renew', k, re.I):
            out.append('%s=[%s]' % (k, ','.join(str(x)[:12] for x in v[:6])))
    return out


def auto_actions(cid, fresh=False):
    c = client(cid, max_age=0 if fresh else 30)
    bools = _flat_bools(c)
    cand = {k: v for k, v in bools.items() if _AUTO_RE.search(k)}
    acts, used = [], set()
    for key, label, rx in AUTO_ACTIONS:
        hit = next((k for k in cand if k not in used and rx.search(k)), None)
        if not hit and key == 'sub':
            # "autoRenew" / "isAutoRenew" בלי מילה נוספת — זה חידוש המנוי
            hit = next((k for k in cand if k not in used and re.fullmatch(r'(is)?_?auto_?renew(al)?(enabled)?', k.split('.')[-1], re.I)), None)
        if hit:
            used.add(hit)
        acts.append({'key': key, 'label': label, 'field': hit or '', 'on': bool(bools[hit]) if hit else None})
    return acts, _key_list(c)


def set_auto_actions(cid, want):
    """want: {'licence': True, ...} — שומרים את כל השינויים בבת אחת, כמו "שמור" באתר שלהם"""
    acts, _ = auto_actions(cid)
    c = client(cid, max_age=30)
    changes = {}
    for a in acts:
        if a['key'] not in want or not a['field'] or bool(want[a['key']]) == a['on']:
            continue
        f = a['field']
        if '.' in f:
            top, sub = f.split('.', 1)
            d = dict(changes.get(top) or c.get(top) or {})
            d[sub] = bool(want[a['key']])
            changes[top] = d
        else:
            changes[f] = bool(want[a['key']])
    if changes:
        update_client(cid, changes)
    after, _ = auto_actions(cid, fresh=True)
    return acts, after


def renew_fields(cid):
    c = client(cid, max_age=30)
    hits = {k: v for k, v in c.items() if _RENEW_RE.search(k) and isinstance(v, bool)}
    bools = {k: v for k, v in c.items() if isinstance(v, bool)}
    return hits, bools


# ---------- תשלומים במקווה ----------
# מאיר: "כאן צריך להיות היסטוריה רק כמו שהוא מכניס למקווה דרך המכשיר, ורואים את זה במכשיר של המקווה —
# לא מנדרים פלוס" (בנדרים הופיעה הו"ק של חבר קהילה לבית הכנסת). התשלומים נלקחים רק ממערכת המקווה:
# קודם רשימות תשלומים בתוך הלקוח המלא, ואם אין — נתיבי קריאה (GET) של המקווה. הנתיב שעבד נזכר.
_PAY_KEY = re.compile(r'pay|purchas|transact|charg|receipt|order|invoice|deal|deposit|topup|load|history', re.I)
_PAY_PATHS = ('Client/GetClientHistory?clientId={id}', 'Client/GetClientHistory/{id}', 'Client/GetClientHistory?id={id}',
              'Payment/GetByClient/{id}', 'Payment/Client/{id}', 'Payment?clientId={id}', 'Payments?clientId={id}',
              'ClientPayment/{id}', 'GetClientPayments/{id}', 'Transaction?clientId={id}', 'Transaction/GetByClient/{id}',
              'ClientTransaction/{id}', 'Purchase?clientId={id}', 'Order?clientId={id}', 'Charge?clientId={id}',
              'Receipt?clientId={id}', 'Invoice?clientId={id}')
_PAY = {'path': None, 'bad': set()}


def _is_pay_row(d):
    if not isinstance(d, dict):
        return False
    ks = ' '.join(d.keys())
    return bool(re.search(r'amount|sum|price|total', ks, re.I) and re.search(r'date|time|createdAt|at\b', ks, re.I))


def _pay_norm(rows):
    out = []
    for d in rows:
        if not _is_pay_row(d):
            continue
        ak = next((k for k in d if re.search(r'^(amount|sum|total|price)$', k, re.I)), None) or \
            next((k for k in d if re.search(r'amount|sum|total|price', k, re.I) and isinstance(d[k], (int, float))), None)
        dk = next((k for k in d if re.search(r'^(date|paymentDate|transactionDate|createdAt|time)$', k, re.I)), None) or \
            next((k for k in d if re.search(r'date|time|createdAt', k, re.I) and d[k]), None)
        if not ak or not dk or not isinstance(d.get(ak), (int, float)):
            continue
        desc = next((str(d[k]) for k in d if re.search(r'descr|product|type|item|name|remark|reason|note', k, re.I)
                     and isinstance(d[k], str) and d[k].strip()), '')
        how = next((str(d[k]) for k in d if re.search(r'method|source|device|terminal|channel', k, re.I)
                    and isinstance(d[k], (str, int)) and str(d[k]).strip()), '')
        ok = next((d[k] for k in d if re.search(r'success|approved|isOk|status', k, re.I)), None)
        out.append({'iso': str(d[dk])[:10], 'time': str(d[dk])[11:16], 'amount': d[ak], 'desc': desc[:80], 'how': how[:40],
                    'failed': ok is False or (isinstance(ok, str) and re.search(r'fail|declin|error|reject', ok, re.I) is not None)})
    # המחירים במקווה שמורים באגורות — אם גם התשלומים (כל הסכומים שלמים וגדולים) — מחלקים ב-100
    am = sorted(abs(x['amount']) for x in out if x['amount'])
    if am and all(float(a).is_integer() for a in am) and am[len(am) // 2] >= 500:
        for x in out:
            x['amount'] = x['amount'] / 100.0
    out.sort(key=lambda x: (x['iso'], x['time']), reverse=True)
    return out


_DISC = {'at': 0.0, 'paths': [], 'files': [], 'error': ''}
_PAYWORD = re.compile(r'pay|transact|charg|receipt|deal|invoice|purchas|order|credit|deposit|topup|history|financ|account(?!/login)', re.I)


def grep_ui(pattern, ctx=140, limit=80):
    """אבחון: קטעים מקוד מסך הניהול של המקווה (קבצי ה-JS הציבוריים) שמכילים ביטוי — כדי לראות איך
    המסך שלהם מעדכן שדה (למשל יתרה). קריאה בלבד."""
    root = base() + 'adminUi/'
    rx = re.compile(pattern, re.I)
    out, files = [], []
    req = urllib.request.Request(root, headers={'User-Agent': UA})
    html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace')
    srcs = re.findall(r'<script[^>]+src="([^"]+\.js)"', html)
    for src in srcs[:12]:
        u = urllib.parse.urljoin(root, src)
        try:
            js = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30).read(6_000_000).decode('utf-8', 'replace')
        except Exception as e:
            files.append('%s: %s' % (src, e)); continue
        files.append('%s (%d KB)' % (src.rsplit('/', 1)[-1], len(js) // 1024))
        for m in rx.finditer(js):
            a, b = max(0, m.start() - ctx), min(len(js), m.end() + ctx)
            out.append(js[a:b].replace('\n', ' '))
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    paths = sorted({m.group(0) for o in out for m in re.finditer(r'[A-Za-z]+(?:/[A-Za-z{}]+){1,3}', o) if rx.search(m.group(0))})
    return {'files': files, 'paths': paths, 'hits': out}


def ui_endpoints():
    """אבחון: כל הקריאות של מסך הניהול לשרת — שם הפונקציה, השיטה והנתיב. קריאה בלבד של קבצי ה-JS."""
    root = base() + 'adminUi/'
    req = urllib.request.Request(root, headers={'User-Agent': UA})
    html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace')
    out = []
    for src in re.findall(r'<script[^>]+src="([^"]+\.js)"', html)[:12]:
        try:
            js = urllib.request.urlopen(urllib.request.Request(urllib.parse.urljoin(root, src), headers={'User-Agent': UA}), timeout=30).read(6_000_000).decode('utf-8', 'replace')
        except Exception:
            continue
        for m in re.finditer(r'(\w+)\(([^)]{0,40})\)\{return this\.http\.(get|post|put|patch|delete)\(`\$\{this\.url\}/([^`]+)`(,[^)]{0,60})?\)', js):
            out.append('%s %s  ←  %s(%s)%s' % (m.group(3).upper(), m.group(4), m.group(1), m.group(2), (' body:' + m.group(5)[1:]) if m.group(5) else ''))
    return sorted(set(out))


def ui_context(name, back=1800, fwd=400, limit=6):
    """אבחון: לכל מופע של שם (למשל getBalanceById) — הקטע מתחילת ה-class / constructor שלפניו ועד אחריו,
    כדי לראות מה הבסיס (this.url) של השירות הזה. קריאה בלבד של קבצי ה-JS."""
    root = base() + 'adminUi/'
    req = urllib.request.Request(root, headers={'User-Agent': UA})
    html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace')
    out = []
    for src in re.findall(r'<script[^>]+src="([^"]+\.js)"', html)[:12]:
        try:
            js = urllib.request.urlopen(urllib.request.Request(urllib.parse.urljoin(root, src), headers={'User-Agent': UA}), timeout=30).read(6_000_000).decode('utf-8', 'replace')
        except Exception:
            continue
        for m in re.finditer(re.escape(name), js):
            a = max(0, m.start() - back)
            seg = js[a:m.start()]
            k = max(seg.rfind('constructor('), seg.rfind('class '))
            if k > 0:
                a += k
            out.append('%s @%d:\n%s' % (src.rsplit('/', 1)[-1], m.start(), js[a:m.end() + fwd]))
            if len(out) >= limit:
                return out
    return out or ['לא נמצא: ' + name]


def discover_paths(force=False):
    """נתיבי ה-API שמסך הניהול של המקווה עצמו קורא להם (מתוך קבצי ה-JS שלו) — שקשורים לתשלומים.
    רק קריאה של קבצי האתר הציבוריים; נשמר בזיכרון ליום."""
    if not force and _DISC['paths'] and time.time() - _DISC['at'] < 86400:
        return _DISC['paths']
    root = base() + 'adminUi/'
    out, allp, files, err = set(), set(), [], ''
    try:
        req = urllib.request.Request(root, headers={'User-Agent': UA})
        html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace')
        srcs = re.findall(r'<script[^>]+src="([^"]+\.js)"', html)
        for src in srcs[:12]:
            u = urllib.parse.urljoin(root, src)
            try:
                js = urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=30).read(6_000_000).decode('utf-8', 'replace')
            except Exception:
                continue
            files.append(src.rsplit('/', 1)[-1])
            # גם קבצי chunk שנטענים בהמשך (lazy) — שמות כמו 123.abcdef.js
            for m_ in re.finditer(r'["\'`}]/?((?:api/)?[A-Z][A-Za-z]{2,}(?:/[A-Za-z]{2,}){0,3}/?)(?=["\'`$?])', js):
                pth = m_.group(1)
                # רק נתיבי קריאה — בלי שום נתיב שנשמע כמו פעולה (חיוב, ביטול, מחיקה, יצירה, שליחה, פתיחת דלת)
                if len(pth) < 80 and not re.search(
                        r'charge|refund|cancel|delete|remove|create|add|update|save|send|set|pay(?!ment)|execute|approve|token|open|unlock|login|logout|reset', pth, re.I):
                    allp.add(pth)
                    if _PAYWORD.search(pth):
                        out.add(pth)
    except Exception as e:
        err = str(e)[:200]
    _DISC.update(at=time.time(), paths=sorted(out)[:40], all=sorted(allp), files=files, error=err)
    return _DISC['paths']


# ---------- יומן כניסות (היסטוריה של היום) ----------
# מאיר: "אין לך את הנתונים של כל משתמש מזדמן? יש את זה במערכת, בהיסטוריה של אותו יום" — הנתיב של ההיסטוריה
# מתוך האתר של המקווה, ונזכר אחרי שנמצא. רק GET.
# מאיר: "איך אתה לא רואה במקווה את יומן פעילות" — גם activity / journal / audit
_ENTR_WORD = re.compile(r'activ|journal|audit|entr|enter|histor|visit|log(?!in|out)|report|daily|attend|access|door|gate|pass(?!word)|movement|event', re.I)
_ENTR_GUESS = ('ActivityLog', 'Activity', 'ActivityLog/GetAll', 'Activities', 'ClientActivity', 'Log', 'Logs', 'EntranceLog',
               'Entrance', 'Entrances', 'History', 'Journal')
_ENTR = {'pat': None, 'tried': []}


def _entr_forms(path, day):
    d1 = (datetime.date.fromisoformat(day) + datetime.timedelta(days=1)).isoformat()
    p = path.rstrip('/')
    return [(p, {'date': day}), (p, {'fromDate': day, 'toDate': d1}), (p, {'from': day, 'to': d1}),
            (p, {'startDate': day, 'endDate': d1}), (p + '/' + day, None), (p, None)]


def _dt_of(v):
    try:
        return datetime.datetime.fromisoformat(str(v).replace('Z', '+00:00')[:32])
    except Exception:
        return None


def _entr_rows(res, day):
    rows = res if isinstance(res, list) else next((res[k] for k in ('items', 'data', 'result', 'list', 'entrances', 'history')
                                                    if isinstance(res, dict) and isinstance(res.get(k), list)), None)
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None
    tk = next((k for k in rows[0] if re.search(r'entr|date|time|created|at$', k, re.I) and _dt_of(rows[0].get(k))), None)
    if not tk:
        return None
    hit = [r for r in rows if str(_dt_of(r.get(tk)) or '')[:10] == day or str(r.get(tk) or '')[:10] == day]
    return (rows, tk) if hit else None


# ---------- יומן פעילויות (AttendanceLog/GetAttendanceLogs) ----------
# מאיר שלח צילום של "יומן פעילויות" במקווה (מסננים: לקוח, תאריכים, סוג פעולה, קבוצה, סכום, אמצעי תשלום) —
# הנתיב AttendanceLog/GetAttendanceLogs החזיר 405 ל-GET, כלומר זו בקשת POST עם גוף של מסננים (קריאה בלבד).
# צורת הגוף לא ידועה מראש — מנסים כמה צורות נפוצות, והצורה שעבדה נזכרת.
ATT_PATH = 'AttendanceLog/GetAttendanceLogs'
_ATT = {'tpl': None, 'tries': []}


def _att_bodies(d0, d1, cid=None):
    f, t = d0 + 'T00:00:00', d1 + 'T00:00:00'
    club_id = _TOK.get('club_id') or None
    base_ = {'clientId': cid} if cid else {}
    pg = {'page': 1, 'pageSize': 5000, 'pageNumber': 1, 'take': 5000, 'skip': 0}
    out = []
    for a, b in (('fromDate', 'toDate'), ('startDate', 'endDate'), ('dateFrom', 'dateTo'), ('from', 'to'), ('start', 'end')):
        out.append(dict(base_, **{a: f, b: t}, **pg))
    out.append(dict(base_, **{'dates': [f, t]}, **pg))
    out.append(dict(base_, **{'dateRange': {'from': f, 'to': t}}, **pg))
    if club_id:
        out = out[:2] + [dict(x, clubId=club_id) for x in out[:2]] + out[2:]
    return out


def _att_rows(res):
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        for k in ('items', 'data', 'result', 'list', 'logs', 'attendanceLogs', 'records', 'rows'):
            v = res.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                for k2 in ('items', 'data', 'list', 'records'):
                    if isinstance(v.get(k2), list):
                        return v[k2]
    return None


def attendance(d0, d1, cid=None):
    """שורות יומן הפעילויות בין d0 ל-d1 (YYYY-MM-DD, d1 לא כולל). מחזיר רשימה גולמית או None"""
    try:
        tok = login()
    except RuntimeError:
        return None
    if not _ATT['tpl'] and time.time() - (_ATT.get('fail_at') or 0) < 600:
        return None          # נוסה לפני פחות מ-10 דקות ולא עבד — לא מנסים שוב בכל כרטיס
    bodies = []
    if _ATT['tpl']:
        a, b, extra = _ATT['tpl']
        bodies.append(dict(extra, **({'clientId': cid} if cid else {}), **{a: d0 + 'T00:00:00', b: d1 + 'T00:00:00'}))
    bodies += _att_bodies(d0, d1, cid)
    tries = []
    for body in bodies:
        code, res = _http('POST', ATT_PATH, body, None, tok, 40)
        rows = _att_rows(res) if code == 200 else None
        tries.append({'body': {k: v for k, v in body.items() if k not in ('clientId',)}, 'code': code,
                      'resp': (json.dumps(res, ensure_ascii=False)[:300] if not isinstance(res, str) else res[:300]) if code != 200 or rows is None else '(%d שורות)' % len(rows)})
        if rows is not None:
            keys = list(body.keys())
            dk = [k for k in keys if isinstance(body[k], str) and body[k].endswith('T00:00:00')]
            if len(dk) == 2:
                _ATT['tpl'] = (dk[0], dk[1], {k: v for k, v in body.items() if k not in dk and k != 'clientId'})
            _ATT['tries'] = tries
            return rows
    _ATT['tries'] = tries
    _ATT['fail_at'] = time.time()
    return None


def _att_txt(r):
    """תיאור הפעולה של שורה ביומן (טקסט), גם אם הוא בתוך אובייקט"""
    parts = []
    for k, v in r.items():
        if re.search(r'action|type|descr|activ|operation|status|message|text|result', k, re.I):
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, dict):
                parts += [str(x) for x in v.values() if isinstance(x, str)]
    return ' '.join(parts)


def att_norm(r):
    """שורה ביומן → {'at', 'cid', 'name', 'group', 'gname', 'kind': entry/entry_fail/pay/other, 'amount', 'method', 'text'}"""
    at = None
    for k in r:
        if re.search(r'date|time|created', k, re.I):
            at = _dt_of(r.get(k))
            if at:
                break
    ck = next((k for k in r if re.fullmatch(r'client_?id', k, re.I)), None)
    cl = r.get('client') if isinstance(r.get('client'), dict) else {}
    cid = r.get(ck) if ck else cl.get('id')
    nm = next((str(r[k]) for k in r if re.search(r'client_?name|full_?name', k, re.I) and isinstance(r[k], str) and r[k].strip()), '') or \
        ' '.join(str(x.get(k) or '').strip() for x in (r, cl) for k in ('firstName', 'lastName') if x.get(k)).strip()
    grp = next((r[k] for k in r if re.fullmatch(r'group_?id', k, re.I)), None) or (cl.get('groupId') if cl else None)
    gnm = next((str(r[k]) for k in r if re.search(r'group_?name', k, re.I) and r.get(k)), '')
    if not gnm and isinstance(r.get('group'), dict):
        gnm = str(r['group'].get('name') or '')
    txt = _att_txt(r)
    amt = next((r[k] for k in r if re.search(r'amount|sum|price|total', k, re.I) and isinstance(r[k], (int, float)) and not isinstance(r[k], bool)), None)
    meth = next((str(r[k]) for k in r if re.search(r'payment_?(method|type)|method', k, re.I) and r.get(k) not in (None, '')), '')
    if re.search(r'כניס', txt) and re.search(r'נכשל|נדח|חסר|fail|denied', txt, re.I):
        kind = 'entry_fail'
    elif re.search(r'תשלום|payment|paid|charge', txt, re.I) or (amt and not re.search(r'כניסה מאושרת', txt)):
        kind = 'pay'
    elif re.search(r'כניס|entr|enter', txt, re.I):
        kind = 'entry'
    else:
        kind = 'other'
    return {'at': at, 'cid': cid, 'name': nm, 'group': grp, 'gname': gnm, 'kind': kind, 'amount': amt, 'method': meth, 'text': txt[:120]}


def entrances(day):
    """כל הכניסות של היום מהיומן של המקווה: [{'at': datetime, 'cid', 'name', 'group', 'casual', 'raw_keys'}] או None"""
    d1 = (datetime.date.fromisoformat(day) + datetime.timedelta(days=1)).isoformat()
    try:
        raw = attendance(day, d1)
    except Exception:
        raw = None
    if raw is not None:
        out = []
        for r in raw:
            n = att_norm(r)
            if n['kind'] != 'entry' or not n['at']:
                continue
            out.append({'at': n['at'], 'cid': n['cid'], 'name': n['name'], 'group': n['group'], 'gname': n['gname'],
                        'casual': n['name'].strip().startswith('[') or 'מזדמ' in n['name'] or 'מזדמ' in n['gname']})
        return {'rows': out, 'path': ATT_PATH, 'keys': sorted(raw[0].keys())[:30] if raw else []}
    try:
        tok = login()
    except RuntimeError:
        return None
    pats = ([_ENTR['pat']] if _ENTR['pat'] else [])
    if not pats:
        try:
            discover_paths()
        except Exception:
            pass
        found = [x for x in (_DISC.get('all') or []) if _ENTR_WORD.search(x)]
        # קודם "יומן פעילות" (activity), אחר כך השאר; ובסוף ניחושים נפוצים
        found.sort(key=lambda x: (0 if re.search(r'activ|journal|audit', x, re.I) else 1, x))
        pats = (found + [g for g in _ENTR_GUESS if g not in found])[:30]
    tried = []
    for pth in pats:
        for path, q in _entr_forms(pth, day):
            code, res = _http('GET', path, None, q, tok, 15)
            got = _entr_rows(res, day) if code == 200 else None
            tried.append({'path': path + ('?' + urllib.parse.urlencode(q) if q else ''), 'code': code,
                          'rows': len(res) if isinstance(res, list) else None, 'ok': bool(got),
                          # 400 — המקווה אומר אילו פרמטרים חסרים
                          'resp': (json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res)[:220] if code == 400 else ''})
            if code in (404, 405):
                break
            if got:
                _ENTR['pat'] = pth
                rows, tk = got
                # ביומן פעילות יש גם פעולות אחרות (תשלום, עדכון…) — אם יש שדה סוג / תיאור, רק הכניסות
                dk = [k for k in rows[0] if re.search(r'type|action|kind|descr|event|activ|operation|text|message', k, re.I)
                      and isinstance(rows[0].get(k), (str, int))]
                if dk:
                    ent = [r for r in rows if any(re.search(r'כניס|entr|enter|door|דלת|gate', str(r.get(k) or ''), re.I) for k in dk)]
                    if ent:
                        rows = ent
                out = []
                for r in rows:
                    at = _dt_of(r.get(tk))
                    if not at:
                        continue
                    ck = next((k for k in r if re.fullmatch(r'client_?id', k, re.I)), None)
                    cid = r.get(ck) if ck else None
                    nm = ' '.join(str(r.get(k) or '').strip() for k in ('firstName', 'lastName') if r.get(k)) or \
                        next((str(r[k]) for k in r if re.search(r'name', k, re.I) and isinstance(r[k], str) and r[k].strip()), '')
                    cas = any(bool(r.get(k)) for k in r if re.search(r'casual|guest|anonym|temp|single', k, re.I) and isinstance(r.get(k), bool))
                    grp = next((r[k] for k in r if re.fullmatch(r'group_?id', k, re.I)), None)
                    gnm = next((str(r[k]) for k in r if re.search(r'group_?name', k, re.I) and r.get(k)), '')
                    out.append({'at': at, 'cid': cid, 'name': nm, 'group': grp, 'gname': gnm, 'casual': cas})
                _ENTR['tried'] = tried
                return {'rows': out, 'path': pth, 'keys': sorted(rows[0].keys())[:30]}
    _ENTR['tried'] = tried
    return None


def probe_payments(cid):
    """מנסה (רק GET) את כל הנתיבים שנמצאו לתשלומים, עם מזהה הלקוח. מחזיר מה כל נתיב החזיר — לאבחון"""
    try:
        tok = login()
    except RuntimeError as e:
        return {'error': str(e), 'paths': [], 'tries': []}
    tries = []
    for pth in discover_paths():
        base_p = pth.rstrip('/')
        for form in (base_p + '/' + cid, base_p + '?clientId=' + cid, base_p):
            path, _, q = form.partition('?')
            code, res = _http('GET', path, None, dict([q.split('=', 1)]) if q else None, tok, 12)
            rows = res if isinstance(res, list) else next((res[k] for k in ('items', 'data', 'result', 'list')
                                                            if isinstance(res, dict) and isinstance(res.get(k), list)), None)
            pay = bool(rows) and any(_is_pay_row(x) for x in rows[:5])
            tries.append({'path': form.replace(cid, '{id}'), 'code': code, 'rows': len(rows) if isinstance(rows, list) else None,
                          'pay': pay, 'keys': sorted(rows[0].keys())[:20] if pay and isinstance(rows[0], dict) else []})
            if code in (404, 405):
                break
            if pay:
                break
    return {'paths': _DISC['paths'], 'files': _DISC['files'], 'error': _DISC['error'], 'tries': tries}


def payments(cid):
    """התשלומים של הלקוח במערכת המקווה. מחזיר (רשימה, מאיפה, שמות שדות לאבחון)"""
    # קודם יומן הפעילויות של הלקוח (שנה אחורה) — שורות "תשלום"
    try:
        t = datetime.date.today()
        raw = attendance((t - datetime.timedelta(days=365)).isoformat(), (t + datetime.timedelta(days=1)).isoformat(), cid)
    except Exception:
        raw = None
    if raw is not None:
        rows = [att_norm(r) for r in raw]
        if any(n['cid'] for n in rows):
            mine = [n for n in rows if str(n['cid'] or '') == str(cid)]
        else:
            # בלי מזהה לקוח בשורות — רק לפי השם המלא (שלא יוצגו תשלומים של אחרים אם המקווה התעלם מהסינון)
            try:
                c0 = client(cid, max_age=120)
                nk = lambda x: re.sub(r'\s+', '', str(x or ''))
                full = {nk((c0.get('firstName') or '') + (c0.get('lastName') or '')), nk((c0.get('lastName') or '') + (c0.get('firstName') or ''))}
                mine = [n for n in rows if nk(n['name']) in full]
            except Exception:
                mine = []
        if raw == [] or mine:
            out = []
            for n in mine:
                if n['kind'] != 'pay' or not n['at']:
                    continue
                out.append({'iso': n['at'].strftime('%Y-%m-%d'), 'time': n['at'].strftime('%H:%M'), 'amount': n['amount'] or 0,
                            'desc': n['text'][:80], 'how': n['method'][:40], 'failed': bool(re.search(r'נכשל|fail|declin', n['text'], re.I))})
            am = sorted(abs(x['amount']) for x in out if x['amount'])
            if am and all(float(a).is_integer() for a in am) and am[len(am) // 2] >= 500:
                for x in out:
                    x['amount'] = x['amount'] / 100.0
            out.sort(key=lambda x: (x['iso'], x['time']), reverse=True)
            return out, ATT_PATH, []
    c = client(cid, max_age=60)
    for k, v in c.items():
        if isinstance(v, list) and v and _PAY_KEY.search(k) and any(_is_pay_row(x) for x in v[:5]):
            return _pay_norm(v), 'client.' + k, []
    disc = []
    try:
        for d_ in discover_paths():
            b_ = d_.rstrip('/')
            disc += [b_ + '/{id}', b_ + '?clientId={id}']
    except Exception:
        pass
    paths = ([_PAY['path']] if _PAY['path'] else []) + [p for p in list(_PAY_PATHS) + disc if p != _PAY['path'] and p not in _PAY['bad']]
    try:
        tok = login()
    except RuntimeError:
        tok = ''
    for p in paths if tok else ():
        path, _, q = p.format(id=cid).partition('?')
        # ישירות (לא דרך call) — ניסיון של נתיב שלא קיים לא יירשם כשגיאת חיבור למקווה
        code, res = _http('GET', path, None, dict([q.split('=', 1)]) if q else None, tok, 15)
        rows = res if isinstance(res, list) else next((res[k] for k in ('items', 'data', 'result', 'list', 'payments', 'transactions')
                                                        if isinstance(res, dict) and isinstance(res.get(k), list)), None)
        if code in (404, 405) or (code == 200 and rows is None):
            _PAY['bad'].add(p)
            continue
        # ההיסטוריה של הלקוח (כמו יומן הפעילויות, רק שלו) — שורות "תשלום"
        if code == 200 and rows and p.startswith('Client/GetClientHistory') and isinstance(rows[0], dict):
            norm = [att_norm(x) for x in rows]
            if any(n['at'] for n in norm):
                if any(n['cid'] for n in norm):
                    norm = [n for n in norm if str(n['cid'] or '') == str(cid)]
                _PAY['path'] = p
                out = [{'iso': n['at'].strftime('%Y-%m-%d'), 'time': n['at'].strftime('%H:%M'), 'amount': n['amount'] or 0,
                        'desc': n['text'][:80], 'how': n['method'][:40], 'failed': bool(re.search(r'נכשל|fail|declin', n['text'], re.I))}
                       for n in norm if n['kind'] == 'pay' and n['at']]
                am = sorted(abs(x['amount']) for x in out if x['amount'])
                if am and all(float(a).is_integer() for a in am) and am[len(am) // 2] >= 500:
                    for x in out:
                        x['amount'] = x['amount'] / 100.0
                out.sort(key=lambda x: (x['iso'], x['time']), reverse=True)
                return out, p, []
        if code != 200 or not rows or not any(_is_pay_row(x) for x in rows[:5]):
            continue
        # שלא יוצגו תשלומים של אחרים: אם יש בשורות מזהה לקוח — רק שלו; נתיב בלי {id} בכתובת חייב מזהה כזה
        ck = next((k for k in rows[0] if re.fullmatch(r'client_?id', k, re.I)), None)
        if ck:
            rows = [x for x in rows if str(x.get(ck)) == str(cid)]
        elif '?' in p:
            _PAY['bad'].add(p)
            continue
        _PAY['path'] = p
        return _pay_norm(rows), p, []
    return [], '', _key_list(c)


def raw_group(gid):
    for g in _items(get('Group')):
        if str(g.get('id')) == str(gid):
            return dict(g)
    raise RuntimeError('הקבוצה לא נמצאה במקווה')


def update_group(gid, changes):
    """עדכון קבוצה במקווה — כמו עדכון לקוח: כל הקבוצה, עם השינוי בלבד."""
    obj = raw_group(gid)
    obj.update(changes)
    code, res = call('PATCH', 'Group/%s' % gid, body=obj, timeout=30)
    if code in (404, 405):
        code, res = call('PUT', 'Group/%s' % gid, body=obj, timeout=30)
    if code in (404, 405):
        code, res = call('PUT', 'Group', body=obj, timeout=30)
    if not (200 <= code < 300):
        raise RuntimeError('העדכון במקווה נכשל: %s' % (LAST.get('error') or code))
    _GR.update(rows=None)
    return res if isinstance(res, dict) else obj
