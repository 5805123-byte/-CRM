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
מוסד נוסף — מאיר: "יש לי עוד מספר מוסד בנדרים פלוס שהייתי רוצה שתמשוך משם":
    NEDARIM_MOSAD2    מספר המוסד השני
    NEDARIM_API_KEY2  מפתח ה-API של המוסד השני (נוצר בתוך המוסד השני)
    NEDARIM_NAME2     שם קצר לתצוגה (רשות)   — וכך גם 3
מספרי זהות שחוזרים מנדרים פלוס לא נשמרים במערכת.
"""
import contextlib
import csv
import io
import json
import os
import threading
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://matara.pro/nedarimplus/Reports/Manage3.aspx'
# הוראות קבע בנקאיות (מס"ב) — דף אחר באותו שרת. מאיר: "יש כאלו שיש להם הוראת קבע בנקאית"
MASAV = 'https://matara.pro/nedarimplus/Reports/Masav3.aspx'
TAMAL = 'https://matara.pro/nedarimplus/Reports/Tamal3.aspx'     # קבלות של נדרים פלוס
MOSAD_DEFAULT = '5777499'
UA = 'KollelChatzosCRM/1.0'
LAST = {'at': '', 'ok': None, 'error': '', 'action': ''}


def _env(k):
    return (os.environ.get(k) or '').strip()


_CUR = threading.local()


def accounts():
    """כל המוסדות שמוגדרים ב-Render: הראשי, ואחריו 2, 3. כל אחד עם המפתח שלו."""
    out = []
    if _env('NEDARIM_API_KEY'):
        out.append({'mosad': _env('NEDARIM_MOSAD') or MOSAD_DEFAULT, 'key': _env('NEDARIM_API_KEY'),
                    'name': _env('NEDARIM_NAME') or 'כולל חצות', 'main': True})
    for i in ('2', '3'):
        if _env('NEDARIM_MOSAD' + i) and _env('NEDARIM_API_KEY' + i):
            out.append({'mosad': _env('NEDARIM_MOSAD' + i), 'key': _env('NEDARIM_API_KEY' + i),
                        'name': _env('NEDARIM_NAME' + i) or ('מוסד ' + _env('NEDARIM_MOSAD' + i)), 'main': False})
    return out


def account_for(mosad_id):
    """המוסד של הוראה / עסקה (ריק = הראשי)."""
    acc = accounts()
    return next((a for a in acc if a['mosad'] == str(mosad_id or '')), acc[0] if acc else None)


@contextlib.contextmanager
def use(acct):
    """כל הפניות בתוך הבלוק הולכות למוסד הזה."""
    prev = getattr(_CUR, 'a', None)
    _CUR.a = acct
    try:
        yield acct
    finally:
        _CUR.a = prev


def _cur():
    return getattr(_CUR, 'a', None)


def configured():
    return bool(_env('NEDARIM_API_KEY'))


def mosad():
    a = _cur()
    return (a['mosad'] if a else '') or _env('NEDARIM_MOSAD') or MOSAD_DEFAULT


def _key():
    a = _cur()
    return (a['key'] if a else '') or _env('NEDARIM_API_KEY')


def call(action, params=None, post=False, timeout=45, raw=False, masav=False, page=''):
    """פנייה אחת. מחזיר (הצלחה, JSON / טקסט). הודעת השגיאה נשמרת ב-LAST — בלי המפתח."""
    p = dict(params or {}, Action=action, MosadId=mosad(), ApiPassword=_key())
    if masav:
        p['MosadNumber'] = p['MosadId']      # בדף המס"ב חלק מהפעולות קוראות לזה MosadNumber
    url = (_env('NEDARIM_TAMAL_BASE') or TAMAL) if page == 'tamal' else (_env('NEDARIM_MASAV_BASE' if masav else 'NEDARIM_BASE') or (MASAV if masav else BASE))
    if page == 'tamal':
        p['MosadNumber'] = p['MosadId']
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


def _num(v):
    """סכום כמספר נקי ("₪1,200.00" → "1200") — נדרים פלוס מחזירים אותו מעוצב לתצוגה."""
    m = re.search(r'-?\d[\d,]*(?:\.\d+)?', str(v or ''))
    if not m:
        return ''
    x = m.group(0).replace(',', '')
    return x[:-3] if x.endswith('.00') else x


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
                    'amount': _num(r.get('4') or r.get('Amount')),
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
                            'itra': str(r.get('Itra') or '').strip(), 'error': str(r.get('ErrorText') or '').strip(),
                            'amount': _num(r.get('Amount')), 'groupe': str(r.get('Groupe') or '').strip(),
                            'next': str(r.get('NextDate') or '').strip(), 'last4': str(r.get('LastNum') or '').strip(),
                            'name': str(r.get('ClientName') or '').strip(), 'phone': str(r.get('Phone') or '').strip()}
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


def _rows(res):
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        return res.get('data') or res.get('Data') or res.get('rows') or []
    return []


def masav_kevas():
    """הוראות הקבע הבנקאיות (GetMasavKevaNew): מזהה, שם, פרטי חשבון, חיוב הבא, יתרה, סכום, קטגוריה.
    מספר החשבון לא נשמר — רק הבנק ו-3 הספרות האחרונות לתצוגה."""
    ok, res = call('GetMasavKevaNew', masav=True, timeout=90)
    if not ok:
        raise RuntimeError('נדרים פלוס (הוראות בנקאיות): %s' % (LAST.get('error') or str(res)[:120]))
    out = []
    for r in _rows(res):
        if not isinstance(r, dict):
            continue
        kid = str(r.get('DT_RowId') or r.get('ID') or '').strip().lstrip('-')
        if not kid:
            continue
        acct = re.sub(r'<[^>]+>', ' ', str(r.get('3') or ''))
        digits = re.findall(r'\d+', acct)
        bank = ('בנק %s ' % digits[0] if digits else '') + ('***' + digits[-1][-3:] if len(digits) > 1 else '')
        out.append({'id': kid, 'name': str(r.get('2') or '').strip(), 'bank': bank.strip(),
                    'next': str(r.get('4') or '').strip(), 'itra': str(r.get('5') or '').strip(),
                    'amount': _num(r.get('6')), 'groupe': str(r.get('7') or '').strip(), 'note': str(r.get('8') or '').strip()})
    return out


def masav_detail(masav_id):
    """פרטי הוראה בנקאית אחת (GetMasavId) — בשביל הטלפון והסטטוס. ת"ז ומספר חשבון לא נשמרים."""
    ok, res = call('GetMasavId', {'MasavId': str(masav_id)}, masav=True)
    if not ok or not isinstance(res, dict):
        return {}
    return {'phone': str(res.get('ClientPhone') or '').strip(), 'mail': str(res.get('ClientMail') or '').strip(),
            'status': str(res.get('StatusText') or res.get('Status') or '').strip(),
            'deleted': str(res.get('Deleted') or '0').strip() == '1', 'next': str(res.get('FullNextDate') or '').strip(),
            'amount': _num(res.get('Amount')), 'groupe': str(res.get('Groupe') or '').strip()}


