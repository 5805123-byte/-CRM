# -*- coding: utf-8 -*-
"""קבלה אמריקאית (501(c)(3)) על תרומה אחת — כקובץ PDF על הבלאנק של הכולל.

מאיר: "חלון קבלות… אחד של חו"ל, העמותה שלנו בארצות הברית, עם הקבלה שעיצבת
לי… וכל הקבלות שאנחנו מפיקים יישמרו שם וגם יישלחו לאימייל של התורם".
הדף /receipt (receipt.html) מצויר בדפדפן; כאן אותו עיצוב בדיוק מצויר ב-PIL
כדי שאפשר יהיה לצרף אותו למייל ולשמור אותו — כמו הקבלה הישראלית (receipt_il).
המספר הסידורי הוא אותו מספר של הדף (מפתח 'd<donation_id>' בטבלת receipts),
ולכן הדפסה מהדפדפן ושליחה במייל נותנות את אותה קבלה.
"""
import datetime
import io
import os
import re

ORG_LINE = '1540 40th Street, Brooklyn, NY 11218  ·  EIN 20-0447034  ·  501(c)(3)'
ORG_LEGAL = 'registered as Cong. Zikhron Avos'
SIGNER = 'Rabbi Yehoshua Meir Deutsch'
SIGNER_ROLE = 'Rosh HaKollel · Authorized Signatory'
WARM = 'With deep appreciation for your partnership in the Torah of Chatzos.'
STMT = [('This letter is your official receipt for tax purposes. ', False),
        ('No goods or services were provided', True),
        (' in exchange for this contribution. Kollel Chatzos is exempt under Section 501(c)(3) of the '
         'Internal Revenue Code; contributions are tax-deductible to the extent allowed by law. '
         'Please retain this receipt for your records.', False)]

# הייעוד ואמצעי התשלום — אותן טבלאות כמו ב-receipt.html
PMAP = [(r'יששכר|זבולון|zevulun|yissachar', 'Yissachar–Zevulun Partnership in Torah'),
        (r'פרנס.?לילה|לימוד.?לילה', 'Sponsorship of a Night of Torah Study'),
        (r'נר.?למאור|ner\s?la?maor', 'Ner LaMaor'),
        (r'חדר.?קפה|coffee', 'Refreshments for the Kollel'),
        (r'ארוחת.?בוקר|breakfast', 'Breakfast for the Kollel'),
        (r'קמחא|kimcha|pesach', 'Kimcha D’Pischa'),
        (r'מתנות.?לאביונים|matanos', 'Matanos LaEvyonim'),
        (r'הכנסת.?כלה|kalla', 'Hachnosas Kallah'),
        (r'בנין|בניין|building', 'Building Fund'),
        (r'קוויטל|kvittel', 'Kvittel')]
MMAP = [(r'אשראי|credit|אותורייז|authorize|banquest|בנק ווסט|card', 'Credit Card'),
        (r"צק|צ׳ק|צ'ק|check|cheque", 'Check'),
        (r'מזומן|cash', 'Cash'),
        (r'בנק|bank|wire|zelle|העברה', 'Bank Transfer'),
        (r'דונרס|donors\s*fund|daf', 'Donor Advised Fund'),
        (r'paypal|פייפאל', 'PayPal'),
        (r'נדרים|nedarim', 'Nedarim Plus')]


def purpose_en(p):
    p = (p or '').strip()
    for rx, en in PMAP:
        if re.search(rx, p, re.I):
            return en
    return 'General Donation' if (not p or re.search(r'[֐-׿]', p)) else p


def method_en(m):
    m = (m or '').strip()
    if not m:
        return ''
    for rx, en in MMAP:
        if re.search(rx, m, re.I):
            return en
    return '' if re.search(r'[֐-׿]', m) else m


def money(a):
    try:
        n = float(re.sub(r'[^\d.]', '', str(a or '')) or 0)
    except ValueError:
        n = 0.0
    return '$' + format(n, ',.2f')


