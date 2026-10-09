# -*- coding: utf-8 -*-
"""חיבור חי לבנק ווסט (Banquest) — מערכת accept.blue, API v2.

מאיר: "אם אני רוצה לעשות את החיובים באשראי של בנק ווסט דרך המערכת שלנו…
גם בכרטיס תורם שאפשר לחייב אותו במיידי וגם בדף ייעודי". בנק ווסט מריץ את
הוראות הקבע בעצמו; המערכת שלנו מושכת את העסקאות, הוראות הקבע והלקוחות,
מציגה אותם, ומאפשרת לחייב עכשיו כרטיס שמור, להשהות ולשנות סכום / תאריך.

הפרטים לחיבור — ב-Render בלבד (לא בקוד, לא בקובץ ולא בהודעות):
    BANQUEST_KEY   ה-Source Key (Control Panel ← Sources)
    BANQUEST_PIN   ה-PIN שנבחר ליצירת המפתח
אופציונלי:
    BANQUEST_BASE  כתובת אחרת (למשל sandbox: https://api.sandbox.accept.blue/api/v2/)
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

PROD = 'https://api.accept.blue/api/v2/'
UA = 'KollelChatzosCRM/1.0 (+banquest sync)'
LAST = {'at': '', 'ok': None, 'error': '', 'method': ''}

# סטטוסים — מה נחשב כסף שעבר ומה חזר
OK_ST = ('captured', 'settled', 'approved', 'pending', 'originated', 'queued')
BAD_ST = ('declined', 'error', 'blocked', 'expired', 'returned', 'cancelled')


def _env(k):
    return (os.environ.get(k) or '').strip()


def configured():
    return bool(_env('BANQUEST_KEY'))


def base():
    b = _env('BANQUEST_BASE') or PROD
    return b if b.endswith('/') else b + '/'


def _auth():
    tok = base64.b64encode(('%s:%s' % (_env('BANQUEST_KEY'), _env('BANQUEST_PIN'))).encode('utf-8')).decode('ascii')
    return 'Basic ' + tok


def call(method, path, body=None, query=None, timeout=45):
    """בקשה אחת. מחזיר (קוד, JSON או טקסט). השגיאה נשמרת ב-LAST למסך הבדיקה."""
    url = base() + path.lstrip('/')
    if query:
        url += '?' + urllib.parse.urlencode({k: v for k, v in query.items() if v not in (None, '')})
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': _auth(), 'Accept': 'application/json', 'User-Agent': UA,
        **({'Content-Type': 'application/json'} if data is not None else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, raw = r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        LAST.update(at=time.strftime('%Y-%m-%d %H:%M'), ok=False, error=str(e)[:200], method=path)
        return 0, str(e)
    try:
        out = json.loads(raw) if raw.strip() else {}
    except ValueError:
        out = raw
    ok = 200 <= code < 300
    err = ''
    if not ok:
        err = (out.get('error_message') or out.get('message') or '') if isinstance(out, dict) else str(out)[:200]
        err = '%s %s' % (code, err or raw[:160])
    LAST.update(at=time.strftime('%Y-%m-%d %H:%M'), ok=ok, error=err, method=path)
    return code, out


def pages(path, query=None, limit=100, cap=60):
    """כל העמודים של רשימה (limit/offset)."""
    out, off = [], 0
    for _ in range(cap):
        q = dict(query or {}, limit=limit, offset=off)
        code, res = call('GET', path, query=q)
        if code != 200 or not isinstance(res, list):
            if code != 200:
                raise RuntimeError('בנק ווסט %s: %s' % (path, LAST.get('error') or code))
            break
        out.extend(res)
        if len(res) < limit:
            break
        off += limit
    return out


# ---------- משיכה ----------

def transactions(date_from, date_to=''):
    return pages('transactions', {'date_from': date_from, 'date_to': date_to, 'order': 'asc'})


def schedules():
    return pages('recurring-schedules')


def customers():
    return pages('customers')


def payment_methods():
    return pages('payment-methods')


def tx_row(t):
    """עסקה אחת בשפה של המערכת שלנו."""
    td = t.get('transaction_details') or {}
    ad = t.get('amount_details') or {}
    cu = t.get('customer') or {}
    bi = t.get('billing_info') or {}
    cd = t.get('card_details') or t.get('check_details') or {}
    st = (t.get('status_details') or {})
    ref = td.get('reference_number') or t.get('id')
    name = ' '.join(x for x in ((bi.get('first_name') or '').strip(), (bi.get('last_name') or '').strip()) if x) \
        or (cd.get('name') or '').strip() or (cu.get('identifier') or '').strip()
    return {
        'id': int(t.get('id') or 0), 'ref': int(ref or 0),
        'created': (t.get('created_at') or '')[:19].replace('T', ' '),
        'settled': t.get('settled_date') or '',
        'amount': float(ad.get('amount') or 0),
        'status': (st.get('status') or '').lower(),
        'error': (st.get('error_message') or '').strip(),
        'type': (td.get('type') or '').lower(),
        'schedule_id': int(td.get('schedule_id') or 0),
        'description': (td.get('description') or '').strip(),
        'customer_id': int(cu.get('customer_id') or 0),
        'email': (cu.get('email') or '').strip(),
        'name': name, 'first': (bi.get('first_name') or '').strip(), 'last': (bi.get('last_name') or '').strip(),
        'phone': (bi.get('phone') or '').strip(),
        'addr': (bi.get('street') or '').strip(), 'city': (bi.get('city') or '').strip(),
        'state': (bi.get('state') or '').strip(), 'zip': (bi.get('zip') or '').strip(),
        'card': ('%s %s' % (cd.get('card_type') or '', cd.get('last4') or '')).strip(),
    }


# ---------- פעולות ----------

def charge_pm(pm_id, amount, description='', customer_id=0, email='', send_receipt=True, custom=None, cit=False):
    """חיוב מיידי של כרטיס שמור (pm-…). בנק ווסט שולח לתורם את אישור העסקה שלו.
    cit — החיוב הראשון בכרטיס שהתורם נתן עכשיו (חיוב של בעל הכרטיס, לא של העסק)."""
    body = {'amount': round(float(amount), 2), 'source': 'pm-%d' % int(pm_id),
            'transaction_details': {'description': (description or '')[:255]},
            'transaction_flags': {'is_customer_initiated': bool(cit)}}
    cust = {}
    if customer_id:
        cust['customer_id'] = int(customer_id)
    if email:
        cust['email'] = email
        cust['send_receipt'] = bool(send_receipt)
    if cust:
        body['customer'] = cust
    if custom:
        body['custom_fields'] = custom
    return call('POST', 'transactions/charge', body)


def token_key():
    """מפתח Tokenization (מתחיל ב-pk_) — לטופס הכרטיס המאובטח בדפדפן. מפתח ציבורי לפי
    בנק ווסט, אבל גם הוא נכנס רק ב-Render: BANQUEST_TOKEN_KEY."""
    return _env('BANQUEST_TOKEN_KEY')


def token_js():
    return _env('BANQUEST_TOKEN_JS') or ('https://tokenization.sandbox.accept.blue/tokenization/v0.3'
                                          if 'sandbox' in base() else 'https://tokenization.accept.blue/tokenization/v0.3')


def create_customer(name, first='', last='', email='', phone='', number=''):
    body = {'identifier': (name or 'Donor')[:255], 'first_name': first[:255], 'last_name': last[:255]}
    if email:
        body['email'] = email
    if phone:
        body['phone'] = re.sub(r'[()]', '', phone)[:50]
    if number:
        body['customer_number'] = str(number)[:255]
    return call('POST', 'customers', body)


def create_pm(customer_id, source, exp_m=0, exp_y=0, name='', avs_zip='', is_default=True):
    """כרטיס שמור ללקוח מתוך nonce של הטופס המאובטח (או ref- של עסקה)."""
    body = {'source': source, 'is_default': bool(is_default)}
    if exp_m and exp_y:
        body.update(expiry_month=int(exp_m), expiry_year=int(exp_y))
    if name:
        body['name'] = name[:255]
    if avs_zip:
        body['avs_zip'] = avs_zip[:50]
    return call('POST', 'customers/%d/payment-methods' % int(customer_id), body)


def charge_source(source, amount, description='', customer_id=0, email='', exp_m=0, exp_y=0, name='', avs_zip='',
                  save_card=False):
    body = {'amount': round(float(amount), 2), 'source': source, 'save_card': bool(save_card),
            'transaction_details': {'description': (description or '')[:255]}}
    if exp_m and exp_y:
        body.update(expiry_month=int(exp_m), expiry_year=int(exp_y))
    if name:
        body['name'] = name[:255]
    if avs_zip:
        body['avs_zip'] = avs_zip[:50]
    cust = {}
    if customer_id:
        cust['customer_id'] = int(customer_id)
    if email:
        cust.update(email=email, send_receipt=True)
    if cust:
        body['customer'] = cust
    return call('POST', 'transactions/charge', body)


def void_tx(ref):
    """ביטול עסקה שעוד לא נסגרה (באותו יום, לפני ה-batch) — כל הסכום."""
    return call('POST', 'transactions/void', {'reference_number': int(ref)})


def refund_tx(ref, amount=None):
    """החזר לכרטיס על עסקה שנסגרה — כל הסכום, או חלק ממנו (amount)."""
    body = {'reference_number': int(ref)}
    if amount:
        body['amount'] = round(float(amount), 2)
    return call('POST', 'transactions/refund', body)


def update_schedule(sid, **fields):
    body = {k: v for k, v in fields.items() if v is not None}
    return call('PATCH', 'recurring-schedules/%d' % int(sid), body)


def create_schedule(customer_id, title, amount, payment_method_id, next_run_date='', num_left=0,
                    receipt_email='', frequency='monthly'):
    body = {'title': (title or 'תרומה')[:255], 'amount': round(float(amount), 2),
            'payment_method_id': int(payment_method_id), 'frequency': frequency,
            'num_left': int(num_left or 0)}
    if next_run_date:
        body['next_run_date'] = next_run_date
    if receipt_email:
        body['receipt_email'] = receipt_email
    return call('POST', 'customers/%d/recurring-schedules' % int(customer_id), body)


def check():
    """לבדיקת החיבור במסך המערכת."""
    if not configured():
        return False, 'חסר BANQUEST_KEY ב-Render'
    code, res = call('GET', 'recurring-schedules', query={'limit': 1})
    if code == 200:
        return True, 'מחובר'
    return False, LAST.get('error') or str(code)
