# -*- coding: utf-8 -*-
"""קול אנושי להודעות הקוליות — Gemini TTS (Google AI Studio).

מאיר: "נעשה דרך AI סטודיו של גימני עם ה-API… ליצור הודעה, להוריד ולהעלות לימות".
הטקסט נשלח ל-Gemini, חוזר שמע (PCM 24kHz), מומר כאן ל-WAV טלפוני (8kHz, מונו,
16 ביט) ומועלה לתיקייה של הטלפון בימות במקום קובץ ה-TTS.

הגדרה ב-Render בלבד (לא בקוד, לא בקובץ ולא בהודעות):
    GEMINI_API_KEY     המפתח מ-https://aistudio.google.com/apikey
אופציונלי:
    GEMINI_TTS_MODEL   ברירת מחדל gemini-2.5-flash-preview-tts
"""
import array
import base64
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import wave

DEF_MODEL = 'gemini-2.5-flash-preview-tts'
# מאיר: "תשים רק גברים בלבד במערכת" — 16 הקולות הגבריים של Gemini, שם ותיאור בעברית
VOICES = [('Charon', 'כרון — מסביר'), ('Orus', 'אורוס — יציב'), ('Iapetus', 'יאפטוס — צלול'),
          ('Algieba', 'אלגיבה — חלק'), ('Puck', 'פאק — עליז'), ('Fenrir', 'פנריר — נלהב'),
          ('Enceladus', 'אנקלדוס — נושם, שקט'), ('Umbriel', 'אומבריאל — נינוח'), ('Algenib', 'אלגניב — מחוספס'),
          ('Rasalgethi', 'רסלגתי — מסביר'), ('Alnilam', 'אלנילם — נחרץ'), ('Schedar', 'שדר — אחיד'),
          ('Achird', 'אכירד — ידידותי'), ('Zubenelgenubi', 'זובנלגנובי — יומיומי'),
          ('Sadachbia', 'סדכביה — חי ותוסס'), ('Sadaltager', 'סדלטגר — בקיא, סמכותי')]
DEF_VOICE = 'Charon'


def voice_ok(v):
    """קול שנשמר בעבר ואינו ברשימה (למשל קול נשי) -> קול ברירת המחדל."""
    return v if v in [k for k, _ in VOICES] else DEF_VOICE


# מודל הקול: Flash (ברירת מחדל) או Pro — איכות גבוהה יותר, בערך כפול במחיר
MODELS = [('', 'Flash — רגיל'), ('gemini-2.5-pro-preview-tts', 'Pro — טבעי יותר (×2 מחיר)')]
DEF_STYLE = 'Read the following Hebrew text aloud in a warm, calm and respectful voice, at a natural pace:'


def _env(k, d=''):
    return (os.environ.get(k) or d).strip()


def configured():
    return bool(_env('GEMINI_API_KEY'))


def _to_wav8k(pcm, rate):
    """PCM 16 ביט מונו -> WAV של 8kHz (איכות טלפון, קובץ קטן)."""
    a = array.array('h')
    a.frombytes(pcm[:len(pcm) - (len(pcm) % 2)])
    if sys.byteorder != 'little':
        a.byteswap()
    f = rate // 8000 if rate % 8000 == 0 and rate > 8000 else 1
    if f > 1:
        out = array.array('h', (int(sum(a[i:i + f]) / f) for i in range(0, len(a) - f + 1, f)))
        rate = 8000
    else:
        out = a
    if sys.byteorder != 'little':
        out.byteswap()
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())
    return buf.getvalue()


