# -*- coding: utf-8 -*-
"""מלגות אברכים — קריאת "סיכום מלגות אברכים" החודשי (PDF) ורשימות מלגות חגים.

מאיר: "חלון מיוחד שקוראים לזה אברכים, שם יהיה מרוכז כל הקבצי מלגות חודשיים
וגם מלגות חגים כפי מה שאעלה לך… תמיד שהכולל חצות יהיה מופרד לגמרי מכולל הוראה".

הדוח החודשי מגיע כ-PDF עם טקסט (לא סריקה). pypdf מוציא את הטקסט בסדר קצת
הפוך, ולכן הקריאה כאן היא לפי תבניות קבועות:
    כולל חצות ₪157,274כ"  סה· אברכים90          <- כותרת כולל
    19/25נוכחותאבלסון מאיר ₪1,956                 <- אברך: נוכחות, שם, סה"כ
    ·  95 :ליקוטי הלכות·  90 :ה" טור              <- רכיבי המלגה
    :כ לאברך"   |   ₪ 607 :לומד גם בחיים טובים    <- לומד גם בכולל אחר
רשימת חג (מלגות סוכות וכד') מגיעה כטקסט/CSV: "שם  סכום" בכל שורה.
"""
import re

KOLLELIM = ('חצות', 'הוראה', 'חיים טובים')
_HDR = re.compile(r'^(?:\(המשך\)\s*)?כולל\s+(חצות|הוראה|חיים טובים)\s+₪\s?([\d,]+)')
_AV = re.compile(r'^(\d+)/(\d+)נוכחות(.+?)\s+₪\s?([\d,]+)\s*$')
_AV_NOATT = re.compile(r'^([֐-׿][֐-׿\'" .\-]+?)\s+₪\s?([\d,]+)\s*$')
_ATT_ONLY = re.compile(r'^(\d+)/(\d+)נוכחות\s*$')
_AMT_ONLY = re.compile(r'^\s*₪\s?([\d,]+)\s*$')
_ALSO = re.compile(r'₪\s?([\d,]+)\s*:לומד גם ב(.+?)\s*$')
_COMP = re.compile(r'(-?\s?[\d,]+)\s*:\s*([^·]+)')
_PERIOD = re.compile(r'\((\d{2})/(\d{4})\)')


def _num(s):
    try:
        return float(str(s).replace(',', '').replace(' ', ''))
    except ValueError:
        return 0.0


def _label(s):
    s = re.sub(r'\s+', ' ', s).strip(' :·')
    w = s.split(' ')
    # תווית של שתי מילים שהתהפכה בחילוץ ('ה" טור' -> 'טור ה"')
    if len(w) == 2 and ('"' in w[0] or '״' in w[0]):
        w = w[::-1]
    return ' '.join(w)


def parse_monthly(text):
    """מחזיר (period 'YYYY-MM' או '', [{kollel,name,amount,att,details,also}], totals{kollel:amount})."""
    period = ''
    m = _PERIOD.search(text)
    if m:
        period = '%s-%s' % (m.group(2), m.group(1))
    rows, totals = [], {}
    kollel = ''
    cur = None
    pending_name = None
    for raw in text.split('\n'):
        ln = raw.strip()
        if not ln or ln.startswith('=====') or 'עמוד' in ln and 'מתוך' in ln:
            continue
        h = _HDR.match(ln)
        if h:
            kollel = h.group(1)
            totals.setdefault(kollel, _num(h.group(2)))
            cur = None; pending_name = None
            continue
        if not kollel or ln.startswith('סיכום מלגות') or ln.startswith('אברך שלומד') or ln.startswith('מחולק') or ln.startswith('סה'):
            continue
        a = _AV.match(ln)
        if a:
            cur = {'kollel': kollel, 'name': a.group(3).strip(), 'amount': _num(a.group(4)),
                   'att': '%s/%s' % (a.group(1), a.group(2)), 'details': [], 'also': ''}
            rows.append(cur); pending_name = None
            continue
        if pending_name is not None:
            t = _ATT_ONLY.match(ln)
            if t:
                pending_name['att'] = '%s/%s' % (t.group(1), t.group(2)); continue
            t = _AMT_ONLY.match(ln)
            if t:
                pending_name['amount'] = _num(t.group(1)); cur = pending_name; rows.append(cur); pending_name = None; continue
        also = _ALSO.search(ln)
        if also and cur:
            cur['also'] = 'לומד גם ב%s (₪%s)' % (also.group(2).strip(), also.group(1))
            continue
        if cur and _AMT_ONLY.match(ln):
            continue                      # סה"כ לאברך בשני כוללים — לא צריך
        if ':' in ln and re.search(r'\d', ln):
            if cur:
                if 'ניכויים' in ln or 'שונות' in ln:
                    ln = ln.replace('ניכויים /שונות', '').replace(': ניכויים', '').strip(' :')
                for amt, lab in _COMP.findall(ln):
                    lab = _label(lab)
                    if lab:
                        cur['details'].append('%s %s' % (lab, amt.replace(' ', '')))
            continue
        n = _AV_NOATT.match(ln)
        if n and not re.search(r'\d :', ln):
            cur = {'kollel': kollel, 'name': n.group(1).strip(), 'amount': _num(n.group(2)), 'att': '', 'details': [], 'also': ''}
            rows.append(cur); pending_name = None
            continue
        if re.match(r'^[֐-׿][֐-׿\'" .\-]+$', ln) and len(ln) < 40:
            pending_name = {'kollel': kollel, 'name': ln.strip(), 'amount': 0.0, 'att': '', 'details': [], 'also': ''}
            continue
    for r in rows:
        r['details'] = ' · '.join(r['details'])
    return period, rows, totals


def parse_list(text):
    """רשימת חג: 'שם  סכום' בכל שורה (טאב / כמה רווחים / פסיק). מחזיר [{name, amount}]."""
    out = []
    for raw in text.split('\n'):
        ln = raw.strip().strip('﻿')
        if not ln:
            continue
        m = re.match(r'^(?:\d+[.)]?\s+)?(.+?)[\t,;]+\s*₪?\s*(-?[\d,]+(?:\.\d+)?)\s*₪?\s*$', ln) or \
            re.match(r'^(?:\d+[.)]?\s+)?(.+?)\s{2,}₪?\s*(-?[\d,]+(?:\.\d+)?)\s*₪?\s*$', ln) or \
            re.match(r'^(?:\d+[.)]?\s+)?([֐-׿][^\d₪]*?)\s+₪?\s*(-?[\d,]+(?:\.\d+)?)\s*₪?\s*$', ln)
        if not m:
            continue
        name = m.group(1).strip(' -–·')
        if not name or name in ('סה"כ', 'סה״כ', 'שם האברך'):
            continue
        out.append({'name': name, 'amount': _num(m.group(2))})
    return out
