"""📧 מאיר: "אתה פה ב-CRM… אני חייב אותך כל הזמן… אל תגיד שאני לא יכול לעבוד איתך" — חיפוש, קריאה ושליחה של מיילים
מתיבת הג'ימייל של הכולל, דרך החיבור של המערכת עצמה (GMAIL_USER + GMAIL_APP_PASSWORD ב-Render) — לא דרך מחבר חיצוני
שמתנתק. משמש את כלי ה-MCP של היומן (search_email / read_email / send_email). ספריית התקן בלבד."""
import os, re, imaplib, email, datetime
from email.utils import parsedate_to_datetime, getaddresses
import gmail_intake as _gi


def _login():
    user = (os.environ.get('GMAIL_USER') or '').strip()
    pw = (os.environ.get('GMAIL_APP_PASSWORD') or '').strip().replace(' ', '')
    if not user or not pw:
        raise RuntimeError('GMAIL_USER / GMAIL_APP_PASSWORD לא מוגדרים ב-Render')
    M = imaplib.IMAP4_SSL('imap.gmail.com', timeout=25)
    M.login(user, pw)
    return M


def _all_mail(M):
    """שם התיקייה "כל הדואר" (\\All) — לפי הסימון, כי השם משתנה לפי שפת הממשק."""
    typ, data = M.list()
    for ln in data or []:
        s = ln.decode('utf-8', 'replace') if isinstance(ln, bytes) else str(ln)
        if '\\All' in s:
            m = re.search(r'"([^"]+)"\s*$', s) or re.search(r'\s(\S+)\s*$', s)
            if m:
                return '"%s"' % m.group(1)
    return '"[Gmail]/All Mail"'


def _search_uids(M, q):
    q = (q or '').strip()
    if not q:
        typ, data = M.uid('SEARCH', None, 'ALL')
    else:
        M.literal = q.encode('utf-8')
        typ, data = M.uid('SEARCH', 'CHARSET', 'UTF-8', 'X-GM-RAW')
    if typ != 'OK' or not data or not data[0]:
        return []
    return [int(x) for x in data[0].split()]


def _date_of(msg):
    try:
        d = parsedate_to_datetime(msg.get('Date'))
        if d.tzinfo:
            d = d.astimezone(datetime.timezone(datetime.timedelta(hours=2)))
        return d.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return (msg.get('Date') or '')[:25]


def _fetch(M, uid, full=False):
    part = 'BODY.PEEK[]' if full else 'BODY.PEEK[]<0.60000>'
    typ, data = M.uid('FETCH', str(uid), '(X-GM-THRID X-GM-LABELS %s)' % part)
    raw, meta = b'', b''
    for it in data or []:
        if isinstance(it, tuple):
            meta += it[0]
            raw = it[1]
    msg = email.message_from_bytes(raw or b'')
    m = re.search(rb'X-GM-THRID (\d+)', meta)
    labs = re.search(rb'X-GM-LABELS \(([^)]*)\)', meta)
    return msg, (m.group(1).decode() if m else ''), (labs.group(1).decode('utf-8', 'replace') if labs else '')


def _hdr(msg, k):
    return _gi._dec(msg.get(k) or '') if hasattr(_gi, '_dec') else (msg.get(k) or '')


def _text(msg):
    try:
        t = _gi._extract_text(msg) or ''
    except Exception:
        t = ''
    return re.sub(r'\n{3,}', '\n\n', t).strip()


def search(q, limit=15):
    """חיפוש בכל התיבה בתחביר של ג'ימייל (from:, to:, subject:, after:…). מהחדש לישן."""
    M = _login()
    try:
        M.select(_all_mail(M), readonly=True)
        uids = _search_uids(M, q)[-max(1, min(int(limit or 15), 40)):]
        out = []
        for uid in reversed(uids):
            msg, thr, labs = _fetch(M, uid)
            body = _text(msg)
            try:
                body = _gi._strip_quoted(body)
            except Exception:
                pass
            out.append({'uid': uid, 'thread': thr, 'date': _date_of(msg), 'from': _hdr(msg, 'From'), 'to': _hdr(msg, 'To'),
                        'subject': _hdr(msg, 'Subject'), 'sent': 'Sent' in labs,
                        'snippet': re.sub(r'\s+', ' ', body)[:260]})
        return out
    finally:
        try: M.logout()
        except Exception: pass


def read(uid):
    """מייל אחד במלואו + כל ההודעות באותו שרשור (תאריך / מאת / נושא / uid)."""
    M = _login()
    try:
        M.select(_all_mail(M), readonly=True)
        msg, thr, labs = _fetch(M, int(uid), full=True)
        if not msg.get('Date') and not msg.get('Subject'):
            return None
        atts = []
        for p in msg.walk():
            fn = p.get_filename()
            if fn:
                atts.append(_gi._dec(fn) if hasattr(_gi, '_dec') else fn)
        thread = []
        if thr:
            typ, data = M.uid('SEARCH', 'X-GM-THRID', thr)
            for u in (data[0].split() if typ == 'OK' and data and data[0] else [])[-25:]:
                typ2, d2 = M.uid('FETCH', u, '(BODY.PEEK[HEADER.FIELDS (FROM DATE SUBJECT)])')
                h = email.message_from_bytes(next((x[1] for x in d2 if isinstance(x, tuple)), b''))
                thread.append({'uid': int(u), 'date': _date_of(h), 'from': _hdr(h, 'From'), 'subject': _hdr(h, 'Subject')})
        return {'uid': int(uid), 'thread_id': thr, 'date': _date_of(msg), 'from': _hdr(msg, 'From'), 'to': _hdr(msg, 'To'),
                'cc': _hdr(msg, 'Cc'), 'subject': _hdr(msg, 'Subject'), 'message_id': (msg.get('Message-ID') or '').strip(),
                'references': (msg.get('References') or '').strip(), 'text': _text(msg)[:12000], 'attachments': atts, 'thread': thread}
    finally:
        try: M.logout()
        except Exception: pass


def reply_headers(uid):
    """לתשובה בתוך השרשור: נושא "Re: …", In-Reply-To ו-References של המייל שעונים עליו, ולמי לענות."""
    r = read(uid)
    if not r:
        return None
    subj = r['subject'] or ''
    if not re.match(r'^\s*(re|תשובה)\s*:', subj, re.I):
        subj = 'Re: ' + subj
    refs = (r['references'] + ' ' + r['message_id']).strip()
    frm = [a for _n, a in getaddresses([r['from']]) if a]
    return {'subject': subj, 'headers': {'In-Reply-To': r['message_id'], 'References': refs}, 'from': frm[0] if frm else '',
            'from_full': r['from']}
