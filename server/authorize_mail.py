# -*- coding: utf-8 -*-
"""אוטורייז דרך המיילים שלהם בג'ימייל — בלי מפתחות API.

מאיר: "תבדוק טוב לפי הדוח ששלחתי לך מאוטרייז מה הסיפור… אין בכלל תרומה שלו של אוקטובר פה במערכת",
"אתה אמור להתריע לי על כל תרומה שלא עברה באוטרייז".

עד היום החיובים של אוטורייז נכנסו רק מהדוח החודשי שמאיר שולח. החיבור החי (API) לא הוגדר, ולכן חודש שלם
חסר עד שהדוח מגיע. אוטורייז שולחים לתיבה (תווית "אוטרייז") מייל על כל עסקה:
  • "Merchant Email Receipt"                      — כל חיוב שאושר (גם של הוראת קבע), עם מספר עסקה, סכום, שם, כרטיס
  • "ARB Subscription N: Failed transaction"      — חיוב של הוראת קבע שנדחה, עם הסיבה
  • "Summary of Automated Recurring Billing"      — סיכום יומי עם Failed.csv (ניסיונות שנכשלו)
הסריקה רצה כל שעה דרך IMAP (GMAIL_USER / GMAIL_APP_PASSWORD — אותו חיבור של משיכת השמות לקוויטל),
ומכניסה כל עסקה ל-recon עם אותו מזהה עסקה כמו בדוח — כך דוח שיגיע אחר כך לא יוצר כפילות.
"""
import os, re, csv, io, imaplib, email, datetime

from gmail_intake import _extract_text, _attachments, _batch_headers, _mail_when, _dec

SRC = 'Authorize מייל'
SENDER = 'mail.authorize.net'
_SUBJ_RECEIPT = 'Merchant Email Receipt'
_SUBJ_ARB_FAIL = re.compile(r'ARB Subscription (\d+): Failed transaction', re.I)
_SUBJ_SUMMARY = 'Summary of Automated Recurring Billing'


def configured():
    return bool((os.environ.get('GMAIL_USER') or '').strip() and os.environ.get('GMAIL_APP_PASSWORD'))


def _field(text, label):
    m = re.search(r'^[ \t]*' + re.escape(label) + r'[ \t]*:[ \t]*(.*)$', text, re.M | re.I)
    return (m.group(1).strip() if m else '')


