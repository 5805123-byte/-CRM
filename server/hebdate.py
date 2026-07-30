# -*- coding: utf-8 -*-
"""המרת תאריך עברי (למשל "ג' אב") לתאריך לועזי של המופע הקרוב — לתזכורות פרנס יום."""
import re, datetime
try:
    from pyluach import dates
    OK = True
except Exception:
    OK = False

HMONTHS = {'ניסן':1,'אייר':2,'סיון':3,'סיוון':3,'תמוז':4,'אב':5,'אלול':6,'תשרי':7,
           'חשון':8,'חשוון':8,'מרחשון':8,'כסלו':9,'טבת':10,'שבט':11,
           'אדר':12,'אדר א':12,'אדר ב':13,'אדר א׳':12,'אדר ב׳':13}
GEM = {'א':1,'ב':2,'ג':3,'ד':4,'ה':5,'ו':6,'ז':7,'ח':8,'ט':9,'י':10,'כ':20,'ל':30}

def _day(s):
    s = re.sub(r'[\"\'׳״־]', '', s).strip()
    return sum(GEM.get(c, 0) for c in s)

def heb_to_greg(text, today=None):
    """מקבל טקסט עברי; מחזיר datetime.date של המופע הבא (>= היום), או None."""
    if not OK or not text:
        return None
    today = today or datetime.date.today()
    txt = re.sub(r'[\"\']', '', str(text)).strip()
    parts = txt.split()
    if len(parts) < 2:
        return None
    d = _day(parts[0]); mon = ' '.join(parts[1:]).strip()
    m = HMONTHS.get(mon)
    if not m or not (1 <= d <= 30):
        return None
    ty = dates.GregorianDate(today.year, today.month, today.day).to_heb().year
    for yr in (ty, ty + 1):
        try:
            g = dates.HebrewDate(yr, m, d).to_pydate()
            if g >= today:
                return g
        except Exception:
            pass
    return None

def week_before(text, today=None):
    """תאריך התזכורת — 7 ימים לפני הלילה. מחזיר 'YYYY-MM-DD' או None."""
    g = heb_to_greg(text, today)
    if not g:
        return None
    return (g - datetime.timedelta(days=7)).isoformat()
