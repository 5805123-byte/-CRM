# -*- coding: utf-8 -*-
"""הפקת קבלה ושליחתה לתורם דרך EZcount (איזיקאונט).

מאיר: "אם אני מכניס ידנית הפקדה לבנק הישראלי שלנו שהפקידו לנו תרומה,
אני רוצה שאוכל לשלוח קבלה ישירות מהמערכת לאימייל של התורם, שהוא יראה
שזה מגיע מהמייל שלנו, דרך מערכת הקבלות של איזיקאונט. בלחיצת כפתור
תישלח לו קבלה כשאני מכניס תרומות שלו."

הקבלה מופקת בחשבון EZcount של הכולל, ו-EZcount שולח אותה במייל לתורם
מכתובת השולח שמוגדרת שם — כך התורם רואה שזה הגיע מהכולל.

הגדרה ב-Render (משתני סביבה בלבד; לא בקוד, לא בקובץ ולא בהודעות):
    EZCOUNT_API_KEY     מפתח ה-API מתוך חשבון EZcount
    EZCOUNT_API_EMAIL   כתובת המשתמש בחשבון

אופציונלי:
    EZCOUNT_DEV_EMAIL   כתובת המפתח, אם EZcount דורש אותה
    EZCOUNT_BASE        כתובת השרת (ברירת מחדל https://api.ezcount.co.il)
                        לבדיקות אפשר להצביע על https://demo.ezcount.co.il
    EZCOUNT_DOCTYPE     סוג המסמך (ברירת מחדל 320 — קבלה)
"""
import json
import os
import urllib.error
import urllib.request

DEF_BASE = 'https://api.ezcount.co.il'
# EZcount ענה: "document type 320 can't be created for company type 4" — החשבון הוא
# מלכ"ר/עמותה, והמסמך המתאים לתרומה הוא "קבלה על תרומה" (405). אם גם הוא לא מותר,
# מנסים את הסוגים שהשרת מציין כמותרים (ראה _doc_type_fallback).
DEF_TYPE = 405                 # קבלה על תרומה
DOC_TYPES_TRY = (405, 400, 320)
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 KollelChatzosCRM/1.0'
LAST = {'at': '', 'ok': None, 'msg': ''}      # הקריאה האחרונה ל-createDoc — מוצגת ב-🩺

# אמצעי התשלום כפי שהוא נרשם אצלנו -> קוד התשלום ב-EZcount
PAY_CASH, PAY_CHEQUE, PAY_TRANSFER, PAY_CARD = 1, 2, 3, 4


def _env(k, d=''):
    return (os.environ.get(k) or d).strip()


def _now():
    import datetime
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo('Asia/Jerusalem')).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return datetime.datetime.now().strftime('%Y-%m-%d %H:%M')


def configured():
    """האם החיבור הוגדר. לא נוגע במפתח עצמו — רק בודק שהוא קיים."""
    return bool(_env('EZCOUNT_API_KEY') and _env('EZCOUNT_API_EMAIL'))


def _base():
    return _env('EZCOUNT_BASE', DEF_BASE).rstrip('/')


def _auth():
    # ה-API של EZcount מזדהה עם api_key + developer_email (איש הקשר לעניין ה-API).
    # המייל של החשבון (EZCOUNT_API_EMAIL) משמש כ-developer_email אם לא הוגדר אחר.
    a = {'api_key': _env('EZCOUNT_API_KEY'),
         'developer_email': _env('EZCOUNT_DEV_EMAIL') or _env('EZCOUNT_API_EMAIL')}
    # EZcount ענה: "'created_by_api_key' is a mandatory key for distributors users" —
    # החשבון מוגדר אצלם כמפיץ, ולכן המסמך חייב לציין באיזה מפתח (של העסק) הוא נוצר.
    # ברירת המחדל: אותו מפתח; אם לעסק יש מפתח נפרד — EZCOUNT_CREATED_BY_KEY ב-Render.
    a['created_by_api_key'] = _env('EZCOUNT_CREATED_BY_KEY') or a['api_key']
    return a