def masav_history(date_from, date_to):
    """חיובי ההוראות הבנקאיות (GetMasavHistoryNew) בין שני תאריכים (dd/mm/yyyy): שידורים, החזרות, עמלות."""
    ok, res = call('GetMasavHistoryNew', {'From': date_from, 'To': date_to}, masav=True, timeout=120)
    if not ok:
        raise RuntimeError('נדרים פלוס (הסטוריית מס"ב): %s' % (LAST.get('error') or str(res)[:120]))
    out = []
    for r in _rows(res):
        if not isinstance(r, dict):
            continue
        rid = str(r.get('DT_RowId') or '').strip()
        if not rid or rid.upper().startswith('B'):        # B… = חיוב בודד שעוד לא שודר
            continue
        m = re.search(r'-?\d[\d,]*(?:\.\d+)?', str(r.get('5') or ''))
        out.append({'id': rid, 'keva': str(r.get('2') or '').strip(), 'name': str(r.get('3') or '').strip(),
                    'date': str(r.get('4') or '').strip(), 'amount': float(m.group(0).replace(',', '')) if m else 0.0,
                    'type': str(r.get('6') or '').strip(), 'groupe': str(r.get('8') or '').strip()})
    return out


def masav_boded(masav_id, amount, date, ajax=''):
    """תשלום בודד מהוראה בנקאית (MasavBoded) — נשלח לבנק בשידור הקרוב, לא מיידי."""
    p = {'MasavId': str(masav_id), 'Amount': ('%.2f' % float(amount)).rstrip('0').rstrip('.'), 'Date': date}
    if ajax:
        p['AjaxId'] = str(ajax)[:60]
    ok, txt = call('MasavBoded', p, post=True, masav=True, timeout=60, raw=True)
    if not ok:
        return False, txt
    try:
        res = json.loads(txt)
    except ValueError:
        res = {'Result': 'Error' if 'error' in txt.lower() or 'שגיאה' in txt else 'OK', 'Message': txt.strip()[:200]}
    good = str(res.get('Result') or res.get('Status') or '').lower() in ('ok', 'success') if isinstance(res, dict) else False
    return good, res


