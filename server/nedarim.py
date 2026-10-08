# -*- coding: utf-8 -*-
"""חיבור לנדרים פלוס — הוראות קבע באשראי, רשימת התורמים, וגביית תשלום בודד.

מאיר: "אני רוצה שיהיה אפשרות לשלם דרך TashlumBodedNew — נעשה דרך הטלפון שיחייב דרך
ההוראת קבע שלו", "התורמים של נדרים פלוס זה בעצם הקהילה בממשק". המתקשר מזוהה לפי
הטלפון, ההוראה שלו נמצאת ברשימת הוראות הקבע, והחיוב נרשם בהיסטוריית ההוראה (Join).

ב-Render בלבד (לא בקוד, לא בקובץ ולא בהודעות):
    NEDARIM_API_KEY   מפתח API (npk_…) — הגדרות ← API ← מפתחות API
אופציונלי:
    NEDARIM_MOSAD     מספר המוסד (ברירת מחדל 5777499)
    NEDARIM_BASE      כתובת אחרת לבדיקות
מספרי זהות שחוזרים מנדרים פלוס לא נשמרים במערכת.
"""
import csv
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://matara.pro/nedarimplus/Reports/Manage3.aspx'
MOSAD_DEFAULT = '5777499'
UA = 'KollelChatzosCRM/1.0'
LAST = {'at': '', 'ok': None, 'error': '', 'action': ''}


def _env(k):
    return (os.environ.get(k) or '').strip()


def configured():
    return bool(_env('NEDARIM_API_KEY'))


def mosad():
    return _env('NEDARIM_MOSAD') or MOSAD_DEFAULT


