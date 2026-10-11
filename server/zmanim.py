# -*- coding: utf-8 -*-
"""זמני תפילות — שבתות לפי פרשה, חגים, צומות, ימי חול; חישוב נץ / שקיעה לביתר עילית.

מאיר: "עכשיו לעדכון זמני התפילות בשבת, תפתח לשונית חדשה ושלוחת API לשמיעת הזמנים —
לפי פרשות וכו', למשל על חג וכו'". כל "אירוע" (שבת / חג / צום / ימי חול / אירוע מיוחד)
מחזיק רשימת שורות: {day, label, time}. day = מספר היום בתוך האירוע (0 = ערב שבת / ערב חג).
time הוא שעה ("6:10"), ביטוי יחסי ("שקיעה-20", "נץ", "הדלקה", "שקיעה+20"), או טקסט
("כוותיקין", "מיד לאחר מנחה") — הטקסט נקרא כמו שהוא.
"""
import datetime
import math
import re

try:
    from zoneinfo import ZoneInfo
    IL = ZoneInfo('Asia/Jerusalem')
except Exception:
    IL = None

# ביתר עילית
LAT, LON = 31.6966, 35.1153

WEEKDAYS = ['שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת', 'ראשון']   # date.weekday()


def il_today():
    if IL is not None:
        return datetime.datetime.now(IL).date()
    return datetime.date.today()


def il_now():
    if IL is not None:
        return datetime.datetime.now(IL).replace(tzinfo=None)
    return datetime.datetime.now()


# ---------- נץ ושקיעה (אלגוריתם NOAA, גובה פני הים, שבירת אור רגילה) ----------

def _utc_offset(d):
    if IL is None:
        return 2.0
    return datetime.datetime(d.year, d.month, d.day, 12, tzinfo=IL).utcoffset().total_seconds() / 3600.0


def _sun_event(d, rise, zenith=90.833):
    n = d.timetuple().tm_yday
    lng_h = LON / 15.0
    t = n + ((6 if rise else 18) - lng_h) / 24.0
    M = 0.9856 * t - 3.289
    L = (M + 1.916 * math.sin(math.radians(M)) + 0.020 * math.sin(math.radians(2 * M)) + 282.634) % 360
    RA = math.degrees(math.atan(0.91764 * math.tan(math.radians(L)))) % 360
    RA = (RA + (math.floor(L / 90) * 90 - math.floor(RA / 90) * 90)) / 15.0
    sin_dec = 0.39782 * math.sin(math.radians(L))
    cos_dec = math.cos(math.asin(sin_dec))
    cos_h = (math.cos(math.radians(zenith)) - sin_dec * math.sin(math.radians(LAT))) / (cos_dec * math.cos(math.radians(LAT)))
    if not -1 <= cos_h <= 1:
        return None
    H = (360 - math.degrees(math.acos(cos_h))) if rise else math.degrees(math.acos(cos_h))
    T = H / 15.0 + RA - 0.06571 * t - 6.622
    ut = (T - lng_h) % 24
    loc = (ut + _utc_offset(d)) % 24
    secs = int(round(loc * 3600))
    return datetime.datetime(d.year, d.month, d.day) + datetime.timedelta(seconds=secs)


def sun(d, adj=0):
    """{'netz': datetime, 'shkia': datetime} לתאריך (שעון ישראל). adj — תיקון דקות לשקיעה."""
    r, s = _sun_event(d, True), _sun_event(d, False)
    if s is not None and adj:
        s += datetime.timedelta(minutes=adj)
    return {'netz': r, 'shkia': s}


def hm(dt):
    """6:10 — שעון של 12 שעות, כמו בלוח של בית הכנסת."""
    if not dt:
        return ''
    h = dt.hour % 12 or 12
    return '%d:%02d' % (h, dt.minute)


BASES = {'נץ': 'netz', 'הנץ': 'netz', 'זריחה': 'netz', 'שקיעה': 'shkia', 'השקיעה': 'shkia', 'הדלקה': 'candle',
         'הדלקת נרות': 'candle', 'צאת': 'tzeis', 'צאת הכוכבים': 'tzeis', 'צאה"כ': 'tzeis'}
_EXPR = re.compile(r'^\s*(%s)\s*(?:([+-])\s*(\d{1,3}))?\s*(?:דק[\'׳]?|דקות)?\s*$' % '|'.join(sorted(map(re.escape, BASES), key=len, reverse=True)))
_HM = re.compile(r'^\s*(\d{1,2})[:.](\d{2})\s*$')


