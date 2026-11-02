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

# מאיר: "פה אני רוצה לראות גם תעודת זהות שלו ואימייל שלו" — תעודת הזהות נקראת מהמקווה כשפותחים את
# הכרטיס, ולא נשמרת אצלנו. קודם לפי שם שדה; אם אין — ערך של 9 ספרות עם ספרת ביקורת תקינה (לא טלפון/קוד)
_IDENT_KEY = re.compile(r'id_?num|identity|identif|^tz$|teudat|personal_?id|national|citizen|passport|^ssn$|idcard|id_?card', re.I)


def _il_id_ok(d):
    d = re.sub(r'\D', '', str(d or ''))
    if len(d) not in (8, 9):
        return False
    d = d.zfill(9)
    t = 0
    for i, ch in enumerate(d):
        n = int(ch) * (1 if i % 2 == 0 else 2)
        t += n if n < 10 else n - 9
    return t % 10 == 0


def ident(c):
    """תעודת הזהות כמו שהיא רשומה במקווה (מחרוזת), או ''."""
    if not isinstance(c, dict):
        return ''
    skip = {str(c.get(k) or '') for k in ('id', 'phone', 'clientCode', 'phone2', 'mobile')}
    for k, v in c.items():
        if isinstance(v, (str, int)) and not isinstance(v, bool) and _IDENT_KEY.search(k):
            sv = str(v).strip()
            if re.fullmatch(r'\d{5,12}', sv) and sv not in skip:
                return sv
    for k, v in c.items():
        if k in ('id', 'phone', 'clientCode', 'phone2', 'mobile', 'balance', 'lastBalance') or isinstance(v, bool):
            continue
        if isinstance(v, (str, int)):
            sv = str(v).strip()
            if re.fullmatch(r'\d{8,9}', sv) and sv not in skip and not sv.startswith('05') and _il_id_ok(sv):
                return sv
    return ''


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


def set_sub_dates(cid, end=None, start=None):
    """📅 תאריכי המנוי — כמו המסך של המקווה (setClientSubscriptionDates → PATCH Client/{id}/SubscriptionDates).
    end/start: 'YYYY-MM-DD'. מה שלא נשלח — נשאר כמו שהוא אצל הלקוח."""
    c = client(cid, max_age=60)
    def iso(v, cur):
        if not v:
            return cur or None
        return v[:10] + 'T00:00:00'
    body = {'subscriptionStartDate': iso(start, c.get('subscriptionStartDate')),
            'subscriptionEndDate': iso(end, c.get('subscriptionEndDate'))}
    code, res = call('PATCH', 'Client/%s/SubscriptionDates' % cid, body=body, timeout=30)
    if not (200 <= code < 300):
        raise RuntimeError('עדכון תאריכי המנוי במקווה נכשל: %s' % (LAST.get('error') or code))
    _ONE.pop(str(cid), None)
    c2 = client(cid)
    if _CL['rows'] is not None:
        for i, r in enumerate(_CL['rows']):
            if str(r.get('id')) == str(cid):
                _CL['rows'][i] = dict(r, subscriptionEndDate=c2.get('subscriptionEndDate'), subscriptionStartDate=c2.get('subscriptionStartDate'))
    return {'sub_end': str(c2.get('subscriptionEndDate') or '')[:10], 'sub_start': str(c2.get('subscriptionStartDate') or '')[:10]}


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


def _dt_of(v):
    try:
        return datetime.datetime.fromisoformat(str(v).replace('Z', '+00:00')[:32])
    except Exception:
        return None


