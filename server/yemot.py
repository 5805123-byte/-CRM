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
     אם לטלפון אין עדיין תיקייה: "extension does not exist" — יוצרים אותה
     (UpdateExtension path=ivr2:/Phone/<טלפון> type=playfile), ומתחילים מ-000.
  2. UploadTextFile?what=ivr2:/Phone/<טלפון>/<NNN>.tts&contents=<הטקסט> — ההודעה הבאה.
  3. CallExtensionBridging?phones=<טלפון>&ivrPath=ivr2:/&callsTimeOut=35 — השיחה עצמה.
אופציונלי:
    YEMOT_SMS_FROM    מספר השולח ב-SMS (ברירת מחדל 025803545 — מאושר בימות)
    YEMOT_CALLER_ID   המספר שיוצג בשיחה הקולית
    YEMOT_TTS_VOICE   קול ההקראה (למשל ymMale / ymFemale)
    YEMOT_BASE        כתובת ה-API (ברירת מחדל https://www.call2all.co.il/ym/api/)

כל הודעה נשלחת בבקשה נפרדת לכל נמען — כך כל אחד שומע/מקבל את שמו, ותקלה
בטלפון אחד לא מפילה את כל השאר.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# מאיר: "אני רוצה שיהיה מקום ללוג שיראו בדיוק מה נשלח לימות המשיח ומה התשובה" —
# כל קריאה נרשמת (בלי המפתח) ברשימה של ה-thread הנוכחי; app.py שומר אותה במסד
_TR = threading.local()


def begin_trace():
    _TR.items = []


def end_trace():
    it = getattr(_TR, 'items', None) or []
    _TR.items = None
    return it


def _trace(method, params, ok, raw, ms):
    lst = getattr(_TR, 'items', None)
    if lst is None:
        return
    lst.append({'method': method, 'params': {k: v for k, v in (params or {}).items() if k != 'token'},
                'ok': bool(ok), 'response': (raw or '')[:3000], 'ms': int(ms)})

DEF_BASE = 'https://www.call2all.co.il/ym/api/'
# מאיר: "שרק כשהוא שולח SMS יצא עם זיהוי של 025803545 (זה מאושר כבר בימות המשיח)"
SMS_FROM_DEFAULT = '025803545'
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
    t0 = time.time()
    # כמו בתיעוד של ימות — GET עם הפרמטרים בכתובת
    req = urllib.request.Request(_base() + method + '?' + urllib.parse.urlencode(data),
                                 headers={'Accept': 'application/json, text/plain, */*', 'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
    except urllib.error.URLError as e:
        msg = 'אין תקשורת עם ימות המשיח: %s' % getattr(e, 'reason', e)
        _trace(method, params, False, msg, (time.time() - t0) * 1000)
        return False, msg
    except Exception as e:
        msg = 'שגיאה בפנייה לימות המשיח: %s' % e
        _trace(method, params, False, msg, (time.time() - t0) * 1000)
        return False, msg
    ms = (time.time() - t0) * 1000
    try:
        res = json.loads(raw or '{}')
    except Exception:
        _trace(method, params, False, raw, ms)
        return False, 'תשובה לא מובנת מימות המשיח: %s' % raw[:160]
    if not isinstance(res, dict):
        _trace(method, params, False, raw, ms)
        return False, 'תשובה לא מובנת מימות המשיח'
    st = str(res.get('responseStatus') or '').upper()
    _trace(method, params, st == 'OK', raw, ms)
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


def ensure_phone_dir(phone):
    """מאיר: "למספרים שעדיין אין להם הודעה, התיקייה של המספר שלהם לא נוצרה עדיין, ולכן
    לא שמעתי את ההודעה" — יוצרים את השלוחה Phone/<טלפון> (השמעת הודעות) ובודקים שקמה."""
    p = {'path': 'ivr2:/Phone/' + phone, 'type': 'playfile'}
    ok, res = call('UpdateExtension', p)
    if not ok:
        return False, 'יצירת התיקייה של הטלפון נכשלה — ' + str(res)
    ok, res = call('GetIVR2Dir', {'path': '/Phone/' + phone})
    if not ok:
        return False, 'התיקייה של הטלפון עדיין לא קיימת אחרי היצירה — ' + str(res)
    return True, res


def next_msg_num(phone):
    """המספר הבא לתיקייה של הטלפון: אחרי ההודעה הכי גבוהה שכבר יש (000 → 001).
    אם אין עדיין תיקייה לטלפון — יוצרים אותה ומתחילים מ-000."""
    ok, res = call('GetIVR2Dir', {'path': '/Phone/' + phone})
    if not ok:
        if 'does not exist' in str(res).lower():
            ok2, res2 = ensure_phone_dir(phone)
            if not ok2:
                return False, res2
            return True, 0
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
    p = {'phones': phone, 'message': text, 'from': (from_ or _env('YEMOT_SMS_FROM') or SMS_FROM_DEFAULT).strip()}
    return call('SendSms', p)


def campaign_status(cid):
    """מאיר: "שיוכלו לראות אם המספר ענה להודעה וכמה זמן הוא היה על הקו" — מצב הקמפיין
    שהשיחה יצרה (campaignId שחוזר מ-CallExtensionBridging)."""
    return call('GetCampaignStatus', {'campaignId': cid})


_ANS = re.compile(r'answer|ענה|connected|completed|success', re.I)
_NOANS = re.compile(r'no.?answer|noanswer|busy|failed|לא.?ענה|תפוס|cancel|reject|congestion|unavailable', re.I)
_SECS = re.compile(r'^(duration|billsec|billSec|seconds|secs|talkTime|talk_time|callDuration|call_duration|answeredSeconds|time)$', re.I)


def parse_call_result(res, phone=''):
    """מחפש בתשובה (בכל מבנה) את הרשומה של הטלפון: האם ענה, וכמה שניות היה על הקו.
    מחזיר {'answered': True/False/None, 'secs': int/None, 'status': str}."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            vals = ' '.join(str(v) for v in o.values() if isinstance(v, (str, int)))
            if not phone or phone[-9:] in re.sub(r'\D', '', vals):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(res)
    out = {'answered': None, 'secs': None, 'status': ''}
    for d in found[::-1]:                        # הרשומה הפנימית ביותר קודם
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                continue
            if out['secs'] is None and _SECS.match(str(k)):
                try:
                    out['secs'] = int(float(str(v).replace(',', '.')))
                except ValueError:
                    pass
            if not out['status'] and re.search(r'status|result|state|מצב', str(k), re.I) and str(v).strip():
                out['status'] = str(v)[:60]
            if out['answered'] is None and re.search(r'answered|isAnswer', str(k), re.I):
                sv = str(v).lower()
                out['answered'] = sv in ('1', 'true', 'yes', 'כן')
    if out['answered'] is None and out['status']:
        if _NOANS.search(out['status']):
            out['answered'] = False
        elif _ANS.search(out['status']):
            out['answered'] = True
    if out['answered'] is None and out['secs']:
        out['answered'] = out['secs'] > 0
    return out
