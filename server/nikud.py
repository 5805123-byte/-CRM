# -*- coding: utf-8 -*-
"""ניקוד אוטומטי לטקסט של ההודעות הקוליות.

מאיר: "תוסיף שם אפשרות לנקד אוטומטי בתוך הטקסט — כל הטקסט, או מילה, או משפט מסוים
בלבד (לפעמים במשפחות הוא לא אומר נורמלי)".

שני ספקים, לפי הסדר:
  1. הנקדן של דיקטה (nakdan.dicta.org.il) — בלי מפתח. כתובת אחרת: DICTA_URL ב-Render.
  2. Gemini (אם GEMINI_API_KEY מוגדר) — "הוסף ניקוד בלבד".
בדיקת בטיחות: אחרי הסרת הניקוד התוצאה חייבת להיות זהה למקור — אחרת היא נדחית,
כך שהניקוד לעולם לא משנה מילים.
"""
import threading
import json
import os
import re
import time
import urllib.error
import urllib.request

_NIQ = re.compile('[֑-ׇ]')        # ניקוד וטעמים
DICTA_URLS = ['https://nakdan-api.dicta.org.il/api', 'https://nakdan-5-3.loadbalancer.dicta.org.il/api',
              'https://nakdan-u1-0.loadbalancer.dicta.org.il/api']
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 KollelChatzosCRM/1.0'


def strip(t):
    return _NIQ.sub('', t or '')


def _same(a, b):
    n = lambda x: re.sub(r'\s+', ' ', strip(x).replace('|', '')).strip()
    return n(a) == n(b)


def _post(url, body, headers=None, timeout=40):
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers=dict({'Content-Type': 'application/json', 'User-Agent': UA}, **(headers or {})))
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace'), (time.time() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace'), (time.time() - t0) * 1000
    except Exception as e:
        return 0, str(e), (time.time() - t0) * 1000


def _opt(o):
    """אפשרות ניקוד ראשונה מתוך הצורות השונות שדיקטה מחזירה."""
    if isinstance(o, str):
        return o
    if isinstance(o, list) and o:
        return _opt(o[0])
    if isinstance(o, dict):
        for k in ('w', 'word', 'nikud', 'text'):
            if isinstance(o.get(k), str):
                return o[k]
    return ''


def _dicta_join(res, text=''):
    """מחבר את התשובה של דיקטה לטקסט מנוקד. יש שתי צורות: הישנה ([{word, options}]) והחדשה
    ({"data": [{"nakdan": {"word", "options": [{"w": ...}]}}]}). כדי לא להיות תלויים בצורה של
    הרווחים והסימנים, כל מילה מנוקדת מוצבת במקומה בטקסט המקורי — רק אם בלי הניקוד היא זהה."""
    items = res.get('data') if isinstance(res, dict) else res
    if not isinstance(items, list):
        return ''
    pairs = []
    for it in items:
        if not isinstance(it, dict):
            continue
        nk = it.get('nakdan') if isinstance(it.get('nakdan'), dict) else it
        w = nk.get('word') or nk.get('str') or it.get('word') or ''
        if nk.get('sep') or it.get('sep'):
            continue
        opts = nk.get('options')
        if opts is None and not isinstance(it.get('nakdan'), dict):
            opts = it.get('nakdan')
        v = (_opt(opts) or '').replace('|', '')
        if w and v:
            pairs.append((w, v))
    if not text:
        return ''.join(v for _, v in pairs)
    out, pos = [], 0
    for w, v in pairs:
        i = text.find(w, pos)
        if i < 0:
            continue
        out.append(text[pos:i])
        out.append(v if strip(v) == w else w)
        pos = i + len(w)
    out.append(text[pos:])
    return ''.join(out)


_GOOD = {'url': ''}      # הכתובת של דיקטה שענתה אחרונה — מנסים אותה ראשונה


def _dicta_urls():
    urls = ([os.environ['DICTA_URL'].strip()] if (os.environ.get('DICTA_URL') or '').strip() else []) + DICTA_URLS
    if _GOOD['url'] in urls:
        urls = [_GOOD['url']] + [u for u in urls if u != _GOOD['url']]
    return urls


