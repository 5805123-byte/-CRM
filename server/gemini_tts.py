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
# קולות מובנים של Gemini — שם, ותיאור בעברית לבחירה במסך
VOICES = [('Kore', 'קורה — אישה, יציב וברור'), ('Aoede', 'איודה — אישה, קליל'), ('Leda', 'לדה — אישה, צעיר'),
          ('Zephyr', 'זפיר — אישה, בהיר'), ('Sulafat', 'סולפת — אישה, חם'),
          ('Charon', 'כרון — גבר, מסביר'), ('Orus', 'אורוס — גבר, יציב'), ('Iapetus', 'יאפטוס — גבר, צלול'),
          ('Algieba', 'אלגיבה — גבר, חלק'), ('Puck', 'פאק — גבר, עליז')]
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


def synth(text, voice='Kore', style='', trace=None, tries=3):
    """-> (הצלחה, WAV או הודעת שגיאה). trace(method, params, ok, raw, ms) — ללוג של ימות."""
    if not configured():
        return False, 'Gemini לא מוגדר ב-Render (GEMINI_API_KEY)'
    model = _env('GEMINI_TTS_MODEL', DEF_MODEL)
    prompt = ((style or DEF_STYLE).strip() + '\n' + text).strip()
    body = {'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'responseModalities': ['AUDIO'],
                                 'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': voice or 'Kore'}}}}}
    url = _env('GEMINI_BASE', 'https://generativelanguage.googleapis.com').rstrip('/') + '/v1beta/models/%s:generateContent' % model
    params = {'model': model, 'voice': voice, 'chars': len(text), 'text': text[:400]}
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
        if code in (429, 500, 503) and attempt < tries - 1:
            wait = 8 * (attempt + 1)
            m = re.search(r'"retryDelay":\s*"(\d+)s"', raw)
            if m:
                wait = min(60, int(m.group(1)) + 1)
            time.sleep(wait)
            continue
        break
    return False, last