def calc(expr, d, st=None):
    """הזמן בפועל של שורה ביום d: datetime, או None כשזה טקסט ("כוותיקין")."""
    st = st or {}
    s = str(expr or '').strip()
    m = _HM.match(s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            return None
        return datetime.datetime(d.year, d.month, d.day, h, mi)
    m = _EXPR.match(s)
    if not m:
        return None
    sn = sun(d, int(st.get('adj') or 0))
    base = BASES[m.group(1)]
    if base == 'netz':
        t = sn['netz']
    elif base == 'candle':
        t = sn['shkia'] - datetime.timedelta(minutes=int(st.get('candle') or 40)) if sn['shkia'] else None
    elif base == 'tzeis':
        t = sn['shkia'] + datetime.timedelta(minutes=int(st.get('tzeis') or 18)) if sn['shkia'] else None
    else:
        t = sn['shkia']
    if t is None:
        return None
    off = int(m.group(3) or 0) * (-1 if m.group(2) == '-' else 1)
    t = t.replace(second=0, microsecond=0) + datetime.timedelta(minutes=off)
    return t


def show(expr, d, st=None):
    """מה שכתוב בלוח: "6:10" לשעה / ביטוי מחושב, אחרת הטקסט כמו שהוא."""
    t = calc(expr, d, st)
    if t is None:
        return str(expr or '').strip()
    if _HM.match(str(expr or '')):
        return str(expr).strip().replace('.', ':')
    return hm(t)


# ---------- הקראה בטלפון ----------
_F = ['', 'אחת', 'שתיים', 'שלוש', 'ארבע', 'חמש', 'שש', 'שבע', 'שמונה', 'תשע', 'עשר',
      'אחת עשרה', 'שתים עשרה', 'שלוש עשרה', 'ארבע עשרה', 'חמש עשרה', 'שש עשרה', 'שבע עשרה', 'שמונה עשרה', 'תשע עשרה']
_T = {20: 'עשרים', 30: 'שלושים', 40: 'ארבעים', 50: 'חמישים'}


def fem(n):
    """מספר בלשון נקבה (שעה / דקות): 25 -> 'עשרים וחמש'."""
    if n < 20:
        return _F[n]
    t, u = divmod(n, 10)
    return _T[t * 10] + (' ו' + _F[u] if u else '')


def say_time(s):
    """"6:10" -> "שש ועשר דקות"; "6:30" -> "שש וחצי"; "6:00" -> "שש"."""
    m = _HM.match(str(s or ''))
    if not m:
        return str(s or '')
    h, mi = int(m.group(1)) % 12 or 12, int(m.group(2))
    if mi == 0:
        return fem(h)
    if mi == 30:
        return fem(h) + ' וחצי'
    if mi == 15:
        return fem(h) + ' ורבע'
    return fem(h) + ' ו' + fem(mi) + (' דקות' if mi > 10 or mi in (2, 3, 4, 5, 6, 7, 8, 9, 10) else ' דקה' if mi == 1 else '')


# ---------- האירועים בלוח ----------

def _g(d):
    from pyluach import dates
    return dates.GregorianDate(d.year, d.month, d.day)


def heb_str(d):
    try:
        return _g(d).to_heb().hebrew_date_string()
    except Exception:
        return ''


def parsha(d):
    try:
        from pyluach import parshios
        return parshios.getparsha_string(_g(d), israel=True, hebrew=True) or ''
    except Exception:
        return ''


def _fest(d, working=True):
    try:
        return _g(d).festival(israel=True, hebrew=True, include_working_days=working) or ''
    except Exception:
        return ''


def _fast(d):
    try:
        return _g(d).fast_day(hebrew=True) or ''
    except Exception:
        return ''


def _rosh_chodesh(d):
    try:
        h = _g(d).to_heb()
        return h.day in (30, 1) and h.month != 7
    except Exception:
        return False


# שמות לקבוצה של ימי יום טוב (שני הימים של פסח / סוכות בארץ — כל אחד לבד)
_LAST_YT = {'פסח': 'שביעי של פסח'}


def occasions(start, days=70):
    """שבתות, חגים וצומות מ-start והלאה. כל אחד: key, kind, title, dates (ISO, כולל הערב)."""
    end = start + datetime.timedelta(days=days)
    out = []
    # חגים — ימים רצופים עם אותו שם ואותו סוג (יום טוב / חול המועד / חנוכה)
    d = start - datetime.timedelta(days=1)
    groups = []
    while d <= end:
        f = _fest(d)
        if f and f not in ('פסח שני', 'ט״ו בשבט', 'פורים קטן', 'ל״ג בעומר', 'ט״ו באב'):
            yt = bool(_fest(d, False))
            if groups and groups[-1]['name'] == f and groups[-1]['yt'] == yt and groups[-1]['days'][-1] == d - datetime.timedelta(days=1):
                groups[-1]['days'].append(d)
            else:
                groups.append({'name': f, 'yt': yt, 'days': [d]})
        fd = _fast(d)
        if fd:
            groups.append({'name': fd, 'yt': False, 'fast': True, 'days': [d]})
        d += datetime.timedelta(days=1)
    seen_pesach = 0
    for g in groups:
        name = g['name']
        if g.get('fast'):
            title, kind = name, 'fast'
        elif g['yt']:
            kind = 'chag'
            title = name
            if name == 'פסח':
                seen_pesach += 1
                if g['days'][0] != _first_pesach(g['days'][0]):
                    title = _LAST_YT['פסח']
        elif name in ('סוכות', 'פסח'):
            kind, title = 'chag', 'חול המועד ' + name
        else:
            kind, title = 'chag', name
        if title == 'שמיני עצרת':
            title = 'שמיני עצרת ושמחת תורה'          # בארץ — אותו יום
        days_ = list(g['days'])
        if g['yt'] or kind == 'fast' and name == 'תשעה באב' or name == 'יום כיפור':
            days_ = [days_[0] - datetime.timedelta(days=1)] + days_       # ערב החג
        if days_[-1] < start:
            continue
        out.append({'key': 'chag:%s:%s' % (g['days'][0].isoformat(), title), 'kind': kind, 'title': title,
                    'dates': [x.isoformat() for x in days_]})
    # שבתות
    sat = start + datetime.timedelta(days=(5 - start.weekday()) % 7)
    while sat <= end:
        fri = sat - datetime.timedelta(days=1)
        f, yt = _fest(sat), _fest(sat, False)
        p = parsha(sat)
        if yt:
            # שבת שהיא יום טוב — אירוע אחד עם החג (לוח אחד, כמו "שבת קודש ויו"ט סוכות")
            title = ('שבת ו' + f if f != 'יום כיפור' else 'שבת – יום כיפור').replace('ושמיני עצרת', 'ושמחת תורה')
            ch = next((o for o in out if o['kind'] == 'chag' and sat.isoformat() in o['dates']), None)
            if ch:
                ch['title'] = title
                if fri.isoformat() not in ch['dates'] and fri.isoformat() < ch['dates'][0]:
                    ch['dates'].insert(0, fri.isoformat())
                sat += datetime.timedelta(days=7)
                continue
        elif f in ('סוכות', 'פסח'):
            title = 'שבת חול המועד ' + f
        else:
            title = ('שבת פרשת ' + p) if p else 'שבת קודש'
            if f:
                title += ' – ' + f
            nxt = [sat + datetime.timedelta(days=i) for i in range(1, 8)]
            if any(_rosh_chodesh(x) for x in nxt) and _g(sat).to_heb().month != 6:
                title += ' · מברכים'
        out.append({'key': 'shabbat:' + sat.isoformat(), 'kind': 'shabbat', 'title': title,
                    'dates': [fri.isoformat(), sat.isoformat()]})
        sat += datetime.timedelta(days=7)
    out.sort(key=lambda o: (o['dates'][-1], o['dates'][0]))
    return out


def _first_pesach(d):
    """היום הראשון של פסח באותה שנה (ט"ו בניסן)."""
    try:
        from pyluach import dates
        h = _g(d).to_heb()
        return dates.HebrewDate(h.year, 1, 15).to_pydate()
    except Exception:
        return d


def day_name(iso, kind=''):
    d = datetime.date.fromisoformat(iso)
    return 'יום ' + WEEKDAYS[d.weekday()] if WEEKDAYS[d.weekday()] != 'שבת' else 'שבת'


# ---------- ברירות מחדל (מהלוח של תשרי תשפ"ז) ----------
DEFAULT_SETTINGS = {'candle': 40, 'adj': 0, 'tzeis': 18}

# מאיר: "מאיפה לקחת את הנתונים האלה? זה רק היה דוגמא, תמחק — מכניסים הכל מחדש". אין זמנים מוכנים.
WEEKDAY_LINES = []
TEMPLATES = []

# ---------- שעה של 24 שעות להקראה (z-T13:00 של ימות) ----------
# בלוח כותבים "6:10" — צריך לדעת אם זה בוקר או ערב. מילים בשורה מכריעות; אחרת: 7–11 בוקר, 1–6 אחה"צ / ערב.
_AM_W = ('שחרית', 'כוותיקין', 'ותיקין', 'נץ', 'סליחות', 'הנץ', 'השכמה', 'קידוש', 'הקפות', 'יזכור', 'מוסף', 'קריאת התורה', 'בוקר')
_PM_W = ('מנחה', 'מעריב', 'ערבית', 'שקיעה', 'סעודה שלישית', 'סעודה ג', 'הדלקה', 'הדלקת נרות', 'כל נדרי', 'נעילה',
         'מוצאי', 'מוצ"ש', 'מוצ״ש', 'ערב', 'לילה', 'צאת', 'שקיעת', 'הבדלה', 'תקיעת שופר')


def h24(expr, label, d, st=None):
    """"HH:MM" (24 שעות) לשורה, או '' כשהזמן הוא טקסט."""
    t = calc(expr, d, st)
    if t is None:
        return ''
    if not _HM.match(str(expr or '')):
        return t.strftime('%H:%M')            # ביטוי (שקיעה-20…) — כבר מדויק
    h, mi = t.hour, t.minute
    if h == 0 or h >= 13:
        return '%02d:%02d' % (h, mi)
    lb = str(label or '')
    pm = any(w in lb for w in _PM_W)
    am = any(w in lb for w in _AM_W)
    if h == 12:
        return '12:%02d' % mi
    if pm and not am:
        h += 12
    elif not am and h <= 6:
        h += 12
    return '%02d:%02d' % (h, mi)
