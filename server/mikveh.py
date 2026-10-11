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