def call(action, params=None, post=False, timeout=45, raw=False):
    """פנייה אחת. מחזיר (הצלחה, JSON / טקסט). הודעת השגיאה נשמרת ב-LAST — בלי המפתח."""
    p = dict(params or {}, Action=action, MosadId=mosad(), ApiPassword=_env('NEDARIM_API_KEY'))
    url = _env('NEDARIM_BASE') or BASE
    data = urllib.parse.urlencode(p).encode('utf-8')
    req = (urllib.request.Request(url, data=data, headers={'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded'})
           if post else urllib.request.Request(url + '?' + data.decode('ascii'), headers={'User-Agent': UA}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode('utf-8-sig', 'replace')
    except urllib.error.HTTPError as e:
        txt = e.read().decode('utf-8', 'replace')
        LAST.update(at=time.strftime('%Y-%m-%d %H:%M'), ok=False, error='%s %s' % (e.code, txt[:160]), action=action)
        return False, txt
    except Exception as e:
        LAST.update(at=time.strftime('%Y-%m-%d %H:%M'), ok=False, error=str(e)[:200], action=action)
        return False, str(e)
    if raw:
        LAST.update(at=time.strftime('%Y-%m-%d %H:%M'), ok=True, error='', action=action)
        return True, txt
    try:
        out = json.loads(txt)
    except ValueError:
        LAST.update(at=time.strftime('%Y-%m-%d %H:%M'), ok=False, error=txt[:200], action=action)
        return False, txt
    st = str((out.get('Result') or out.get('Status') or 'OK') if isinstance(out, dict) else 'OK').lower()
    ok = st in ('ok', 'success', '')
    LAST.update(at=time.strftime('%Y-%m-%d %H:%M'), ok=ok,
                error='' if ok else str(out.get('Message') or out)[:200], action=action)
    return ok, out


def kevas():
    """הוראות הקבע באשראי — כמו בממשק (מוקפאות מוסתרות). כל שורה: מזהה, שם, טלפון,
    סכום, קטגוריה, 4 ספרות, תאריך חיוב הבא. בלי מספר זהות."""
    ok, res = call('GetKevaNew')
    if not ok:
        raise RuntimeError('נדרים פלוס (הוראות קבע): %s' % (LAST.get('error') or res))
    rows = (res.get('data') if isinstance(res, dict) else res) or []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        kid = str(r.get('DT_RowId') or r.get('KevaId') or '').strip().lstrip('-')
        if not kid:
            continue
        out.append({'id': kid, 'name': str(r.get('2') or r.get('ClientName') or '').strip(),
                    'phone': str(r.get('Phone') or '').strip(), 'mail': str(r.get('Mail') or '').strip(),
                    'amount': str(r.get('4') or r.get('Amount') or '').strip(),
                    'groupe': str(r.get('5') or r.get('Groupe') or '').strip(),
                    'itra': str(r.get('7') or r.get('Itra') or '').strip(),
                    'next': str(r.get('9') or r.get('NextDate') or '').strip(),
                    'last4': str(r.get('11') or r.get('LastNum') or '').strip(),
                    'torem': str(r.get('ToremId') or '').strip(),
                    'error': str(r.get('10') or r.get('ErrorText') or '').strip(),
                    'city': str(r.get('City') or '').strip()})
    return out


def keva_flags():
    """פעילה / לא פעילה לכל הוראה (GetKevaJson — הרשימה המלאה עם Enabled ויתרת חיובים).
    מאיר: "הוראות קבע שחזרו — לא לכלול את אלה שכבר לא פעילות (למשל שנגמרו התשלומים)".
    מוגבל ל-20 פניות בשעה — נקרא פעם בסנכרון. מחזיר {KevaId: {'enabled': 0/1, 'itra': '...'}}."""
    out, last = {}, ''
    for _ in range(10):
        p = {'MaxId': 2000}
        if last:
            p['LastId'] = last
        ok, res = call('GetKevaJson', p, timeout=90)
        if not ok:
            raise RuntimeError('נדרים פלוס (רשימה מלאה): %s' % (LAST.get('error') or res))
        rows = res if isinstance(res, list) else ((res.get('data') or res.get('Data') or []) if isinstance(res, dict) else [])
        for r in rows:
            kid = str(r.get('KevaId') or '').strip().lstrip('-')
            if kid:
                out[kid] = {'enabled': 1 if str(r.get('Enabled', '1')).strip() in ('1', 'true', 'True') else 0,
                            'itra': str(r.get('Itra') or '').strip(), 'error': str(r.get('ErrorText') or '').strip()}
        if len(rows) < 2000:
            break
        last = str(rows[-1].get('KevaId') or '').lstrip('-')
        if not last:
            break
    return out


def tormim():
    """רשימת התורמים (ייצוא CSV) — מזהה, שם וטלפונים. העמודות מזוהות לפי הכותרת;
    מספר זהות לא נשמר."""
    ok, txt = call('GetTormimCsv', {'ToMail': 0}, raw=True, timeout=90)
    if not ok:
        raise RuntimeError('נדרים פלוס (תורמים): %s' % (LAST.get('error') or txt[:120]))
    t = txt.strip()
    if t.startswith('{'):
        raise RuntimeError('נדרים פלוס (תורמים): %s' % t[:160])
    # שורות שמסתיימות ב-\r בלבד (או \r\n) — מנרמלים לפני הקריאה, אחרת csv נעצר
    t = t.replace('\r\n', '\n').replace('\r', '\n')
    first = t.split('\n', 1)[0]
    delim = max((',', ';', '\t'), key=first.count)
    rd = list(csv.reader(io.StringIO(t, newline=''), delimiter=delim))
    if len(rd) < 2:
        return []
    head = [h.strip() for h in rd[0]]

    def col(*keys):
        return [i for i, h in enumerate(head) if any(k in h for k in keys)]
    c_id = col('מזהה', 'ID', 'Id') or [0]
    c_last, c_first = col('משפחה', 'LastName'), col('פרטי', 'FirstName')
    c_name = col('שם מלא', 'ClientName', 'שם')
    c_ph = col('טלפון', 'Phone', 'נייד', 'פלאפון')
    c_mail = col('מייל', 'Mail', 'Email', 'דוא')
    c_city = col('עיר', 'City')
    out = []
    for r in rd[1:]:
        g = lambda cs: next((' '.join(r[i].split()) for i in cs if i < len(r) and r[i].strip()), '')
        tid = g(c_id[:1])
        if not tid:
            continue
        nm = ' '.join(x for x in (g(c_last), g(c_first)) if x) or g(c_name)
        phones = [r[i].strip() for i in c_ph if i < len(r) and r[i].strip()]
        out.append({'id': tid, 'name': nm, 'phones': phones, 'mail': g(c_mail), 'city': g(c_city)})
    return out


def tashlum_boded(keva_id, amount, groupe='', comments='', ajax='', currency=1):
    """⚡ חיוב מיידי בכרטיס השמור בהוראת הקבע. לא משנה את ההוראה; נרשם בהיסטוריה שלה (Join)."""
    p = {'KevaId': str(keva_id).lstrip('-'), 'Amount': ('%.2f' % float(amount)).rstrip('0').rstrip('.'),
         'Currency': int(currency), 'Tashlumim': 1, 'JoinToKevaId': 'Join'}
    if groupe:
        p['Groupe'] = groupe[:300]
    if comments:
        p['Comments'] = comments[:500]
    if ajax:
        p['AjaxId'] = str(ajax)[:60]
    return call('TashlumBodedNew', p, post=True, timeout=60)


def update_link(keva_id):
    """קישור אישי מאובטח של נדרים פלוס שבו התורם מזין כרטיס חדש להוראת הקבע (14 יום).
    מספר הכרטיס לא עובר אצלנו. קריאה חוזרת מחזירה את הקישור הקיים."""
    ok, res = call('CreateKevaUpdateLink', {'KevaId': str(keva_id).lstrip('-')})
    if ok and isinstance(res, dict) and res.get('Link'):
        return True, res['Link']
    return False, (res.get('Message') if isinstance(res, dict) else str(res)) or LAST.get('error') or 'לא נוצר קישור'


def link_status(keva_id):
    ok, res = call('GetKevaUpdateLinkStatus', {'KevaId': str(keva_id).lstrip('-')})
    return (res if ok and isinstance(res, dict) else {})


def history(last_id='', loops=8):
    """עסקאות האשראי (GetHistoryJson) מ-last_id והלאה, בלי מספר זהות. מוגבל ל-20 פניות
    בשעה — נקרא בסנכרון ואחרי תשלום בטלפון. מחזיר (רשימה, המזהה הגבוה ביותר)."""
    out, last = [], str(last_id or '')
    for _ in range(loops):
        p = {'MaxId': 2000}
        if last:
            p['LastId'] = last
        ok, res = call('GetHistoryJson', p, timeout=90)
        if not ok:
            raise RuntimeError('נדרים פלוס (היסטוריה): %s' % (LAST.get('error') or res))
        rows = res if isinstance(res, list) else ((res.get('data') or res.get('Data') or []) if isinstance(res, dict) else [])
        for r in rows:
            tid = str(r.get('TransactionId') or '').strip()
            if not tid:
                continue
            out.append({'id': tid, 'time': str(r.get('TransactionTime') or '').strip(),
                        'phone': str(r.get('Phone') or '').strip(), 'name': str(r.get('ClientName') or '').strip(),
                        'amount': str(r.get('Amount') or '').strip(), 'currency': str(r.get('Currency') or '1').strip(),
                        'keva': str(r.get('KevaId') or '').strip(), 'groupe': str(r.get('Groupe') or '').strip(),
                        'comments': str(r.get('Comments') or '').strip(), 'conf': str(r.get('Confirmation') or '').strip(),
                        'last4': str(r.get('LastNum') or '').strip(), 'type': str(r.get('TransactionType') or '').strip()})
            last = tid
        if len(rows) < 2000:
            break
    return out, last
