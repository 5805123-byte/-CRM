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
# מילות מפתח לבקשות מורכבות (מספר בקשות בשורה) — התאמה חלקית, לפי סדר
_REQ_KW = [
    ('refu', 'לרפואה שלמה'), ('refua', 'לרפואה שלמה'),
    ('good health', 'לבריאות איתנה'), ('health', 'לבריאות איתנה'),
    ('parnas', 'לפרנסה טובה'), ('parnos', 'לפרנסה טובה'),
    ('shidduch', 'לזיווג הגון'), ('zivug', 'לזיווג הגון'),
    ('nachas', 'לנחת מהילדים'), ('nachos', 'לנחת מהילדים'),
    ('kids', 'לזרע של קיימא'), ('children', 'לזרע של קיימא'), ('bracha', 'לברכה'),
    ('hatzlach', 'להצלחה'), ('success', 'להצלחה'), ('yeshua', 'לישועה'),
    ('leilui', 'לעילוי נשמה'), ('simcha', 'לשמחה'), ('brachot', 'לכל הברכות'), ('brochos', 'לכל הברכות'),
    ('apartment', 'למצוא דירה'), ('shalom bayis', 'לשלום בית'),
]
# שמות נשיים נפוצים — לקביעת "בת" (ברירת מחדל: בן)
_FEMALE = {
    'rivka', 'rivkah', 'rifka', 'rifky', 'rivky', 'rebecca', 'sara', 'sarah', 'suri', 'surie', 'sury', 'surele',
    'esther', 'ester', 'estie', 'esty', 'chana', 'chanah', 'hana', 'hannah', 'chany', 'chanie', 'chani',
    'leah', 'lea', 'leie', 'rachel', 'rochel', 'ruchy', 'ruchie', 'ruchel', 'miriam', 'mirel', 'mimi', 'miri', 'mindy', 'mindel',
    'devora', 'devorah', 'deborah', 'devoiry', 'devoiri', 'zelda', 'zeldy', 'cherna', 'charna', 'gitel', 'gittel', 'gitty', 'giti',
    'feiga', 'faiga', 'faigy', 'faige', 'feigy', 'bracha', 'brocha', 'hinda', 'hindy', 'hindi', 'henya', 'henny', 'heni',
    'malka', 'malky', 'shaindel', 'shaindl', 'shaindy', 'yenta', 'yente', 'yentel', 'frieda', 'fraida', 'freida', 'fraidy', 'freidy',
    'breindel', 'breiny', 'toba', 'tova', 'toby', 'toiba', 'tzipora', 'tzipporah', 'tzippy', 'tzipi', 'chaya', 'chaia', 'chayie',
    'baila', 'bayla', 'baily', 'raizel', 'rayzel', 'raizy', 'raizle', 'reizel', 'sima', 'simy', 'perl', 'perel', 'perry', 'pearl',
    'yocheved', 'yochi', 'nechama', 'nechy', 'nechie', 'ruchama', 'elka', 'elke', 'golda', 'goldie', 'goldy', 'tema', 'temma', 'temy',
    'blima', 'blimie', 'bluma', 'blumie', 'pessy', 'pesha', 'peshy', 'shprintza', 'shprintzy', 'yita', 'yitta', 'itta', 'ita',
    'necha', 'nechie', 'roiza', 'roizy', 'fruma', 'frumy', 'frumie', 'yehudis', 'yides', 'sheva', 'shevy', 'kaila', 'kayla',
    'dina', 'diny', 'chava', 'chavy', 'basya', 'basy', 'basha', 'alta', 'yittel', 'machla', 'machy', 'krayndel', 'kreindel',
    'libby', 'liba', 'libe', 'tzirel', 'tzirl', 'chaviva', 'gitla',
}