def dicta_fast(text, trace=None, timeout=7):
    """מאיר: "זה גם מחכה מידי הרבה זמן לראות מה יקריא לו" — לתצוגה: כל הכתובות של דיקטה במקביל,
    הראשונה שעונה נכון קובעת, ובכל מקרה לא יותר מ-7 שניות."""
    import queue
    q = queue.Queue()
    urls = _dicta_urls()
    body = {'task': 'nakdan', 'data': text, 'genre': 'modern', 'addmorph': False, 'keepqq': False,
            'nodageshdefmem': False, 'patachma': False, 'keepmetagim': True, 'useTokenization': True}

    def one(u):
        code, raw, ms = _post(u, body, timeout=timeout)
        out = ''
        if code == 200:
            try:
                out = _dicta_join(json.loads(raw), text)
            except Exception:
                out = ''
        good = bool(out) and _same(out, text) and bool(_NIQ.search(out))
        q.put((u, good, out, raw, ms))
    for u in urls:
        threading.Thread(target=one, args=(u,), daemon=True).start()
    end = time.time() + timeout + 0.5
    last = 'דיקטה לא ענתה בזמן'
    for _ in urls:
        try:
            u, good, out, raw, ms = q.get(timeout=max(0.1, end - time.time()))
        except Exception:
            break
        if good:
            _GOOD['url'] = u
            if trace:
                trace('Nakdan', {'url': u, 'chars': len(text), 'fast': 1}, True, json.dumps({'responseStatus': 'OK', 'message': out[:300]}, ensure_ascii=False), ms)
            return True, out
        last = 'דיקטה: %s' % (raw or '')[:100]
    return False, last


def dicta(text, trace=None):
    urls = _dicta_urls()
    body = {'task': 'nakdan', 'data': text, 'genre': 'modern', 'addmorph': False, 'keepqq': False,
            'nodageshdefmem': False, 'patachma': False, 'keepmetagim': True, 'useTokenization': True}
    last = ''
    for u in urls:
        code, raw, ms = _post(u, body, timeout=20)
        ok = False
        if code == 200:
            try:
                out = _dicta_join(json.loads(raw), text)
                ok = bool(out) and _same(out, text) and bool(_NIQ.search(out))
                if ok:
                    _GOOD['url'] = u
                    if trace:
                        trace('Nakdan', {'url': u, 'chars': len(text), 'text': text[:200]}, True, json.dumps({'responseStatus': 'OK', 'message': out[:300]}, ensure_ascii=False), ms)
                    return True, out
                last = ('דיקטה החזירה טקסט בלי ניקוד' if out and _same(out, text) else
                        'דיקטה החזירה טקסט שונה מהמקור' if out else 'תשובה לא מובנת מדיקטה')
            except Exception as e:
                last = 'תשובה לא מובנת מדיקטה: %s' % str(e)[:80]
        else:
            last = 'דיקטה %s: %s' % (code or '', raw[:120])
        if trace:
            trace('Nakdan', {'url': u, 'chars': len(text)}, False, raw[:800], ms)
    return False, last


def _opts_all(o):
    """כל אפשרויות הניקוד של מילה מתשובת דיקטה (בכל הצורות), בלי כפילויות."""
    out = []
    def add(v):
        v = (v or '').replace('|', '').strip()
        if v and v not in out:
            out.append(v)
    if isinstance(o, str):
        add(o)
    elif isinstance(o, list):
        for x in o:
            for v in _opts_all(x):
                add(v)
    elif isinstance(o, dict):
        for k in ('w', 'word', 'nikud', 'text'):
            if isinstance(o.get(k), str):
                add(o[k]); break
    return out