# ---------- פעולות על הוראה: הקפאה / הפעלה / עריכה ----------
# מאיר: "תחבר הכל, ותתחיל מהקפאה הפעלה". ת"ז ומספר חשבון שעוברים בעריכה נלקחים מנדרים פלוס
# ברגע השליחה ומוחזרים אליהם כמו שהם — לא נשמרים אצלנו.

def _txt_ok(ok, txt):
    """תשובה שהיא טקסט ("OK" / שגיאה) או JSON עם Result."""
    if not ok:
        return False, str(txt)[:200]
    t = (txt or '').strip()
    try:
        j = json.loads(t)
        if isinstance(j, dict):
            good = str(j.get('Result') or j.get('Status') or '').lower() in ('ok', 'success')
            return good, str(j.get('Message') or ('' if good else t))[:200]
    except ValueError:
        pass
    return t.upper().startswith('OK'), t[:200]


def disable_keva(keva_id):
    """⏸ הקפאת הוראת קבע באשראי (DisableKeva)."""
    return _txt_ok(*call('DisableKeva', {'KevaId': str(keva_id), 'MosadNumber': mosad()}, raw=True))


def enable_keva(keva_id):
    """▶ הפעלת הוראה מוקפאת (EnableKevaNew). מחזיר גם את תאריך החיוב הבא."""
    ok, txt = call('EnableKevaNew', {'KevaId': str(keva_id), 'MosadNumber': mosad()}, raw=True)
    if ok:
        try:
            j = json.loads((txt or '').strip())
            if isinstance(j, dict) and j.get('NextDate'):
                return True, 'החיוב הבא %s' % j['NextDate']
        except ValueError:
            pass
    return _txt_ok(ok, txt)


def delete_keva(keva_id):
    """🗑️ מחיקת הוראת קבע באשראי (DeleteKeva) — לצמיתות."""
    return _txt_ok(*call('DeleteKeva', {'KevaId': str(keva_id), 'MosadNumber': mosad()}, raw=True))


def masav_delete(masav_id):
    """🗑️ מחיקת הוראה בנקאית (DeleteMasavKeva) — מחיקה רכה, אפשר לשחזר בנדרים פלוס."""
    return _txt_ok(*call('DeleteMasavKeva', {'MasavId': str(masav_id)}, masav=True, raw=True))


def keva_detail(keva_id):
    ok, res = call('GetKevaId', {'KevaId': str(keva_id)})
    return res if ok and isinstance(res, dict) else {}