def nice_date(s):
    s = str(s or '').strip()
    d = None
    try:
        d = datetime.date.fromisoformat(s[:10])
    except (TypeError, ValueError):
        # 09.09.2026 / 9/9/2026 — יום.חודש.שנה כמו בכרטיס
        m = re.match(r'^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})', s)
        if m:
            y = int(m.group(3)); y += 2000 if y < 100 else 0
            try:
                d = datetime.date(y, int(m.group(2)), int(m.group(1)))
            except ValueError:
                d = None
    return (d or datetime.date.today()).strftime('%B %-d, %Y')


def receipt_data(con, don_id, RECEIPT_START, today_iso):
    row = con.execute("SELECT * FROM donations WHERE id=?", (don_id,)).fetchone()
    if not row:
        return None
    d = con.execute("SELECT * FROM donors WHERE id=?", (row['donor_id'],)).fetchone()
    name, addr, email = 'Friend', '', ''
    if d:
        name = (d['english'] or '').strip() or ((d['last'] or '') + ' ' + (d['first'] or '')).strip() or 'Friend'
        tail = ' '.join(x for x in (str(d['city'] or '').strip(), str(d['country'] or '').strip(), str(d['zip'] or '').strip()) if x)
        addr = ', '.join(x for x in (str(d['addr'] or '').strip(), tail) if x)
        email = (d['email'] or '').strip()
    key = 'd%d' % don_id                   # אותו מפתח כמו הדף /receipt — אותו מספר
    r = con.execute("SELECT num FROM receipts WHERE rkey=?", (key,)).fetchone()
    if r:
        num = int(r['num'])
    else:
        mx = con.execute("SELECT MAX(num) m FROM receipts WHERE rkey NOT LIKE 'il:%'").fetchone()['m']
        num = max(RECEIPT_START, int(mx or 0) + 1)
        con.execute("INSERT OR IGNORE INTO receipts(rkey,num,created) VALUES(?,?,?)", (key, num, today_iso()))
        con.commit()
    try:
        amt = float(re.sub(r'[^\d.]', '', str(row['amount'] or '')) or 0)
    except ValueError:
        amt = 0.0
    return {'donation_id': don_id, 'donor_id': row['donor_id'], 'name': name, 'addr': addr, 'email': email,
            'amount': amt, 'date': (row['date'] or today_iso())[:10], 'issued': today_iso(),
            'purpose': purpose_en(row['category']), 'method': method_en(row['method']), 'num': num}


