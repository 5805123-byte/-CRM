# -*- coding: utf-8 -*-
"""ייבוא יומן השיחות מהטלפון ליומן הקשר של התורמים.

מאיר: "כל מי שחייגתי אליו דרך המערכת אני רוצה שזה ייכנס בדף קשר שלו…
אם היה אפשר גם לעשות כמה זמן שיחה היתה" — ו"מה עם מה שהיה עד עכשיו?"
המערכת לא יודעת על שיחות שנעשו מחוץ לה, אבל יומן השיחות של הטלפון
יודע. הקובץ של SMS Backup & Restore (XML או ה-HTML שהאפליקציה מציגה)
נקרא כאן, כל מספר מוצלב עם הטלפונים של התורמים, וכל שיחה נכנסת ליומן
הקשר עם התאריך, השעה, המשך והכיוון. שיחה שכבר יובאה לא נכנסת פעמיים.
"""
import re, html, datetime

# החודשים כפי שהאפליקציה כותבת אותם בעברית ובאנגלית
_HE_MON = {'ינו': 1, 'פבר': 2, 'מרץ': 3, 'מרס': 3, 'אפר': 4, 'מאי': 5, 'יונ': 6, 'יול': 7,
           'אוג': 8, 'ספט': 9, 'אוק': 10, 'נוב': 11, 'דצמ': 12}
_EN_MON = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7,
           'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
# type ב-XML של האפליקציה (Android CallLog.Calls)
_XML_TYPE = {'1': 'in', '2': 'out', '3': 'missed', '4': 'voicemail', '5': 'rejected',
             '6': 'blocked', '7': 'external'}
_HE_TYPE = {'יוצאת': 'out', 'נכנסת': 'in', 'שלא נענתה': 'missed', 'לא נענתה': 'missed',
            'נדחתה': 'rejected', 'חסומה': 'blocked', 'תא קולי': 'voicemail',
            'outgoing': 'out', 'incoming': 'in', 'missed': 'missed', 'rejected': 'rejected',
            'blocked': 'blocked', 'voicemail': 'voicemail'}


def digits(s):
    return re.sub(r'\D', '', s or '')


def phone_key(s):
    """מפתח להשוואה בין מספרים: הספרות בלי קידומת בינלאומית/אפס מוביל.
    +1 917-613-0192 ↔ 9176130192 ↔ 1 (917) 613-0192 ; 052-762-8272 ↔ +972527628272"""
    d = digits(s)
    if not d:
        return ''
    if d.startswith('00'):
        d = d[2:]
    if len(d) == 11 and d[0] == '1':
        return d[1:]                       # ארה"ב/קנדה
    if d.startswith('972') and len(d) >= 11:
        d = d[3:]
        return d.lstrip('0')
    if d[:1] == '0' and len(d) in (9, 10):
        return d[1:]                       # ישראלי מקומי
    return d


def pretty(num):
    """+19176130192 → '+1 917-613-0192' ; +972527628272 → '+972 52-762-8272' (כמו בכרטיסים)"""
    d = digits(num)
    if d.startswith('00'):
        d = d[2:]
    if len(d) == 11 and d[0] == '1':
        r = d[1:]; return '+1 %s-%s-%s' % (r[:3], r[3:6], r[6:])
    if len(d) == 10 and d[0] != '0':
        return '+1 %s-%s-%s' % (d[:3], d[3:6], d[6:])
    if d.startswith('972'):
        r = d[3:].lstrip('0')
    elif d[:1] == '0' and len(d) in (9, 10):
        r = d[1:]
    else:
        return '+' + d if '+' in (num or '') else (num or '').strip()
    if len(r) == 9:
        return '+972 %s-%s-%s' % (r[:2], r[2:5], r[5:])
    if len(r) == 8:
        return '+972 %s-%s-%s' % (r[:1], r[1:4], r[4:])
    return '+972 ' + r


