# -*- coding: utf-8 -*-
"""קבלה ישראלית על תרומה — לתורמים בארץ, על הבלאנק של הכולל, בעברית.

מאיר: "אני רוצה להנפיק קבלות ישראליות מעמותה שלנו לסעיף 46, תעצב לי משהו
יפה מסודר". הקבלה מצוירת על הבלאנק המלא (letterhead.jpg) ונשמרת כ-PDF של
עמוד אחד (או JPG לתצוגה), כמו הקבלה השנתית לארה"ב.

פרטי העמותה (שם רשמי, מספר ע"ר, כתובת, שורת סעיף 46, החותם) נשמרים פעם אחת
ב-app_kv ומתמלאים מהמסך /receipt-il. סדרת המספור של הקבלות הישראליות נפרדת
מהסדרה האמריקאית (rkey שמתחיל ב-'il:').
"""
import datetime
import io
import os
import re

ORG_KEYS = ('org_il_name', 'org_il_reg', 'org_il_addr', 'org_il_sec46', 'org_il_signer', 'org_il_role', 'org_il_phone')
# ברירות המחדל — כפי שמודפס בסרגל הבלאנק של הכולל
ORG_DEFAULT = {
    'org_il_name': 'כולל חצות נחלת יהושע ביתר עילית (ע"ר)',
    'org_il_reg': '580493914',
    'org_il_addr': 'ת.ד. 30067 ביתר עילית 90500',
    'org_il_sec46': 'למוסד אישור לפי סעיף 46 לפקודת מס הכנסה',
    'org_il_signer': 'הרב יהושע מאיר דויטש',
    'org_il_role': 'ראש הכולל',
    'org_il_phone': '02-5803545',
}

# ---- סכום במילים (שקלים חדשים — זכר; אגורות — נקבה) ----
_U_M = ['', 'אחד', 'שניים', 'שלושה', 'ארבעה', 'חמישה', 'שישה', 'שבעה', 'שמונה', 'תשעה']
_U_F = ['', 'אחת', 'שתיים', 'שלוש', 'ארבע', 'חמש', 'שש', 'שבע', 'שמונה', 'תשע']
_T_M = ['', 'עשרה', 'עשרים', 'שלושים', 'ארבעים', 'חמישים', 'שישים', 'שבעים', 'שמונים', 'תשעים']
_T_F = ['', 'עשר', 'עשרים', 'שלושים', 'ארבעים', 'חמישים', 'שישים', 'שבעים', 'שמונים', 'תשעים']
_H = ['', 'מאה', 'מאתיים', 'שלוש מאות', 'ארבע מאות', 'חמש מאות', 'שש מאות', 'שבע מאות', 'שמונה מאות', 'תשע מאות']
_TH = {1: 'אלף', 2: 'אלפיים', 3: 'שלושת אלפים', 4: 'ארבעת אלפים', 5: 'חמשת אלפים', 6: 'ששת אלפים',
       7: 'שבעת אלפים', 8: 'שמונת אלפים', 9: 'תשעת אלפים', 10: 'עשרת אלפים'}


def _below_1000(n, fem=False):
    U, T = (_U_F, _T_F) if fem else (_U_M, _T_M)
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append(_H[h])
    if r:
        if r < 10:
            parts.append(U[r])
        elif r == 10:
            parts.append('עשר' if fem else 'עשרה')
        elif r < 20:
            u = r - 10
            parts.append(({2: 'שתים', 1: 'אחת'}.get(u, U[u]) + ' עשרה') if fem
                         else ({2: 'שנים', 1: 'אחד'}.get(u, U[u]) + ' עשר'))
        else:
            t, u = divmod(r, 10)
            parts.append(T[t] + (' ו' + U[u] if u else ''))
    if len(parts) == 2:
        return parts[0] + ' ו' + parts[1]
    return ''.join(parts)


def _thousands(k):
    if k in _TH:
        return _TH[k]
    if k < 20:
        return _below_1000(k) + ' אלף'
    return _below_1000(k) + ' אלף'


