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
DEF_TYPE = 320                 # קבלה

# אמצעי התשלום כפי שהוא נרשם אצלנו -> קוד התשלום ב-EZcount
PAY_CASH, PAY_CHEQUE, PAY_TRANSFER, PAY_CARD = 1, 2, 3, 4


def _env(k, d=''):
    return (os.environ.get(k) or d).strip()


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
    return a


def _post(path, payload, timeout=30):
    """קריאה ל-API. מחזירה (הצלחה, גוף/שגיאה בעברית).
    שגיאה של EZcount מוחזרת כלשונה, כדי שיהיה ברור מה בדיוק חסר."""
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(_base() + path, data=data,
                                 headers={'Content-Type': 'application/json'})
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
    ok, res = _post('/api/checkApiKey', _auth())
    if ok:
        return True, 'מחובר ל-EZcount ✓'
    t = str(res)
    # מאיר ראה "מחובר ✓ (error code 1010)" — שגיאה היא שגיאה, לא מדווחים חיבור תקין
    return False, t + ' — בדוק ב-Render את EZCOUNT_API_KEY (המפתח מהגדרות ה-API באיזיקאונט) ואת EZCOUNT_API_EMAIL'


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
                 method='', note='', address='', phone='', require_email=True):
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
    if date:
        body['doc_date'] = date           # תאריך ההפקדה, לא תאריך ההפקה
    ok, res = _post('/api/createDoc', body)
    if not ok:
        # ניסיון שני בלי השדות האופציונליים (כתובת, טלפון, תאריך, הערה) — אם אחד מהם
        # הוא מה שהפריע ל-EZcount, הקבלה עדיין תופק עם השם והסכום
        first_err = res
        for k in ('customer_address', 'customer_phone', 'doc_date', 'comment'):
            body.pop(k, None)
        ok, res = _post('/api/createDoc', body)
        if not ok:
            print('  EZcount createDoc נכשל:', first_err, '|', res)
            return False, first_err
    return True, {
        'docnum': str(res.get('docnum') or res.get('doc_number') or res.get('doc_uuid') or ''),
        'doc_url': res.get('pdf_link') or res.get('doc_url') or '',
        'sent': bool(email),
    }


def fetch_pdf(url, timeout=30):
    """מוריד את ה-PDF של הקבלה מהקישור ש-EZcount החזיר. מחזיר bytes או None."""
    if not (url or '').startswith('http'):
        return None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'kollel-crm'}), timeout=timeout) as r:
            data = r.read()
        return data if data[:4] == b'%PDF' else None
    except Exception:
        return None