def options(word, context='', trace=None):
    """מאיר: "שזה יציע לי כמה אפשרויות על מילה" — כל צורות הניקוד שדיקטה מכירה למילה, לפי המשפט שבו היא נמצאת.
    -> רשימה (הראשונה = מה שדיקטה הייתה בוחרת)."""
    w = strip(word or '').strip()
    if not w or not re.search(r'[א-ת]', w):
        return []
    text = strip(context or '').strip() or w
    if w not in text:
        text = w
    urls = ([os.environ['DICTA_URL'].strip()] if (os.environ.get('DICTA_URL') or '').strip() else []) + DICTA_URLS
    body = {'task': 'nakdan', 'data': text, 'genre': 'modern', 'addmorph': False, 'keepqq': False,
            'nodageshdefmem': False, 'patachma': False, 'keepmetagim': True, 'useTokenization': True}
    for u in urls:
        code, raw, ms = _post(u, body, timeout=20)
        if code != 200:
            if trace:
                trace('Nakdan', {'url': u, 'options': w}, False, raw[:500], ms)
            continue
        try:
            res = json.loads(raw)
        except Exception:
            continue
        items = res.get('data') if isinstance(res, dict) else res
        out = []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            nk = it.get('nakdan') if isinstance(it.get('nakdan'), dict) else it
            ww = nk.get('word') or nk.get('str') or it.get('word') or ''
            if strip(ww) != w:
                continue
            opts = nk.get('options')
            if opts is None and not isinstance(it.get('nakdan'), dict):
                opts = it.get('nakdan')
            for v in _opts_all(opts):
                if strip(v) == w and v not in out:
                    out.append(v)
        if trace:
            trace('Nakdan', {'url': u, 'options': w}, True, json.dumps({'responseStatus': 'OK', 'message': ' / '.join(out)[:300]}, ensure_ascii=False), ms)
        if out:
            return out[:8]
    return []


DEF_TEXT_MODEL = 'gemini-3.8-flash'


def newer_model(code, raw):
    """מודל שגוגל הוציאו משימוש עונה 404 עם "Please update your code to use models/X" — מחזיר את X."""
    if code not in (400, 404):
        return ''
    m = re.search(r'use (?:the )?models/([\w.\-]+?)(?=[\s,;)]|\.\s|\.?$|\.?["\'])', raw or '')
    return m.group(1) if m else ''


def gemini(text, trace=None):
    key = (os.environ.get('GEMINI_API_KEY') or '').strip()
    if not key:
        return False, 'אין GEMINI_API_KEY'
    model = (os.environ.get('GEMINI_TEXT_MODEL') or DEF_TEXT_MODEL).strip()
    base = (os.environ.get('GEMINI_BASE') or 'https://generativelanguage.googleapis.com').rstrip('/')
    prompt = ('הוסף ניקוד מלא ומדויק לטקסט העברי הבא, כפי שהוא נקרא בעברית ישראלית מדוברת. '
              'אל תשנה, אל תוסיף ואל תוריד אף מילה, אות או סימן פיסוק. השאר כמו שהם מספרים, אותיות לועזיות '
              'וכל דבר בסוגריים מסולסלים כמו {שם}. החזר רק את הטקסט המנוקד, בלי שום הסבר.\n\n' + text)
    body = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'temperature': 0}}
    code, raw, ms = _post('%s/v1beta/models/%s:generateContent' % (base, model), body, {'x-goog-api-key': key}, timeout=60)
    nm = newer_model(code, raw)
    if nm and nm != model:
        # גוגל הוציאו את המודל משימוש ("no longer available… use models/X") — עוברים לחדש
        if trace:
            trace('GeminiNikud', {'model': model}, False, raw[:800], ms)
        model = nm
        code, raw, ms = _post('%s/v1beta/models/%s:generateContent' % (base, model), body, {'x-goog-api-key': key}, timeout=60)
    if code == 200:
        try:
            out = ''.join(p.get('text', '') for p in json.loads(raw)['candidates'][0]['content']['parts'] if not p.get('thought')).strip()
            if _same(out, text) and _NIQ.search(out):
                if trace:
                    trace('GeminiNikud', {'model': model, 'chars': len(text), 'text': text[:200]}, True, json.dumps({'responseStatus': 'OK', 'message': out[:300]}, ensure_ascii=False), ms)
                return True, out
            if trace:
                trace('GeminiNikud', {'model': model, 'chars': len(text)}, False, json.dumps({'message': 'הטקסט השתנה — נדחה', 'got': out[:300]}, ensure_ascii=False), ms)
            return False, 'Gemini שינה את הטקסט — לא נוקד'
        except Exception as e:
            if trace:
                trace('GeminiNikud', {'model': model}, False, raw[:800], ms)
            return False, 'תשובה לא מובנת מ-Gemini: %s' % str(e)[:80]
    if trace:
        trace('GeminiNikud', {'model': model}, False, raw[:800], ms)
    return False, 'Gemini %s' % code


