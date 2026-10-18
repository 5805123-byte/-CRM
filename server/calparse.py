# -*- coding: utf-8 -*-
"""📋 מאיר: "שאני יכול להדביק לבד ביומן — משימות, פגישות ואירועים, והמערכת תכניס לתאריך שצריך".
טקסט (או תמונה של הזמנה) → רשימת פריטים {date, time, kind, title, place}. עם GEMINI_API_KEY — Gemini קורא
את הטקסט / התמונה; בלי — זיהוי פשוט לפי שורות (תאריך לועזי / עברי, שעה)."""
import os, re, json, datetime
import nikud, hebdate

KINDS = ('event', 'followup', 'email', 'other')
_HM = '|'.join(sorted(hebdate.HMONTHS, key=len, reverse=True))
_HEB_RX = re.compile(r"(?<![א-ת])([א-ל][\"'׳״]?[א-ט]?[\"'׳״]?)\s+(?:ב|ל)?(%s)(?![א-ת])" % _HM)
_GREG_RX = re.compile(r'(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?!\d)')
_TIME_RX = re.compile(r'(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)')
_WD = {'היום': 0, 'מחר': 1, 'מחרתיים': 2}


def _greg(m, today):
    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    y = int(y) + (2000 if y and len(y) == 2 else 0) if y else today.year
    try:
        g = datetime.date(y, mo, d)
    except ValueError:
        return None
    if not m.group(3) and g < today - datetime.timedelta(days=30):
        g = g.replace(year=g.year + 1)
    return g


def heb(text, today=None):
    m = _HEB_RX.search(text or '')
    if not m:
        return None
    return hebdate.heb_to_greg(m.group(1) + ' ' + m.group(2), today)


def _kind(t):
    if re.search(r'חתונ|בר.?מצו|בת.?מצו|ברית|שבע.?ברכות|אירוסין|וורט|קידוש|בר מצוה|שמחה|הזמנ|אולם|אולמי', t):
        return 'event'
    if re.search(r'להתקשר|לטלפן|שיחה|לחזור אל', t):
        return 'followup'
    if re.search(r'מייל|אימייל|וואטסאפ|לשלוח', t):
        return 'email'
    return 'other'


def simple(text, today=None):
    """בלי Gemini: כל שורה עם תאריך היא פריט; הזמנה (הרבה שורות, תאריך אחד) — פריט אחד."""
    today = today or hebdate.il_today()
    lines = [l.strip(' \t-•*') for l in (text or '').splitlines() if l.strip()]
    hits = [l for l in lines if _GREG_RX.search(l) or _HEB_RX.search(l) or any(w in l for w in _WD)]
    whole = len(hits) <= 1 and len(lines) > 2
    out = []
    for l in ([' '.join(lines)] if whole else hits):
        g = None
        m = _GREG_RX.search(l)
        if m:
            g = _greg(m, today)
        if not g:
            g = heb(l, today)
        if not g:
            for w, n in _WD.items():
                if w in l:
                    g = today + datetime.timedelta(days=n)
        t = _TIME_RX.search(l)
        # "פגישה עם רבינוביץ 25.10 בשעה 14:30" → "פגישה עם רבינוביץ" (התאריך והשעה כבר בשדות)
        title, place = re.sub(r'\s+', ' ', _TIME_RX.sub('', _GREG_RX.sub('', _HEB_RX.sub('', l)))
                              .replace('בשעה', '').replace('ב-', ' ')).strip(' ,-–') or l, ''
        for w in _WD:
            title = re.sub(r'(?<![א-ת])%s(?![א-ת])' % w, '', title).strip() or title
        title = re.sub(r'\s{2,}', ' ', title).strip(' ,-–')
        if whole:
            # הזמנה: "בר מצווה — <השורה שאחרי> (<השורה האחרונה>)", המקום — שורת האולם / הרחוב
            L2 = [x for x in lines if not re.search(r'סיעתא|בס"ד|בעזרת ה|^ב"ה$', x)]
            ix = next((i for i, x in enumerate(L2) if re.search(r'בר.?מצו|בת.?מצו|חתונ|ברית|אירוסין|שבע.?ברכות', x)), -1)
            if ix >= 0:
                kw = re.search(r'בר.?מצו\S*|בת.?מצו\S*|חתונ\S*|ברית\S*|אירוסין|שבע.?ברכות', L2[ix]).group(0)
                kw = {'חתונת': 'חתונה', 'חתונתם': 'חתונה'}.get(kw, kw)
                nm = re.sub(r'["\'׳״]?נ["\'׳״]?י$|נ"י|ני"ו', '', L2[ix + 1]).strip() if ix + 1 < len(L2) else ''
                title = kw.replace('מצוה', 'מצווה') + (' — ' + nm if nm and len(nm) < 40 else '') + (' (' + L2[-1] + ')' if L2[-1] != L2[ix] and len(L2[-1]) < 50 else '')
            else:
                title = L2[0] if L2 else lines[0]
            place = next((re.sub(r'^\s*(ב|יתקיים |תתקיים )', '', x) for x in lines if re.search(r'אולם|אולמי|רחוב|רח\'|היכל|בית הכנסת', x)), '')
        out.append({'date': g.isoformat() if g else '', 'time': ('%02d:%s' % (int(t.group(1)), t.group(2))) if t else '',
                    'kind': _kind(l), 'title': title[:200], 'place': place[:200]})
    return out


