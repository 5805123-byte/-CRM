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


def _fix8bit(t):
    """כותרת שנשלחה כ-UTF-8 גולמי מגיעה עם בייטים משומרים — משחזרים לעברית תקינה."""
    try:
        if any('\udc80' <= c <= '\udcff' for c in t):
            return t.encode('utf-8', 'surrogateescape').decode('utf-8', 'replace')
    except Exception:
        pass
    return t


def _dec(s):
    if not s:
        return ''
    chunks = getattr(s, '_chunks', None)      # כותרת לא־מקודדת (unknown-8bit)
    if chunks:
        try:
            return ''.join(_fix8bit(t) for t, _cs in chunks)
        except Exception:
            pass
    try:
        out = str(make_header(decode_header(s)))
    except Exception:
        out = str(s)
    return _fix8bit(out)


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


def _heb_score(txt):
    """ניקוד לזיהוי הפענוח הנכון: הרבה אותיות עבריות = טוב, תווי־שגיאה = רע."""
    heb = sum(1 for c in txt if '֐' <= c <= '׿')
    bad = txt.count('�')
    return heb - 50 * bad


def _payload(part):
    """מפענח גוף מייל בעברית גם אם הקידוד שגוי (utf-8 / windows-1255 / iso-8859-8 וכו')."""
    try:
        raw = part.get_payload(decode=True)
    except Exception:
        raw = None
    if raw is None:
        try:
            return str(part.get_payload())
        except Exception:
            return ''
    if isinstance(raw, str):
        return raw
    declared = (part.get_content_charset() or '').lower()
    cands, seen = [], set()
    for cs in [declared, 'utf-8', 'windows-1255', 'iso-8859-8', 'cp1252']:
        if cs and cs not in seen:
            seen.add(cs); cands.append(cs)
    best, best_score = None, None
    for cs in cands:
        try:
            txt = raw.decode(cs)
        except Exception:
            continue
        sc = _heb_score(txt)
        if best_score is None or sc > best_score:
            best, best_score = txt, sc
    return best if best is not None else raw.decode('utf-8', 'replace')


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
    ('refu', 'לרפואה שלמה'), ('refua', 'לרפואה שלמה'), ('recover', 'לרפואה שלמה'),
    ('good health', 'לבריאות איתנה'), ('health', 'לבריאות איתנה'),
    ('engag', 'לזיווג הגון'), ('marry', 'לזיווג הגון'), ('married', 'לזיווג הגון'), ('marriage', 'לזיווג הגון'),
    ('shidduch', 'לזיווג הגון'), ('zivug', 'לזיווג הגון'), ('spouse', 'לזיווג הגון'),
    ('earn', 'לפרנסה טובה'), ('income', 'לפרנסה טובה'), ('money', 'לפרנסה טובה'), ('job', 'לפרנסה טובה'),
    ('parnas', 'לפרנסה טובה'), ('parnos', 'לפרנסה טובה'), ('livelihood', 'לפרנסה טובה'),
    ('business', 'להצלחה בעסקים'), ('deal', 'להצלחה בעסקים'),
    ('nachas', 'לנחת מהילדים'), ('nachos', 'לנחת מהילדים'),
    ('kids', 'לזרע של קיימא'), ('children', 'לזרע של קיימא'), ('baby', 'לזרע של קיימא'),
    ('conceive', 'לזרע של קיימא'), ('pregnan', 'לזרע של קיימא'), ('fertil', 'לזרע של קיימא'),
    ('bracha', 'לברכה'), ('blessing', 'לכל הברכות'),
    ('hatzlach', 'להצלחה'), ('success', 'להצלחה'), ('succeed', 'להצלחה'), ('yeshua', 'לישועה'), ('salvation', 'לישועה'),
    ('leilui', 'לעילוי נשמה'), ('neshoma', 'לעילוי נשמה'), ('soul', 'לעילוי נשמה'),
    ('simcha', 'לשמחה'), ('joy', 'לשמחה'), ('happ', 'לשמחה'),
    ('brachot', 'לכל הברכות'), ('brochos', 'לכל הברכות'),
    ('apartment', 'למצוא דירה'), ('home', 'למצוא דירה'), ('house', 'למצוא דירה'),
    ('shalom bayis', 'לשלום בית'), ('peace at home', 'לשלום בית'), ('protect', 'לשמירה'), ('safe', 'לשמירה'),
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
    'tamar', 'yael', 'yaeli', 'yosefa', 'yoseefa', 'shulamit', 'shulamis', 'noa', 'noya', 'shira', 'shani',
    'michal', 'meital', 'sylvana', 'sylvia', 'louris', 'racheli', 'orly', 'orit', 'sivan', 'moriah', 'moria',
    'aviva', 'ayelet', 'hadas', 'hadasa', 'hadassah', 'liora', 'liat', 'gila', 'galit', 'irit', 'dalia', 'daliya',
}


