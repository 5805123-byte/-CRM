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

def hq(s):
    """אחידות בסימני הגרשיים — pyluach מחזיר גרשיים עבריים (״) והרשימות במסך משתמשות ב-".
    בלי הנרמול הזה 'תשפ״ו' ו-'תשפ"ו' נחשבות שתי שנים שונות והבורר קופץ לשנה הלא נכונה."""
    return (s or '').replace('״', '"').replace('׳', "'")

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

def greg_to_heb_monthyear(date_str):
    """מקבל '2026-07' או '2026-07-20' ומחזיר חודש+שנה עברית, למשל 'אב תשפ״ו'."""
    if not OK or not date_str:
        return ''
    m = re.match(r'(\d{4})-(\d{2})(?:-(\d{2}))?', str(date_str))
    if not m:
        return ''
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 15)
    try:
        h = dates.GregorianDate(y, mo, d).to_heb()
        year_str = hq(h.hebrew_date_string().split()[-1])
        return h.month_name(hebrew=True) + ' ' + year_str
    except Exception:
        return ''

def kvittel_default_month(today=None):
    """חודש/שנה עבריים לקוויטל מזדמן: החודש הנוכחי, ומכ' בחודש ואילך — החודש הבא."""
    if not OK:
        return ('', '')
    try:
        d = today or datetime.date.today()
        h = dates.GregorianDate(d.year, d.month, d.day).to_heb()
        if h.day >= 20:                       # מכ' לחודש כבר מכינים לחודש הבא
            h = h.add(months=1)
        return (h.month_name(hebrew=True), hq(h.hebrew_date_string().split()[-1]))
    except Exception:
        return ('', '')


def current_heb_year(today=None):
    """שם השנה העברית הנוכחית, למשל 'תשפ״ו'."""
    if not OK:
        return ''
    import datetime
    t = today or datetime.date.today()
    try:
        return hq(dates.GregorianDate(t.year, t.month, t.day).to_heb().hebrew_date_string().split()[-1])
    except Exception:
        return ''

_GY = {'א':1,'ב':2,'ג':3,'ד':4,'ה':5,'ו':6,'ז':7,'ח':8,'ט':9,'י':10,'כ':20,'ך':20,
       'ל':30,'מ':40,'ם':40,'נ':50,'ן':50,'ס':60,'ע':70,'פ':80,'ף':80,'צ':90,'ץ':90,
       'ק':100,'ר':200,'ש':300,'ת':400}

def heb_year_num(s):
    """שם שנה עברי ('תשפ״ו') -> מספר (5786). מחזיר 0 אם לא ניתן."""
    s = re.sub(r'[^א-ת]', '', s or '')
    if not s:
        return 0
    n = sum(_GY.get(c, 0) for c in s)
    return 5000 + n if n < 1000 else n

def heb_greg_year(date_text, hyear):
    """תאריך לועזי מדויק ליום עברי בשנה עברית נתונה (למשל 'ג׳ אב' + 'תשפ״ו'). None אם לא ניתן."""
    if not OK:
        return None
    txt = re.sub(r'[\"\']', '', str(date_text or '')).strip()
    parts = txt.split()
    if len(parts) < 2:
        return None
    d = _day(parts[0]); mon = ' '.join(parts[1:]).strip(); m = HMONTHS.get(mon); yr = heb_year_num(hyear)
    if not m or not (1 <= d <= 30) or not yr:
        return None
    try:
        return dates.HebrewDate(yr, m, d).to_pydate()
    except Exception:
        return None

def _cur_heb_year_num(today=None):
    if not OK:
        return 0
    import datetime
    t = today or datetime.date.today()
    try:
        return dates.GregorianDate(t.year, t.month, t.day).to_heb().year
    except Exception:
        return 0

def future_parnes(date_text, hyear, n=3, today=None):
    """אותו יום עברי (יום+חודש) בשנים הבאות — החל מהשנה שאחרי הנוכחית (לא לפני תשפ״ז).
    מחזיר [(שם-שנה-עברי, 'YYYY-MM-DD'), ...]."""
    if not OK:
        return []
    txt = re.sub(r'[\"\']', '', str(date_text or '')).strip()
    parts = txt.split()
    if len(parts) < 2:
        return []
    d = _day(parts[0]); mon = ' '.join(parts[1:]).strip(); m = HMONTHS.get(mon)
    base = heb_year_num(hyear)
    if not m or not (1 <= d <= 30) or not base:
        return []
    cur = _cur_heb_year_num(today)
    start = max(base, cur) + 1   # אף פעם לא השנה הנוכחית או קודמת — מתחיל מהשנה הבאה (תשפ״ז והלאה)
    out = []
    for yr in range(start, start + n):
        try:
            hd = dates.HebrewDate(yr, m, d)
            ys = hq(hd.hebrew_date_string().split()[-1])
            out.append((ys, hd.to_pydate().isoformat()))
        except Exception:
            pass
    return out

def week_before(text, today=None):
    """תאריך התזכורת — 7 ימים לפני הלילה. מחזיר 'YYYY-MM-DD' או None."""
    g = heb_to_greg(text, today)
    if not g:
        return None
    return (g - datetime.timedelta(days=7)).isoformat()