PROMPT = """אתה עוזר שמכניס דברים ליומן. היום: {today} ({heb}).
מהטקסט {img}למטה — הוצא כל משימה, פגישה או אירוע שיש לו תאריך (או יום יחסי כמו "מחר", "יום שלישי הבא").
הזמנה לשמחה (חתונה, בר מצווה, ברית וכו') = פריט אחד מסוג event: כותרת קצרה כמו "בר מצווה — אלחנן בן יוסף חיים ומרים חסידי",
השעה — של קבלת הפנים / תחילת האירוע, והמקום — שם האולם והכתובת המלאה.
החזר JSON בלבד — מערך של אובייקטים:
{{"date":"YYYY-MM-DD","heb":"התאריך העברי כפי שנכתב, למשל ח' חשון תשפ\\"ז, או ריק","time":"HH:MM או ריק",
"kind":"event (שמחה/אירוע) | followup (להתקשר) | email (לשלוח מייל/וואטסאפ) | other (משימה/פגישה)",
"title":"מה — קצר וברור, בעברית","place":"מקום/כתובת או ריק"}}
אם כתוב גם תאריך עברי וגם לועזי — ה-date הוא הלועזי שכתוב. אל תמציא פריטים בלי תאריך."""


def gemini(text, image=None, today=None):
    key = (os.environ.get('GEMINI_API_KEY') or '').strip()
    if not key:
        return None, 'אין GEMINI_API_KEY'
    today = today or hebdate.il_today()
    try:
        from pyluach import dates
        h = dates.GregorianDate(today.year, today.month, today.day).to_heb()
        hs = hebdate.hq(h.hebrew_date_string())
    except Exception:
        hs = ''
    days = ['שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת', 'ראשון']
    parts = [{'text': PROMPT.format(today=today.isoformat() + ' יום ' + days[today.weekday()], heb=hs,
                                    img='ומהתמונה ' if image else '') + '\n\n' + (text or '')}]
    if image:
        m = re.match(r'data:(image/[\w.+-]+);base64,(.+)$', image, re.S)
        if m:
            parts.append({'inline_data': {'mime_type': m.group(1), 'data': m.group(2)}})
    model = (os.environ.get('GEMINI_TEXT_MODEL') or nikud.DEF_TEXT_MODEL).strip()
    base = (os.environ.get('GEMINI_BASE') or 'https://generativelanguage.googleapis.com').rstrip('/')
    body = {'contents': [{'parts': parts}], 'generationConfig': {'temperature': 0, 'responseMimeType': 'application/json'}}
    url = lambda md: '%s/v1beta/models/%s:generateContent' % (base, md)
    code, raw, _ = nikud._post(url(model), body, {'x-goog-api-key': key}, timeout=60)
    nm = nikud.newer_model(code, raw)
    if nm and nm != model:
        code, raw, _ = nikud._post(url(nm), body, {'x-goog-api-key': key}, timeout=60)
    if code != 200:
        return None, 'Gemini %s' % code
    try:
        out = ''.join(p.get('text', '') for p in json.loads(raw)['candidates'][0]['content']['parts'] if not p.get('thought'))
        out = re.sub(r'^```(?:json)?|```$', '', out.strip()).strip()
        L = json.loads(out)
        if isinstance(L, dict):
            L = L.get('items') or [L]
    except Exception as e:
        return None, 'תשובה לא מובנת מ-Gemini: %s' % str(e)[:80]
    res = []
    for x in L if isinstance(L, list) else []:
        if not isinstance(x, dict):
            continue
        d = str(x.get('date') or '')[:10]
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', d):
            g = heb(str(x.get('heb') or ''), today)
            d = g.isoformat() if g else ''
        t = str(x.get('time') or '')[:5]
        res.append({'date': d, 'time': t if re.fullmatch(r'\d{2}:\d{2}', t) else '',
                    'kind': x.get('kind') if x.get('kind') in KINDS else 'other',
                    'title': str(x.get('title') or '').strip()[:200], 'place': str(x.get('place') or '').strip()[:200],
                    'heb': str(x.get('heb') or '')[:40]})
    return res, ''


def parse(text, image=None):
    items, err = gemini(text, image)
    if items is not None:
        return items, 'gemini', ''
    if image and not (text or '').strip():
        return [], '', err or 'כדי לקרוא תמונה צריך GEMINI_API_KEY'
    return simple(text), 'simple', err
