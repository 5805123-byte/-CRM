# -*- coding: utf-8 -*-
"""
משיכת בקשות תפילה (שמות לקוויטל) מתיבת הג'ימייל הראשית — דרך IMAP עם סיסמת־אפליקציה.
אין צורך ב-Google Cloud / OAuth: מפעילים אימות דו־שלבי, יוצרים App Password, ומגדירים
משתני סביבה ב-Render. הכל בספריית התקן של פייתון (imaplib + email).

משתני סביבה:
    GMAIL_USER          כתובת התיבה (למשל main@gmail.com)
    GMAIL_APP_PASSWORD  סיסמת אפליקציה בת 16 תווים (לא הסיסמה הרגילה!)
    INTAKE_FROM         (רשות) סינון לפי שולח — תת־מחרוזות מופרדות בפסיק (כתובת האתר ששולח)
    INTAKE_SUBJECT      (רשות) סינון לפי נושא — תת־מחרוזת
    INTAKE_SINCE        (רשות) תאריך התחלה בפורמט IMAP, ברירת מחדל 01-Jan-2026
    INTAKE_MAILBOX      (רשות) תיבה, ברירת מחדל INBOX
"""
import os, re, imaplib, email, datetime
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime


def _dec(s):
    if not s:
        return ''
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return str(s)


def _html_to_text(html):
    html = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', html)
    html = re.sub(r'(?i)<br\s*/?>', '\n', html)
    html = re.sub(r'(?i)</(p|div|tr|li|h[1-6])>', '\n', html)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = (html.replace('&nbsp;', ' ').replace('&amp;', '&')
                .replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'"))
    return html


def _extract_text(msg):
    """מחזיר טקסט נקי מגוף המייל (מעדיף text/plain, אחרת HTML מומר לטקסט)."""
    plain, html = '', ''
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get('Content-Disposition') or '')
            if 'attachment' in disp:
                continue
            if ctype == 'text/plain' and not plain:
                plain = _payload(part)
            elif ctype == 'text/html' and not html:
                html = _payload(part)
    else:
        if msg.get_content_type() == 'text/html':
            html = _payload(msg)
        else:
            plain = _payload(msg)
    text = plain or _html_to_text(html)
    lines = [ln.strip() for ln in re.split(r'\r?\n', text)]
    out = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return '\n'.join(out).strip()


def _payload(part):
    try:
        raw = part.get_payload(decode=True)
        if raw is None:
            return ''
        return raw.decode(part.get_content_charset() or 'utf-8', 'replace')
    except Exception:
        try:
            return str(part.get_payload())
        except Exception:
            return ''


# מיפוי תוויות השדות בטופס האתר לשדות מובנים
_LABEL_MAP = [
    (('name to daven for', 'name for prayer', 'prayer name', 'שם לתפילה', 'שם המתפלל'), 'name'),
    (("mother's name", 'mothers name', 'mother name', 'שם האם', 'שם אם', 'שם האמא'), 'mother'),
    (("father's name", 'fathers name', 'father name', 'שם האב', 'שם אב'), 'father'),
    (('request', 'בקשה', 'ישועה'), 'request'),
]
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')


def _submitter_email(body):
    m = _EMAIL_RE.search(body or '')
    return m.group(0).lower() if m else ''


