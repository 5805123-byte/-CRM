# -*- coding: utf-8 -*-
"""שליחת הודעה קולית (TTS) ו-SMS דרך ימות המשיח (call2all).

מאיר: "אני רוצה להתחבר לימות המשיח, שבני הקהילה או תורמים יוכלו לקבל הודעה
טלפונית או סמס או אימייל על תרומה שהם התחייבו, או נדבה, או הו"ק שחזרה — לפי
הקלדה שלי במערכת, שתשלח הודעה קולית."

הגדרה ב-Render בלבד (משתני סביבה — לא בקוד, לא בקובץ ולא בהודעות):
    YEMOT_TOKEN       מפתח ה-API של ימות (WU1BUElL.apik_…) — או במקומו שני המשתנים הבאים
    YEMOT_USERNAME    מספר המערכת בימות המשיח
    YEMOT_PASSWORD    הסיסמה של המערכת

הודעה קולית — לפי התיעוד שמאיר הביא מימות המשיח, שלושה שלבים לכל טלפון:
  1. GetIVR2Dir?path=/Phone/<טלפון> — איזו הודעה הכי גבוהה כבר יש לטלפון (000, 001…);
     אם לטלפון אין עדיין תיקייה: "extension does not exist" — מתחילים מ-000.
  2. UploadTextFile?what=ivr2:/Phone/<טלפון>/<NNN>.tts&contents=<הטקסט> — ההודעה הבאה.
  3. CallExtensionBridging?phones=<טלפון>&ivrPath=ivr2:/&callsTimeOut=35 — השיחה עצמה.
אופציונלי:
    YEMOT_SMS_FROM    שם/מספר השולח ב-SMS (חייב להיות מאושר בימות)
    YEMOT_CALLER_ID   המספר שיוצג בשיחה הקולית
    YEMOT_TTS_VOICE   קול ההקראה (למשל ymMale / ymFemale)
    YEMOT_BASE        כתובת ה-API (ברירת מחדל https://www.call2all.co.il/ym/api/)

כל הודעה נשלחת בבקשה נפרדת לכל נמען — כך כל אחד שומע/מקבל את שמו, ותקלה
בטלפון אחד לא מפילה את כל השאר.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

DEF_BASE = 'https://www.call2all.co.il/ym/api/'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 KollelChatzosCRM/1.0'


def _env(k, d=''):
    return (os.environ.get(k) or d).strip()


def configured():
    return bool(_env('YEMOT_TOKEN') or (_env('YEMOT_USERNAME') and _env('YEMOT_PASSWORD')))


def _token():
    t = _env('YEMOT_TOKEN')
    if t:
        return t
    return '%s:%s' % (_env('YEMOT_USERNAME'), _env('YEMOT_PASSWORD'))


def _base():
    b = _env('YEMOT_BASE', DEF_BASE)
    return b if b.endswith('/') else b + '/'


def call(method, params, timeout=40):
    """קריאה ל-API. מחזירה (הצלחה, גוף התשובה או הודעת שגיאה בעברית)."""
    if not configured():
        return False, 'ימות המשיח לא מוגדר ב-Render (YEMOT_TOKEN — מפתח ה-API של ימות)'
    data = dict(params or {})
    data['token'] = _token()
    # כמו בתיעוד של ימות — GET עם הפרמטרים בכתובת
    req = urllib.request.Request(_base() + method + '?' + urllib.parse.urlencode(data),
                                 headers={'Accept': 'application/json, text/plain, */*', 'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
    except urllib.error.URLError as e:
        return False, 'אין תקשורת עם ימות המשיח: %s' % getattr(e, 'reason', e)
    except Exception as e:
        return False, 'שגיאה בפנייה לימות המשיח: %s' % e
    try:
        res = json.loads(raw or '{}')
    except Exception:
        return False, 'תשובה לא מובנת מימות המשיח: %s' % raw[:160]
    if not isinstance(res, dict):
        return False, 'תשובה לא מובנת מימות המשיח'
    st = str(res.get('responseStatus') or '').upper()
    if st == 'OK':
        return True, res
    msg = res.get('message') or res.get('error') or res.get('errorMessage') or raw[:160]
    return False, 'ימות המשיח: %s' % msg


def session():
    """פרטי המערכת — לבדיקת חיבור ויתרת יחידות."""
    ok, res = call('GetSession', {})
    if not ok:
        # בדיקה חלופית — אם אפשר לקרוא את התיקייה הראשית, המפתח תקין
        ok2, res2 = call('GetIVR2Dir', {'path': '/'})
        if ok2:
            return True, {'name': '', 'units': None}
        return False, res
    units = res.get('units')
    if units is None:
        units = res.get('Units')
    return True, {'name': res.get('name') or res.get('username') or '', 'units': units}


def norm_phone(p):
    """מספר ישראלי בפורמט 05XXXXXXXX / 0XXXXXXXX. מחזיר '' אם לא תקין."""
    d = re.sub(r'\D', '', str(p or ''))
    if d.startswith('00972'):
        d = d[5:]
    elif d.startswith('972'):
        d = d[3:]
    if d and not d.startswith('0'):
        d = '0' + d
    if re.fullmatch(r'0(5\d|7\d)\d{7}', d) or re.fullmatch(r'0[2-489]\d{7}', d):
        return d
    return ''


def is_mobile(p):
    return bool(re.fullmatch(r'05\d{8}', p or ''))


def next_msg_num(phone):
    """המספר הבא לתיקייה של הטלפון: אחרי ההודעה הכי גבוהה שכבר יש (000 → 001)."""
    ok, res = call('GetIVR2Dir', {'path': '/Phone/' + phone})
    if not ok:
        if 'does not exist' in str(res).lower():
            return True, 0                    # אין עדיין הודעות לטלפון הזה
        return False, res
    nums = []
    for f in (res.get('files') or []):
        m = re.match(r'^(\d+)\.', str(f.get('name') or ''))
        if m:
            nums.append(int(m.group(1)))
    return True, (max(nums) + 1 if nums else 0)


def send_tts(phone, text, timeout=35):
    """הודעה קולית: מעלה את הטקסט כקובץ TTS לתיקיית הטלפון ומתקשר אליו."""
    ok, n = next_msg_num(phone)
    if not ok:
        return False, n
    name = '%03d.tts' % n
    ok, res = call('UploadTextFile', {'what': 'ivr2:/Phone/%s/%s' % (phone, name), 'contents': text})
    if not ok:
        return False, 'העלאת ההודעה נכשלה — ' + str(res)
    ok, res = call('CallExtensionBridging', {'phones': phone, 'ivrPath': 'ivr2:/', 'callsTimeOut': str(timeout)})
    if not ok:
        return False, 'השיחה לא יצאה — ' + str(res)
    errs = res.get('errors') or {}
    if errs:
        return False, 'השיחה לא יצאה — %s' % json.dumps(errs, ensure_ascii=False)[:160]
    return True, {'file': name, 'campaignId': res.get('campaignId') or '', 'callerId': res.get('callerId') or ''}


def send_sms(phone, text, from_=''):
    p = {'phones': phone, 'message': text}
    f = (from_ or _env('YEMOT_SMS_FROM')).strip()
    if f:
        p['from'] = f
    return call('SendSms', p)
