"""📎 דפי בנק ודוחות שהגיעו במייל (דפי צ'ייס, הדוחות של הערשי פרידמן) — הטקסט שלהם נשמר במערכת
כדי שאפשר יהיה לחפש בהם תורם או סכום בלי לפתוח קבצים ביד.
מאיר: "יש כן דוחות של צ'ייס ב-2025… תחפש טוב באימיילים של פרידמן".

מה נסרק: מיילים מהערשי פרידמן (hfriedman@yeshivanet.com) ומתיבת המשרד (chatzot.ah@gmail.com) שיש בהם
קובץ PDF / Excel / CSV שהשם או הנושא שלו מרמזים על דף בנק או דוח (Chase, CCF_, Report from…, צייס).
הקבצים עצמם לא נשמרים — רק הטקסט שחולץ מהם (לחיפוש)."""
import os, re, io, imaplib, email, datetime

from gmail_intake import _attachments, _batch_headers, _mail_when, _dec
from authorize_mail import _all_mail_folder

SENDERS = ('hfriedman@yeshivanet.com', 'chatzot.ah@gmail.com')
SUBJ_RX = re.compile(r'chase|ccf|report|emailing|quickbooks|צייס|צ\'ייס|שיקים|דוח|statement', re.I)
FILE_RX = re.compile(r'\.(pdf|xlsx|xls|csv)$', re.I)
MAX_ATT = 16 * 1024 * 1024


def configured():
    return bool(os.environ.get('GMAIL_USER') and os.environ.get('GMAIL_APP_PASSWORD'))


def ensure(con):
    con.execute("""CREATE TABLE IF NOT EXISTS mail_docs(id INTEGER PRIMARY KEY AUTOINCREMENT, mid TEXT, fname TEXT,
                   subject TEXT, mail_date TEXT, sender TEXT, pages INTEGER, size INTEGER, text TEXT, created TEXT,
                   UNIQUE(mid, fname))""")
    con.execute("CREATE TABLE IF NOT EXISTS mail_docs_seen(mid TEXT PRIMARY KEY, at TEXT)")


def _pdf_text(data):
    try:
        import fitz
        doc = fitz.open(stream=data, filetype='pdf')
        return '\n'.join(p.get_text() for p in doc), len(doc)
    except Exception:
        pass
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        return '\n'.join((p.extract_text() or '') for p in r.pages), len(r.pages)
    except Exception as e:
        return '[PDF לא נקרא: %s]' % str(e)[:80], 0


def _xlsx_text(data):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        out, n = [], 0
        for ws in wb.worksheets:
            n += 1
            out.append('== ' + ws.title)
            for row in ws.iter_rows(values_only=True):
                cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if cells:
                    out.append(' | '.join(cells))
        return '\n'.join(out), n
    except Exception as e:
        return '[Excel לא נקרא: %s]' % str(e)[:80], 0


def extract(fname, data):
    f = (fname or '').lower()
    if f.endswith('.pdf'):
        return _pdf_text(data)
    if f.endswith('.xlsx'):
        return _xlsx_text(data)
    if f.endswith('.xls'):
        return '[קובץ xls ישן — אין קורא בשרת]', 0
    if f.endswith('.csv'):
        return data.decode('utf-8', 'replace'), 1
    return '', 0