def _parse_he_date(txt):
    """'11 בספט׳ 2026 04:25:12' / 'Sep 11, 2026 4:25:12 PM' → datetime"""
    t = (txt or '').strip()
    m = re.match(r'(\d{1,2})\s+ב?([^\s\d׳\']+)[׳\']?\.?\s+(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?', t)
    if m:
        mon = _HE_MON.get(m.group(2)[:3]) or _EN_MON.get(m.group(2)[:3].lower())
        if mon:
            return datetime.datetime(int(m.group(3)), mon, int(m.group(1)), int(m.group(4)), int(m.group(5)),
                                     int(m.group(6) or 0))
    m = re.match(r'([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4}),?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?', t)
    if m:
        mon = _EN_MON.get(m.group(1).lower())
        h = int(m.group(4))
        if m.group(7):
            if m.group(7).lower() == 'pm' and h < 12: h += 12
            if m.group(7).lower() == 'am' and h == 12: h = 0
        if mon:
            return datetime.datetime(int(m.group(3)), mon, int(m.group(2)), h, int(m.group(5)), int(m.group(6) or 0))
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})', t)
    if m:
        return datetime.datetime(*map(int, m.groups()))
    return None


def parse(text):
    """מחזיר רשימת שיחות: {number, name, kind, at (datetime), secs}"""
    text = text or ''
    calls = []
    if re.search(r'<call\b', text):
        for m in re.finditer(r'<call\b([^>]*)/?>', text):
            a = dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))
            num = html.unescape(a.get('number', ''))
            if not digits(num):
                continue
            at = None
            try:
                ms = int(a.get('date', '0'))
                if ms > 0:
                    # readable_date הוא בשעון הטלפון — עדיף עליו; date הוא UTC במילישניות
                    at = _parse_he_date(html.unescape(a.get('readable_date', ''))) or \
                         datetime.datetime.utcfromtimestamp(ms / 1000)
            except Exception:
                at = _parse_he_date(html.unescape(a.get('readable_date', '')))
            if not at:
                continue
            calls.append({'number': num.strip(), 'name': html.unescape(a.get('contact_name', '') or '').strip(),
                          'kind': _XML_TYPE.get(a.get('type', ''), 'out'),
                          'at': at, 'secs': int(a.get('duration', '0') or 0)})
        return calls
    # ה-HTML שהאפליקציה מציגה ב"הצג גיבויים" → שתף
    rows = re.findall(r'<tr>(.*?)</tr>', text, re.S)
    for r in rows:
        cells = [html.unescape(re.sub(r'<[^>]+>', '', c)).strip() for c in re.findall(r'<td[^>]*>(.*?)</td>', r, re.S)]
        if len(cells) < 4:
            continue
        kind = _HE_TYPE.get(cells[0].strip().lower(), _HE_TYPE.get(cells[0].strip(), None))
        if kind is None:
            continue
        at = _parse_he_date(cells[1])
        if not at:
            continue
        who = cells[2]
        m = re.search(r'\(([+\d][\d\s\-()]*)\)\s*$', who)
        if m:
            num, name = m.group(1), who[:m.start()].strip()
        else:
            num, name = who, ''
        if not digits(num):
            continue
        sm = re.search(r'(\d+)', cells[3])
        calls.append({'number': num.strip(), 'name': name, 'kind': kind, 'at': at,
                      'secs': int(sm.group(1)) if sm else 0})
    return calls


def fmt_secs(s):
    s = int(s or 0)
    if s <= 0:
        return ''
    if s < 60:
        return '%d שנ׳' % s
    m, sec = divmod(s, 60)
    if m < 60:
        return '%d:%02d דק׳' % (m, sec)
    h, m = divmod(m, 60)
    return '%d:%02d שע׳' % (h, m)


KIND_HE = {'out': 'שיחה יוצאת', 'in': 'שיחה נכנסת', 'missed': 'שיחה שלא נענתה',
           'rejected': 'שיחה שנדחתה', 'blocked': 'שיחה חסומה', 'voicemail': 'תא קולי', 'external': 'שיחה'}


def summary_of(c, disp):
    k = c['kind']
    if k == 'out' and not c['secs']:
        k_he = 'שיחה יוצאת · לא נענתה'
    elif k == 'in' and not c['secs']:
        k_he = 'שיחה נכנסת · לא נענתה'
    else:
        k_he = KIND_HE.get(k, 'שיחה')
    dur = fmt_secs(c['secs'])
    return '📲 ' + k_he + (' · ' + dur if dur else '') + ' · ' + disp


