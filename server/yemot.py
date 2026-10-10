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


# ---------- הקול וההקראה ----------
# מאיר: "אני גם רוצה להחליף קול, שיהיה יותר אנושי, ויותר נורמלי בלי טעויות".
# ימות ביטלו את בחירת הקולות — יש קול אחד, ברירת המחדל שלהם. (set_voice נשאר, לא בשימוש.)
VOICES = [('', 'ברירת המחדל של ימות')]
_DIG = ['אפס', 'אחת', 'שתיים', 'שלוש', 'ארבע', 'חמש', 'שש', 'שבע', 'שמונה', 'תשע']


def num_words(n):
    """158 -> 'מאה חמישים ושמונה' (לשון זכר, כמו "שקלים")."""
    try:
        import receipt_il as _r
    except Exception:
        return str(n)
    n = int(n)
    if n == 0:
        return 'אפס'
    if n >= 1000000:
        return ' '.join(_DIG[int(c)] for c in str(n))
    def b1000(x):
        h, r = divmod(x, 100)
        hs = _r._H[h] if h else ''
        rs = _r._below_1000(r) if r else ''
        if hs and rs:
            return hs + (' ' if ' ו' in rs else ' ו') + rs   # מאה חמישים ושמונה · מאה ושמונים
        return hs or rs
    k, low = divmod(n, 1000)
    hi = (_r._TH[k] if k in _r._TH else (b1000(k) + ' אלף')) if k else ''
    lo = b1000(low) if low else ''
    sep = ' ' if ' ו' in lo else ' ו'
    return (hi + (sep if hi and lo else '') + lo).strip()


def _phone_words(m):
    d = re.sub(r'\D', '', m.group(0))
    groups = [d[:3], d[3:6], d[6:]] if d.startswith('05') or d.startswith('07') else [d[:2], d[2:5], d[5:]]
    return ', '.join(' '.join(_DIG[int(c)] for c in g) for g in groups if g)


# ראשי תיבות שכותבים בחובות ובהתחייבויות — מאיר: "צריך לפתוח את כל הראשי תיבות" (ההקראה לא יודעת לקרוא אותם).
# מילון ההגייה של מאיר גובר — הוא רץ קודם.
ABBR = [
    ('יוהכ"פ', 'יום הכיפורים'), ('יוה"כ', 'יום הכיפורים'), ('יו"כ', 'יום כיפור'),
    ('שמח"ת', 'שמחת תורה'), ('שמע"צ', 'שמיני עצרת'), ('הושע"ר', 'הושענא רבה'), ('הוש"ר', 'הושענא רבה'),
    ('ר"ה', 'ראש השנה'), ('ר"ח', 'ראש חודש'), ('חוה"מ', 'חול המועד'), ('יו"ט', 'יום טוב'), ('ל"ג', 'לג'),
    ('ש"ק', 'שבת קודש'), ('שב"ק', 'שבת קודש'), ('עש"ק', 'ערב שבת קודש'), ('מוצש"ק', 'מוצאי שבת קודש'), ('מוצ"ש', 'מוצאי שבת'),
    ('ביהכ"נ', 'בית הכנסת'), ('ביהכנ"ס', 'בית הכנסת'), ('בהכ"נ', 'בית הכנסת'), ('ביהמ"ד', 'בית המדרש'), ('בית המד"ר', 'בית המדרש'),
    ('ת"ת', 'תלמוד תורה'), ('הו"ק', 'הוראת קבע'), ('ע"ח', 'על חשבון'), ('ע"י', 'על ידי'), ('ע"ש', 'על שם'),
    ('ז"ל', 'זכרונו לברכה'), ('ע"ה', 'עליו השלום'), ('נ"י', 'נרו יאיר'), ('שליט"א', 'שליטא'), ('הרה"ג', 'הרב הגאון'), ('הרה"צ', 'הרב הצדיק'),
    ('מס\'', 'מספר'), ('גמ"ח', 'גמח'), ('בס"ד', 'בסיעתא דשמיא'), ('ב"ה', 'ברוך השם'), ('אי"ה', 'אם ירצה השם'), ('בע"ה', 'בעזרת השם'),
]