def update_keva(keva_id, amount=None, next_date=None, groupe=None, tashlumim=None):
    """✎ שינוי סכום / תאריך חיוב / קטגוריה בהוראת אשראי (UpdateKevaNew). שאר השדות נשלחים כמו
    שהם בנדרים פלוס (נמשכים רגע לפני), כדי שלא יימחקו. הכרטיס נשאר — 4 הספרות והתוקף שלו."""
    d = keva_detail(keva_id)
    if not d or not d.get('KevaLastNum'):
        return False, 'לא הצלחתי למשוך את פרטי ההוראה מנדרים פלוס'
    tok = re.sub(r'\D', '', str(d.get('KevaTokef') or ''))
    p = {'KevaId': str(keva_id), 'MosadNumber': mosad(),
         'Zeout': d.get('KevaZeout') or '', 'ClientName': d.get('KevaName') or '', 'Adresse': d.get('KevaAdresse') or '',
         'City': d.get('KevaCity') or '', 'Phone': d.get('KevaPhone') or '', 'Mail': d.get('KevaMail') or '',
         'Tashlumim': d.get('KevaTashlumim') or '' if tashlumim is None else str(tashlumim),
         'Groupe': (d.get('KevaGroupe') or '') if groupe is None else groupe, 'Avour': d.get('KevaAvour') or '',
         'NextDate': next_date or d.get('KevaNextDate') or '', 'Frequency': d.get('KevaFrequency') or '1',
         'Amount': ('%.2f' % float(amount)).rstrip('0').rstrip('.') if amount else _num(d.get('KevaAmount')),
         'CreditCard': str(d.get('KevaLastNum') or ''), 'Tokef': (tok[:2] + '/' + tok[2:4]) if len(tok) >= 4 else str(d.get('KevaTokef') or '')}
    return _txt_ok(*call('UpdateKevaNew', p, post=True, raw=True))


def masav_status(masav_id, status, comments=''):
    """שינוי סטטוס הוראה בנקאית (SetMasavStatus): 7 הקפאה · 1 הפעלה ("אני מאשר") · 9 / 8 חודש הבא / קודם."""
    p = {'MasavId': str(masav_id), 'StatusNumber': str(status)}
    if comments:
        p['Comments'] = comments
    return _txt_ok(*call('SetMasavStatus', p, masav=True, raw=True))


def masav_edit(masav_id, amount=None, day=None, groupe=None, tashlumim=None):
    """✎ שינוי סכום / יום גביה / קטגוריה בהוראה בנקאית (EditMasavKeva). פרטי החשבון והת"ז נמשכים
    מנדרים פלוס רגע לפני ונשלחים בחזרה כמו שהם."""
    ok, d = call('GetMasavId', {'MasavId': str(masav_id)}, masav=True)
    if not ok or not isinstance(d, dict) or not d.get('Account'):
        return False, 'לא הצלחתי למשוך את פרטי ההוראה הבנקאית'
    nd = str(day or d.get('NextDate') or '').strip()
    p = {'KevaId': str(masav_id), 'ClientName': d.get('ClientName') or '', 'ClientAdresse': d.get('ClientAdresse') or '',
         'ClientZeout': d.get('ClientZeout') or '', 'ClientPhone': d.get('ClientPhone') or '', 'ClientMail': d.get('ClientMail') or '',
         'NextDate': nd, 'Amount': ('%.2f' % float(amount)).rstrip('0').rstrip('.') if amount else _num(d.get('Amount')),
         'Tashlumim': (d.get('Tashlumim') or '') if tashlumim is None else str(tashlumim),
         'Groupe': (d.get('Groupe') or '') if groupe is None else groupe, 'Comments': d.get('Comments') or '',
         'Bank': d.get('Bank') or '', 'Agency': d.get('Agency') or '', 'Account': d.get('Account') or ''}
    return _txt_ok(*call('EditMasavKeva', p, post=True, masav=True, raw=True))


def error_logs(last_id='', loops=5):
    """יומן הסירובים (GetErrorLogsJson) מ-last_id והלאה: סירובי אשראי וסירובי הוראות קבע שכבר נרשמו.
    בלי ת"ז ובלי תוקף. מחזיר (רשימה, המזהה הגבוה)."""
    out, last = [], str(last_id or '')
    for _ in range(loops):
        p = {'MaxId': 2000}
        if last:
            p['LastId'] = last
        ok, res = call('GetErrorLogsJson', p, timeout=90)
        if not ok:
            raise RuntimeError('נדרים פלוס (סירובים): %s' % (LAST.get('error') or str(res)[:120]))
        rows = _rows(res)
        for r in rows:
            rid = str(r.get('ID') or '').strip()
            if not rid:
                continue
            out.append({'id': rid, 'date': str(r.get('ErrorDate') or '').strip(), 'error': str(r.get('Error') or '').strip(),
                        'amount': _num(r.get('Amount')), 'last4': str(r.get('LastNum') or '').strip(),
                        'name': str(r.get('ClientName') or '').strip(), 'phone': str(r.get('Phone') or '').strip(),
                        'keva': str(r.get('KevaId') or '').strip(), 'groupe': str(r.get('Groupe') or '').strip(),
                        'done': str(r.get('Done') or '0').strip() == '1'})
            last = rid
        if len(rows) < 2000:
            break
    return out, last