# ---------- יומן פעילות, היסטוריה של לקוח, יתרה, חובות, חסימה, לוח בקרה ----------
# הנתיבים האמיתיים — מהקלטה של מסך הניהול של המקווה (2.11.2026), לא ניחושים:
#   POST Report/GetActivityLog           — יומן הפעילות (כל הכניסות והתשלומים, גם מזדמנים), בדפים עם סמן
#   POST Report/GetEnteraceAndPayments   — כניסות, תשלומים וחובות של לקוח אחד ("Enterace" — כך זה כתוב אצלם)
#   POST Client/AdminPurchase            — הוספת / הפחתת יתרה (פעימות או זיכוי), כמו הכפתור במסך
#   GET Debts/GetByClientId/{id} · POST Debts · PATCH Debts/Delete/{id}
# הקודים (אושרו מול לוח הבקרה של המקווה): אמצעי תשלום 0 = מזומן, 1 = אשראי.
# סוג פריט: 1 = טעינת מנוי, 2 = טעינת פעימות, 4 = כניסה. יתרה רגילה = פעימות, יתרה זמנית = זיכוי.
# חוב: ‎-1 = פתוח, 3 = נמחק.
ACT_PATH = 'Report/GetActivityLog'
HIST_PATH = 'Report/GetEnteraceAndPayments'
ATT_PATH = ACT_PATH                      # השם הישן — app.py מציג אותו כמקור הנתונים
PAY_METHOD = {0: 'מזומן', 1: 'אשראי'}
ITEM_TYPE = {1: 'טעינת מנוי', 2: 'טעינת פעימות', 4: 'כניסה'}
DEBT_OPEN, DEBT_DELETED = -1, 3
_ATT = {'tries': [], 'fail_at': 0}       # app.py מאפס את fail_at ב"לבדוק שוב"
_ENTR = {'tried': []}
try:
    from zoneinfo import ZoneInfo
    _IL = ZoneInfo('Asia/Jerusalem')
except Exception:                         # בלי מאגר אזורי זמן — שעון ישראל קבוע (חורף)
    _IL = datetime.timezone(datetime.timedelta(hours=2))