def scan(con, since='01-Jan-2025', max_msgs=600):
    """מוריד מהתיבה את הקבצים הרלוונטיים שעוד לא נסרקו. מחזיר (מיילים שנבדקו, קבצים שנשמרו)."""
    if not configured():
        return 0, 0
    ensure(con)
    user, pw = (os.environ.get('GMAIL_USER') or '').strip(), os.environ.get('GMAIL_APP_PASSWORD')
    M, checked, saved = None, 0, 0
    try:
        M = imaplib.IMAP4_SSL('imap.gmail.com', timeout=90)
        M.login(user, pw)
        box = _all_mail_folder(M)
        if M.select('"%s"' % box, readonly=True)[0] != 'OK':
            M.select('INBOX', readonly=True)
        ids = []
        for s in SENDERS:
            typ, data = M.search(None, 'FROM', '"%s"' % s, 'SINCE', since)
            if typ == 'OK' and data and data[0]:
                ids += data[0].split()
        ids = sorted(set(ids), key=lambda x: int(x))[-max_msgs:]
        heads = _batch_headers(M, ids, fields='FROM SUBJECT DATE MESSAGE-ID')
        todo = []
        for seq, raw in heads:
            try:
                h = email.message_from_bytes(raw)
            except Exception:
                continue
            subj = _dec(h.get('Subject')) or ''
            mid = (h.get('Message-ID') or '').strip() or ('seq:' + seq.decode())
            if con.execute("SELECT 1 FROM mail_docs_seen WHERE mid=?", (mid,)).fetchone():
                continue
            sender = _dec(h.get('From')) or ''
            # מהערשי — כל מייל עם קובץ נבדק; מהמשרד — רק לפי נושא שמרמז על דף בנק/דוח
            if 'hfriedman' not in sender.lower() and not SUBJ_RX.search(subj):
                continue
            dstr, _at = _mail_when(h)
            todo.append((seq, mid, subj, sender, dstr))
        for seq, mid, subj, sender, dstr in todo:
            checked += 1
            try:
                typ, md = M.fetch(seq.decode(), '(BODY.PEEK[])')
                if typ != 'OK' or not md or not md[0]:
                    continue
                msg = email.message_from_bytes(md[0][1])
                for fname, ctype, data in _attachments(msg, max_bytes=MAX_ATT):
                    if not FILE_RX.search(fname or ''):
                        continue
                    text, pages = extract(fname, data)
                    con.execute("INSERT OR IGNORE INTO mail_docs(mid,fname,subject,mail_date,sender,pages,size,text,created) "
                                "VALUES(?,?,?,?,?,?,?,?,?)",
                                (mid, fname, subj[:200], dstr, sender[:120], pages, len(data), text,
                                 datetime.datetime.now().isoformat(timespec='minutes')))
                    saved += 1
                con.execute("INSERT OR IGNORE INTO mail_docs_seen(mid,at) VALUES(?,?)", (mid, dstr))
                con.commit()
            except Exception as e:
                print('  mail_docs fetch error:', str(e)[:120])
    finally:
        if M is not None:
            try: M.logout()
            except Exception: pass
    return checked, saved


def find(con, pattern, ctx=2, limit=400):
    """שורות מכל המסמכים שמתאימות לביטוי (לא תלוי רישיות), עם כמה שורות הקשר לפני ואחרי."""
    rx = re.compile(pattern, re.I)
    out = []
    for d in con.execute("SELECT id,fname,subject,mail_date,pages FROM mail_docs ORDER BY mail_date, id"):
        text = con.execute("SELECT text FROM mail_docs WHERE id=?", (d['id'],)).fetchone()['text'] or ''
        lines = text.split('\n')
        hits = [i for i, ln in enumerate(lines) if rx.search(ln)]
        if not hits:
            continue
        blocks, last_end = [], -1
        for i in hits:
            a, b = max(0, i - ctx), min(len(lines), i + ctx + 1)
            if a <= last_end:
                blocks[-1] = (blocks[-1][0], b)
            else:
                blocks.append((a, b))
            last_end = b
        out.append({'id': d['id'], 'fname': d['fname'], 'subject': d['subject'], 'mail_date': d['mail_date'],
                    'pages': d['pages'], 'n': len(hits),
                    'blocks': ['\n'.join(x.strip() for x in lines[a:b] if x.strip()) for a, b in blocks][:limit]})
    return out


def summary(con):
    return [dict(r) for r in con.execute(
        "SELECT id,fname,subject,mail_date,sender,pages,size,length(COALESCE(text,'')) AS chars FROM mail_docs ORDER BY mail_date, id")]