def _auth_variants():
    """כל הצירופים הסבירים של שני המפתחות — הראשון הוא ברירת המחדל (_auth)."""
    k1, k2 = _env('EZCOUNT_API_KEY'), _env('EZCOUNT_CREATED_BY_KEY')
    dev = _env('EZCOUNT_DEV_EMAIL') or _env('EZCOUNT_API_EMAIL')
    out = [_auth()]
    if k2 and k2 != k1:
        out.append({'api_key': k2, 'developer_email': dev, 'created_by_api_key': k1})
        out.append({'api_key': k2, 'developer_email': dev})
        out.append({'api_key': k1, 'developer_email': dev})
    return out


def _is_key_error(res):
    t = str(res or '').lower()
    return any(w in t for w in ('api_key', 'api key', 'distributor', 'מפתח', 'developer_email'))


def _is_type_error(res):
    t = str(res or '').lower()
    return 'document type' in t or 'company type' in t or 'סוג מסמך' in t


def _doc_type_fallback(res, current):
    """סוגי מסמך לנסות אחרי שגיאת סוג: קודם מה שהשרת מציין כמותר, אחר כך הרשימה שלנו."""
    import re as _re
    t = str(res or '')
    allowed = []
    m = _re.search(r'allowed[^\d]*((?:\d{3,4}[^\d]{0,6})+)', t, _re.I)
    if m:
        allowed = [int(x) for x in _re.findall(r'\d{3,4}', m.group(1))]
    # קודם סוגי הקבלה (405 קבלה על תרומה, 400 קבלה) מתוך המותרים, אחר כך השאר
    pref = [x for x in DOC_TYPES_TRY if x in allowed] + [x for x in allowed if x not in DOC_TYPES_TRY]
    out = []
    for x in pref + list(DOC_TYPES_TRY):
        if x != current and x not in out:
            out.append(x)
    return out[:4]