def _iso(s):
    """'1-Oct-2026 7:16:59 EDT' → '2026-10-01'"""
    m = re.search(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', s or '')
    if not m:
        return ''
    try:
        return datetime.datetime.strptime('%s-%s-%s' % m.groups(), '%d-%b-%Y').date().isoformat()
    except ValueError:
        return ''


def _amt(s):
    m = re.search(r'(\d[\d,]*\.?\d*)', s or '')
    return ('%.2f' % float(m.group(1).replace(',', ''))) if m else ''


def _card(s):
    """'Visa xxxx3190' → 'Visa 3190' (כמו בדוח)"""
    m = re.match(r'\s*([A-Za-z ]+?)\s*x+(\d{4})', s or '')
    return ('%s %s' % (m.group(1).strip(), m.group(2))) if m else (s or '').strip()[:30]


def _billing(text):
    sec = text.split('CUSTOMER BILLING INFORMATION', 1)[-1].split('CUSTOMER SHIPPING', 1)[0] if 'CUSTOMER BILLING INFORMATION' in text else text
    return {'first': _field(sec, 'First Name'), 'last': _field(sec, 'Last Name'), 'business': _field(sec, 'Company'),
            'addr': _field(sec, 'Address'), 'city': _field(sec, 'City'), 'state': _field(sec, 'State/Province'),
            'zip': _field(sec, 'Zip/Postal Code'), 'phone': _field(sec, 'Phone'),
            'email': (_field(sec, 'E-Mail') or _field(sec, 'E-mail')).lower()}


def parse_receipt(text, mail_date=''):
    """Merchant Email Receipt → שורה אחת (או None)."""
    tid = re.sub(r'\D', '', _field(text, 'Transaction ID'))
    if not tid:
        return None
    resp = _field(text, 'Response')
    desc = _field(text, 'Description')
    row = {'tid': tid, 'amount': _amt(_field(text, 'Amount')), 'date': _iso(_field(text, 'Date/Time')) or mail_date,
           'card': _card(_field(text, 'Payment Method')), 'desc': desc, 'reason': '' if 'approved' in resp.lower() else resp,
           'recurring': 1 if re.search(r'monthly|recurring|subscription', desc, re.I) else 0, 'sub_id': '', 'sub_pay': '',
           'st': 'settled' if 'approved' in resp.lower() else 'declined'}
    row.update(_billing(text))
    return row if row['amount'] else None


def parse_arb_failed(text, sub_id, mail_date=''):
    tid = re.sub(r'\D', '', _field(text, 'Transaction ID'))
    row = {'tid': tid or ('anet-arb-%s-%s' % (sub_id, mail_date)), 'amount': _amt(_field(text, 'Amount')), 'date': mail_date,
           'card': '', 'desc': '', 'reason': _field(text, 'Response') or 'declined', 'recurring': 1, 'sub_id': sub_id,
           'sub_pay': (re.search(r'Transaction\s*:\s*(\d+)\s+of', text) or [None, ''])[1], 'st': 'declined'}
    row.update(_billing(text))
    return row if row['amount'] else None


def parse_failed_csv(data, mail_date=''):
    """Failed.csv מהסיכום היומי — העמודות לא מתועדות, ולכן לפי שמות העמודות ככל שיש."""
    out = []
    try:
        txt = data.decode('utf-8-sig', 'replace')
        rd = csv.DictReader(io.StringIO(txt))
        for r in rd:
            g = lambda *ks: next((str(r[k]).strip() for k in r if k and any(x.lower() in k.lower() for x in ks) and str(r[k] or '').strip()), '')
            amt = _amt(g('amount'))
            if not amt:
                continue
            tid = re.sub(r'\D', '', g('transaction id', 'transid', 'trans id'))
            sub = re.sub(r'\D', '', g('subscription id', 'subscriptionid', 'subscription'))
            first, last = g('first name', 'firstname'), g('last name', 'lastname')
            if not (first or last):
                nm = g('customer name', 'name').split()
                first, last = (' '.join(nm[:-1]), nm[-1]) if len(nm) > 1 else ('', nm[0] if nm else '')
            out.append({'tid': tid or ('anet-arb-%s-%s' % (sub, mail_date)), 'amount': amt, 'date': mail_date, 'card': '', 'desc': '',
                        'reason': g('response', 'reason', 'error', 'status') or 'declined', 'recurring': 1, 'sub_id': sub, 'sub_pay': '',
                        'st': 'declined', 'first': first, 'last': last, 'business': g('company'), 'addr': '', 'city': '', 'state': '',
                        'zip': '', 'phone': '', 'email': g('email', 'e-mail').lower()})
    except Exception as e:
        print('  Failed.csv parse:', e)
    return out


def _all_mail_folder(M):
    """תיקיית 'כל הדואר' — לפי הדגל \\All (השם תלוי בשפת החשבון)."""
    try:
        typ, data = M.list()
        for line in data or []:
            s = line.decode('utf-8', 'replace') if isinstance(line, bytes) else str(line)
            if '\\All' in s:
                m = re.search(r'"([^"]+)"\s*$', s) or re.search(r'\s(\S+)\s*$', s)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return '[Gmail]/All Mail'


def scan(con, days=60, max_msgs=2500):
    """סורק את מיילי אוטורייז של הימים האחרונים ומכניס ל-recon מה שחסר. מחזיר תוצאה כמו authorize_sync.save."""
    if not configured():
        return {'שגיאה': 'GMAIL לא מוגדר'}
    user, pw = (os.environ.get('GMAIL_USER') or '').strip(), os.environ.get('GMAIL_APP_PASSWORD')
    con.execute("CREATE TABLE IF NOT EXISTS anet_mail(mid TEXT PRIMARY KEY, at TEXT, kind TEXT)")
    since = (datetime.date.today() - datetime.timedelta(days=days)).strftime('%d-%b-%Y')
    M = None
    rows, checked = [], 0
    try:
        M = imaplib.IMAP4_SSL('imap.gmail.com', timeout=60)
        M.login(user, pw)
        box = _all_mail_folder(M)
        if M.select('"%s"' % box, readonly=True)[0] != 'OK':
            M.select('INBOX', readonly=True)
        typ, data = M.search(None, 'FROM', '"%s"' % SENDER, 'SINCE', since)
        ids = data[0].split() if typ == 'OK' else []
        ids = ids[-max_msgs:]
        heads = _batch_headers(M, ids, fields='SUBJECT DATE MESSAGE-ID')
        todo = []
        for seq, raw in heads:
            try:
                h = email.message_from_bytes(raw)
            except Exception:
                continue
            subj = _dec(h.get('Subject')) or ''
            mid = (h.get('Message-ID') or '').strip() or ('seq:' + seq.decode())
            kind = 'receipt' if _SUBJ_RECEIPT in subj else ('arb' if _SUBJ_ARB_FAIL.search(subj) else ('summary' if _SUBJ_SUMMARY in subj else ''))
            if not kind:
                continue
            if con.execute("SELECT 1 FROM anet_mail WHERE mid=?", (mid,)).fetchone():
                continue
            dstr, _at = _mail_when(h)
            todo.append((seq, mid, kind, subj, dstr))
        for seq, mid, kind, subj, dstr in todo:
            checked += 1
            try:
                typ, md = M.fetch(seq.decode(), '(BODY.PEEK[])')
                if typ != 'OK' or not md or not md[0]:
                    continue
                msg = email.message_from_bytes(md[0][1])
            except Exception:
                continue
            try:
                if kind == 'receipt':
                    r = parse_receipt(_extract_text(msg), dstr)
                    if r:
                        rows.append(r)
                elif kind == 'arb':
                    r = parse_arb_failed(_extract_text(msg), _SUBJ_ARB_FAIL.search(subj).group(1), dstr)
                    if r:
                        rows.append(r)
                else:
                    for fname, ctype, data in _attachments(msg):
                        if (fname or '').lower().startswith('failed'):
                            # הסיכום של הבוקר מדווח על אתמול
                            try:
                                d0 = (datetime.date.fromisoformat(dstr) - datetime.timedelta(days=1)).isoformat()
                            except Exception:
                                d0 = dstr
                            rows += parse_failed_csv(data, d0)
                con.execute("INSERT OR IGNORE INTO anet_mail(mid,at,kind) VALUES(?,?,?)", (mid, dstr, kind))
            except Exception as e:
                print('  authorize mail parse error:', e)
        con.commit()
    finally:
        if M is not None:
            try: M.logout()
            except Exception: pass
    return save(con, rows, checked)


def save(con, rows, checked=0):
    cur = con.cursor()
    added, new_dec = 0, []
    for r in rows:
        if cur.execute("SELECT 1 FROM recon WHERE tid=?", (r['tid'],)).fetchone():
            # כבר נכנס מהדוח / מה-API — אם שם זה "לא עבר" ופה אישור, לא נוגעים
            continue
        st = r.get('st') or 'settled'
        note = (r.get('card') or '')
        if st == 'declined':
            note = ('לא עבר' + (' · ' + r['reason'] if r.get('reason') else '') + (' · הו"ק %s' % r['sub_id'] if r.get('sub_id') else ''))[:200]
        cur.execute("""INSERT INTO recon(tid,first,last,amount,date,addr,city,state,zip,phone,
                           email,recurring,donor_id,category,processed,source,status,note)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL,'',0,?,?,?)""",
                    (r['tid'], r.get('first', ''), r.get('last', '') or r.get('business', ''), r['amount'], r['date'],
                     r.get('addr', ''), r.get('city', ''), r.get('state', ''), r.get('zip', ''), r.get('phone', ''), r.get('email', ''),
                     int(r.get('recurring') or 0), SRC, st, note))
        added += 1
        if st == 'declined':
            new_dec.append(r['tid'])
    con.commit()
    return {'נבדקו': checked, 'נמצאו': len(rows), 'נוספו': added, 'new_declined': new_dec}
