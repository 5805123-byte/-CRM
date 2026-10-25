# -*- coding: utf-8 -*-
"""חיבור חי ל-Authorize.net — כל חיוב שנגבה שם נכנס למערכת מעצמו.

שני מסלולים, ושניהם עובדים יחד:
  1. משיכה תקופתית  — סורקת את האצוות שנסגרו ומביאה כל עסקה שטרם נרשמה.
  2. Webhook         — Authorize.net דוחף אלינו הודעה ברגע שחיוב עובר,
                       ואז מושכים בדיוק את העסקה הזו. עדכון תוך שניות.

המשיכה היא רשת הביטחון: גם אם הודעה אחת אבדה בדרך, הסריקה הבאה תתפוס אותה.

הפרטים לחיבור נקראים ממשתני סביבה בלבד — לעולם לא בקוד ולא במסד:
  AUTHNET_LOGIN_ID       שם ה-API (API Login ID)
  AUTHNET_TRANSACTION_KEY מפתח העסקאות (Transaction Key)
  AUTHNET_SIGNATURE_KEY  מפתח החתימה — לאימות שההודעה באמת מ-Authorize.net
  AUTHNET_ENV            production (ברירת מחדל) או sandbox לבדיקות
"""

import os, json, hmac, hashlib, urllib.request, datetime

PROD = 'https://api.authorize.net/xml/v1/request.api'
TEST = 'https://apitest.authorize.net/xml/v1/request.api'
SRC = 'Authorize אונליין'          # מקור החיובים במסך ההפקדות


def _login():
    return (os.environ.get('AUTHNET_LOGIN_ID') or '').strip()


def _key():
    return (os.environ.get('AUTHNET_TRANSACTION_KEY') or '').strip()


def _sig_key():
    return (os.environ.get('AUTHNET_SIGNATURE_KEY') or '').strip()


def configured():
    """האם יש פרטי חיבור. בלעדיהם המערכת פשוט לא מנסה להתחבר."""
    return bool(_login() and _key())


def endpoint():
    return TEST if (os.environ.get('AUTHNET_ENV') or '').lower().startswith('sand') else PROD


def _auth():
    return {'name': _login(), 'transactionKey': _key()}