def _post(path, payload, timeout=30):
    """קריאה ל-API. מחזירה (הצלחה, גוף/שגיאה בעברית).
    שגיאה של EZcount מוחזרת כלשונה, כדי שיהיה ברור מה בדיוק חסר."""
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    # מאיר ראה "error code: 1010" בטקסט פשוט (לא JSON) — זו חסימה של Cloudflare מול
    # User-Agent של סקריפט (Python-urllib), לא תשובה של EZcount. לכן כותרות כמו דפדפן.
    req = urllib.request.Request(_base() + path, data=data,
                                 headers={'Content-Type': 'application/json; charset=utf-8',
                                          'Accept': 'application/json, text/plain, */*',
                                          'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
    except urllib.error.URLError as e:
        return False, 'אין תקשורת אל EZcount: %s' % getattr(e, 'reason', e)
    except Exception as e:
        return False, 'שגיאה בפנייה ל-EZcount: %s' % e
    try:
        body = json.loads(raw or '{}')
    except Exception:
        return False, 'תשובה לא מובנת מ-EZcount: %s' % raw[:200]
    if not isinstance(body, dict):
        return False, 'תשובה לא מובנת מ-EZcount'
    if body.get('success') in (True, 'true', 1, '1'):
        return True, body
    msg = (body.get('errMsg') or body.get('error') or body.get('message')
           or body.get('err') or '')
    code = body.get('errCode') or body.get('error_code') or body.get('code') or ''
    if not msg:
        msg = 'תשובה לא מובנת: %s' % raw[:200]
    if code:
        msg = 'error code %s: %s' % (code, msg)
    return False, 'EZcount: %s' % msg


def check():
    """בדיקת חיבור — בלי להפיק מסמך אמיתי. (תקין, הודעה בעברית).

    EZcount אינו מציע נקודת בדיקה נפרדת, ולכן נשלחת בקשה חסרה בכוונה:
    אם האישורים תקינים תחזור שגיאה על התוכן, ואם לא — שגיאת הרשאה.
    """
    if not configured():
        return False, 'לא הוגדר. יש להגדיר ב-Render את EZCOUNT_API_KEY ו-EZCOUNT_API_EMAIL'
    # ל-EZcount אין נקודת בדיקה (checkApiKey מחזיר דף HTML) — הבדיקה האמיתית היא ההפקה
    # האחרונה בפועל (LAST), שמוצגת לצד השורה הזו ב-🩺
    if LAST.get('at') and not LAST.get('ok'):
        return False, 'המפתח מוגדר, אבל ההפקה האחרונה נכשלה'
    return True, 'המפתח מוגדר' + (' · מחובר ✓' if LAST.get('ok') else ' (עדיין לא הופקה קבלה)')


def _pay_type(method):
    m = (method or '').strip().lower()
    if 'מזומן' in m:
        return PAY_CASH
    if "צ'ק" in m or 'צ׳ק' in m or 'check' in m or 'cheque' in m:
        return PAY_CHEQUE
    if 'אשראי' in m or 'authorize' in m or 'banquest' in m or 'card' in m:
        return PAY_CARD
    return PAY_TRANSFER          # הפקדה/העברה בבנק — המקרה שמאיר תיאר


def send_receipt(name, email, amount, currency='ILS', date='', purpose='',
                 method='', note='', address='', phone='', require_email=True, crn=''):
    """מפיק קבלה ושולח אותה לתורם. מחזיר (הצלחה, תוצאה/שגיאה).

    בהצלחה התוצאה היא dict עם docnum (מספר הקבלה) ו-doc_url אם התקבל.
    מאיר: "אני מעדיף שקבלות ישראליות יעברו דרך איזיקאונט… שאני אשלח לך אסמכתא
    ואני אוציא משם קבלה" — לכן אפשר להפיק גם בלי מייל (require_email=False):
    הקבלה נוצרת ב-EZcount ונשמרת אצלנו, ונשלחת מהמערכת כשיהיה מייל.
    """
    if not configured():
        return False, 'החיבור ל-EZcount לא הוגדר ב-Render'
    email = (email or '').strip()
    if require_email and not email:
        return False, 'אין כתובת מייל לתורם — אי אפשר לשלוח קבלה'
    try:
        amt = round(float(str(amount).replace(',', '') or 0), 2)
    except Exception:
        amt = 0
    if amt <= 0:
        return False, 'סכום הקבלה חייב להיות גדול מאפס'
    desc = (purpose or '').strip() or 'תרומה לכולל חצות'
    body = _auth()
    body.update({
        'type': int(_env('EZCOUNT_DOCTYPE', str(DEF_TYPE)) or DEF_TYPE),
        'customer_name': (name or '').strip() or 'תורם',
        'item': [{'details': desc, 'amount': 1, 'price': amt, 'price_type': 0}],
        'payment': [{'payment_type': _pay_type(method), 'payment_sum': amt}],
        'price_total': amt,
        'currency': (currency or 'ILS').upper(),
        'comment': (note or '').strip(),
        'lang': 'he',
    })
    if email:
        body['customer_email'] = email
        body['send_email'] = True         # EZcount שולח את הקבלה לתורם
        body['email_to'] = email
        body['email_text'] = 'תודה רבה על תרומתך לכולל חצות. הקבלה מצורפת.'
    else:
        body['send_email'] = False
    if (address or '').strip():
        body['customer_address'] = address.strip()
    if (phone or '').strip():
        body['customer_phone'] = phone.strip()
    if (crn or '').strip():
        body['customer_crn'] = crn.strip()       # ת.ז. / ח.פ של התורם — מודפס על הקבלה
    if date:
        # מאיר: "אני צריך שהקבלה תהיה על היום שהוא נתן, כמו שכתוב במסמך" — תאריך המסמך
        # ותאריך התשלום הם יום ההעברה; וליתר ביטחון התאריך נכתב גם בהערה שמודפסת על הקבלה
        body['date'] = date
        body['doc_date'] = date
        for p in body['payment']:
            p['date'] = date
        try:
            import datetime as _dt
            nice = _dt.date.fromisoformat(date[:10]).strftime('%d.%m.%Y')
        except Exception:
            nice = date
        body['comment'] = ('התקבל ב-' + nice + ((' · ' + body['comment']) if body.get('comment') else ''))
    ok, res = _post('/api/createDoc', body)
    if not ok and _is_type_error(res):
        # סוג מסמך שאינו מותר לסוג החשבון — מנסים את הסוגים שהשרת מציין, ואז את הרשימה שלנו
        first_err = res
        for t in _doc_type_fallback(res, body['type']):
            body['type'] = t
            ok, res = _post('/api/createDoc', body)
            if ok or not _is_type_error(res):
                break
        if not ok:
            res = first_err
    if not ok and _is_key_error(res):
        # מאיר: בעמוד ה-API של איזיקאונט יש מפתח ל"מערכות שונות", ובנפרד לפייפאל/ויקס.
        # לא ברור איזה מפתח הוא "של העסק" ואיזה "של המפיץ" — אם הוגדרו שניים ב-Render
        # (EZCOUNT_API_KEY + EZCOUNT_CREATED_BY_KEY), מנסים את כל הצירופים לפני שמוותרים.
        first_err = res
        for auth in _auth_variants()[1:]:
            for k in ('api_key', 'developer_email', 'created_by_api_key'):
                body.pop(k, None)
            body.update(auth)
            ok, res = _post('/api/createDoc', body)
            if ok or not _is_key_error(res):
                break
        if not ok:
            res = first_err
    if not ok:
        # ניסיון נוסף בלי השדות האופציונליים (כתובת, טלפון, תאריך, הערה) — אם אחד מהם
        # הוא מה שהפריע ל-EZcount, הקבלה עדיין תופק עם השם והסכום
        first_err = res
        for k in ('customer_address', 'customer_phone', 'doc_date', 'date'):
            body.pop(k, None)
        for p in body.get('payment', []):
            p.pop('date', None)
        ok, res = _post('/api/createDoc', body)
        if not ok:
            print('  EZcount createDoc נכשל:', first_err, '|', res)
            LAST.update(at=_now(), ok=False, msg=str(first_err)[:600])
            return False, first_err
    link = ''
    for k in ('pdf_link', 'pdf_link_copy', 'doc_url', 'pdfLink', 'pdf', 'link', 'url', 'doc_link'):
        v = res.get(k)
        if isinstance(v, str) and v.startswith('http'):
            link = v; break
    # מאיר קיבל "not found" בפתיחת ה-PDF — כדי לדעת מה איזיקאונט מחזיר, שמות השדות של
    # התשובה (בלי ערכים) מוצגים ב-🩺 ליד ההפקה האחרונה
    LAST.update(at=_now(), ok=True, msg='קבלה %s הופקה · שדות בתשובה: %s · קישור PDF: %s' % (
        res.get('docnum') or res.get('doc_number') or '', ','.join(sorted(k for k in res.keys() if k != 'success'))[:200], 'יש' if link else 'אין'))
    return True, {
        'docnum': str(res.get('docnum') or res.get('doc_number') or res.get('doc_uuid') or ''),
        'doc_url': link,
        'sent': bool(email),
    }


def fetch_pdf(url, timeout=30):
    """מוריד את ה-PDF של הקבלה מהקישור ש-EZcount החזיר. מחזיר bytes או None."""
    if not (url or '').startswith('http'):
        return None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=timeout) as r:
            data = r.read()
        return data if data[:4] == b'%PDF' else None
    except Exception:
        return None