def vocalize(text, trace=None, fast=False):
    """-> (הצלחה, טקסט מנוקד או שגיאה, ספק). טקסט שכבר מנוקד מנוקד מחדש.
    fast — לתצוגה: דיקטה במקביל, עד 7 שניות, בלי Gemini."""
    text = text or ''
    if not re.search(r'[א-ת]', text):
        return True, text, ''
    # {שם}, {סכום}, {קישור} — לא לגעת: מוחלפים זמנית בסימון לועזי ומוחזרים אחרי הניקוד
    ph = []

    def keep(m):
        ph.append(m.group(0))
        return 'QQ%dQQ' % (len(ph) - 1)
    # הסימונים נשמרים לפני הסרת הניקוד — כך מילה מהמילון (מנוקדת כמו שמאיר כתב) לא משתנה
    base = strip(re.sub(r'\{[^{}]*\}', keep, text))

    def back(t):
        return re.sub(r'QQ(\d+)QQ', lambda m: ph[int(m.group(1))] if int(m.group(1)) < len(ph) else m.group(0), t)
    ok, out = dicta_fast(base, trace) if fast else dicta(base, trace)
    if ok:
        return True, back(out), 'דיקטה'
    if fast:
        return False, out, ''
    ok2, out2 = gemini(base, trace)
    if ok2:
        return True, back(out2), 'Gemini'
    return False, out if not (os.environ.get('GEMINI_API_KEY') or '').strip() else (out + ' · ' + out2), ''


# מאיר: "השמעת מילה לא עובדת טוב, וגם הניקוד… זה בקושי משתנה כשאני משמיע או מנסה לנקד".
# Gemini כמעט לא מתייחס לניקוד, אבל כן מקשיב להנחיית הגייה באותיות לטיניות. מהמילה המנוקדת
# בונים תעתיק (קְלֶפֶּר → kleper), והוא נשלח כהנחיה ("the Hebrew word X is pronounced ...").
_V = {'ְ': '', 'ֱ': 'e', 'ֲ': 'a', 'ֳ': 'o', 'ִ': 'i', 'ֵ': 'e', 'ֶ': 'e',
      'ַ': 'a', 'ָ': 'a', 'ֹ': 'o', 'ֺ': 'o', 'ֻ': 'u', 'ׇ': 'o'}
_C = {'א': '', 'ב': 'v', 'ג': 'g', 'ד': 'd', 'ה': 'h', 'ו': 'v', 'ז': 'z', 'ח': 'ch', 'ט': 't', 'י': 'y',
      'כ': 'ch', 'ך': 'ch', 'ל': 'l', 'מ': 'm', 'ם': 'm', 'נ': 'n', 'ן': 'n', 'ס': 's', 'ע': '', 'פ': 'f', 'ף': 'f',
      'צ': 'ts', 'ץ': 'ts', 'ק': 'k', 'ר': 'r', 'ש': 'sh', 'ת': 't'}
_HARD = {'ב': 'b', 'כ': 'k', 'ך': 'k', 'פ': 'p'}


def translit(word):
    """מילה מנוקדת -> תעתיק לטיני פשוט (הגייה ישראלית). בלי ניקוד — '' (אין ממה ללמוד)."""
    w = str(word or '').replace('׳', "'").replace('״', '"')
    if not re.search(r'[ְ-ׇּׁׂ]', w):
        return ''
    units = []
    for ch in w:
        if 'א' <= ch <= 'ת':
            units.append([ch, ''])
        elif units and ('֑' <= ch <= 'ׇ'):
            units[-1][1] += ch
    out = []
    prev_v = ''
    for i, (L, M) in enumerate(units):
        dag, last = 'ּ' in M, i == len(units) - 1
        v = next((_V[m] for m in M if m in _V), None)
        if L == 'ו' and v == 'o' and 'ֹ' in M and len(M.replace('ֹ', '')) == 0:
            out.append('o'); prev_v = 'o'; continue           # חולם מלא
        if L == 'ו' and dag and v is None:
            out.append('u'); prev_v = 'u'; continue            # שורוק
        if L == 'י' and v is None and prev_v in ('i', 'e'):
            continue                                            # י' אם קריאה
        if L == 'ה' and last and v is None:
            continue                                            # ה' בסוף בלי ניקוד
        if L == 'ש':
            c = 's' if 'ׂ' in M else 'sh'
        else:
            c = _HARD.get(L, _C.get(L, '')) if dag else _C.get(L, '')
        if L == 'ח' and last and v == 'a':
            out.append('ach'); prev_v = 'a'; continue          # פתח גנובה
        out.append(c + (v or ''))
        if v:
            prev_v = v
    return ''.join(out)