def _abbr(t):
    for w, say in ABBR:
        for q in {w, w.replace('"', '״'), w.replace('"', "''")}:
            # גם עם אות שימוש לפני (בביהכ"נ, לר"ה, ושמח"ת)
            t = re.sub(r'(?<![\u0590-\u05ffA-Za-z])([בלוהמשכ]{0,2})' + re.escape(q) + r'(?![\u0590-\u05ffA-Za-z])', lambda m: m.group(1) + say, t)
    # שנה עברית: תשפ"ז / תשפ״ז -> תשפז (ההקראה אומרת "תַּשְׁפַּז")
    t = re.sub(r'(?<![\u0590-\u05ff])([בלוהמש]{0,2}ת[שר][א-ת]?)["״\']{1,2}([א-ת])(?![\u0590-\u05ff])', r'\1\2', t)
    return t


def hints_for(text, hints):
    """רק הנחיות ההגייה של מילים שבאמת מופיעות בטקסט (במקור או בניקוד)."""
    t = text or ''
    return [h for h in (hints or []) if h.get('word') and (h['word'] in t or (h.get('nikud') and h['nikud'] in t))]


def speakable(text, pron=''):
    """הטקסט כפי שימות יקריא אותו: טלפונים ספרה-ספרה בקבוצות, סכומים במילים,
    ש"ח/₪ -> שקלים, ומילון הגייה של מאיר ("מילה=איך לומר", שורה לכל מילה)."""
    t = str(text or '')
    for ln in str(pron or '').replace('\r', '').split('\n'):
        if '=' in ln:
            w, say = ln.split('=', 1)
            w, say = w.strip(), say.strip()
            if w and say:
                t = re.sub(r'(?<![\u0590-\u05ffA-Za-z])' + re.escape(w) + r'(?![\u0590-\u05ffA-Za-z])', say, t)
    t = _abbr(t)
    t = re.sub(r'(?<!\d)0\d{1,2}-?\d{3}-?\d{4}(?!\d)|(?<!\d)05\d-?\d{7}(?!\d)', _phone_words, t)
    t = re.sub(r'(\d)\s*(?:ש"ח|ש״ח|ש\'\'ח|₪|שח\b)', r'\1 שקלים', t)
    t = re.sub(r'₪\s*(\d[\d,]*)', r'\1 שקלים', t)
    t = re.sub(r'(?<=\d),(?=\d{3}\b)', '', t)
    t = re.sub(r'\d+(?:\.\d+)?', lambda m: num_words(float(m.group(0))) if float(m.group(0)) < 1000000 else m.group(0), t)
    t = t.replace('{', '').replace('}', '')
    return re.sub(r'\s{2,}', ' ', t).strip()


def set_voice(phone, voice):
    """הקול בתיקייה של הטלפון (tts_voice ב-ext.ini שלה)."""
    if not voice:
        return True, ''
    return call('UpdateExtension', {'path': 'ivr2:/Phone/' + phone, 'type': 'playfile', 'tts_voice': voice})


def ensure_phone_dir(phone, voice=''):
    """מאיר: "למספרים שעדיין אין להם הודעה, התיקייה של המספר שלהם לא נוצרה עדיין, ולכן
    לא שמעתי את ההודעה" — יוצרים את השלוחה Phone/<טלפון> (השמעת הודעות) ובודקים שקמה."""
    p = {'path': 'ivr2:/Phone/' + phone, 'type': 'playfile'}
    if voice:
        p['tts_voice'] = voice
    ok, res = call('UpdateExtension', p)
    if not ok:
        return False, 'יצירת התיקייה של הטלפון נכשלה — ' + str(res)
    ok, res = call('GetIVR2Dir', {'path': '/Phone/' + phone})
    if not ok:
        return False, 'התיקייה של הטלפון עדיין לא קיימת אחרי היצירה — ' + str(res)
    return True, res


def next_msg_num(phone, voice=''):
    """המספר הבא לתיקייה של הטלפון: אחרי ההודעה הכי גבוהה שכבר יש (000 → 001).
    אם אין עדיין תיקייה לטלפון — יוצרים אותה (עם הקול שנבחר) ומתחילים מ-000."""
    ok, res = call('GetIVR2Dir', {'path': '/Phone/' + phone})
    if not ok:
        if 'does not exist' in str(res).lower():
            ok2, res2 = ensure_phone_dir(phone, voice)
            if not ok2:
                return False, res2
            return True, 0
        return False, res
    if voice and str((res.get('extIni') or {}).get('tts_voice') or '') != voice:
        set_voice(phone, voice)            # תיקייה קיימת — מעדכנים רק את הקול
    nums = []
    for f in (res.get('files') or []):
        m = re.match(r'^(\d+)\.', str(f.get('name') or ''))
        if m:
            nums.append(int(m.group(1)))
    return True, (max(nums) + 1 if nums else 0)