# תרגום הבקשה (מגיעה באנגלית מהטופס) לנוסח קוויטל בעברית
_REQ_MAP = {
    'zivug': 'לזיווג הגון', 'shidduch': 'לזיווג הגון', 'zivug hagun': 'לזיווג הגון',
    'refuah': 'לרפואה שלמה', 'refuah shleima': 'לרפואה שלמה', 'refua': 'לרפואה שלמה',
    'leilui neshomo': 'לעילוי נשמה', 'leilui nishmas': 'לעילוי נשמה', 'leilei neshomo': 'לעילוי נשמה',
    'parnasa': 'לפרנסה טובה', 'parnossa': 'לפרנסה בריווח', 'parnassah': 'לפרנסה טובה',
    'hatzlacha': 'להצלחה', 'hatzlocha': 'להצלחה', 'success': 'להצלחה',
    'banim': 'לזרע של קיימא', 'zera shel kayama': 'לזרע של קיימא', 'children': 'לזרע של קיימא',
    'yeshua': 'לישועה', 'yeshuah': 'לישועה', 'nachas': 'לנחת', 'shalom bayis': 'לשלום בית',
}
# שמות נשיים נפוצים — לקביעת "בת" (ברירת מחדל: בן)
_FEMALE = {'rivka', 'rivkah', 'sarah', 'sara', 'esther', 'ester', 'estie', 'chana', 'chanah', 'hana',
           'leah', 'lea', 'rachel', 'rochel', 'zelda', 'cherna', 'miriam', 'devora', 'devorah', 'deborah',
           'gitel', 'gittel', 'feiga', 'faiga', 'bracha', 'brocha', 'hinda', 'henya', 'malka', 'malky',
           'shaindel', 'shaindl', 'yenta', 'yente', 'frieda', 'fraida', 'freida', 'breindel', 'toba', 'tova',
           'tzipora', 'tzipporah', 'chaya', 'chaia', 'baila', 'bayla', 'raizel', 'rayzel', 'sima', 'simcha',
           'perl', 'perel', 'yocheved', 'nechama', 'ruchama', 'elka', 'etel', 'ettel', 'golda', 'tema', 'temma',
           'blima', 'bluma', 'pessy', 'pesha', 'rifka', 'shprintza', 'yita', 'itta', 'necha', 'roiza'}