def synth(text, voice=DEF_VOICE, style='', trace=None, tries=3, model='', hints=None):
    """-> (הצלחה, WAV או הודעת שגיאה). trace(method, params, ok, raw, ms) — ללוג של ימות."""
    if not configured():
        return False, 'Gemini לא מוגדר ב-Render (GEMINI_API_KEY)'
    model = (model if model in [k for k, _ in MODELS if k] else '') or _env('GEMINI_TTS_MODEL', DEF_MODEL)
    # הנחיית ההגייה לפני ההוראה "הקרא את הטקסט הבא" — כדי שלא תוקרא
    prompt = (hint_text(hints) + '\n' + (style or DEF_STYLE).strip() + '\n' + text).strip()
    body = {'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'responseModalities': ['AUDIO'],
                                 'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voice_ok(voice)}}}}}
    url = _env('GEMINI_BASE', 'https://generativelanguage.googleapis.com').rstrip('/') + '/v1beta/models/%s:generateContent' % model
    params = {'model': model, 'voice': voice_ok(voice), 'chars': len(text), 'text': text[:400]}
    last = ''
    for attempt in range(tries):
        t0 = time.time()
        req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                     headers={'Content-Type': 'application/json', 'x-goog-api-key': _env('GEMINI_API_KEY')})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read().decode('utf-8', 'replace')
            code = 200
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', 'replace'); code = e.code
        except Exception as e:
            raw = str(e); code = 0
        ms = (time.time() - t0) * 1000
        if code == 200:
            try:
                res = json.loads(raw)
                part = res['candidates'][0]['content']['parts'][0]['inlineData']
                pcm = base64.b64decode(part['data'])
                m = re.search(r'rate=(\d+)', part.get('mimeType') or '')
                wav = _to_wav8k(pcm, int(m.group(1)) if m else 24000)
                if trace:
                    trace('GeminiTTS', params, True, json.dumps({'responseStatus': 'OK', 'message': 'נוצר שמע · %.1f שניות' % (len(wav) / 16000.0),
                                                                  'mimeType': part.get('mimeType')}, ensure_ascii=False), ms)
                return True, wav
            except Exception as e:
                last = 'תשובה לא צפויה מ-Gemini: %s' % str(e)[:120]
                if trace:
                    trace('GeminiTTS', params, False, raw[:1500], ms)
                return False, last
        # שגיאה — שומרים את ההודעה (בלי המפתח) ובעומס מחכים ומנסים שוב
        try:
            msg = json.loads(raw).get('error', {}).get('message') or raw[:200]
        except Exception:
            msg = raw[:200]
        last = 'Gemini %s: %s' % (code or '', msg)
        if trace:
            trace('GeminiTTS', params, False, raw[:1500], ms)
        # המודל הוצא משימוש ("no longer available… use models/X") — עוברים לחדש שגוגל מציינים
        import nikud as _nk
        nm = _nk.newer_model(code, raw)
        if nm and nm != model and attempt < tries - 1:
            model = nm
            params = dict(params, model=model)
            url = url.rsplit('/models/', 1)[0] + '/models/%s:generateContent' % model
            continue
        if code in (429, 500, 503) and attempt < tries - 1:
            wait = 8 * (attempt + 1)
            m = re.search(r'"retryDelay":\s*"(\d+)s"', raw)
            if m:
                wait = min(60, int(m.group(1)) + 1)
            time.sleep(wait)
            continue
        break
    return False, last



def _frames(wav):
    """WAV -> (קצב, בתים של PCM 16 ביט מונו)."""
    with wave.open(io.BytesIO(wav), 'rb') as w:
        return w.getframerate(), w.readframes(w.getnframes())


def hint_text(hints):
    """מאיר: "שזה יהיה קול של ג'ימיני, רק עם הגייה נכונה" — הנחיית הגייה לפני הטקסט (לא מוקראת)."""
    hs = [h for h in (hints or []) if h.get('latin')]
    if not hs:
        return ''
    return ('Pronunciation guide (do not read this line aloud): ' +
            '; '.join('%s is pronounced "%s"' % (h.get('nikud') or h['word'], h['latin']) for h in hs) + '.')


def transcribe_word(wav, word, trace=None):
    """הקלטה של מילה אחת (שם משפחה) -> איך אומרים אותה: ניקוד מלא + תעתיק לטיני עם הטעמה.
    ההקלטה משמשת רק ללמוד את ההגייה — ההודעה עצמה נשארת בקול של Gemini."""
    import nikud as _nk
    if not configured():
        return False, 'Gemini לא מוגדר ב-Render (GEMINI_API_KEY)'
    model = (os.environ.get('GEMINI_TEXT_MODEL') or _nk.DEF_TEXT_MODEL).strip()
    ask = ('This audio is one Hebrew word, a family name written "%s". Listen carefully to exactly how the speaker pronounces it '
           '(vowels, stress). Reply with JSON only: {"nikud": the word written in Hebrew letters with full niqqud exactly as pronounced, '
           '"latin": simple English transliteration split into syllables with hyphens and the stressed syllable in CAPITALS}.') % word
    body = {'contents': [{'parts': [{'text': ask}, {'inlineData': {'mimeType': 'audio/wav', 'data': base64.b64encode(wav).decode('ascii')}}]}],
            'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0}}
    base = _env('GEMINI_BASE', 'https://generativelanguage.googleapis.com').rstrip('/')
    for _try in range(2):
        code, raw, ms = _nk._post('%s/v1beta/models/%s:generateContent' % (base, model), body, {'x-goog-api-key': _env('GEMINI_API_KEY')}, timeout=60)
        nm = _nk.newer_model(code, raw)
        if nm and nm != model:
            model = nm
            continue
        break
    try:
        res = json.loads(raw)
        txt = res['candidates'][0]['content']['parts'][0]['text']
        o = json.loads(re.search(r'\{.*\}', txt, re.S).group(0))
        out = {'nikud': str(o.get('nikud') or '').strip()[:60], 'latin': str(o.get('latin') or '').strip()[:60]}
        if trace:
            trace('GeminiHear', {'model': model, 'word': word}, True, json.dumps(dict(out, responseStatus='OK'), ensure_ascii=False), ms)
        if not out['latin']:
            return False, 'לא הבנתי את ההקלטה — נסה שוב'
        return True, out
    except Exception:
        if trace:
            trace('GeminiHear', {'model': model, 'word': word}, False, (raw or '')[:800], ms)
        return False, 'Gemini לא הבין את ההקלטה (%s)' % (code or '')