def upload_file(path, data, filename='msg.wav', timeout=60):
    """העלאת קובץ שמע לימות (UploadFile, multipart), עם המרה אוטומטית לפורמט של ימות."""
    if not configured():
        return False, 'ימות המשיח לא מוגדר ב-Render'
    bnd = '----kc%d' % int(time.time() * 1000)
    parts = []
    for k, v in (('token', _token()), ('path', path), ('convertAudio', '1')):
        parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (bnd, k, v)).encode('utf-8'))
    parts.append(('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\nContent-Type: audio/wav\r\n\r\n' % (bnd, filename)).encode('utf-8'))
    body = b''.join(parts) + data + ('\r\n--%s--\r\n' % bnd).encode('utf-8')
    params = {'path': path, 'convertAudio': '1', 'file': '%s (%d KB)' % (filename, len(data) // 1024)}
    t0 = time.time()
    req = urllib.request.Request(_base() + 'UploadFile', data=body,
                                 headers={'Content-Type': 'multipart/form-data; boundary=' + bnd, 'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
    except Exception as e:
        _trace('UploadFile', params, False, str(e), (time.time() - t0) * 1000)
        return False, 'העלאת הקובץ נכשלה: %s' % e
    ms = (time.time() - t0) * 1000
    try:
        res = json.loads(raw or '{}')
    except Exception:
        _trace('UploadFile', params, False, raw, ms)
        return False, 'תשובה לא מובנת מימות: %s' % raw[:160]
    ok = str(res.get('responseStatus') or '').upper() == 'OK'
    _trace('UploadFile', params, ok, raw, ms)
    return (True, res) if ok else (False, 'ימות המשיח: %s' % (res.get('message') or raw[:160]))


def send_tts(phone, text, timeout=35, voice='', engine='', gvoice='', gstyle='', fallback=True, gmodel='', hints=None):
    """הודעה קולית: מעלה את ההודעה לתיקיית הטלפון ומתקשר אליו.
    engine='gemini' — קול אנושי מ-Gemini (קובץ WAV); אחרת קובץ TTS של ימות."""
    ok, n = next_msg_num(phone, voice)
    if not ok:
        return False, n
    used = 'yemot'
    if engine == 'gemini':
        import gemini_tts as _g
        okg, wav = _g.synth(text, gvoice, gstyle, trace=_trace, model=gmodel, hints=hints_for(text, hints))
        if okg:
            name = '%03d.wav' % n
            ok, res = upload_file('ivr2:/Phone/%s/%s' % (phone, name), wav, name)
            if ok:
                used = 'gemini'
            elif not fallback:
                return False, 'העלאת הקול האנושי נכשלה — ' + str(res)
        elif not fallback:
            return False, str(wav)
    if used == 'yemot':
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
    return True, {'file': name, 'campaignId': res.get('campaignId') or '', 'callerId': res.get('callerId') or '', 'engine': used}


def send_sms(phone, text, from_=''):
    p = {'phones': phone, 'message': text, 'from': (from_ or _env('YEMOT_SMS_FROM') or SMS_FROM_DEFAULT).strip()}
    return call('SendSms', p)


def download(path, timeout=40):
    """תוכן קובץ במערכת (DownloadFile) — טקסט גולמי, לא JSON. נרשם בלוג."""
    if not configured():
        return False, 'ימות המשיח לא מוגדר ב-Render'
    params = {'path': path}
    t0 = time.time()
    req = urllib.request.Request(_base() + 'DownloadFile?' + urllib.parse.urlencode(dict(params, token=_token())),
                                 headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
    except Exception as e:
        _trace('DownloadFile', params, False, str(e), (time.time() - t0) * 1000)
        return False, 'הורדת הקובץ נכשלה: %s' % e
    ms = (time.time() - t0) * 1000
    st = ''
    if raw.lstrip().startswith('{'):
        try:
            st = str(json.loads(raw).get('responseStatus') or '').upper()
        except Exception:
            st = ''
    if st and st != 'OK':
        _trace('DownloadFile', params, False, raw, ms)
        try:
            msg = json.loads(raw).get('message') or raw[:160]
        except Exception:
            msg = raw[:160]
        return False, 'ימות המשיח: %s' % msg
    _trace('DownloadFile', params, True, raw, ms)
    return True, raw


def download_bin(path, timeout=60):
    """קובץ שמע מהמערכת (DownloadFile) — בתים, לא טקסט. (False, הודעה) אם ימות החזירו שגיאה."""
    if not configured():
        return False, 'ימות המשיח לא מוגדר ב-Render'
    params = {'path': path}
    t0 = time.time()
    req = urllib.request.Request(_base() + 'DownloadFile?' + urllib.parse.urlencode(dict(params, token=_token())),
                                 headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
    except Exception as e:
        _trace('DownloadFile', params, False, str(e), (time.time() - t0) * 1000)
        return False, 'הורדת הקובץ נכשלה: %s' % e
    ms = (time.time() - t0) * 1000
    if data[:1] == b'{':
        try:
            res = json.loads(data.decode('utf-8', 'replace'))
            _trace('DownloadFile', params, False, data[:300].decode('utf-8', 'replace'), ms)
            return False, 'ימות המשיח: %s' % (res.get('message') or 'שגיאה')
        except Exception:
            pass
    _trace('DownloadFile', params, True, '(%d KB)' % (len(data) // 1024), ms)
    return True, data


def norm_ext(path):
    """'5' / '/5' / 'ivr2:5' / 'ivr2:/5/' -> 'ivr2:/5'"""
    p = (path or '').strip().replace('\\', '/')
    p = re.sub(r'^ivr2:', '', p).strip('/')
    return 'ivr2:/' + p if p else ''


def parse_ymgr(text):
    out = []
    for ln in (text or '').replace('\r', '').split('\n'):
        if '#' not in ln:
            continue
        rec = {}
        for part in ln.split('%'):
            if '#' in part:
                k, v = part.split('#', 1)
                rec[k.strip()] = v.strip()
        if rec.get('Phone') or rec.get('CallId'):
            out.append(rec)
    return out


def _dt(date_s, time_s):
    import datetime as _d
    try:
        return _d.datetime.strptime('%s %s' % (date_s, time_s), '%d/%m/%Y %H:%M:%S')
    except ValueError:
        return None


def group_calls(recs):
    """השורות -> שיחות: לכל CallId — הטלפון, התחלה/סוף, כמה שמע (main), לאיזו שלוחה עבר."""
    calls = {}
    order = []
    for r in recs:
        cid = r.get('CallId') or ('%s|%s|%s' % (r.get('Phone'), r.get('EnterDate'), r.get('EnterTime')))
        c = calls.get(cid)
        if not c:
            c = {'call_id': cid, 'phone': r.get('Phone') or '', 'date': r.get('EnterDate') or '',
                 'start': r.get('EnterTime') or '', 'end': r.get('ExitTime') or '',
                 'incoming': r.get('IncomingDID') or '', 'listen': 0, 'total': 0, 'steps': []}
            calls[cid] = c; order.append(cid)
        try:
            secs = int(r.get('TimeTotal') or 0)
        except ValueError:
            secs = 0
        fol = r.get('Folder') or ''
        c['total'] += secs
        if fol == 'main':
            c['listen'] += secs
        c['steps'].append({'folder': fol, 'title': r.get('PathTitle') or '', 'start': r.get('EnterTime') or '',
                           'secs': secs, 'id': r.get('EnterId') or ''})
        if (r.get('ExitTime') or '') > c['end']:
            c['end'] = r.get('ExitTime')
        if (r.get('EnterTime') or '') < c['start']:
            c['start'] = r.get('EnterTime')
        if r.get('IncomingDID'):
            c['incoming'] = r.get('IncomingDID')
    out = []
    for cid in order:
        c = calls[cid]
        other = [x for x in c['steps'] if x['folder'] not in ('main', '')]
        c['pressed'] = sorted({x['folder'] for x in other})
        c['pressed_secs'] = sum(x['secs'] for x in other)
        c['outgoing'] = not c['incoming']
        c['dt'] = _dt(c['date'], c['start'])
        out.append(c)
    return out


def month_calls(ym):
    """ym = 'YYYY-MM' -> (הצלחה, רשימת שיחות / שגיאה)"""
    ok, txt = download('ivr2:Log/LogFolderEnterExit-%s.ymgr' % ym)
    if not ok:
        if re.search(r'not exist|not found|does not|no such|לא קיים|לא נמצא', str(txt), re.I):
            return True, []
        return False, txt
    return True, group_calls(parse_ymgr(txt))


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