def _utc(day, end=False):
    """'YYYY-MM-DD' (יום בשעון ישראל) → ISO ב-UTC כמו שהמסך שלהם שולח. end — הרגע האחרון של היום."""
    d = datetime.datetime.combine(datetime.date.fromisoformat(day[:10]), datetime.time(23, 59, 59, 999000) if end else datetime.time(0, 0))
    u = d.replace(tzinfo=_IL).astimezone(datetime.timezone.utc)
    return u.strftime('%Y-%m-%dT%H:%M:%S.') + '%03dZ' % (u.microsecond // 1000)


def _local(v):
    """זמן מהמקווה (UTC) → datetime בשעון ישראל, בלי אזור זמן"""
    dt = _dt_of(v)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(_IL).replace(tzinfo=None)


def _nis(agorot):
    return None if agorot is None else round(float(agorot) / 100.0, 2)


def club_uuid():
    """המזהה הפנימי של המועדון (לא 2087) — חלק מהבקשות דורשות אותו"""
    if not _TOK.get('club_uuid'):
        try:
            _TOK['club_uuid'] = current_club().get('id') or ''
        except Exception:
            pass
    return _TOK.get('club_uuid') or _TOK.get('club_id') or None


def activity_log(d0, d1, cid=None, pay_only=False, max_rows=20000):
    """כל השורות ביומן הפעילות מ-d0 עד d1 כולל (ימים בשעון ישראל). רשימה גולמית, או None אם לא ענה.
    pay_only — רק פעולות ששולמו במזומן / אשראי (מסונן אצלם, הרבה פחות שורות)."""
    body = {'fromDate': _utc(d0), 'toDate': _utc(d1, end=True), 'clientId': cid or None, 'actionTypes': None,
            'performerTerminalIds': None, 'performerAdminUserIds': None, 'includeAutoPerformer': False, 'groupIds': None,
            'paymentMethods': [0, 1] if pay_only else None, 'amountAgorot': None, 'sortBy': 'createdAt', 'sortDescending': True,
            'offset': 0, 'limit': 500, 'cursorCreatedAt': None, 'cursorId': None}
    rows, tries = [], []
    for _ in range(200):
        code, res = call('POST', ACT_PATH, body=body, timeout=60)
        if code == 400 and body['limit'] > 100:          # אם 500 בדף זה יותר מדי אצלם — כמו המסך שלהם, 100
            body['limit'] = 100
            code, res = call('POST', ACT_PATH, body=body, timeout=60)
        if code == 400 and body['paymentMethods']:       # אם הסינון לפי אמצעי תשלום לא מתקבל — בלי סינון
            body['paymentMethods'] = None
            pay_only = False
            code, res = call('POST', ACT_PATH, body=body, timeout=60)
        tries.append({'body': {k: v for k, v in body.items() if v is not None and k != 'clientId'}, 'code': code,
                      'resp': '' if code == 200 else str(res)[:300]})
        if code != 200 or not isinstance(res, dict) or not isinstance(res.get('rows'), list):
            _ATT.update(tries=tries, fail_at=time.time())
            return None if not rows else rows
        page = res['rows']
        rows += page
        nxt_at, nxt_id = res.get('nextCursorCreatedAt'), res.get('nextCursorId')
        if not page or not nxt_id or len(rows) >= max_rows or len(page) < body['limit']:
            break
        body.update(cursorCreatedAt=nxt_at, cursorId=nxt_id)
    if pay_only:
        rows = [r for r in rows if _row_paid(r) > 0]
    _ATT.update(tries=tries, fail_at=0)
    return rows


def attendance(d0, d1, cid=None, pay_only=False):
    """תאימות לשם הישן: d1 לא כולל (כמו קודם)"""
    last = (datetime.date.fromisoformat(d1[:10]) - datetime.timedelta(days=1)).isoformat()
    return activity_log(d0, max(d0, last), cid, pay_only)


def _row_paid(r):
    """כמה שולם בפועל במזומן / אשראי בשורה ביומן (באגורות), אחרי עודף"""
    s = 0
    for p in r.get('paymentMethods') or []:
        if isinstance(p, dict) and p.get('method') in PAY_METHOD:
            s += (p.get('paidAgorot') or 0) - (p.get('changeAgorot') or 0)
    return s


def _row_how(r):
    ms = []
    for p in r.get('paymentMethods') or []:
        if isinstance(p, dict):
            m = PAY_METHOD.get(p.get('method'), 'אמצעי %s' % p.get('method'))
            if m not in ms:
                ms.append(m)
    return ' + '.join(ms)


def att_norm(r):
    """שורה ביומן → {'at' (שעון ישראל), 'cid', 'name', 'group', 'gname', 'kind', 'entry', 'casual', 'amount' (₪), 'method', 'text'}
    kind: pay (שולם במזומן / אשראי — גם כניסה של מזדמן ששילם), entry, entry_fail, other. entry — האם זו כניסה (גם אם שולמה)."""
    is_ent = str(r.get('id') or '').startswith('entrance:')
    ok = r.get('status') == 1
    paid = _row_paid(r)
    amt = r.get('amountAgorot')
    nm = ' '.join(x for x in (str(r.get('clientFirstName') or '').strip(), str(r.get('clientLastName') or '').strip()) if x)
    if is_ent and not ok:
        kind = 'entry_fail'
    elif paid > 0:
        kind = 'pay'
    elif is_ent:
        kind = 'entry'
    else:
        kind = 'other'
    sub = r.get('subLine') or {}
    parts = []
    if is_ent:
        parts.append('כניסה' if ok else 'כניסה שנדחתה')
    if paid > 0:
        parts.append('שולם ₪%g' % (paid / 100.0))
    if sub.get('key') == 'Activity_Log_SubLine_SubscriptionValidUntil' and (sub.get('params') or {}).get('date'):
        parts.append('מנוי בתוקף עד ' + sub['params']['date'])
    if r.get('balanceBeforeAgorot') is not None:
        parts.append('ערך צבור לפני ₪%g' % (r['balanceBeforeAgorot'] / 100.0))
    if not parts:
        parts.append('פעולה %s' % r.get('actionType'))
    return {'at': _local(r.get('createdAt')), 'cid': r.get('clientId'), 'name': nm, 'group': None,
            'gname': str(r.get('clientGroupName') or '').strip(), 'kind': kind, 'entry': is_ent and ok,
            'casual': bool(r.get('isCasualClient')), 'amount': _nis(paid if paid > 0 else amt), 'method': _row_how(r),
            'text': ' · '.join(parts)}


def entrances(day):
    """כל הכניסות של היום (כולל מזדמנים) מיומן הפעילות: {'rows': [{'at', 'cid', 'name', 'group', 'gname', 'casual'}], 'path', 'keys'} או None"""
    raw = activity_log(day, day)
    if raw is None:
        return None
    out = []
    for r in raw:
        n = att_norm(r)
        if n['entry'] and n['at']:
            out.append({'at': n['at'], 'cid': n['cid'], 'name': n['name'], 'group': None, 'gname': n['gname'], 'casual': n['casual']})
    return {'rows': out, 'path': ACT_PATH, 'keys': sorted(raw[0].keys())[:30] if raw else []}


def history(cid, d0=None, d1=None):
    """כניסות, תשלומים וחובות של לקוח (Report/GetEnteraceAndPayments) — רשימה גולמית. ברירת מחדל: שנה אחורה"""
    t = datetime.datetime.now(_IL).date()
    d0 = d0 or (t - datetime.timedelta(days=365)).isoformat()
    d1 = d1 or t.isoformat()
    body = {'clubId': club_uuid(), 'fromDate': _utc(d0), 'toDate': _utc(d1, end=True), 'terminals': [], 'clientId': cid}
    code, res = call('POST', HIST_PATH, body=body, timeout=60)
    if code != 200 or not isinstance(res, list):
        raise RuntimeError('ההיסטוריה של הלקוח במקווה לא נטענה: %s' % (LAST.get('error') or code))
    return [x for x in res if isinstance(x, dict) and str(x.get('clientId') or cid) == str(cid)]


def _h_paid(x):
    return (x.get('paidByCash') or 0) + (x.get('paidByCredit') or 0) + (x.get('paidByTransaction') or 0)


def _h_failed(x):
    st = x.get('paymentStatus')
    resp = str(x.get('paymentResponse') or '')
    return (st not in (None, 0)) or ('"Status"' in resp and '"Status":"OK"' not in resp.replace(' ', ''))


def _h_how(x):
    out = []
    if x.get('paidByCash'):
        out.append('מזומן')
    if x.get('paidByCredit'):
        out.append('אשראי')
    if x.get('paidByTransaction'):
        out.append('אחר')
    return ' + '.join(out)


def _h_desc(x):
    src = str(x.get('source') or '')
    if src == 'Debts':
        return 'חוב'
    return ITEM_TYPE.get(x.get('itemType')) or ('כניסה' if src == 'Entrances' else src or 'פעולה')


def payments(cid):
    """התשלומים של הלקוח במקווה (מזומן / אשראי), שנה אחורה. מחזיר (רשימה, מקור, []) — כמו קודם.
    שורה: {'iso', 'time', 'amount' (₪), 'desc', 'how', 'failed'}"""
    PAYDIAG[str(cid)] = {}
    out = []
    for x in history(cid):
        if x.get('source') == 'Debts':
            continue
        paid = _h_paid(x)
        failed = _h_failed(x)
        if paid <= 0 and not failed:
            continue
        at = _local(x.get('createdAt'))
        if not at:
            continue
        out.append({'iso': at.strftime('%Y-%m-%d'), 'time': at.strftime('%H:%M'), 'amount': _nis(paid if paid else x.get('amount') or 0),
                    'desc': _h_desc(x), 'how': _h_how(x), 'failed': failed})
    out.sort(key=lambda x: (x['iso'], x['time']), reverse=True)
    return out, HIST_PATH, []


PAYDIAG = {}


def activity(cid, days=365):
    """כל הפעילות של הלקוח (כניסות, תשלומים, חובות), חדש קודם.
    שורה: {'at', 'kind', 'text', 'amount' (₪), 'method', 'extra'}"""
    t = datetime.datetime.now(_IL).date()
    out = []
    for x in history(cid, (t - datetime.timedelta(days=days)).isoformat(), t.isoformat()):
        at = _local(x.get('createdAt'))
        if not at:
            continue
        src = x.get('source')
        paid = _h_paid(x)
        if src == 'Debts':
            kind, text = 'other', 'חוב' + (': ' + str(x.get('reason')) if x.get('reason') else '')
        elif src == 'Entrances' and x.get('entranceStatus') not in (None, 1):
            kind, text = 'entry_fail', 'כניסה שנדחתה'
        elif paid > 0 or _h_failed(x):
            kind, text = 'pay', _h_desc(x) + (' · ✗ נכשל' if _h_failed(x) else '')
        elif src == 'Entrances':
            kind, text = 'entry', 'כניסה' + (' על חשבון ערך צבור (פעימות)' if (x.get('balanceBefore') or 0) != (x.get('balanceAfter') or 0) else '')
        else:
            kind, text = 'other', _h_desc(x)
        extra = {}
        for k, lbl in (('balanceBefore', 'balanceBefore'), ('balanceAfter', 'balanceAfter'), ('paidByCash', 'cash'), ('paidByCredit', 'credit')):
            if x.get(k):
                extra[lbl] = _nis(x[k])
        if (x.get('tmpBalanceBefore') or 0) != (x.get('tmpBalanceAfter') or 0):
            extra['זיכוי לפני'] = _nis(x.get('tmpBalanceBefore') or 0)
            extra['זיכוי אחרי'] = _nis(x.get('tmpBalanceAfter') or 0)
        out.append({'at': at.strftime('%Y-%m-%d %H:%M'), 'kind': kind, 'text': text[:120],
                    'amount': _nis(paid if paid else (x.get('amount') if src == 'Debts' else 0)), 'method': _h_how(x), 'extra': extra})
    out.sort(key=lambda x: x['at'], reverse=True)
    return out


def probe_payments(cid):
    """תאימות — הבדיקה הישנה של נתיבים. היום הנתיב ידוע; מחזיר כמה שורות יש ללקוח"""
    try:
        n = len(history(cid))
        return {'paths': [HIST_PATH], 'files': [], 'error': '', 'tries': [{'path': HIST_PATH, 'code': 200, 'rows': n, 'pay': True}]}
    except Exception as e:
        return {'paths': [HIST_PATH], 'files': [], 'error': str(e)[:200], 'tries': []}


# ---------- יתרה (פעימות / זיכוי) ----------

def temp_balance(cid):
    """יתרת הזיכוי (tempBalance) באגורות"""
    _ONE.pop(str(cid), None)
    c = client(cid)
    for k in ('tempBalance', 'lastTempBalance'):
        if c.get(k) is not None:
            try:
                return int(round(float(c[k])))
            except (TypeError, ValueError):
                pass
    return 0


def add_credit(cid, amount, temp=False):
    """הוספת יתרה (סכום שלילי = הפחתה), באגורות — כמו הכפתור במסך המקווה (Client/AdminPurchase).
    temp=False — פעימות (יתרה רגילה), temp=True — זיכוי (יתרה זמנית). נרשם אצלם ביומן ובדוחות."""
    amount = int(amount)
    if not amount:
        return {}
    cu = club_uuid()
    body = {'payments': [], 'purchaseItems': [{'transactionType': 2 if temp else 1, 'itemType': 2, 'clientId': cid,
                                               'moneyValue': amount, 'clubId': cu}],
            'IsAdminUser': True, 'clientId': cid, 'clubId': cu}
    code, res = call('POST', 'Client/AdminPurchase', body=body, timeout=30)
    if not (200 <= code < 300) or (isinstance(res, dict) and res.get('isSuccess') is False):
        msg = (res.get('message') if isinstance(res, dict) else '') or LAST.get('error') or code
        raise RuntimeError('עדכון היתרה במקווה נכשל: %s' % msg)
    _ONE.pop(str(cid), None)
    return res


# ---------- חובות ----------

def debts(cid, include_deleted=False):
    """החובות של הלקוח במקווה: [{'id', 'amount' (₪), 'reason', 'date', 'open', 'status'}]"""
    code, res = call('GET', 'Debts/GetByClientId/%s' % cid, timeout=20)
    if code != 200 or not isinstance(res, list):
        raise RuntimeError('החובות במקווה לא נטענו: %s' % (LAST.get('error') or code))
    out = []
    for d in res:
        st = d.get('status')
        if st == DEBT_DELETED and not include_deleted:
            continue
        at = _local(d.get('createdAt') or d.get('date'))
        out.append({'id': d.get('id'), 'amount': _nis(d.get('amount') or 0), 'reason': str(d.get('reason') or ''),
                    'date': at.strftime('%Y-%m-%d') if at else '', 'paid': str(d.get('payDate') or '')[:10],
                    'open': st == DEBT_OPEN, 'status': st})
    out.sort(key=lambda x: x['date'], reverse=True)
    return out


def add_debt(cid, agorot, reason):
    """חוב חדש ללקוח (באגורות) — כמו "הוספת חוב" במסך המקווה"""
    agorot = int(agorot)
    if agorot <= 0:
        raise RuntimeError('סכום החוב חייב להיות גדול מאפס')
    body = {'amount': agorot, 'reason': str(reason or '').strip()[:200],
            'date': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'), 'clientId': cid}
    code, res = call('POST', 'Debts/', body=body, timeout=30)
    if not (200 <= code < 300):
        raise RuntimeError('הוספת החוב במקווה נכשלה: %s' % (LAST.get('error') or code))
    return res


def delete_debt(debt_id):
    code, res = call('PATCH', 'Debts/Delete/%s' % debt_id, body={}, timeout=30)
    if not (200 <= code < 300):
        raise RuntimeError('מחיקת החוב במקווה נכשלה: %s' % (LAST.get('error') or code))
    return True


# ---------- חסימה ----------

def set_blocked(cid, blocked, reason=''):
    """חסימה / שחרור של לקוח במקווה (כמו המתג במסך שלהם)"""
    res = update_client(cid, {'isBlocked': bool(blocked), 'blockReason': (str(reason or '').strip()[:200] or None) if blocked else None})
    if _CL['rows'] is not None:
        for i, c in enumerate(_CL['rows']):
            if str(c.get('id')) == str(cid):
                _CL['rows'][i] = dict(c, isBlocked=bool(blocked), blockReason=(reason or None) if blocked else None)
    return res


# ---------- לוח בקרה ----------

def terminals():
    try:
        return [t.get('id') for t in _items(get('Terminal')) if t.get('id')]
    except Exception:
        return []


def dashboard(d0, d1):
    """הנתונים של לוח הבקרה של המקווה לתקופה (ימים בשעון ישראל, כולל): כניסות, הכנסות, לקוחות פעילים,
    הכנסות לפי אמצעי תשלום ולפי סוג. סכומים ב-₪."""
    body = {'terminals': terminals(), 'fromDate': _utc(d0), 'toDate': _utc(d1, end=True), 'timeFilter': 1}

    def one(path):
        code, res = call('POST', 'Report/' + path, body=body, timeout=40)
        return res if code == 200 else None

    out = {'from': d0, 'to': d1}
    v = one('GetMonthlyEntranceCount')
    out['entrances'] = v if isinstance(v, (int, float)) else None
    v = one('GetMonthlyIncome')
    out['income'] = _nis(v) if isinstance(v, (int, float)) else None
    v = one('GetActiveClientsCount')
    out['active'] = v if isinstance(v, (int, float)) else None
    v = one('GetPulseBalanceSpentAtEntrances')
    out['pulses_spent'] = _nis(v) if isinstance(v, (int, float)) else None
    v = one('GetChartPaymentData')
    out['by_method'] = [{'method': PAY_METHOD.get(x.get('paymentType'), 'אמצעי %s' % x.get('paymentType')), 'sum': _nis(x.get('value') or 0)}
                        for x in v] if isinstance(v, list) else []
    v = one('GetChartDataByItemType')
    out['by_type'] = [{'type': ITEM_TYPE.get(x.get('itemType'), 'סוג %s' % x.get('itemType')), 'sum': _nis(x.get('value') or 0)}
                      for x in v] if isinstance(v, list) else []
    return out


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