def amount_words(amount):
    """3150.5 -> 'שלושת אלפים מאה וחמישים שקלים חדשים וחמישים אגורות'."""
    try:
        v = round(float(amount), 2)
    except (TypeError, ValueError):
        return ''
    sh = int(v)
    ag = int(round((v - sh) * 100))
    if sh >= 1000000:
        m, rest = divmod(sh, 1000000)
        head = ('מיליון' if m == 1 else _below_1000(m) + ' מיליון')
        tail = _thousands(rest // 1000) if rest >= 1000 else ''
        low = _below_1000(rest % 1000)
        words = ' ו'.join(x for x in (head, tail, low) if x)
    else:
        k, low = divmod(sh, 1000)
        hi = _thousands(k) if k else ''
        lo = _below_1000(low)
        # "שלושת אלפים מאה וחמישים" אבל "שלושת אלפים וחמש מאות" / "אלף ואחד"
        sep = ' ' if ' ו' in lo else ' ו'
        words = (hi + (sep if hi and lo else '') + lo) if (hi or lo) else 'אפס'
    if sh == 1:
        words = 'שקל חדש אחד'
    elif sh == 2:
        words = 'שני שקלים חדשים'
    else:
        words += ' שקלים חדשים'
    if ag:
        words += ' ו' + (_below_1000(ag, fem=True) if ag != 1 else 'אגורה אחת') + (' אגורות' if ag != 1 else '')
    return words


def org_settings(con, kv_get):
    out = {}
    for k in ORG_KEYS:
        out[k] = (kv_get(con, k, '') or ORG_DEFAULT.get(k, '')).strip()
    return out


def method_he(m):
    m = (m or '').strip()
    table = [(r'העברה|bank|wire|זל|zelle|בנקאית', 'העברה בנקאית'), (r'מזומן|cash', 'מזומן'),
             (r"צ'ק|צק|צ׳ק|המחאה|check", 'המחאה'), (r'אשראי|credit|card|נדרים|nedarim|אותורייז|בנק ווסט|banquest|paypal|פייפאל|ביט|bit', 'כרטיס אשראי'),
             (r'הוראת קבע|קבע', 'הוראת קבע')]
    for rx, he in table:
        if re.search(rx, m, re.I):
            return he
    return m


def receipt_data(con, don_id, kv_get, RECEIPT_IL_START, today_iso, greg_to_heb_full):
    row = con.execute("SELECT * FROM donations WHERE id=?", (don_id,)).fetchone()
    if not row:
        return None
    d = con.execute("SELECT * FROM donors WHERE id=?", (row['donor_id'],)).fetchone()
    name = ''
    if d:
        name = (d['business'] or '').strip() or ((d['last'] or '') + ' ' + (d['first'] or '')).strip()
    note = (row['note'] or '')
    ref = ''
    m = re.search(r'אסמכתא\s*[:#]?\s*([A-Za-z0-9\-]+)', note)
    if m:
        ref = m.group(1)
    tz = ''
    m = re.search(r'(ח\.?\s?פ\.?|ת\.?\s?ז\.?|ע\.?\s?מ\.?)\s*:?\s*(\d{6,9})', note + ' ' + (d['notes'] or '' if d else ''))
    if m:
        tz = m.group(1).replace(' ', '').rstrip('.') + '. ' + m.group(2)
    addr = ''
    if d:
        addr = ', '.join(x for x in (str(d['addr'] or '').strip(), str(d['city'] or '').strip()) if x)
    key = 'il:%d' % don_id
    r = con.execute("SELECT num FROM receipts WHERE rkey=?", (key,)).fetchone()
    if r:
        num = int(r['num'])
    else:
        mx = con.execute("SELECT MAX(num) m FROM receipts WHERE rkey LIKE 'il:%'").fetchone()['m']
        num = max(RECEIPT_IL_START, int(mx or 0) + 1)
        con.execute("INSERT OR IGNORE INTO receipts(rkey,num,created) VALUES(?,?,?)", (key, num, today_iso()))
        con.commit()
    try:
        amt = float(re.sub(r'[^\d.]', '', str(row['amount'] or '')) or 0)
    except ValueError:
        amt = 0.0
    date = (row['date'] or today_iso())[:10]
    try:
        heb = greg_to_heb_full(date)
    except Exception:
        heb = ''
    org = org_settings(con, kv_get)
    return {'donation_id': don_id, 'donor_id': row['donor_id'], 'name': name, 'tz': tz, 'addr': addr,
            'amount': amt, 'words': amount_words(amt), 'date': date, 'date_heb': heb,
            'method': method_he(row['method']), 'ref': ref, 'purpose': (row['category'] or '').strip() or 'תרומה',
            'num': num, 'org': org, 'issued': today_iso(),
            'email': (d['email'] or '').strip() if d else ''}


def receipt_file(con, don_id, fmt, STATIC, kv_get, RECEIPT_IL_START, today_iso, greg_to_heb_full):
    """הקבלה על הבלאנק — PDF של עמוד אחד או JPG. עברית מימין לשמאל (raqm)."""
    from PIL import Image, ImageDraw, ImageFont
    info = receipt_data(con, don_id, kv_get, RECEIPT_IL_START, today_iso, greg_to_heb_full)
    if not info:
        raise ValueError('donation')
    im = Image.open(os.path.join(STATIC, 'letterhead.jpg')).convert('RGB')
    W, H = im.size
    u = W / 100.0
    dr = ImageDraw.Draw(im)
    reg = os.path.join(STATIC, 'frankruhl-regular.ttf'); bold = os.path.join(STATIC, 'frankruhl-bold.ttf')
    cache = {}

    def font(px, heavy=False):
        k = (int(px), heavy)
        if k not in cache:
            cache[k] = ImageFont.truetype(bold if heavy else reg, max(8, int(px)))
        return cache[k]
    RTL = {'direction': 'rtl', 'language': 'he'}

    def wid(t, f):
        try:
            return dr.textlength(t, font=f, **RTL)
        except Exception:
            return dr.textlength(t, font=f)

    def R(t, f, x, y, fill):        # מיושר לימין
        dr.text((x, y), t, font=f, fill=fill, anchor='ra', **RTL)

    def L(t, f, x, y, fill):        # מיושר לשמאל
        dr.text((x, y), t, font=f, fill=fill, anchor='la', **RTL)

    def C(t, f, xc, y, fill):
        dr.text((xc, y), t, font=f, fill=fill, anchor='ma', **RTL)

    def wrap(t, f, maxw):
        out, cur = [], ''
        for w in t.split():
            tt = (cur + ' ' + w).strip()
            if wid(tt, f) <= maxw or not cur:
                cur = tt
            else:
                out.append(cur); cur = w
        if cur:
            out.append(cur)
        return out
    INK, DEEP, GOLD, SOFT, LINE = (0x3a, 0x2f, 0x1a), (0x7a, 0x1f, 0x1f), (0x9c, 0x7a, 0x2e), (0x6b, 0x62, 0x49), (0xcd, 0xbf, 0x98)
    org = info['org']
    x0, x1 = int(W * .24), int(W * (1 - .055))     # הצד הפתוח של הבלאנק — מימין לסרגל
    cw = x1 - x0
    y = int(H * .054)
    # ---- כותרת: קבלה (ימין) · מספר ותאריך (שמאל) ----
    R('קבלה', font(4.6 * u, True), x1, y, GOLD)
    R('מקור · על תרומה', font(1.6 * u), x1, y + int(5.2 * u), DEEP)
    fm, fmb, fno = font(1.75 * u), font(1.75 * u, True), font(2.6 * u, True)
    num = str(info['num']).zfill(4)
    L(num, fno, x0, y - int(.4 * u), GOLD)
    L("מס' קבלה", fm, x0 + int(wid(num, fno)) + int(.8 * u), y + int(.3 * u), SOFT)
    dstr = datetime.date.fromisoformat(info['issued']).strftime('%d.%m.%Y')
    L(dstr, fmb, x0, y + int(3.4 * u), INK)
    L('תאריך הפקה', fm, x0 + int(wid(dstr, fmb)) + int(.8 * u), y + int(3.4 * u), SOFT)
    if info['date_heb']:
        L(info['date_heb'], fm, x0, y + int(5.6 * u), SOFT)
    y += int(7.6 * u)
    dr.line([(x0, y), (x1, y)], fill=GOLD, width=max(2, int(.22 * u)))
    # ---- העמותה ----
    y += int(1.1 * u)
    fo, fob = font(1.6 * u), font(1.6 * u, True)
    nm = org['org_il_name'] or 'כולל חצות'
    R(nm, fob, x1, y, INK)
    xx = x1 - int(wid(nm, fob)) - int(.9 * u)
    tail = ' · '.join(x for x in (('ע"ר ' + org['org_il_reg']) if org['org_il_reg'] else '', org['org_il_addr'], org['org_il_phone']) if x)
    if tail:
        R(tail, fo, xx, y, SOFT)
    if org['org_il_sec46']:
        y += int(2.2 * u)
        R(org['org_il_sec46'], font(1.55 * u, True), x1, y, DEEP)
    y += int(3.6 * u)
    # ---- התקבל מאת ----
    fl, fn, fa = font(1.45 * u), font(2.8 * u, True), font(1.75 * u)
    extra = [x for x in (info['tz'], info['addr']) if x]
    box_h = int((1.3 + 1.45 + .5 + 2.8 * 1.15 + len(extra) * 1.75 * 1.5 + 1.2) * u)
    dr.rounded_rectangle([x0, y, x1, y + box_h], radius=int(.7 * u), fill=(255, 253, 247), outline=LINE, width=max(2, int(.13 * u)))
    yy = y + int(1.2 * u); xx = x1 - int(1.8 * u)
    R('התקבל מאת', fl, xx, yy, SOFT); yy += int(1.45 * u + .6 * u)
    R(info['name'] or '—', fn, xx, yy, INK); yy += int(2.8 * u * 1.15 + .2 * u)
    for t in extra:
        R(t, fa, xx, yy, SOFT); yy += int(1.75 * u * 1.5)
    y += box_h + int(1.8 * u)
    # ---- הסכום ----
    th = int(9.2 * u)
    dr.rounded_rectangle([x0, y, x1, y + th], radius=int(.7 * u), fill=(244, 236, 220))
    R('סכום התרומה', font(1.5 * u), x1 - int(1.6 * u), y + int(1.0 * u), SOFT)
    amt = '₪' + format(info['amount'], ',.2f')
    R(amt, font(4.6 * u, True), x1 - int(1.6 * u), y + int(2.9 * u), DEEP)
    fw = font(1.8 * u)
    words = info['words']
    ww = wrap(words, fw, cw - int(3.2 * u))
    wy = y + int(2.9 * u) + int(.4 * u)
    if len(ww) == 1 and wid(amt, font(4.6 * u, True)) + wid(words, fw) + int(6 * u) < cw:
        L(words, fw, x0 + int(1.6 * u), y + int(5.2 * u), INK)
    else:
        for ln in ww[:2]:
            L(ln, fw, x0 + int(1.6 * u), wy, INK); wy += int(1.6 * u * 1.5)
    y += th + int(1.8 * u)
    # ---- פרטים ----
    fk, fv = font(1.55 * u), font(1.75 * u, True)
    rows = [('אמצעי תשלום', info['method'] + ((' · אסמכתא ' + info['ref']) if info['ref'] else '')),
            ('תאריך קבלת התרומה', datetime.date.fromisoformat(info['date']).strftime('%d.%m.%Y')),
            ('עבור', info['purpose'])]
    for k, v in rows:
        if not v.strip():
            continue
        R(k, fk, x1, y + int(.2 * u), SOFT)
        R(v, fv, x1 - int(cw * .3), y, INK)
        y += int(2.6 * u)
        dr.line([(x0, y), (x1, y)], fill=LINE, width=max(1, int(.1 * u)))
        y += int(.9 * u)
    # ---- ההצהרה ----
    y += int(.8 * u)
    fp, fpb = font(1.6 * u), font(1.6 * u, True)
    stmt = ['תרומה זו התקבלה ללא כל תמורה.']
    if org['org_il_sec46']:
        stmt.append('העמותה היא מוסד ציבורי שאושר לעניין סעיף 46 לפקודת מס הכנסה, והתרומה מזכה בזיכוי ממס בכפוף להוראות הסעיף.')
    stmt.append('קבלה זו הופקה באופן ממוחשב. נא לשמור אותה לצורכי מס.')
    lh = int(1.6 * u * 1.55)
    for i, s in enumerate(stmt):
        for ln in wrap(s, fpb if i == 0 else fp, cw):
            R(ln, fpb if i == 0 else fp, x1, y, DEEP if i == 0 else INK); y += lh
    # ---- ברכה + חתימה — צמודות לתוכן, לא בתחתית הדף ----
    sy = min(y + int(9.5 * u), int(H * (1 - .115)) - int(9.5 * u))
    C('תודה על שותפותך בתורת חצות. תזכו למצוות.', font(2.0 * u), x0 + cw // 2, sy - int(4.6 * u), DEEP)
    dr.line([(x0, sy), (x0 + int(26 * u), sy)], fill=INK, width=max(2, int(.14 * u)))
    L(org['org_il_signer'] or '', font(2.2 * u, True), x0, sy + int(.7 * u), DEEP)
    L(' · '.join(x for x in (org['org_il_role'], 'מורשה חתימה') if x), font(1.6 * u), x0, sy + int(3.4 * u), SOFT)
    R(nm + ((' · ע"ר ' + org['org_il_reg']) if org['org_il_reg'] else ''), font(1.5 * u), x1, sy + int(1.2 * u), SOFT)
    buf = io.BytesIO()
    safe = re.sub(r'[^\w֐-׿ .-]+', '', info['name'] or '')[:40].strip() or 'donor'
    if fmt == 'pdf':
        im.save(buf, 'PDF', resolution=300.0)
        return buf.getvalue(), 'קבלה-%s-%s.pdf' % (num, safe)
    im2 = im.resize((1240, int(H * 1240 / W)), Image.LANCZOS)
    im2.save(buf, 'JPEG', quality=88)
    return buf.getvalue(), 'קבלה-%s-%s.jpg' % (num, safe)