ACH_TYPES = {'מזומן': 1, 'צ׳ק': 2, "צ'ק": 2, 'העברה בנקאית': 3, 'אשראי (לא בנדרים)': 4}


def zeout_for(keva_id, bank=False):
    """מספר הזהות מתוך ההוראה בנדרים פלוס — רק כדי להעביר אותו בחזרה לנדרים (הכנסה חיצונית). לא נשמר."""
    if bank:
        ok, d = call('GetMasavId', {'MasavId': str(keva_id)}, masav=True)
        return str(d.get('ClientZeout') or '').strip() if ok and isinstance(d, dict) else ''
    return str(keva_detail(keva_id).get('KevaZeout') or '').strip()


def save_achnasot(zeout, amount, date, method, groupe='', avour='', ref='', name=''):
    """💵 הכנסה חיצונית (SaveAchnasot) — מזומן / צ'ק / העברה / אחר, כדי שנדרים פלוס יפיקו עליה קבלה."""
    t = ACH_TYPES.get(method, 6)
    p = {'Type': t, 'Zeout': zeout, 'Amount': ('%.2f' % float(amount)).rstrip('0').rstrip('.'), 'Date': date, 'Currency': 1,
         'Groupe': groupe[:200], 'Avour': avour[:300], 'MosadNumber': mosad()}
    if t == 2:
        p.update(Asmahta=ref or '0', Asmahta2='00-000-000000')
    elif t == 3:
        p.update(Asmahta=ref or '0', Asmahta2='00-000-000000')
    elif t == 4:
        p.update(Asmahta='אשראי', Asmahta2=(ref or '0000')[-4:])
    elif t == 6:
        p.update(Asmahta=method[:40] or 'אחר', Asmahta2=ref or '-')
    if name:
        p['SpecialName'] = name[:80]
    ok, res = call('SaveAchnasot', p, post=True)
    if ok and isinstance(res, dict) and res.get('ID'):
        return True, str(res['ID'])
    return False, (res.get('Message') if isinstance(res, dict) else str(res)) or LAST.get('error') or 'לא נשמר'


def invoice_achnasot(ach_id, tamal_type=405):
    """🧾 הפקת קבלה של נדרים פלוס על הכנסה חיצונית (CreateInvoice, Type=Achnasot; 405 = קבלת תרומה)."""
    ok, res = call('CreateInvoice', {'ID': str(ach_id), 'Type': 'Achnasot', 'TamalType': str(tamal_type)}, page='tamal')
    return ok, (res.get('Message') if isinstance(res, dict) else str(res)) or ''


def show_invoice(transaction_id):
    """🧾 קישור לקבלה שנדרים פלוס הפיקו לעסקת אשראי (ShowInvoice). מאיר: "הם מוציאים קבלות לבד —
    מי שתורם בנדרים פלוס מקבל מהם קבלה אוטומטית". לעסקאות בנקאיות אין קישור (הן באיזיקאונט)."""
    key = 'AchnasotId' if str(transaction_id).startswith('A') else 'TransactionId'
    ok, res = call('ShowInvoice', {key: str(transaction_id).lstrip('A')}, page='tamal')
    msg = str(res.get('Message') or '') if isinstance(res, dict) else str(res)
    if ok and msg.startswith('http'):
        return True, msg
    return False, msg or LAST.get('error') or 'לא נמצאה קבלה'


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
                        'amount': _num(r.get('Amount')), 'currency': str(r.get('Currency') or '1').strip(),
                        'keva': str(r.get('KevaId') or '').strip(), 'groupe': str(r.get('Groupe') or '').strip(),
                        'comments': str(r.get('Comments') or '').strip(), 'conf': str(r.get('Confirmation') or '').strip(),
                        'last4': str(r.get('LastNum') or '').strip(), 'type': str(r.get('TransactionType') or '').strip()})
            last = tid
        if len(rows) < 2000:
            break
    return out, last