# תעתיק אנגלית→עברית לשמות נפוצים. מה שלא במילון נשאר באנגלית (המזכיר משלים בדף הבקשות).
_NAME_HE = {
    # גברים
    'avraham': 'אברהם', 'avrohom': 'אברהם', 'abraham': 'אברהם', 'avrum': 'אברהם',
    'yitzchok': 'יצחק', 'yitzchak': 'יצחק', 'isaac': 'יצחק', 'itzik': 'יצחק',
    'yaakov': 'יעקב', 'yakov': 'יעקב', 'jacob': 'יעקב', 'yankel': 'יעקב',
    'moshe': 'משה', 'moishe': 'משה', 'moses': 'משה', 'dovid': 'דוד', 'david': 'דוד',
    'shlomo': 'שלמה', 'shloime': 'שלמה', 'solomon': 'שלמה', 'chaim': 'חיים', 'chaym': 'חיים',
    'yosef': 'יוסף', 'yossef': 'יוסף', 'joseph': 'יוסף', 'yossi': 'יוסף',
    'aharon': 'אהרן', 'aron': 'אהרן', 'aaron': 'אהרן', 'azriel': 'עזריאל',
    'menachem': 'מנחם', 'mendel': 'מענדל', 'shmuel': 'שמואל', 'samuel': 'שמואל',
    'yisroel': 'ישראל', 'yisrael': 'ישראל', 'israel': 'ישראל', 'srul': 'ישראל',
    'mordechai': 'מרדכי', 'mordche': 'מרדכי', 'motel': 'מרדכי', 'boruch': 'ברוך', 'baruch': 'ברוך',
    'shimon': 'שמעון', 'simon': 'שמעון', 'naftali': 'נפתלי', 'naftoli': 'נפתלי',
    'yehuda': 'יהודה', 'yehudah': 'יהודה', 'judah': 'יהודה', 'leib': 'לייב', 'leibel': 'לייבל',
    'binyomin': 'בנימין', 'binyamin': 'בנימין', 'benjamin': 'בנימין',
    'eliezer': 'אליעזר', 'elazar': 'אלעזר', 'lazer': 'אליעזר', 'ephraim': 'אפרים', 'efraim': 'אפרים',
    'gershon': 'גרשון', 'zev': 'זאב', 'wolf': 'זאב', 'velvel': 'זאב', 'dov': 'דוב', 'ber': 'בער',
    'tzvi': 'צבי', 'hirsch': 'צבי', 'herschel': 'הערשל', 'hershel': 'הערשל',
    'yechiel': 'יחיאל', 'michoel': 'מיכאל', 'michael': 'מיכאל', 'pinchas': 'פנחס',
    'raphael': 'רפאל', 'refoel': 'רפאל', 'nosson': 'נתן', 'nathan': 'נתן', 'noson': 'נתן',
    'asher': 'אשר', 'usher': 'אשר', 'zalman': 'זלמן', 'feivel': 'פייבל', 'fishel': 'פישל',
    'yoel': 'יואל', 'joel': 'יואל', 'elimelech': 'אלימלך', 'kalman': 'קלמן', 'zusha': 'זושא', 'zisha': 'זישא',
    'meir': 'מאיר', 'meyer': 'מאיר', 'simcha': 'שמחה', 'sholom': 'שלום', 'shalom': 'שלום',
    'anshel': 'אנשל', 'sender': 'סענדער', 'gedalya': 'גדליה', 'gedaliah': 'גדליה', 'shraga': 'שרגא',
    # נשים
    'rivka': 'רבקה', 'rivkah': 'רבקה', 'rifka': 'רבקה', 'rebecca': 'רבקה',
    'sara': 'שרה', 'sarah': 'שרה', 'esther': 'אסתר', 'ester': 'אסתר', 'estie': 'אסתי',
    'chana': 'חנה', 'chanah': 'חנה', 'hannah': 'חנה', 'leah': 'לאה', 'lea': 'לאה',
    'rochel': 'רחל', 'rachel': 'רחל', 'miriam': 'מרים', 'devora': 'דבורה', 'devorah': 'דבורה',
    'gitel': 'גיטל', 'gittel': 'גיטל', 'feiga': 'פייגא', 'faiga': 'פייגא', 'bracha': 'ברכה', 'brocha': 'ברכה',
    'malka': 'מלכה', 'malky': 'מלכי', 'chaya': 'חיה', 'chaia': 'חיה', 'baila': 'ביילא', 'bayla': 'ביילא',
    'yocheved': 'יוכבד', 'nechama': 'נחמה', 'ruchama': 'רוחמה', 'golda': 'גאלדא', 'tova': 'טובה', 'toba': 'טובה',
    'tzipora': 'ציפורה', 'tzipporah': 'ציפורה', 'raizel': 'רייזל', 'rayzel': 'רייזל', 'perl': 'פערל', 'perel': 'פערל',
    'shaindel': 'שיינדל', 'shaindl': 'שיינדל', 'frieda': 'פרידא', 'freida': 'פרידא', 'fraida': 'פרידא',
    'hinda': 'הינדא', 'henya': 'העניא', 'breindel': 'ברײנדל', 'blima': 'בלימא', 'bluma': 'בלומא',
    'elka': 'עלקא', 'cherna': 'טשערנא', 'zelda': 'זעלדא', 'tema': 'טעמא', 'temma': 'טעמא',
    'yenta': 'יענטא', 'yente': 'יענטא', 'sima': 'סימא', 'shprintza': 'שפרינצא', 'pesha': 'פעשא',
    'fruma': 'פרומא', 'raizy': 'רייזי', 'suri': 'סורי', 'surie': 'סורי', 'yehudis': 'יהודית', 'yidis': 'יהודית',
}


def _he_name(s):
    parts = re.split(r'(\s+)', (s or '').strip())
    out = []
    for w in parts:
        if w.strip():
            out.append(_NAME_HE.get(w.lower().strip(' ,.'), w))
        else:
            out.append(w)
    return ''.join(out)


def _fmt_one(name, mother, father, request):
    eng_first = re.split(r'\s+', name.strip())[0].lower() if name.strip() else ''
    rel = 'בת' if eng_first in _FEMALE else 'בן'
    s = _he_name(name)
    parent = _he_name((mother or father).strip())
    if parent:
        s += ' ' + rel + ' ' + parent
    req = request.strip()
    if req:
        s += ' ' + _REQ_MAP.get(req.lower(), req)
    return s