# תעתיק אנגלית→עברית לפי איות חסידי־יידישאי אמריקאי. מה שלא במילון נשאר באנגלית (המזכיר משלים בדף הבקשות).
_NAME_HE = {
    # ===== גברים =====
    'avraham': 'אברהם', 'avrohom': 'אברהם', 'abraham': 'אברהם', 'avrum': 'אברהם', 'avrumi': 'אברהם', 'avremel': 'אברהם',
    'yitzchok': 'יצחק', 'yitzchak': 'יצחק', 'isaac': 'יצחק', 'itzik': 'יצחק', 'itche': 'יצחק', 'itchie': 'יצחק',
    'yaakov': 'יעקב', 'yakov': 'יעקב', 'jacob': 'יעקב', 'yankel': 'יאנקל', 'yankev': 'יעקב', 'koppel': 'קאפל',
    'moshe': 'משה', 'moishe': 'משה', 'moses': 'משה', 'moshy': 'משה',
    'menachem': 'מנחם', 'mendel': 'מענדל', 'mendy': 'מענדל', 'mendil': 'מענדל',
    'dovid': 'דוד', 'david': 'דוד', 'duvid': 'דוד', 'duvi': 'דוד', 'dudi': 'דוד',
    'shlomo': 'שלמה', 'shloime': 'שלמה', 'shloimy': 'שלמה', 'solomon': 'שלמה', 'zalman': 'זלמן',
    'chaim': 'חיים', 'chaym': 'חיים', 'chaimke': 'חיים',
    'yosef': 'יוסף', 'yossef': 'יוסף', 'joseph': 'יוסף', 'yossi': 'יוסף', 'yossel': 'יאסל', 'yosef': 'יוסף',
    'aharon': 'אהרן', 'aron': 'אהרן', 'aaron': 'אהרן', 'arele': 'אהרן', 'azriel': 'עזריאל',
    'shmuel': 'שמואל', 'samuel': 'שמואל', 'shmiel': 'שמואל', 'shmil': 'שמואל', 'shumel': 'שמואל',
    'yisroel': 'ישראל', 'yisrael': 'ישראל', 'israel': 'ישראל', 'srul': 'ישראל', 'srulik': 'ישראל',
    'mordechai': 'מרדכי', 'mordche': 'מרדכי', 'motel': 'מרדכי', 'mottel': 'מרדכי', 'motti': 'מרדכי', 'motty': 'מרדכי',
    'boruch': 'ברוך', 'baruch': 'ברוך', 'berel': 'בערל', 'berish': 'בעריש', 'ber': 'בער', 'bere': 'בערע',
    'shimon': 'שמעון', 'simon': 'שמעון', 'naftali': 'נפתלי', 'naftoli': 'נפתלי', 'naftuli': 'נפתלי',
    'yehuda': 'יהודה', 'yehudah': 'יהודה', 'judah': 'יהודה', 'yidel': 'יידל', 'yudel': 'יודל',
    'leib': 'לייב', 'leibel': 'לייבל', 'label': 'לייבל', 'leibish': 'לייביש', 'leibush': 'לייבוש',
    'binyomin': 'בנימין', 'binyamin': 'בנימין', 'benjamin': 'בנימין', 'bini': 'בנימין',
    'eliezer': 'אליעזר', 'lazer': 'אליעזר', 'leizer': 'אליעזר', 'elazar': 'אלעזר', 'eluzer': 'אלעזר',
    'ephraim': 'אפרים', 'efraim': 'אפרים', 'efroim': 'אפרים',
    'gershon': 'גרשון', 'getzel': 'געצל', 'gedalya': 'גדליה', 'gedaliah': 'גדליה',
    'zev': 'זאב', 'velvel': 'וועלוועל', 'wolf': 'וואלף', 'volf': 'וואלף', 'dov': 'דוב', 'duv': 'דוב',
    'tzvi': 'צבי', 'hirsch': 'הירש', 'hersh': 'הערש', 'herschel': 'הערשל', 'hershel': 'הערשל', 'heshy': 'צבי',
    'yechiel': 'יחיאל', 'michel': 'מיכל', 'michoel': 'מיכאל', 'michael': 'מיכאל', 'pinchas': 'פנחס', 'pinye': 'פנחס',
    'raphael': 'רפאל', 'refoel': 'רפאל', 'rafael': 'רפאל',
    'nosson': 'נתן', 'nathan': 'נתן', 'noson': 'נתן', 'nussen': 'נתן', 'nuta': 'נטע',
    'asher': 'אשר', 'usher': 'אשר', 'anshel': 'אנשל', 'zelig': 'זעליג',
    'feivel': 'פייוועל', 'feivish': 'פייביש', 'faivish': 'פייביש', 'fishel': 'פישל', 'faitel': 'פייטל', 'feitel': 'פייטל',
    'yoel': 'יואל', 'joel': 'יואל', 'elimelech': 'אלימלך', 'meilech': 'מלך', 'kalman': 'קלמן',
    'zusha': 'זושא', 'zisha': 'זישא', 'meir': 'מאיר', 'meyer': 'מאיר', 'simcha': 'שמחה', 'bunim': 'בונים',
    'sholom': 'שלום', 'shalom': 'שלום', 'shulem': 'שולעם', 'sender': 'סענדער', 'alexander': 'אלכסנדר', 'zisskind': 'זיסקינד',
    'shraga': 'שרגא', 'nuchem': 'נחום', 'nachum': 'נחום', 'chuna': 'חונא', 'lipa': 'ליפא', 'lipe': 'ליפע',
    'shia': 'יהושע', 'yehoshua': 'יהושע', 'shaya': 'ישעיה', 'yeshaya': 'ישעיה', 'eliyahu': 'אליהו', 'elya': 'אליהו',
    'tuvia': 'טוביה', 'zanvil': 'זנוויל', 'zundel': 'זונדל', 'kopel': 'קאפל', 'shea': 'שעיה',
    'yisocher': 'יששכר', 'yissochor': 'יששכר', 'zevulun': 'זבולון', 'zevulin': 'זבולון',
    # ===== נשים =====
    'rivka': 'רבקה', 'rivkah': 'רבקה', 'rifka': 'רבקה', 'rifky': 'רבקה', 'rivky': 'רבקה', 'rebecca': 'רבקה',
    'sara': 'שרה', 'sarah': 'שרה', 'suri': 'סורי', 'surie': 'סורי', 'sury': 'סורי', 'surele': 'שרה',
    'esther': 'אסתר', 'ester': 'אסתר', 'estie': 'אסתי', 'esty': 'אסתי',
    'chana': 'חנה', 'chanah': 'חנה', 'hannah': 'חנה', 'chany': 'חנה', 'chanie': 'חנה', 'chani': 'חנה',
    'leah': 'לאה', 'lea': 'לאה', 'leie': 'לאה',
    'rochel': 'רחל', 'rachel': 'רחל', 'ruchy': 'רחל', 'ruchie': 'רחל', 'ruchel': 'רחל',
    'miriam': 'מרים', 'mirel': 'מירל', 'mimi': 'מרים', 'miri': 'מרים', 'mindel': 'מינדל', 'mindy': 'מינדל',
    'devora': 'דבורה', 'devorah': 'דבורה', 'deborah': 'דבורה', 'devoiry': 'דבורה', 'devoiri': 'דבורה',
    'gitel': 'גיטל', 'gittel': 'גיטל', 'gitty': 'גיטל', 'giti': 'גיטל', 'gitla': 'גיטלא',
    'feiga': 'פייגא', 'faiga': 'פייגא', 'faigy': 'פייגא', 'faige': 'פייגע', 'feigy': 'פייגא',
    'bracha': 'ברכה', 'brocha': 'ברכה', 'malka': 'מלכה', 'malky': 'מלכי',
    'chaya': 'חיה', 'chaia': 'חיה', 'chayie': 'חיה', 'baila': 'ביילא', 'bayla': 'ביילא', 'baily': 'ביילא',
    'yocheved': 'יוכבד', 'yochi': 'יוכבד', 'nechama': 'נחמה', 'nechy': 'נחמה', 'nechie': 'נחמה', 'ruchama': 'רוחמה',
    'golda': 'גאלדא', 'goldie': 'גאלדא', 'goldy': 'גאלדא', 'tova': 'טובה', 'toba': 'טויבא', 'toby': 'טובה', 'toiba': 'טויבא',
    'tzipora': 'ציפורה', 'tzipporah': 'ציפורה', 'tzippy': 'ציפורה', 'tzipi': 'ציפורה',
    'raizel': 'רייזל', 'rayzel': 'רייזל', 'raizy': 'רייזי', 'raizle': 'רייזל', 'reizel': 'רייזל',
    'perl': 'פערל', 'perel': 'פערל', 'perry': 'פערל', 'pearl': 'פערל',
    'shaindel': 'שיינדל', 'shaindl': 'שיינדל', 'shaindy': 'שיינדל',
    'frieda': 'פרידא', 'freida': 'פרידא', 'fraida': 'פרידא', 'fraidy': 'פרידא', 'freidy': 'פרידא',
    'hinda': 'הינדא', 'hindy': 'הינדא', 'hindi': 'הינדא', 'henya': 'העניא', 'henny': 'העניא', 'heni': 'העניא',
    'breindel': 'בריינדל', 'breiny': 'בריינדל', 'blima': 'בלימא', 'blimie': 'בלימא', 'bluma': 'בלומא', 'blumie': 'בלומא',
    'elka': 'עלקא', 'elke': 'עלקע', 'cherna': 'טשערנא', 'charna': 'טשארנא', 'zelda': 'זעלדא', 'zeldy': 'זעלדא',
    'tema': 'טעמא', 'temma': 'טעמא', 'temy': 'טעמא', 'yenta': 'יענטא', 'yente': 'יענטא', 'yentel': 'יענטל',
    'sima': 'סימא', 'simy': 'סימא', 'shprintza': 'שפרינצא', 'shprintzy': 'שפרינצא',
    'pesha': 'פעשא', 'peshy': 'פעשא', 'pessy': 'פעסי', 'fruma': 'פרומא', 'frumy': 'פרומא', 'frumie': 'פרומא',
    'yehudis': 'יהודית', 'yides': 'יהודית', 'necha': 'נעכא', 'roiza': 'רויזא', 'roizy': 'רויזא',
    'sheva': 'שבע', 'shevy': 'שבע', 'kaila': 'קיילא', 'kayla': 'קיילא', 'dina': 'דינה', 'diny': 'דינה',
    'chava': 'חוה', 'chavy': 'חוה', 'basya': 'בתיה', 'basy': 'בתיה', 'basha': 'באשא', 'alta': 'אלטא',
    'tamar': 'תמר', 'brach': 'ברכה', 'brocha': 'ברכה', 'henna': 'הענא', 'hena': 'הענא', 'frimet': 'פרימעט', 'frumet': 'פרומעט', 'frima': 'פרימא',
    'daniel': 'דניאל', 'yael': 'יעל', 'yaron': 'ירון', 'yoseefa': 'יוסיפא', 'yosefa': 'יוסיפא', 'chagag': 'חגג',
    'yittel': 'יטל', 'yitta': 'איטא', 'itta': 'איטא', 'ita': 'איטא', 'machla': 'מחלה', 'machy': 'מחלה',
    'krayndel': 'קריינדל', 'kreindel': 'קריינדל', 'libby': 'ליבא', 'liba': 'ליבא', 'libe': 'ליבא',
    'tzirel': 'צירל', 'tzirl': 'צירל',
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


def _req_he(request):
    """נוסח בקשה בעברית — מיפוי מלא, אחרת מיפוי חלקי למילות מפתח, אחרת הטקסט כמו שהוא."""
    req = (request or '').strip()
    if not req:
        return ''
    low = req.lower()
    if low in _REQ_MAP:
        return _REQ_MAP[low]
    parts = []
    for kw, he in _REQ_KW:
        if kw in low:
            if he not in parts:
                parts.append(he)
    return ' '.join(parts) if parts else req


def _fmt_one(name, mother, father, request):
    name = (name or '').strip()
    m = re.search(r'\b(ben|bas|bat|בן|בת)\s*$', name, re.I)  # שם שכבר מסתיים ב-ben/bas
    rel = None
    if m:
        w = m.group(1).lower()
        rel = 'בת' if w in ('bas', 'bat', 'בת') else 'בן'
        name = name[:m.start()].strip()
    eng_first = re.split(r'\s+', name)[0].lower() if name else ''
    if rel is None:
        rel = 'בת' if eng_first in _FEMALE else 'בן'
    s = _he_name(name)
    par_raw = (mother or father).strip()
    # "ומשפחתו" / "and family" — לא שם אם, מצרפים בלי בן/בת
    if re.match(r'^(u?mishpach|and family|family)', par_raw, re.I) or 'משפח' in par_raw:
        s += ' ומשפחתו'
    elif par_raw:
        s += ' ' + rel + ' ' + _he_name(par_raw)
    r = _req_he(request)
    if r:
        s += ' ' + r
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