def import_calls(con, text, since='', only_key=''):
    """מייבא את הקובץ. מחזיר סיכום + רשימת מספרים שלא זוהו (שם מהטלפון + מספר).
    only_key — רק השיחות של מספר אחד (אחרי שמאיר שייך אותו לתורם)."""
    calls = parse(text)
    if only_key:
        calls = [c for c in calls if phone_key(c['number']) == only_key]
    if since:
        try:
            s = datetime.datetime.strptime(since[:10], '%Y-%m-%d')
            calls = [c for c in calls if c['at'] >= s]
        except Exception:
            pass
    # מפת מספר → תורם
    bykey = {}
    for r in con.execute("SELECT id,first,last,phone FROM donors WHERE COALESCE(TRIM(phone),'')<>''"):
        for p in re.split(r'\s*/\s*', r['phone'] or ''):
            k = phone_key(p)
            if len(k) >= 7 and k not in bykey:
                bykey[k] = r['id']
    try:
        ignored = {r[0] for r in con.execute("SELECT key FROM call_ignore")}
    except Exception:
        ignored = set()
    added = 0; updated = 0; dup = 0; donors = set(); unmatched = {}; nign = 0
    matched = []           # מאיר: "רשימה סיכום מסודרת כל מי שהתקשרתי אליו והוא תורם — כמה זמן ומתי"
    for c in calls:
        key = phone_key(c['number'])
        did = bykey.get(key)
        if not did:
            if key in ignored:
                nign += 1; continue
            u = unmatched.setdefault(key or c['number'], {'number': c['number'], 'name': c['name'], 'n': 0, 'secs': 0, 'last': ''})
            u['n'] += 1; u['secs'] += c['secs']
            if not u['name'] and c['name']:
                u['name'] = c['name']
            u['last'] = max(u['last'], c['at'].strftime('%Y-%m-%d %H:%M'))
            continue
        at = c['at'].strftime('%Y-%m-%d %H:%M')
        ext = 'call:%s|%s' % (key, c['at'].strftime('%Y%m%d%H%M%S'))
        matched.append({'donor_id': did, 'at': at, 'kind': c['kind'], 'secs': c['secs'],
                        'dur': fmt_secs(c['secs']), 'number': c['number']})
        if con.execute("SELECT 1 FROM contacts_log WHERE msg_id=?", (ext,)).fetchone():
            dup += 1; continue
        disp = c['number']
        summ = summary_of(c, disp)
        # חיוג שנעשה מהמערכת באותן דקות — משלימים לו את המשך במקום שורה כפולה
        near = None
        for r in con.execute("SELECT id,at,summary FROM contacts_log WHERE donor_id=? AND channel='טלפון' "
                             "AND summary LIKE 'חיוג מהמערכת%' AND COALESCE(msg_id,'')='' AND date=?",
                             (did, c['at'].strftime('%Y-%m-%d'))):
            try:
                t = datetime.datetime.strptime((r['at'] or '')[:16], '%Y-%m-%d %H:%M')
            except Exception:
                continue
            if abs((t - c['at']).total_seconds()) <= 240 and c['kind'] == 'out':
                near = r['id']; break
        if near:
            con.execute("UPDATE contacts_log SET summary=?, at=?, msg_id=? WHERE id=?", (summ, at, ext, near))
            updated += 1
        else:
            con.execute("INSERT INTO contacts_log(donor_id,date,channel,summary,next_date,seen,at,msg_id) "
                        "VALUES(?,?,?,?,'',1,?,?)", (did, c['at'].strftime('%Y-%m-%d'), 'טלפון', summ, at, ext))
            added += 1
        donors.add(did)
    con.commit()
    un = sorted(unmatched.values(), key=lambda u: (-u['n'], u['last']), reverse=False)
    names = {r['id']: ((r['last'] or '') + ' ' + (r['first'] or '')).strip()
             for r in con.execute("SELECT id,last,first FROM donors")}
    for m in matched:
        m['name'] = names.get(m['donor_id'], '#%s' % m['donor_id'])
    matched.sort(key=lambda m: m['at'])
    return {'ok': True, 'calls': len(calls), 'added': added, 'updated': updated, 'dup': dup, 'ignored': nign,
            'donors': len(donors), 'unmatched': un[:200], 'unmatched_total': len(un), 'matched': matched[:500],
            'from': min((c['at'] for c in calls), default=None) and min(c['at'] for c in calls).strftime('%Y-%m-%d'),
            'to': max((c['at'] for c in calls), default=None) and max(c['at'] for c in calls).strftime('%Y-%m-%d')}