def _parse_names(body):
    """בונה שם/שמות קוויטל מתוך הטופס — תומך בכמה שמות במייל אחד: 'Name בן/בת Mother נוסח'."""
    if not body:
        return ''
    records = []
    cur = {}

    def flush():
        if cur.get('name'):
            records.append(_fmt_one(cur.get('name', ''), cur.get('mother', ''), cur.get('father', ''), cur.get('request', '')))
        cur.clear()

    generic = []
    for ln in body.split('\n'):
        m = re.match(r'^\s*([^:：]{1,40})[:：]\s*(.*)$', ln)
        if m:
            key = m.group(1).strip().lower()
            val = m.group(2).strip()
            fld = None
            for labels, f in _LABEL_MAP:
                if any(lbl in key for lbl in labels):
                    fld = f
                    break
            if fld:
                if fld == 'name' and cur.get('name'):
                    flush()   # התחלת בלוק שם חדש — סגור את הקודם
                if val:
                    cur[fld] = val
                continue
        if re.search(r'[֐-׿]', ln) and re.search(r'\b(בן|בת)\b', ln):
            generic.append(ln.strip())
    flush()
    out = records + [g for g in generic if g]
    return '\n'.join(dict.fromkeys([o for o in out if o]))


def _imap_since(default='01-Jan-2026'):
    return os.environ.get('INTAKE_SINCE', default)


def configured():
    return bool(os.environ.get('GMAIL_USER') and os.environ.get('GMAIL_APP_PASSWORD'))


def sync(con):
    """מושך מיילים חדשים לתוך טבלת intake. מחזיר dict עם התוצאה."""
    user = os.environ.get('GMAIL_USER')
    pw = os.environ.get('GMAIL_APP_PASSWORD')
    if not (user and pw):
        return {'ok': False, 'error': 'not_configured'}
    froms = [x.strip().lower() for x in (os.environ.get('INTAKE_FROM') or '').split(',') if x.strip()]
    subj = (os.environ.get('INTAKE_SUBJECT') or '').strip()
    mailbox = os.environ.get('INTAKE_MAILBOX', 'INBOX')
    new = 0
    try:
        M = imaplib.IMAP4_SSL('imap.gmail.com')
        M.login(user, pw)
        M.select(mailbox)
        crit = ['SINCE', _imap_since()]
        if subj:
            crit += ['SUBJECT', subj]
        # אם הוגדרו כמה שולחנים — נחפש לכל אחד בנפרד ונאחד
        id_sets = []
        if froms:
            for f in froms:
                typ, data = M.search(None, *(crit + ['FROM', f]))
                if typ == 'OK':
                    id_sets.append(set(data[0].split()))
            ids = set().union(*id_sets) if id_sets else set()
        else:
            typ, data = M.search(None, *crit)
            ids = set(data[0].split()) if typ == 'OK' else set()
        for i in sorted(ids, key=lambda x: int(x)):
            typ, md = M.fetch(i, '(RFC822)')
            if typ != 'OK' or not md or not md[0]:
                continue
            msg = email.message_from_bytes(md[0][1])
            mid = (msg.get('Message-ID') or '').strip() or f'{user}:{i.decode()}'
            if con.execute("SELECT 1 FROM intake WHERE message_id=?", (mid,)).fetchone():
                continue
            fname, femail = parseaddr(_dec(msg.get('From')))
            subject = _dec(msg.get('Subject'))
            try:
                dt = parsedate_to_datetime(msg.get('Date'))
                received = dt.date().isoformat()
            except Exception:
                received = ''
            body = _extract_text(msg)
            names = _parse_names(body)
            con.execute("""INSERT OR IGNORE INTO intake(message_id,from_name,from_email,subject,received,body,names,status,created)
                           VALUES(?,?,?,?,?,?,?, 'new', ?)""",
                        (mid, fname, femail.lower(), subject, received, body, names,
                         datetime.date.today().isoformat()))
            new += 1
        M.logout()
        con.commit()
        return {'ok': True, 'new': new}
    except imaplib.IMAP4.error as e:
        return {'ok': False, 'error': 'login_failed', 'detail': str(e)}
    except Exception as e:
        return {'ok': False, 'error': 'sync_failed', 'detail': str(e)}