def receipt_file(con, don_id, fmt, STATIC, RECEIPT_START, today_iso):
    """הקבלה על הבלאנק — PDF של עמוד אחד או JPG. אותו סידור כמו receipt.html."""
    from PIL import Image, ImageDraw, ImageFont
    info = receipt_data(con, don_id, RECEIPT_START, today_iso)
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
    wid = lambda t, f: dr.textlength(t, font=f)
    INK, DEEP, GOLD, SOFT, LINE, PALE = (0x3a, 0x2f, 0x1a), (0x7a, 0x1f, 0x1f), (0x9c, 0x7a, 0x2e), (0x6b, 0x62, 0x49), (0xcd, 0xbf, 0x98), (0xa2, 0x9a, 0x86)

    def spaced(t, f, x, y, fill, sp):
        for ch in t:
            dr.text((x, y), ch, font=f, fill=fill); x += wid(ch, f) + sp
        return x

    def spaced_w(t, f, sp):
        return sum(wid(ch, f) + sp for ch in t) - sp

    def wrap_runs(runs, maxw):
        """שורות של [(מילה, bold)] — ריצות טקסט עם הדגשה חלקית."""
        words = []
        for t, b in runs:
            for w in t.split():
                words.append((w, b))
        lines, cur, cw_ = [], [], 0
        for w, b in words:
            f = font(1.8 * u, b)
            ww = wid(w + ' ', f)
            if cur and cw_ + ww > maxw:
                lines.append(cur); cur, cw_ = [], 0
            cur.append((w, b)); cw_ += ww
        if cur:
            lines.append(cur)
        return lines

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

    x0, x1 = int(W * .24), int(W * (1 - .055))
    cw = x1 - x0
    y = int(H * .054)
    # ---- Receipt No. · Date ----
    fm, fno = font(1.85 * u), font(2.7 * u, True)
    num = str(info['num'])
    x = spaced('Receipt No. ', fm, x0, y + int(.75 * u), SOFT, .06 * u)
    spaced(num, fno, x, y, GOLD, .1 * u)
    # מאיר: "רשמתי תאריך 9.9 וזה רושם לי להיום" — תאריך התרומה (מתי הכסף הועבר), כמו בדף הקבלה
    dstr = nice_date(info.get('date') or info['issued'])
    fmb = font(1.85 * u, True)
    tw = spaced_w('Date: ', fm, .06 * u) + spaced_w(dstr, fmb, .06 * u)
    x = spaced('Date: ', fm, x1 - int(tw), y + int(.75 * u), SOFT, .06 * u)
    spaced(dstr, fmb, x, y + int(.75 * u), INK, .06 * u)
    y += int(2.7 * u + 1.6 * u)
    # ---- DONATION RECEIPT ----
    ft = font(3.05 * u); sp = .42 * u
    t = 'DONATION RECEIPT'
    spaced(t, ft, x0 + (cw - int(spaced_w(t, ft, sp))) // 2, y, GOLD, sp)
    y += int(3.05 * u + .9 * u)
    for i in range(cw):                     # קו מתפוגג בקצוות
        k = i / cw
        a = min(1.0, k / .18) if k < .18 else (min(1.0, (1 - k) / .18) if k > .82 else 1.0)
        col = tuple(int(253 - (253 - c) * a) for c in LINE)
        dr.line([(x0 + i, y), (x0 + i, y + max(1, int(.14 * u)))], fill=col)
    y += int(2.4 * u)
    # ---- העמותה ----
    fo = font(1.75 * u)
    dr.text((x0 + cw // 2, y), ORG_LINE, font=fo, fill=SOFT, anchor='ma')
    y += int(1.75 * u * 1.5)
    dr.text((x0 + cw // 2, y), ORG_LEGAL, font=font(1.35 * u), fill=PALE, anchor='ma')
    y += int(1.35 * u + 2.6 * u)
    # ---- Received from ----
    fl, fn, fa = font(1.4 * u), font(2.9 * u, True), font(1.75 * u)
    box_h = int((1.5 + 1.4 + .6 + 2.9 * 1.2 + (1.75 * 1.5 if info['addr'] else 0) + 1.5) * u)
    dr.rounded_rectangle([x0, y, x1, y + box_h], radius=int(.7 * u), fill=(254, 252, 246), outline=LINE, width=max(2, int(.13 * u)))
    yy = y + int(1.5 * u); xx = x0 + int(1.8 * u)
    spaced('RECEIVED FROM', fl, xx, yy, SOFT, .28 * u); yy += int(1.4 * u + .6 * u)
    dr.text((xx, yy), info['name'], font=fn, fill=INK); yy += int(2.9 * u * 1.2)
    if info['addr']:
        dr.text((xx, yy), info['addr'], font=fa, fill=SOFT)
    y += box_h + int(2 * u)
    # ---- Amount ----
    dr.line([(x0, y), (x1, y)], fill=LINE, width=max(2, int(.22 * u)))
    ay = y + int(2 * u); xx = x0 + int(1.8 * u)
    spaced('AMOUNT RECEIVED', font(1.5 * u), xx, ay, SOFT, .3 * u)
    fv = font(6.2 * u, True)
    dr.text((xx, ay + int(1.5 * u + .9 * u)), money(info['amount']), font=fv, fill=DEEP)
    # צד ימין: עבור מה · אמצעי תשלום
    fs, fsb = font(1.8 * u), font(1.8 * u, True)
    side = []
    if info['purpose']:
        side += [('Designated for:', fs, SOFT), (info['purpose'], fsb, INK)]
    if info['method']:
        side += [('Method: ' + info['method'], None, None)]
    sy = ay + int(.4 * u)
    for t, f, col in side:
        if f is None:
            w1 = wid('Method: ', fs); w2 = wid(info['method'], fsb)
            dr.text((x1 - int(1.8 * u) - int(w1 + w2), sy), 'Method: ', font=fs, fill=SOFT)
            dr.text((x1 - int(1.8 * u) - int(w2), sy), info['method'], font=fsb, fill=INK)
        else:
            dr.text((x1 - int(1.8 * u), sy), t, font=f, fill=col, anchor='ra')
        sy += int(1.8 * u * 1.7)
    y = ay + int(1.5 * u + .9 * u + 6.2 * u * 1.05 + 2 * u)
    dr.line([(x0, y), (x1, y)], fill=LINE, width=max(2, int(.22 * u)))
    y += int(2.2 * u)
    # ---- ההצהרה ----
    lines = wrap_runs(STMT, cw - int(1.4 * u * 2 + .3 * u))
    lh = int(1.8 * u * 1.55)
    kh = int(1.2 * u * 2) + lh * len(lines)
    dr.rectangle([x0, y, x1, y + kh], fill=(246, 241, 229))
    dr.rectangle([x0, y, x0 + max(2, int(.3 * u)), y + kh], fill=GOLD)
    ty = y + int(1.2 * u)
    for ln in lines:
        tx = x0 + int(1.4 * u + .3 * u)
        for w, b in ln:
            f = font(1.8 * u, b)
            dr.text((tx, ty), w, font=f, fill=INK); tx += wid(w + ' ', f)
        ty += lh
    y += kh
    # ---- חתימה (בתחתית) + המילים החמות מעליה ----
    bottom = int(H * (1 - .115))
    sign_h = int((.7 + 2.3 * 1.2 + 1.7 * 1.3 + .9 + 1.5 * 1.55) * u)
    sy = bottom - sign_h
    dr.line([(x1 - int(26 * u), sy), (x1, sy)], fill=INK, width=max(2, int(.14 * u)))
    yy = sy + int(.7 * u)
    dr.text((x1, yy), SIGNER, font=font(2.3 * u, True), fill=DEEP, anchor='ra'); yy += int(2.3 * u * 1.2)
    dr.text((x1, yy), SIGNER_ROLE, font=font(1.7 * u), fill=SOFT, anchor='ra'); yy += int(1.7 * u * 1.3 + .9 * u)
    f1, f2 = font(1.5 * u, True), font(1.5 * u)
    t2 = ' · EIN 20-0447034'
    dr.text((x1, yy), t2, font=f2, fill=SOFT, anchor='ra')
    spaced('KOLLEL CHATZOS', f1, x1 - int(wid(t2, f2)) - int(spaced_w('KOLLEL CHATZOS', f1, .16 * u)), yy, GOLD, .16 * u)
    fw = font(2.05 * u)
    wl = wrap(WARM, fw, cw)
    wy = sy - int(2.6 * u) - int(2.05 * u * 1.5) * len(wl)
    wy = max(wy, y + int(2.2 * u))
    for ln in wl:
        dr.text((x0 + cw // 2, wy), ln, font=fw, fill=DEEP, anchor='ma'); wy += int(2.05 * u * 1.5)
    buf = io.BytesIO()
    safe = re.sub(r'[^\w .-]+', '', info['name'] or '')[:40].strip() or 'donor'
    if fmt == 'pdf':
        im.save(buf, 'PDF', resolution=300.0)
        return buf.getvalue(), 'Receipt-%s-%s.pdf' % (num, safe)
    im2 = im.resize((1240, int(H * 1240 / W)), Image.LANCZOS)
    im2.save(buf, 'JPEG', quality=88)
    return buf.getvalue(), 'Receipt-%s-%s.jpg' % (num, safe)
