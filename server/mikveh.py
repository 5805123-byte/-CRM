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
_PAY_PATHS = ('Payment/GetByClient/{id}', 'Payment/Client/{id}', 'Payment?clientId={id}', 'Payments?clientId={id}',
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


def payments(cid):
    """התשלומים של הלקוח במערכת המקווה. מחזיר (רשימה, מאיפה, שמות שדות לאבחון)"""
    c = client(cid, max_age=60)
    for k, v in c.items():
        if isinstance(v, list) and v and _PAY_KEY.search(k) and any(_is_pay_row(x) for x in v[:5]):
            return _pay_norm(v), 'client.' + k, []
    paths = ([_PAY['path']] if _PAY['path'] else []) + [p for p in _PAY_PATHS if p != _PAY['path'] and p not in _PAY['bad']]
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