def call(name, payload, timeout=45):
    """בקשה אחת ל-Authorize.net. התשובה שלהם מגיעה עם תו BOM בתחילתה,
    ובלי לנקות אותו הפענוח נכשל — זו התקלה הקלאסית מול השירות הזה."""
    body = json.dumps({name: dict({'merchantAuthentication': _auth()}, **payload)}).encode('utf-8')
    req = urllib.request.Request(endpoint(), body, {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        txt = r.read().decode('utf-8-sig', 'replace').lstrip('﻿ \r\n\t')
    out = json.loads(txt)
    msg = (out.get('messages') or {})
    if (msg.get('resultCode') or '') == 'Error':
        m = (msg.get('message') or [{}])[0]
        raise RuntimeError('%s: %s' % (m.get('code', ''), m.get('text', 'שגיאה לא ידועה')))
    return out


# ---------- קריאת עסקאות ----------

def _iso(d):
    return d.strftime('%Y-%m-%dT%H:%M:%SZ')


def settled_batches(days=10):
    """האצוות שנסגרו בימים האחרונים. Authorize.net מגביל ל-31 יום לכל בקשה."""
    days = max(1, min(int(days or 10), 31))
    now = datetime.datetime.utcnow()
    out = call('getSettledBatchListRequest', {
        'firstSettlementDate': _iso(now - datetime.timedelta(days=days)),
        'lastSettlementDate': _iso(now + datetime.timedelta(days=1))})
    b = out.get('batchList') or []
    return [x.get('batchId') for x in b if x.get('batchId')]


def batch_transactions(batch_id):
    """כל העסקאות באצווה אחת, בדפים של 1000."""
    rows, offset = [], 1
    while True:
        out = call('getTransactionListRequest', {
            'batchId': str(batch_id),
            'sorting': {'orderBy': 'submitTimeUTC', 'orderDescending': False},
            'paging': {'limit': 1000, 'offset': offset}})
        page = out.get('transactions') or []
        rows += page
        if len(page) < 1000:
            return rows
        offset += 1


def transaction(tid):
    """פרטים מלאים של עסקה אחת — מייל, כתובת, ומספר המנוי אם זה חיוב קבוע."""
    return (call('getTransactionDetailsRequest', {'transId': str(tid)}) or {}).get('transaction') or {}


def unsettled():
    """עסקאות שעדיין לא נסגרו לאצווה — כדי לראות חיוב מהיום כבר עכשיו."""
    return (call('getUnsettledTransactionListRequest', {}) or {}).get('transactions') or []


# ---------- תרגום לשורה במערכת ----------

def _row(t, detail=None):
    """שורת חיוב אחת בשפה של המערכת שלנו."""
    d = detail or {}
    bill = d.get('billTo') or t.get('billTo') or {}
    sub = d.get('subscription') or {}
    cust = d.get('customer') or {}
    amt = d.get('settleAmount', d.get('authAmount', t.get('settleAmount')))
    when = (d.get('submitTimeUTC') or t.get('submitTimeUTC') or '')[:10]
    return {
        'tid': 'anet-' + str(t.get('transId') or d.get('transId') or ''),
        'first': (bill.get('firstName') or '').strip(),
        'last': (bill.get('lastName') or '').strip(),
        'business': (bill.get('company') or '').strip(),
        'amount': '%.2f' % float(amt or 0),
        'date': when,
        'email': (cust.get('email') or d.get('customer', {}).get('email') or '').strip(),
        'phone': (bill.get('phoneNumber') or '').strip(),
        'addr': (bill.get('address') or '').strip(),
        'city': (bill.get('city') or '').strip(),
        'state': (bill.get('state') or '').strip(),
        'zip': (bill.get('zip') or '').strip(),
        # חיוב קבוע: Authorize.net מחזיר מספר מנוי ומספר תשלום בתוכו
        'recurring': 1 if sub.get('id') else 0,
        'sub_id': str(sub.get('id') or ''),
        'sub_pay': str(sub.get('payNum') or ''),
        'status': (d.get('transactionStatus') or t.get('transactionStatus') or ''),
        # מאיר: "אתה אמור להתריע לי על כל תרומה שלא עברה באוטרייז" — הסיבה לדחייה, כשיש
        'reason': (d.get('responseReasonDescription') or t.get('responseReasonDescription') or '').strip(),
    }


LIVE_OK = ('settledSuccessfully', 'capturedPendingSettlement', 'authorizedPendingCapture')
# חיוב שלא עבר — נכנס למערכת כ"לא עבר" (כמו חיוב שחזר בבנק ווסט), ומאיר מקבל התרעה
DECLINED = ('declined', 'generalError', 'communicationError', 'expired', 'returnedItem', 'failedReview', 'settlementError')


def _classify(rows):
    out = []
    for r in rows:
        if r['status'] in LIVE_OK:
            r['st'] = 'settled'
        elif r['status'] in DECLINED:
            r['st'] = 'declined'
        else:
            continue
        if float(r['amount'] or 0) > 0:
            out.append(r)
    return out


# ---------- הוראות קבע (ARB): חיובים שנכשלו ----------
# רשימת העסקאות הרגילה מביאה רק מה שנסגר לאצווה; חיוב של הוראת קבע שנדחה לא מגיע לשם בכלל.
# לכן פעם ביום עוברים על המנויים (הוראות הקבע) ומביאים מההיסטוריה שלהם את הניסיונות שנכשלו.

def arb_subscriptions(kind='subscriptionActive'):
    rows, offset = [], 1
    while True:
        out = call('ARBGetSubscriptionListRequest', {'searchType': kind,
                   'sorting': {'orderBy': 'id', 'orderDescending': True}, 'paging': {'limit': 1000, 'offset': offset}}) or {}
        page = out.get('subscriptionDetails') or []
        rows += page
        if len(page) < 1000:
            return rows
        offset += 1


def arb_subscription(sid):
    return (call('ARBGetSubscriptionRequest', {'subscriptionId': str(sid), 'includeTransactions': True}) or {}).get('subscription') or {}


def arb_failed(days=45):
    """הניסיונות שנכשלו בהוראות הקבע ב-days הימים האחרונים — שורות כמו של collect, עם st='declined'.
    מחזיר (שורות, רשימת מנויים שהושעו/בוטלו)."""
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    rows, sus = [], []
    subs = []
    for kind in ('subscriptionActive', 'subscriptionInactive'):
        try:
            subs += arb_subscriptions(kind)
        except Exception as e:
            print('  ARB list error:', e)
    for s in subs:
        sid = str(s.get('id') or '')
        if not sid:
            continue
        st = str(s.get('status') or '')
        if st in ('suspended', 'terminated') and (s.get('createTimeStampUTC') or '')[:10] >= '2000':
            sus.append({'sub_id': sid, 'status': st, 'first': s.get('firstName') or '', 'last': s.get('lastName') or '',
                        'amount': '%.2f' % float(s.get('amount') or 0), 'name': s.get('name') or ''})
        try:
            sub = arb_subscription(sid)
        except Exception as e:
            print('  ARB sub error:', sid, e)
            continue
        prof = sub.get('profile') or {}
        pp = prof.get('paymentProfile') or {}
        bill = pp.get('billTo') or {}
        for t in (sub.get('arbTransactions') or []):
            resp = str(t.get('response') or '')
            when = str(t.get('submitTimeUTC') or '')[:10]
            if 'approved' in resp.lower() or not when or when < cutoff:
                continue
            tid = str(t.get('transId') or '')
            rows.append({'tid': ('anet-' + tid) if tid else 'anet-arb-%s-%s-%s' % (sid, t.get('payNum') or '', t.get('attemptNum') or ''),
                         'first': (bill.get('firstName') or s.get('firstName') or '').strip(), 'last': (bill.get('lastName') or s.get('lastName') or '').strip(),
                         'business': (bill.get('company') or '').strip(), 'amount': '%.2f' % float(s.get('amount') or sub.get('amount') or 0), 'date': when,
                         'email': (prof.get('email') or '').strip(), 'phone': (bill.get('phoneNumber') or '').strip(),
                         'addr': (bill.get('address') or '').strip(), 'city': (bill.get('city') or '').strip(), 'state': (bill.get('state') or '').strip(),
                         'zip': (bill.get('zip') or '').strip(), 'recurring': 1, 'sub_id': sid, 'sub_pay': str(t.get('payNum') or ''),
                         'status': 'declined', 'reason': resp, 'st': 'declined', 'sub_status': st})
    return rows, sus


def collect(days=10, with_detail=True, only_tid=None):
    """אוסף את כל החיובים שנגבו — מוכנים להכנסה למערכת."""
    seen, out = set(), []
    if only_tid:
        d = transaction(only_tid)
        if d:
            out.append(_row({'transId': only_tid}, d))
        return _classify(out)
    for t in unsettled():
        tid = str(t.get('transId') or '')
        if tid and tid not in seen:
            seen.add(tid)
            out.append(_row(t, transaction(tid) if with_detail else None))
    for bid in settled_batches(days):
        for t in batch_transactions(bid):
            tid = str(t.get('transId') or '')
            if not tid or tid in seen:
                continue
            seen.add(tid)
            out.append(_row(t, transaction(tid) if with_detail else None))
    return _classify(out)


# ---------- שמירה במערכת ----------

def save(con, rows, link=None):
    """מכניס למסד רק מה שעדיין לא נמצא שם. חיוב שכבר נרשם לא נרשם שוב,
    ולכן אפשר להריץ את המשיכה שוב ושוב בלי לפחד מכפילויות."""
    cur = con.cursor()
    added = matched = 0
    new_dec = []
    for r in rows:
        if cur.execute("SELECT 1 FROM recon WHERE tid=?", (r['tid'],)).fetchone():
            continue
        st = r.get('st') or 'settled'
        note = 'חיוב קבוע · תשלום %s' % r['sub_pay'] if r['recurring'] and r['sub_pay'] else ''
        if st == 'declined':
            note = ('לא עבר' + (' · ' + r['reason'] if r.get('reason') else '') + (' · ' + note if note else ''))[:200]
        cur.execute("""INSERT INTO recon(tid,first,last,amount,date,addr,city,state,zip,phone,
                           email,recurring,donor_id,category,processed,source,status)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,0,?,?)""",
                    (r['tid'], r['first'], r['last'] or r['business'], r['amount'], r['date'],
                     r['addr'], r['city'], r['state'], r['zip'], r['phone'], r['email'],
                     r['recurring'], note, SRC, st))
        added += 1
        if st == 'declined':
            new_dec.append(r['tid'])
    con.commit()
    if added and link:
        try:
            matched = link(con) or 0        # שיוך לפי מייל / טלפון / שם
        except Exception:
            matched = 0
    return {'נבדקו': len(rows), 'נוספו': added, 'שויכו': matched, 'new_declined': new_dec}


def sync(con, days=10, link=None, only_tid=None):
    if not configured():
        return {'שגיאה': 'לא הוגדרו פרטי חיבור ל-Authorize.net'}
    return save(con, collect(days=days, only_tid=only_tid), link=link)


def sync_arb(con, days=45, link=None):
    """סריקת הוראות הקבע: ניסיונות שנכשלו → recon בסטטוס 'declined' (+ רשימת מנויים מושעים)."""
    if not configured():
        return {'שגיאה': 'לא הוגדרו פרטי חיבור ל-Authorize.net'}
    rows, sus = arb_failed(days)
    res = save(con, rows, link=link)
    res['suspended'] = sus
    return res


# ---------- Webhook ----------

def verify(raw_body, header_sig):
    """מוודא שההודעה באמת הגיעה מ-Authorize.net ולא ממישהו שמנחש כתובות.
    בלי מפתח חתימה מוגדר — לא מקבלים הודעות בכלל."""
    key = _sig_key()
    if not key or not header_sig:
        return False
    want = hmac.new(key.encode('utf-8'), raw_body, hashlib.sha512).hexdigest()
    got = str(header_sig).split('=')[-1].strip()
    return hmac.compare_digest(want.lower(), got.lower())


def webhook_tid(payload):
    """מזהה העסקה מתוך ההודעה שהתקבלה."""
    p = (payload or {}).get('payload') or {}
    return str(p.get('id') or '') if (payload or {}).get('eventType', '').find('payment') >= 0 else str(p.get('id') or '')