# תעתיק אנגלית→עברית לפי איות חסידי־יידישאי אמריקאי. מה שלא במילון נשאר באנגלית (המזכיר משלים בדף הבקשות).
_NAME_HE = {
    # ===== גברים =====
    'avraham': 'אברהם', 'avrohom': 'אברהם', 'abraham': 'אברהם', 'avrum': 'אברהם', 'avrumi': 'אברהם', 'avremel': 'אברהם',
    'yitzchok': 'יצחק', 'yitzchak': 'יצחק', 'yitzhak': 'יצחק', 'yitzchack': 'יצחק', 'isaac': 'יצחק', 'itzik': 'יצחק', 'itche': 'יצחק', 'itchie': 'יצחק',
    'hayim': 'חיים', 'haim': 'חיים', 'chayim': 'חיים', 'shulamit': 'שולמית', 'shulamis': 'שולמית', 'sylvana': 'סילבנה', 'sylvia': 'סילביה', 'louris': 'לוריס',
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

# ===== תוספת שמות נפוצים (כולל ספרדים/ישראליים) — עדיף מילון על פני תעתיק פונטי =====
_NAME_HE.update({
    # גברים
    'elchanan': 'אלחנן', 'elhanan': 'אלחנן', 'elchonon': 'אלחנן', 'yisrael': 'ישראל', 'ari': 'ארי', 'arye': 'אריה',
    'aryeh': 'אריה', 'ariel': 'אריאל', 'amram': 'עמרם', 'amos': 'עמוס', 'aviel': 'אביאל', 'avi': 'אבי',
    'aviad': 'אביעד', 'avidan': 'אבידן', 'amichai': 'עמיחי', 'assaf': 'אסף', 'asaf': 'אסף', 'barak': 'ברק',
    'ben': 'בן', 'benzion': 'בן ציון', 'betzalel': 'בצלאל', 'bezalel': 'בצלאל', 'chananya': 'חנניה',
    'chagai': 'חגי', 'chagag': 'חגג', 'dan': 'דן', 'daniel': 'דניאל', 'doron': 'דורון', 'eran': 'ערן',
    'eyal': 'אייל', 'eitan': 'איתן', 'eldad': 'אלדד', 'eli': 'אלי', 'elon': 'אלון', 'gad': 'גד',
    'gavriel': 'גבריאל', 'gabriel': 'גבריאל', 'gidon': 'גדעון', 'gideon': 'גדעון', 'guy': 'גיא',
    'hanan': 'חנן', 'harel': 'הראל', 'ido': 'עידו', 'idan': 'עידן', 'itai': 'איתי', 'itamar': 'איתמר',
    'kobi': 'קובי', 'lior': 'ליאור', 'liran': 'לירן', 'matan': 'מתן', 'maor': 'מאור', 'nadav': 'נדב',
    'nir': 'ניר', 'nissim': 'נסים', 'noam': 'נעם', 'omer': 'עומר', 'omri': 'עומרי', 'oren': 'אורן',
    'ovadia': 'עובדיה', 'ovadya': 'עובדיה', 'ronen': 'רונן', 'roi': 'רועי', 'roee': 'רועי', 'ron': 'רון',
    'shai': 'שי', 'shlomi': 'שלומי', 'tal': 'טל', 'tomer': 'תומר', 'uri': 'אורי', 'uriel': 'אוריאל',
    'yair': 'יאיר', 'yaniv': 'יניב', 'yehonatan': 'יהונתן', 'yonatan': 'יונתן', 'yoni': 'יוני',
    'yaron': 'ירון', 'yotam': 'יותם', 'ziv': 'זיו', 'zohar': 'זוהר', 'shimshon': 'שמשון', 'samson': 'שמשון',
    'yehiel': 'יחיאל', 'menashe': 'מנשה', 'ezra': 'עזרא', 'chananel': 'חננאל', 'yishai': 'ישי',
    # נשים
    'pnina': 'פנינה', 'penina': 'פנינה', 'shifra': 'שפרה', 'shifrah': 'שפרה', 'shprintza': 'שפרינצא',
    'adina': 'עדינה', 'adva': 'אדוה', 'ahuva': 'אהובה', 'anat': 'ענת', 'aviva': 'אביבה', 'avigail': 'אביגיל',
    'ayala': 'איילה', 'ayelet': 'איילת', 'batya': 'בתיה', 'bat sheva': 'בת שבע', 'carmel': 'כרמל',
    'dalia': 'דליה', 'dalya': 'דליה', 'dana': 'דנה', 'daniela': 'דניאלה', 'dvora': 'דבורה', 'efrat': 'אפרת',
    'einat': 'עינת', 'elisheva': 'אלישבע', 'ella': 'אלה', 'gali': 'גלי', 'galit': 'גלית', 'gila': 'גילה',
    'hadar': 'הדר', 'hadas': 'הדס', 'hadassa': 'הדסה', 'hila': 'הילה', 'ilana': 'אילנה', 'inbal': 'ענבל',
    'irit': 'אירית', 'keren': 'קרן', 'liat': 'ליאת', 'liora': 'ליאורה', 'maayan': 'מעיין', 'meirav': 'מירב',
    'merav': 'מירב', 'michal': 'מיכל', 'moria': 'מוריה', 'moriah': 'מוריה', 'naama': 'נעמה', 'naomi': 'נעמי',
    'noa': 'נועה', 'noya': 'נויה', 'nurit': 'נורית', 'ofra': 'עפרה', 'orit': 'אורית', 'orly': 'אורלי',
    'osnat': 'אסנת', 'racheli': 'רחלי', 'reut': 'רעות', 'rina': 'רינה', 'ronit': 'רונית', 'shani': 'שני',
    'shira': 'שירה', 'shlomit': 'שלומית', 'shulamit': 'שולמית', 'sigal': 'סיגל', 'sivan': 'סיון',
    'tal': 'טל', 'talia': 'טליה', 'tamar': 'תמר', 'tehila': 'תהילה', 'tikva': 'תקוה', 'tzofia': 'צופיה',
    'yael': 'יעל', 'yaffa': 'יפה', 'yardena': 'ירדנה', 'yasmin': 'יסמין', 'yehudit': 'יהודית',
    'yifat': 'יפעת', 'yona': 'יונה', 'zahava': 'זהבה', 'ziva': 'זיוה',
})

# שמות נשיים נוספים לזיהוי "בת" (ברירת מחדל: בן)
_FEMALE |= {
    'pnina', 'penina', 'shifra', 'shifrah', 'adina', 'ahuva', 'anat', 'aviva', 'avigail', 'ayala', 'ayelet',
    'batya', 'dalia', 'dalya', 'dana', 'daniela', 'efrat', 'einat', 'elisheva', 'ella', 'gali', 'galit', 'gila',
    'hadar', 'hadas', 'hadassa', 'hila', 'ilana', 'inbal', 'irit', 'keren', 'liat', 'liora', 'maayan',
    'meirav', 'merav', 'michal', 'moria', 'moriah', 'naama', 'naomi', 'noa', 'noya', 'nurit', 'ofra', 'orit',
    'orly', 'osnat', 'racheli', 'reut', 'rina', 'ronit', 'shani', 'shira', 'shlomit', 'sigal', 'sivan',
    'talia', 'tehila', 'tikva', 'tzofia', 'yaffa', 'yardena', 'yasmin', 'yehudit', 'yifat', 'zahava', 'ziva',
}


def _he_norm_g(s):
    """נרמול שם עברי להשוואת מין — אותיות סופיות לרגילות, בלי ניקוד/רווחים."""
    s = re.sub(r'[^֐-׿]', '', str(s or ''))
    return s.translate(str.maketrans('ךםןףץ', 'כמנפצ'))


# שמות נשיים בעברית — כדי לקבוע "בת" גם כשהשם מגיע כבר בעברית (ולא באנגלית)
_FEMALE_HE = {_he_norm_g(_NAME_HE[_e]) for _e in _FEMALE if _e in _NAME_HE}
_FEMALE_HE |= {_he_norm_g(x) for x in [
    'אלישבע', 'דבורה', 'דבורא', 'חדוה', 'ענת', 'ברוניא', 'ברוניה', 'אסתר', 'שרה', 'רבקה', 'רחל', 'לאה',
    'חנה', 'מרים', 'פנינה', 'פנינא', 'שפרה', 'שפרא', 'חוה', 'חיה', 'יונה', 'נעמי', 'נעמה', 'תמר', 'יעל',
    'מיכל', 'אביגיל', 'בתיה', 'יהודית', 'שולמית', 'שלומית', 'שירה', 'הדס', 'הדסה', 'אילנה', 'גיטל', 'גיטלא',
    'פייגא', 'פייגע', 'מלכה', 'מלכי', 'ברכה', 'ציפורה', 'רייזל', 'רייזי', 'פערל', 'שיינדל', 'פרידא', 'הינדא',
    'בריינדל', 'בלימא', 'בלומא', 'טובה', 'טויבא', 'גאלדא', 'יוכבד', 'נחמה', 'רוחמה', 'סימא', 'פרומא', 'אלטא',
    'באשא', 'זעלדא', 'טשארנא', 'טשערנא', 'עלקא', 'עלקע', 'יענטא', 'יענטל', 'שפרינצא', 'פעשא', 'פעסי', 'נעכא',
    'רויזא', 'שבע', 'קיילא', 'דינה', 'עדינה', 'אהובה', 'אביבה', 'איילה', 'איילת', 'דליה', 'דנה', 'אפרת',
    'עינת', 'אלה', 'גלית', 'גילה', 'הדר', 'הילה', 'ענבל', 'אירית', 'קרן', 'ליאת', 'ליאורה', 'מעיין', 'מירב',
    'מוריה', 'נויה', 'נורית', 'עפרה', 'אורית', 'אורלי', 'אסנת', 'רחלי', 'רעות', 'רינה', 'רונית', 'שני',
    'סיגל', 'סיון', 'טליה', 'תהילה', 'תקוה', 'צופיה', 'יפה', 'ירדנה', 'יסמין', 'יפעת', 'זהבה', 'זיוה',
    'סורי', 'אסתי', 'מינדל', 'מירל',
    # תוספת שמות נשיים
    'מנוחה', 'תינוקת', 'שרה רבקה', 'רייזל', 'פעסל', 'פראדל', 'הענדל', 'יוטא', 'יוטע', 'פייגי', 'מירי',
    'נעכי', 'גיטי', 'הודל', 'הענא', 'הענדי', 'סעסל', 'סאשא', 'פראדא', 'רבקי', 'ריזל', 'ריקל', 'רויזי',
    'שולמית', 'שיפרה', 'שפרינצל', 'בלומי', 'ברכי', 'דבורה לאה', 'חוה', 'חיה שרה', 'חיה מושקא', 'מושקא',
    'מושקי', 'נחמי', 'סימי', 'פערי', 'פעסי', 'פרומט', 'פרימט', 'פרימא', 'קילא', 'רוזא', 'שרי', 'שרהלה',
    'תרצה', 'תמרה', 'עטרה', 'עטיא', 'עטל', 'זיסל', 'זיסי', 'טויבי', 'טעמי', 'יאכט', 'יאכעט', 'לאני',
    'ליבי', 'מלכי', 'מלכה', 'מרים', 'נעמי', 'עדי', 'עדן', 'רוני', 'שקד', 'שלי', 'סתיו', 'רוית', 'ליטל',
]}
_FEMALE_HE.discard('')

# מילים שאינן שם אך קובעות מין (תינוקת=בת, תינוק=בן)
_FEM_WORDS_HE = {'תינוקת', 'ילדה', 'בתי', 'בת'}
_MALE_WORDS_HE = {'תינוק', 'ילד', 'בני', 'בן'}


# ===== תעתיק פונטי לגיבוי: כל מילה אנגלית שאינה במילון הופכת לאותיות עבריות (לעולם לא נשאר אנגלית) =====
_TR3 = {'tch': 'טש', 'sch': 'ש'}
_TR2 = {'ch': 'ח', 'sh': 'ש', 'ph': 'פ', 'th': 'ת', 'tz': 'צ', 'ts': 'צ', 'ck': 'ק',
        'kh': 'ח', 'gh': 'ג', 'oo': 'ו', 'ou': 'ו', 'ei': 'יי', 'ai': 'יי', 'ay': 'יי',
        'ee': 'י', 'ea': 'י', 'ie': 'י', 'aw': 'ו', 'ah': 'ה', 'ya': 'יא', 'yo': 'יו'}
_TR1 = {'a': 'א', 'b': 'ב', 'c': 'ק', 'd': 'ד', 'e': '', 'f': 'פ', 'g': 'ג', 'h': 'ה',
        'i': 'י', 'j': "ג'", 'k': 'ק', 'l': 'ל', 'm': 'מ', 'n': 'נ', 'o': 'ו', 'p': 'פ',
        'q': 'ק', 'r': 'ר', 's': 'ס', 't': 'ט', 'u': 'ו', 'v': 'ב', 'w': 'וו', 'x': 'קס',
        'y': 'י', 'z': 'ז'}
_SOFIT = {'מ': 'ם', 'נ': 'ן', 'כ': 'ך', 'פ': 'ף', 'צ': 'ץ'}


def _translit(w):
    s = re.sub(r'[^a-z]', '', (w or '').lower())
    if not s:
        return w
    res, i, n = [], 0, len(s)
    while i < n:
        if s[i:i + 3] in _TR3:
            res.append(_TR3[s[i:i + 3]]); i += 3; continue
        if s[i:i + 2] in _TR2:
            res.append(_TR2[s[i:i + 2]]); i += 2; continue
        c = s[i]; first = (i == 0); last = (i == n - 1)
        if c in ('a', 'e'):
            # תנועה פתוחה: בתחילת מילה א', בסוף ה', באמצע לא נכתבת (כמו בעברית) — מונע ריבוי אלפים
            res.append('א' if first else ('ה' if last else ''))
        else:
            res.append(_TR1.get(c, ''))
        i += 1
    heb = ''.join(res)
    if heb and heb[-1] in _SOFIT:      # אות סופית
        heb = heb[:-1] + _SOFIT[heb[-1]]
    return heb or w


def _he_name(s):
    parts = re.split(r'(\s+)', (s or '').strip())
    out = []
    for w in parts:
        if not w.strip():
            out.append(w); continue
        key = w.lower().strip(' ,.')
        if key in _NAME_HE:
            out.append(_NAME_HE[key])
        elif re.search(r'[֐-׿]', w):   # כבר עברית — משאירים כמו שהוא
            out.append(w)
        else:
            out.append(_translit(w))             # תעתיק פונטי — בלי אנגלית
    return ''.join(out)


def _req_he(request):
    """נוסח בקשה בעברית — מיפוי מלא, אחרת מיפוי חלקי למילות מפתח, אחרת הטקסט כמו שהוא."""
    req = (request or '').strip()
    if not req:
        return ''
    if re.search(r'[֐-׿]', req):    # כבר עברית — משאירים כמו שהוא
        return req
    low = req.lower()
    if low in _REQ_MAP:
        return _REQ_MAP[low]
    parts = []
    for kw, he in _REQ_KW:
        if kw in low:
            if he not in parts:
                parts.append(he)
    # לא נשאיר אנגלית: אם לא זוהתה בקשה — לא מוסיפים טקסט (רק השם יופיע)
    return ' ו'.join(parts)


# ביטויים שאינם שם אמיתי — לא נכנסים לקוויטל (למשל "thank you")
_JUNK = {'thankyou', 'thanks', 'thank', 'thanku', 'thx', 'ty', 'none', 'na', 'nan', 'test',
         'nothing', 'no', 'nil', 'null', 'xxx', 'abc', 'asdf', 'ty', 'amen', 'omein'}


def _is_junk_name(name):
    if re.search(r'[֐-׿]', name or ''):   # עברית — לא ג'אנק
        return False
    low = re.sub(r'[^a-z ]', '', (name or '').lower()).strip()
    if not low:
        return True
    if low.split()[0] in {'thank', 'thanks', 'thankyou', 'thx'}:
        return True
    return re.sub(r'[^a-z]', '', low) in _JUNK


def _fmt_one(name, mother, father, request):
    name = (name or '').strip()
    if _is_junk_name(name):    # "thank you" וכד' — מדלגים
        return ''
    m = re.search(r'\b(ben|bas|bat|בן|בת)\s*$', name, re.I)  # שם שכבר מסתיים ב-ben/bas
    rel = None
    if m:
        w = m.group(1).lower()
        rel = 'בת' if w in ('bas', 'bat', 'בת') else 'בן'
        name = name[:m.start()].strip()
    first_word = re.split(r'\s+', name)[0] if name else ''
    if rel is None:
        low_name = name.lower()
        fw_he = _he_norm_g(first_word)
        if re.search(r'[֐-׿]', first_word):        # השם כבר בעברית — משווים לרשימת שמות נשיים בעברית
            if fw_he in _FEM_WORDS_HE:
                rel = 'בת'
            elif fw_he in _MALE_WORDS_HE:
                rel = 'בן'
            else:
                rel = 'בת' if fw_he in _FEMALE_HE else 'בן'
        elif re.search(r'\bgirl\b', low_name) or 'daughter' in low_name:
            rel = 'בת'
        elif re.search(r'\bboy\b', low_name) or 'son' in low_name:
            rel = 'בן'
        else:                                       # שם באנגלית — לפי הרשימה האנגלית
            rel = 'בת' if first_word.lower() in _FEMALE else 'בן'
    low_name = name.lower()
    if re.search(r'\bgirl\b', low_name):            # "baby girl" → תינוקת (לא תעתיק)
        s = 'תינוקת'
    elif re.search(r'\bboy\b', low_name) or re.fullmatch(r'\s*baby\s*', low_name):
        s = 'תינוק'
    else:
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


def _q(v):
    """מחרוזת IMAP מצוטטת — הכרחי כשהערך מכיל רווח (למשל נושא 'Name Submission')."""
    return '"' + str(v).replace('\\', '\\\\').replace('"', '\\"') + '"'


def _ascii(v):
    try:
        str(v).encode('ascii')
        return True
    except Exception:
        return False


def configured():
    return bool(os.environ.get('GMAIL_USER') and os.environ.get('GMAIL_APP_PASSWORD'))


def _donor_email_map(con):
    """מפה: כתובת מייל → מזהה תורם. רק התאמה מדויקת לכתובת — בלי ניחוש לפי שם."""
    emap = {}
    for r in con.execute("SELECT id,email FROM donors WHERE TRIM(COALESCE(email,''))<>''"):
        for e in re.split(r'[;,\s]+', (r['email'] or '').lower()):
            e = e.strip().strip('<>')
            if '@' in e and e not in emap:      # כתובת שמופיעה אצל שני תורמים — לא נשייך, כדי לא לטעות
                emap[e] = r['id']
            elif e in emap and emap[e] != r['id']:
                emap[e] = None                  # כפילות — מסמנים כלא־ודאי
    return {k: v for k, v in emap.items() if v}


def _snippet(body, n=600):
    t = re.sub(r'\n{3,}', '\n\n', (body or '').strip())
    return t[:n] + ('…' if len(t) > n else '')


def sync_contacts(con):
    """מתייק את כל המיילים שהתקבלו מתורמים (לפי כתובת המייל בלבד) ליומן הקשר שלהם."""
    user = os.environ.get('GMAIL_USER')
    pw = os.environ.get('GMAIL_APP_PASSWORD')
    if not (user and pw):
        return {'ok': False, 'error': 'not_configured'}
    emap = _donor_email_map(con)
    if not emap:
        return {'ok': True, 'new': 0, 'note': 'no_donor_emails'}
    since = os.environ.get('MAILLOG_SINCE') or _imap_since()
    mailbox = os.environ.get('INTAKE_MAILBOX', 'INBOX')
    new = 0
    try:
        M = imaplib.IMAP4_SSL('imap.gmail.com')
        M.login(user, pw)
        M.select(mailbox)
        typ, data = M.search(None, 'SINCE', since)
        ids = data[0].split() if typ == 'OK' else []
        for i in ids:
            # תחילה רק הכותרות — כדי לא להוריד מיילים שאינם של תורמים
            typ, hd = M.fetch(i, '(BODY.PEEK[HEADER.FIELDS (FROM DATE SUBJECT MESSAGE-ID)])')
            if typ != 'OK' or not hd or not hd[0]:
                continue
            hmsg = email.message_from_bytes(hd[0][1])
            _, femail = parseaddr(_dec(hmsg.get('From')))
            femail = (femail or '').strip().lower()
            did = emap.get(femail)
            if not did:
                continue                      # לא זוהה תורם בוודאות — מדלגים
            mid = (hmsg.get('Message-ID') or '').strip() or f'{user}:{i.decode()}'
            if con.execute("SELECT 1 FROM contacts_log WHERE msg_id=?", (mid,)).fetchone():
                continue                      # כבר תויק
            subject = _dec(hmsg.get('Subject')) or '(ללא נושא)'
            try:
                dt = parsedate_to_datetime(hmsg.get('Date'))
                dstr = dt.date().isoformat()
            except Exception:
                dstr = datetime.date.today().isoformat()
            typ, md = M.fetch(i, '(RFC822)')
            body = ''
            if typ == 'OK' and md and md[0]:
                try: body = _extract_text(email.message_from_bytes(md[0][1]))
                except Exception: body = ''
            summary = '📧 ' + subject + (('\n' + _snippet(body)) if body else '')
            con.execute("INSERT INTO contacts_log(donor_id,date,channel,summary,next_date,msg_id) VALUES(?,?,?,?,'',?)",
                        (did, dstr, 'אימייל', summary, mid))
            new += 1
        M.logout()
        con.commit()
        return {'ok': True, 'new': new}
    except imaplib.IMAP4.error as e:
        return {'ok': False, 'error': 'login_failed', 'detail': str(e)}
    except Exception as e:
        return {'ok': False, 'error': 'sync_failed', 'detail': str(e)}


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
    attached = 0

    def _match_donor(femail):
        """מזהה תורם לפי כתובת המייל שלו במערכת — לצירוף אוטומטי לקוויטל."""
        femail = (femail or '').strip().lower()
        if not femail:
            return None
        return con.execute(
            "SELECT id,tier FROM donors WHERE lower(TRIM(email))=? AND TRIM(COALESCE(email,''))<>'' LIMIT 1",
            (femail,)).fetchone()

    def _autoattach(donor, names):
        """מכניס את השמות לקוויטל של התורם (דרגה לפי דרגת התורם)."""
        con.execute("INSERT INTO prayers(donor_id,name,text,tier) VALUES(?,'',?,?)",
                    (donor['id'], names, (donor['tier'] or '')))
    try:
        M = imaplib.IMAP4_SSL('imap.gmail.com')
        M.login(user, pw)
        M.select(mailbox)
        crit = ['SINCE', _imap_since()]
        if subj:
            crit += ['SUBJECT', _q(subj)]   # ציטוט חובה כשהנושא מכיל רווח
        # נדרש CHARSET UTF-8 אם יש תווים לא־אנגליים (עברית) בקריטריונים
        charset = None if all(_ascii(c) for c in crit + froms) else 'UTF-8'

        def _search(*extra):
            args = crit + list(extra)
            if charset:
                return M.search(charset, *[a.encode('utf-8') if not _ascii(a) else a for a in args])
            return M.search(None, *args)

        # אם הוגדרו כמה שולחים — נחפש לכל אחד בנפרד ונאחד
        id_sets = []
        if froms:
            for f in froms:
                typ, data = _search('FROM', _q(f))
                if typ == 'OK':
                    id_sets.append(set(data[0].split()))
            ids = set().union(*id_sets) if id_sets else set()
        else:
            typ, data = _search()
            ids = set(data[0].split()) if typ == 'OK' else set()
        for i in sorted(ids, key=lambda x: int(x)):
            typ, md = M.fetch(i, '(RFC822)')
            if typ != 'OK' or not md or not md[0]:
                continue
            msg = email.message_from_bytes(md[0][1])
            mid = (msg.get('Message-ID') or '').strip() or f'{user}:{i.decode()}'
            existing = con.execute("SELECT id,status FROM intake WHERE message_id=?", (mid,)).fetchone()
            if existing and existing['status'] == 'handled':
                continue   # כבר טופל — לא נוגעים
            fname, femail = parseaddr(_dec(msg.get('From')))
            subject = _dec(msg.get('Subject'))
            try:
                dt = parsedate_to_datetime(msg.get('Date'))
                received = dt.date().isoformat()
            except Exception:
                received = ''
            body = _extract_text(msg)
            names = _parse_names(body)
            if not names.strip():     # אין שמות לתפילה (למשל רק "thank you") — לא מכניסים לרשימה
                continue
            # המייל האמיתי של התורם נמצא בגוף המייל (המיילים מועברים דרך כתובת אחת) — מזהים לפיו
            real_email = (_submitter_email(body) or femail or '').lower()
            donor = _match_donor(real_email)   # זיהוי תורם לפי האימייל האמיתי
            if existing:              # רענון פריט שעדיין לא טופל — מתקן פענוח עברית/תעתיק ישן
                iid = existing['id']
                con.execute("UPDATE intake SET from_name=?, from_email=?, subject=?, received=?, body=?, names=? WHERE id=?",
                            (fname, real_email, subject, received, body, names, iid))
            else:
                cur = con.execute("""INSERT INTO intake(message_id,from_name,from_email,subject,received,body,names,status,created)
                               VALUES(?,?,?,?,?,?,?, 'new', ?)""",
                            (mid, fname, real_email, subject, received, body, names,
                             datetime.date.today().isoformat()))
                iid = cur.lastrowid
                new += 1
            if donor:                 # זוהה תורם לפי מייל — צירוף אוטומטי לקוויטל שלו, נגמר הסיפור
                _autoattach(donor, names)
                con.execute("UPDATE intake SET donor_id=?, status='handled' WHERE id=?", (donor['id'], iid))
                attached += 1
        M.logout()
        con.commit()
        return {'ok': True, 'new': new, 'attached': attached}
    except imaplib.IMAP4.error as e:
        return {'ok': False, 'error': 'login_failed', 'detail': str(e)}
    except Exception as e:
        return {'ok': False, 'error': 'sync_failed', 'detail': str(e)}
