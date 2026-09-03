# -*- coding: utf-8 -*-
"""דיוור לתורמים — הודעה אישית אחת לכל תורם.

מאיר: "אני רוצה שיהיה לי במערכת תוכנה לשליחת מיילים בלי שיועברו לספאם,
ובלי עותק מוסתר."

שני הדברים האלה הם למעשה אותו דבר: מייל אחד שנשלח למאה אנשים ב"עותק
מוסתר" הוא בדיוק מה שמסנני הספאם מחפשים. לכן כאן אין ולא יכול להיות
עותק מוסתר: לכל תורם נבנית הודעה נפרדת משלו, שבה בשורת הנמען כתובה רק
הכתובת שלו, והפנייה היא בשמו. אף תורם אינו רואה את הכתובות של האחרים.

מה עוד נעשה כאן כדי שהמייל יגיע לתיבה ולא לספאם:
  · שורות הכותרת נבנות כמו שצריך — שם השולח, Reply-To, תאריך ו-Message-ID
    מהדומיין שממנו שולחים.
  · כל הודעה נשלחת גם כטקסט פשוט וגם כ-HTML. הודעה שיש בה HTML בלבד
    נחשדת מיד.
  · כותרת List-Unsubscribe עם הסרה בלחיצה אחת. מאז 2024 ג'ימייל ו-Yahoo
    מסננים בכבדות דיוור שאין בו הסרה כזאת.
  · שליחה בקצב אנושי, עם הפוגה בין הודעה להודעה ותקרה יומית — ולא מאות
    הודעות בבת אחת.
  · מי שביקש להסיר את עצמו, או שכתובתו חזרה כשגויה, לא מקבל שוב לעולם.

מה שנשאר בידיים של הכולל, וקוד אינו יכול לעשות במקומו: לשלוח מכתובת של
הדומיין של הכולל (למשל office@kollelchatzot.com) עם SPF, DKIM ו-DMARC
מוגדרים אצל ספק הדואר. דיוור המוני מכתובת ג'ימייל פרטית מסונן בכבדות
ולא משנה כמה הקוד נקי.

הגדרה ב-Render (משתני סביבה בלבד; לא בקוד ולא בקובץ):
    MAIL_HOST       שרת ה-SMTP (ברירת מחדל smtp.gmail.com)
    MAIL_PORT       פורט (ברירת מחדל 587, עם STARTTLS; 465 = SSL)
    MAIL_USER       שם המשתמש (ברירת מחדל GMAIL_USER)
    MAIL_PASS       הסיסמה (ברירת מחדל GMAIL_APP_PASSWORD)
    MAIL_FROM       הכתובת שממנה נשלח (ברירת מחדל MAIL_USER)
    MAIL_FROM_NAME  שם השולח כפי שיוצג (ברירת מחדל "כולל חצות")
    MAIL_REPLY_TO   כתובת לתשובות (ברירת מחדל MAIL_FROM)
    MAIL_DAILY_CAP  תקרה יומית (ברירת מחדל 400 — מתחת למגבלת ג'ימייל)
    MAIL_GAP_SEC    שניות בין הודעה להודעה (ברירת מחדל 8)
"""
import hmac
import os
import re
import socket
import smtplib
import ssl
import time
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid, parseaddr

DEF_HOST, DEF_PORT = 'smtp.gmail.com', 587
DEF_NAME = 'כולל חצות'
DEF_CAP, DEF_GAP = 400, 8

# מצב השליחה הפעילה — נקרא מהמסך כדי להראות התקדמות חיה
STATUS = {'running': False, 'done': True, 'batch': 0, 'total': 0, 'sent': 0,
          'failed': 0, 'skipped': 0, 'left': 0, 'error': '', 'now': '', 'stop': False}

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$')


# מה שמאיר הגדיר במסך "מאיפה נשלח הדואר". גובר על משתני הסביבה, כי הוא
# הדבר האחרון שנקבע במפורש. נטען מהמסד בעליית השרת ובכל שמירה.
# מאיר: "אני לא הבנתי איך אני מחבר אותו בכלל" — ההגדרה ב-Render הייתה
# מסובכת מדי, ולכן היא נעשית מתוך המערכת עצמה.
OVERRIDE = {}


def _env(k, d=''):
    o = OVERRIDE.get(k)
    if o not in (None, ''):
        return str(o).strip()
    return (os.environ.get(k) or d).strip()


def cfg():
    user = _env('MAIL_USER') or _env('GMAIL_USER')
    pw = _env('MAIL_PASS') or _env('GMAIL_APP_PASSWORD')
    frm = _env('MAIL_FROM') or user
    try:
        port = int(_env('MAIL_PORT', str(DEF_PORT)) or DEF_PORT)
    except ValueError:
        port = DEF_PORT
    try:
        cap = int(_env('MAIL_DAILY_CAP', str(DEF_CAP)) or DEF_CAP)
    except ValueError:
        cap = DEF_CAP
    try:
        gap = float(_env('MAIL_GAP_SEC', str(DEF_GAP)) or DEF_GAP)
    except ValueError:
        gap = DEF_GAP
    return {'host': _env('MAIL_HOST', DEF_HOST) or DEF_HOST, 'port': port,
            'user': user, 'pw': pw, 'frm': frm,
            'name': _env('MAIL_FROM_NAME', DEF_NAME) or DEF_NAME,
            'reply': _env('MAIL_REPLY_TO') or frm,
            'cap': max(1, cap), 'gap': max(0.0, gap)}


def configured():
    c = cfg()
    return bool(c['user'] and c['pw'] and c['frm'])


def valid(email):
    e = (email or '').strip()
    return bool(_EMAIL_RE.match(e)) and len(e) <= 254


def domain():
    return (parseaddr(cfg()['frm'])[1].split('@')[-1] or 'localhost').lower()


def free_domain():
    """כתובת שולח בדומיין ציבורי — הסיבה מספר אחת לדיוור שנופל לספאם."""
    return domain() in ('gmail.com', 'googlemail.com', 'yahoo.com', 'hotmail.com',
                        'outlook.com', 'walla.com', 'walla.co.il', 'aol.com')


def _connect():
    c = cfg()

    def open_(relaxed):
        ctx = ssl.create_default_context()
        if relaxed:
            # שרת דואר ישן שההצפנה שלו חלשה מהתקן של היום. בדיקת תעודת
            # האבטחה נשארת מלאה — רק דרישת גודל מפתח ההחלפה מתרככת.
            try:
                ctx.set_ciphers('DEFAULT@SECLEVEL=1')
            except Exception:
                pass
        if c['port'] == 465:
            return smtplib.SMTP_SSL(c['host'], c['port'], timeout=40, context=ctx)
        s2 = smtplib.SMTP(c['host'], c['port'], timeout=40)
        try:
            s2.starttls(context=ctx)
        except smtplib.SMTPNotSupportedError:
            pass                      # שרת מקומי לבדיקות — בלי הצפנה
        return s2
    try:
        s = open_(False)
    except ssl.SSLError as e:
        # אותה תאימות לאחור שבבדיקת החיבור — אחרת החיבור נבדק בהצלחה
        # והשליחה עצמה נופלת
        if not any(x in str(e) for x in _OLD_TLS):
            raise
        s = open_(True)
    if c['pw']:
        try:
            s.login(c['user'], c['pw'])
        except smtplib.SMTPNotSupportedError:
            pass                      # ממסר פנימי שאינו דורש התחברות
    return s


# תווי כיווניות בלתי־נראים שנדבקים לטקסט שמועתק מוואטסאפ, ממייל או
# ממסמך בעברית. מאיר הדביק שם שרת והתקבל:
#   UnicodeEncodeError: 'idna' codec can't encode character '\u202c'
# העין רואה "mail.kollelchatzot.com" והמחרוזת ארוכה בתו אחד. נוקה בכל
# מקום שנכנסת אליו כתובת או שם שרת, כי אי אפשר לראות את זה במסך.
_INVIS = re.compile('[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff\u00ad]')


def clean(s):
    """מנקה תווים בלתי־נראים ורווחים מקצה מחרוזת שהמשתמש הדביק."""
    return _INVIS.sub('', str(s or '')).strip()


# שגיאות הצפנה שמקורן בשרת ישן, ולא בשם או בסיסמה. מאיר קיבל מהשרת של
# האחסון: "DH_KEY_TOO_SMALL" — מפתח החלפה בן 1024 סיביות, שהתקן של היום
# כבר אינו מקבל. במקרים כאלה מנסים שוב בתאימות לאחור.
_OLD_TLS = ('DH_KEY_TOO_SMALL', 'SSLV3_ALERT_HANDSHAKE_FAILURE',
            'UNSUPPORTED_PROTOCOL', 'WRONG_SIGNATURE_TYPE', 'EE_KEY_TOO_SMALL',
            'CA_MD_TOO_WEAK', 'NO_CIPHERS_AVAILABLE')


def _try(host, port, user, pw, relaxed=False):
    """ניסיון התחברות אחד. מחזיר (הצליח, שגיאה).

    relaxed — מתירים אלגוריתמי הצפנה ישנים יותר (SECLEVEL=1) עבור שרתים
    שלא עודכנו. בדיקת תעודת האבטחה נשארת מלאה; מה שמשתנה הוא רק גודל
    מפתח ההחלפה שאנחנו מוכנים לקבל.
    """
    ctx = ssl.create_default_context()
    if relaxed:
        try:
            ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        except Exception:
            pass
    s = None
    try:
        if port == 465:
            s = smtplib.SMTP_SSL(host, port, timeout=20, context=ctx)
        else:
            s = smtplib.SMTP(host, port, timeout=20)
            try:
                s.starttls(context=ctx)
            except smtplib.SMTPNotSupportedError:
                pass
        try:
            s.login(user, pw)
        except smtplib.SMTPNotSupportedError:
            pass                      # ממסר שאינו דורש התחברות
        return True, ''
    except smtplib.SMTPAuthenticationError as e:
        return False, 'auth:' + str(e)[:160]
    except Exception as e:
        # סוג התקלה חשוב לאבחון: timeout = החיבור נחסם בדרך ולא הגיע לשרת,
        # refused = השרת ענה ואמר "לא כאן", ssl = בעיית הצפנה/פורט
        return False, 'conn:' + type(e).__name__ + ': ' + str(e)[:140]
    finally:
        try:
            if s:
                s.quit()
        except Exception:
            pass


def _real_name(host):
    """השם האמיתי של השרת שמאחורי שם אליאס, לפי reverse DNS.

    מאיר קיבל: "certificate is not valid for 'mail.kollelchatzot.com'".
    זה מצב רגיל באחסון משותף — השרת אחד ומשרת הרבה דומיינים, והתעודה
    שלו היא על השם שלו עצמו (mail10.myhsphere.biz) ולא על שם הלקוח.
    החיבור עצמו הצליח; רק בדיקת השם נכשלה. אז מתחברים לשם שהתעודה באמת
    נכתבה עליו — וכך האימות עובר במלואו, בלי לוותר על שום בדיקה.
    """
    try:
        ip = socket.gethostbyname(host)
        rev = socket.gethostbyaddr(ip)[0]
        return rev if rev and rev.lower() != host.lower() else ''
    except Exception:
        return ''


def probe(user, pw, host='', port=0, log=None):
    """מוצא לבד את שרת הדואר והפורט של הכתובת.

    מאיר לא אמור לדעת מהו "SMTP" ומהו "פורט 465". הוא נותן כתובת וסיסמה,
    וכאן מנסים את הצירופים המקובלים עד שאחד מהם מתחבר. מחזיר
    (הצליח, שרת, פורט, הודעה בעברית).
    """
    user = clean(user)
    host = clean(host)
    dom = user.split('@')[-1].lower()
    if not user or '@' not in user or not pw:
        return False, '', 0, 'חסרה כתובת או סיסמה'
    if host:
        hosts = [host.strip()]
    elif dom in ('gmail.com', 'googlemail.com'):
        hosts = ['smtp.gmail.com']
    else:
        hosts = ['mail.' + dom, 'smtp.' + dom, dom]
    ports = [int(port)] if port else [465, 587]
    lastauth = ''
    # מאיר: "היא שלחה לי את השם של השרת ואת המספר וזה לא מצליח להתחבר
    # עדיין, היא אומרת שזה אמור להיות בסדר מבחינתה." בלי לדעת מה בדיוק
    # נכשל אי אפשר להתקדם, ולכן כל ניסיון נרשם: איזה שרת, איזה פורט, ומה
    # השגיאה המדויקת. הרשימה מוצגת במסך כדי שאפשר יהיה להעביר אותה כמו
    # שהיא למנהל האחסון.
    if log is None:
        log = []
    mismatch = []            # שרתים שענו אבל התעודה שלהם על שם אחר
    tried = set()
    legacy = False           # התחברנו רק אחרי ויתור על דרישת הצפנה מודרנית

    def attempt(h, pt):
        nonlocal lastauth, legacy
        if (h, pt) in tried:
            return False
        tried.add((h, pt))
        t0 = time.time()
        ok, err = _try(h, pt, user, pw)
        # שרת ישן שההצפנה שלו חלשה מהתקן של היום — מנסים שוב בתאימות
        # לאחור, בלי לוותר על בדיקת תעודת האבטחה
        if not ok and any(x in err for x in _OLD_TLS):
            ok2, err2 = _try(h, pt, user, pw, relaxed=True)
            if ok2:
                legacy = True
                log.append({'host': h, 'port': pt, 'ok': True,
                            'sec': round(time.time() - t0, 1),
                            'err': '', 'legacy': True})
                return True
            err = err + ' | גם בתאימות לאחור: ' + err2
            if err2.startswith('auth:'):
                lastauth = err2[5:]
        log.append({'host': h, 'port': pt, 'ok': ok,
                    'sec': round(time.time() - t0, 1),
                    'err': '' if ok else err})
        if ok:
            return True
        if err.startswith('auth:'):
            # השרת נמצא ועונה — הסיסמה היא הבעיה, אין טעם לנסות עוד
            lastauth = err[5:]
        elif 'Hostname mismatch' in err or 'CERTIFICATE_VERIFY_FAILED' in err:
            if h not in mismatch:
                mismatch.append(h)
        return False
    old = (' · שים לב: שרת הדואר משתמש בהצפנה ישנה, והתחברנו בתאימות לאחור. '
           'כדאי לבקש ממנהל האחסון לעדכן את השרת.')
    for h in hosts:
        for pt in ports:
            if attempt(h, pt):
                return True, h, pt, ('מחובר · שולח מ־%s' % user) + (old if legacy else '')
    # התעודה על שם אחר — מנסים את השם האמיתי של השרת עצמו
    for h in mismatch:
        real = _real_name(h)
        if not real:
            continue
        for pt in ports:
            if attempt(real, pt):
                return (True, real, pt,
                        ('מחובר · שולח מ־%s (דרך %s — זה שמו האמיתי של שרת '
                         'הדואר של %s)' % (user, real, h)) + (old if legacy else ''))
    if lastauth:
        return False, '', 0, ('שרת הדואר נמצא אבל דחה את הסיסמה. בדוק את הסיסמה '
                              'של התיבה %s. (%s)' % (user, lastauth[:80]))
    # כשכל הניסיונות נגמרו בפסק זמן — החיבור נחסם בדרך ולא הגיע לשרת כלל
    if log and all('TimeoutError' in (x['err'] or '') or 'timed out' in (x['err'] or '')
                   for x in log):
        return False, '', 0, ('החיבור לשרת %s לא נענה כלל (פסק זמן). זה לא שם שגוי '
                              'ולא סיסמה — משהו חוסם את הדרך בין השרת שלנו לשרת '
                              'הדואר. בקש ממנהל האחסון לפתוח שליחת SMTP מכתובות '
                              'חיצוניות.' % (hosts[0] if hosts else dom))
    if mismatch:
        return False, '', 0, ('שרת הדואר של %s ענה, אבל תעודת האבטחה שלו רשומה '
                              'על שם אחר, ולא הצלחתי למצוא את השם הנכון. בקש '
                              'ממנהל האחסון את שם שרת ה-SMTP כפי שהוא רשום '
                              'בתעודה.' % dom)
    return False, '', 0, ('לא הצלחתי להתחבר לשרת הדואר של %s. ייתכן ששם השרת '
                          'שונה — בקש ממנהל האחסון את כתובת ה-SMTP והפורט.' % dom)


def check():
    """בדיקת חיבור בלי לשלוח דבר. מחזיר (תקין, הודעה בעברית)."""
    if not configured():
        return False, ('לא הוגדר. יש להגדיר ב-Render את MAIL_USER ו-MAIL_PASS '
                       '(או GMAIL_USER / GMAIL_APP_PASSWORD)')
    try:
        s = _connect()
        try:
            s.quit()
        except Exception:
            pass
    except smtplib.SMTPAuthenticationError:
        # מאיר: "שיניתי באמת סיסמא, אולי זו הבעיה?" — כן. שינוי סיסמת
        # החשבון מבטל את כל "סיסמאות האפליקציה" שנוצרו קודם, וזאת הסיסמה
        # שהשרת משתמש בה. צריך ליצור חדשה ולהחליף אותה ב-Render.
        return False, ('הדואר דחה את הסיסמה. אם שינית לאחרונה את סיסמת חשבון '
                       'הג׳ימייל — כל "סיסמאות האפליקציה" הישנות בוטלו. צור סיסמת '
                       'אפליקציה חדשה ב-myaccount.google.com/apppasswords והחלף '
                       'את GMAIL_APP_PASSWORD ב-Render (16 תווים, בלי רווחים).')
    except Exception as e:
        return False, 'אין תקשורת אל שרת הדואר: %s' % e
    c = cfg()
    msg = 'מחובר · שולח מ־%s' % c['frm']
    # מלכודת: להגדיר כתובת של הדומיין אבל להתחבר עדיין דרך ג'ימייל.
    # ג'ימייל דורס את שורת השולח ומחזיר את הכתובת שהתחברו איתה, ולכן
    # התורם היה רואה כתובת אחרת ממה שכתוב כאן.
    ud = (parseaddr(c['user'])[1] or c['user']).split('@')[-1].lower()
    if 'gmail' in c['host'].lower() and ud and ud != domain():
        msg += (' ⚠️ אבל השליחה עוברת דרך ג׳ימייל, וג׳ימייל מחליף את כתובת '
                'השולח בכתובת שהתחברת איתה (%s). כדי לשלוח באמת מ־%s צריך '
                'להגדיר MAIL_HOST של שרת הדואר של הדומיין.' % (c['user'], c['frm']))
    elif free_domain():
        msg += ' · שים לב: כתובת ג׳ימייל פרטית — דיוור המוני ממנה מסונן לספאם'
    return True, msg


# ----- בניית ההודעה -----

def unsub_token(email, secret):
    """מפתח הסרה קבוע לכל כתובת — אותו קישור תמיד, בלי לשמור סוד בקישור."""
    return hmac.new((secret or '').encode('utf-8'),
                    (email or '').strip().lower().encode('utf-8'), 'sha256').hexdigest()[:32]


def _esc(s):
    return (str(s or '').replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


_PH = re.compile(r'\{\{\s*([^{}]*?)\s*\}\}')


# מאיר: "אני לא מרוצה מהתוארים — אני רוצה שלכולם יהיה אותו תואר, גם נשים
# גם גברים. התואר הראשון זה ה"ה, והסיום הי"ו. לכולם אותו דבר."
# בפתקי הקוויטל התואר נשאר ר' / מרת / ה"ה לפי האדם; במכתבים הוא אחיד.
TITLE_ALL = 'ה"ה'
GREET_PRE = 'לכבוד ידידינו ושותפינו היקר ה"ה '
GREET_POST = ' הי"ו'
TITLE_END = 'הי"ו'          # התואר שאחרי השם
AV_PRE, AV_POST = 'הר"ר ', ' שליט"א'    # התואר של האברך במכתב
# מאיר: "אני רוצה גופן של עברית במיוחד של שם התורם ושם האברך, בגדול."
# בדואר אי אפשר לצרף גופן — לקוחות הדואר חוסמים גופנים חיצוניים. לכן
# נבחרת שרשרת של גופנים עבריים שמותקנים ברוב המחשבים, ובסופה serif כללי:
# מי שיש לו פרנק־רוהל יראה אותו, ואצל כל האחרים ייפול לגופן עברי מכובד
# אחר — ובכל מקרה שונה בבירור מגוף המכתב.
HEBFONT = ("'Frank Ruhl Libre','FrankRuhlCLM','David Libre',David,'Narkisim',"
           "'Times New Roman',serif")
# שם התורם — הדבר הגדול ביותר במכתב, גדול גם מתיבת הקוויטל
BIG = ('<b style="font-family:%s;font-size:1.6em;line-height:1.35;'
       'letter-spacing:.01em">%%s</b>' % HEBFONT)
# שם האברך — באותו גופן, מודגש וגדול מהטקסט אך קטן משם התורם
BOLD = '<b style="font-family:%s;font-size:1.18em">%%s</b>' % HEBFONT
KVBOX = ('<span style="display:block;margin:14px 0;padding:13px 17px;background:#faf6ec;'
         'border-%s:4px solid #9c7a2e;border-radius:9px;font-size:1.12em;font-weight:700;'
         'line-height:1.8;color:#1c1710">')
KVLINE = '<span style="display:block">%s</span>'

# מאיר: "נעשה ריבועים כאלה יפים שהבן אדם רואה באופן יפה ובולט את כל
# אפשרויות התרומה... או שזה מכביד על המערכת של האימייל?" לא מכביד: אלו
# טבלאות טקסט עם מסגרת, בלי שום תמונה — כמה אלפי תווים בסך הכל. תמונה
# היא מה שמכביד, וגם נחסמת אצל רוב התורמים.
#
# כל אפשרות: כותרת, שורת הסבר, וקישור (ריק = אין למה ללחוץ).
DONATE = [
    ('💳', 'Credit Card', 'Up to 3 monthly payments',
     'https://kollelchatzot.com/donate.php'),
    ('💵', 'Zelle / QuickPay', 'Kollelchatzos1@gmail.com<br>'
     '(appears as Congregation Zichron Avos)', 'mailto:Kollelchatzos1@gmail.com'),
    ('🏦', 'OJC / Donors Fund', 'Kollel Chatzos<br>Tax ID # 20-0447034', ''),
    ('✉️', 'Check', 'Made out to Kollel Chatzos<br>'
     'c/o Friedman Family<br>1540 40th Street, Brooklyn, NY 11218<br>'
     'Tax ID # 20-0447034',
     'https://maps.google.com/?q=1540+40th+Street+Brooklyn+NY+11218'),
    ('💬', 'WhatsApp', 'Straight to me — write any time',
     'https://wa.me/972527628272?text=Hello%20Rabbi%20Deutsch%2C%20I%20would'
     '%20like%20to%20take%20a%20family%20for%20Yom%20Tov'),
    ('📞', 'Phone', 'My own number — call me directly<br>+972 52-762-8272',
     'tel:+972527628272'),
    # מאיר: "תוציא את דגל ישראל, יש כאלה שלא אוהבים. במקום זה סימן של
    # שקל חדש." ו"נדרים פלוס שיהיה הכי למטה" — רוב התורמים בחו״ל.
    ('₪', 'Nedarim Plus', 'Donate in ₪ · the Israeli account',
     'https://www.matara.pro/nedarimplus/online/?mosad=5777499'),
]
DONATE_FOOT = 'All donations are tax deductible · Tax ID # 20-0447034'
# קו מפריד בין חלקי המכתב — במקום מקף על פני כל השורה
DIVIDER = ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
           'border="0" style="margin:22px 0"><tr>'
           '<td style="border-top:1px solid #e2d9c3;font-size:0;line-height:0">&nbsp;</td>'
           '<td width="26" align="center" style="font-size:13px;line-height:1;'
           'color:#c9a94e;padding:0 6px">&#9670;</td>'
           '<td style="border-top:1px solid #e2d9c3;font-size:0;line-height:0">&nbsp;</td>'
           '</tr></table>')
_TILE = ('<td width="50%%" valign="top" style="padding:4px">'
         '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" border="0">'
         '<tr><td style="border:1px solid #ddd6c6;border-radius:10px;background:#fffdf7;'
         'padding:11px 12px;text-align:center;font-size:14px;line-height:1.45">'
         '<div style="font-size:20px;line-height:1">%s</div>'
         '<div style="font-weight:700;color:#2b2b2b;margin-top:3px">%s</div>'
         '<div style="color:#6b6257;font-size:12px;margin-top:2px">%s</div>'
         '</td></tr></table></td>')


def donate_html():
    """אפשרויות התרומה כריבועים — שניים בשורה, בלי תמונות ובלי כלום
    שנחסם. טבלאות ולא flex/grid, כי אאוטלוק אינו תומך בהם."""
    cells = []
    for icon, title, sub, url in DONATE:
        t = title if not url else \
            '<a href="%s" style="color:#1a5fb4;text-decoration:none">%s</a>' % (url, title)
        cells.append(_TILE % (icon, t, sub))
    rows = ''
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2]
        if len(pair) == 1:
            pair.append('<td width="50%"></td>')
        rows += '<tr>' + ''.join(pair) + '</tr>'
    return ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'border="0" style="margin:14px 0">' + rows + '</table>'
            '<div style="text-align:center;color:#6b6257;font-size:12px;margin:2px 0 10px">'
            + _esc(DONATE_FOOT) + '</div>')


def donate_text():
    """אותן אפשרויות בטקסט פשוט — למי שקורא את הגרסה בלי עיצוב."""
    out = []
    for icon, title, sub, url in DONATE:
        s = re.sub(r'<br\s*/?>', ' · ', sub)
        line = '%s %s — %s' % (icon, title, s)
        if url and not url.startswith('mailto:') and not url.startswith('tel:'):
            line += '\n   ' + url
        out.append(line)
    return '\n'.join(out) + '\n\n' + DONATE_FOOT


def personalize(text, who, html=False, d='rtl'):
    """מחליף את הסימונים שבמכתב בפרטי התורם שמקבל אותו.

    מאיר: "אם אני רוצה להכניס לו תואר לפני או אחרי לכל אחד — אם זה גבר
    אז משהו אחד ואם זה אשה אז משהו אחר, איך אני אמור להסתדר עם זה?"

        {{שם}}      שם פרטי                      יצחק
        {{משפחה}}   שם משפחה                     רוזנפלד
        {{שם מלא}}  שם פרטי ומשפחה               יצחק רוזנפלד
        {{תואר}}    ר' לגבר · מרת לאשה · ה"ה לזוג
        {{אברך}}    האברך שלומד עבורו            נתנאל ברנס
        {{קוויטל}}  שמות הקוויטל שלו             יצחק בן חנה לרפואה שלמה, ...

    השמות תמיד נכתבים בעברית, גם כשהמכתב עצמו באנגלית — הם נלקחים
    מהכרטיס כמו שהם.

    ולשון פנייה: כמה מילים עם קו ביניהן — הראשונה לגבר, השנייה לאשה,
    ואם נכתבה שלישית היא לזוג:

        שתזכ{{ה|י|ו}} לכל טוב   ->  שתזכה / שתזכי / שתזכו
        {{היקר|היקרה}}          ->  היקר / היקרה
    """
    if isinstance(who, str):                  # תאימות לקריאה עם שם בלבד
        who = {'name': who}
    first = (who.get('first') or '').strip()
    last = (who.get('last') or '').strip()
    full = (who.get('name') or (first + ' ' + last)).strip()
    if not first:
        first = full
    g = ((who.get('gender') or 'm') + 'm')[0]
    kv = [x.strip() for x in str(who.get('kvittel') or '').split('\n') if x.strip()]
    avs = [x.strip() for x in str(who.get('avreich') or '').split('\n') if x.strip()]
    eng = (who.get('english') or '').strip() or full
    simple = {'שם': first, 'משפחה': last, 'שם מלא': full,
              # מכתב באנגלית — השם הלועזי מהכרטיס
              'אנגלית': eng, 'שם באנגלית': eng, 'english': eng,
              'תואר': (who.get('title') or TITLE_ALL).strip() or TITLE_ALL,
              # מאיר: "יששכר־זבולון — אני רוצה למזג לו את השם של האברך
              # שלומד בשבילו בתוך המכתב, ואת הקוויטל שלו"
              'name': first, 'lastname': last, 'fullname': full}
    side = 'right' if d == 'rtl' else 'left'

    def sub(m):
        key = m.group(1)
        if html:
            # ב-HTML הטקסט מוברח לפני ההצבה, ולכן גרשיים שבתוך הסימון
            # (למשל {{הי"ו}}) הגיעו לכאן כ-&quot; — מחזירים אותם כדי שהשם
            # של הסימון יזוהה
            key = key.replace('&quot;', '"').replace('&#34;', '"').replace('&amp;', '&')
        if '|' in key:                        # לשון זכר / נקבה / זוג
            parts = [p.strip() for p in key.split('|')]
            i = {'m': 0, 'f': 1, 'c': 2}.get(g, 0)
            if i >= len(parts):
                i = 0
            return parts[i]
        if key in ('פנייה', 'greeting'):
            # מאיר: "שאני כותב 'לכבוד ידידינו ושותפינו היקר ה\"ה' ואז את
            # השם שלו באותיות גדולות יותר בעברית מודגשות, ואז הי\"ו.
            # לכולם אותו דבר."
            return (GREET_PRE + BIG % _esc(full) + GREET_POST) if html \
                else (GREET_PRE + full + GREET_POST)
        # מאיר: "אני רוצה פשוט — תואר לפני השם, שם מלא מודגש, תואר אחרי
        # השם, וקוויטל מודגש, ואם יש אברך שלומד בשבילו — מודגש. וזהו."
        if key in ('שם', 'שם גדול', 'name', 'bigname'):
            return (BIG % _esc(full)) if html else full
        if key in ('הי"ו', 'הי\u05f4ו', 'סיום'):
            return _esc(TITLE_END) if html else TITLE_END
        if key in ('אברך', 'אברכים', 'avreich'):
            # מאיר: "ואם יש לתורם כמה אברכים שהוא מחזיק — שאכתוב '3
            # האברכים האלו לומדים בשבילך' ואז אצרף את שלושת השמות."
            if not avs:
                return ''
            # מאיר: "שזה יכתוב את כל התואר של האברך — למשל הר\"ר יעקב יוסף
            # אנשין שליט\"א". התואר בגופן רגיל, השם עצמו מודגש.
            names = [AV_PRE + ((BOLD % _esc(x)) if html else x) + AV_POST for x in avs]
            if len(names) == 1:
                return names[0]
            return ', '.join(names[:-1]) + ' ו' + names[-1]
        if key in ('מספר אברכים', 'כמה אברכים'):
            return str(len(avs))
        if key in ('תרומה', 'תשלום', 'donate'):
            return donate_html() if html else donate_text()
        if key in ('קו', 'הפרדה', 'divider'):
            return DIVIDER if html else '— — —'
        if key in ('קוויטל', 'kvittel'):
            if not kv:
                return ''
            if not html:
                return '\n'.join(kv)
            return (KVBOX % side) + ''.join(KVLINE % _esc(x) for x in kv) + '</span>'
        if key in simple:
            return (_esc(simple[key]) if html else simple[key])
        return m.group(0)                     # סימון לא מוכר — נשאר כמו שהוא

    return _PH.sub(sub, str(text or ''))


_HEB = re.compile(r'[\u0590-\u05ff]')
_LAT = re.compile(r'[A-Za-z]')


def letter_dir(text, raw=True):
    """כיוון המכתב לפי מה שנכתב בו בפועל.

    מאיר: "אני מסגנן את המכתב באנגלית, אבל השם צריך להיות בעברית — שם
    ושם משפחה בעברית." מכתב באנגלית שמיושר לימין נראה שבור, ולכן הכיוון
    נקבע לפי רוב האותיות. שם עברי בתוך משפט אנגלי (או להפך) יושב נכון
    בזכות dir="auto" של כל פסקה — הדפדפן מסדר אותו בעצמו.
    """
    # נמדד על התבנית כפי שנכתבה, בלי הסימונים — אחרת שמות עבריים שנמזגו
    # לתוך מכתב אנגלי היו הופכים אותו לימין-לשמאל
    s = _PH.sub(' ', str(text or '')) if raw else str(text or '')
    return 'rtl' if len(_HEB.findall(s)) >= len(_LAT.findall(s)) else 'ltr'


def open_token(qid, secret):
    """מפתח לפיקסל המעקב — כדי שאיש לא יוכל לזייף פתיחה של תורם אחר."""
    return hmac.new((secret or '').encode('utf-8'),
                    ('o:%s' % qid).encode('utf-8'), 'sha256').hexdigest()[:16]


# מאיר כותב את הקישורים בסגנון [לחץ כאן](כתובת) — וזה יצא אצל התורם
# כטקסט מת, כי גוף המכתב מוברח כ-HTML ואף שלב לא הפך אותו לקישור.
# כאן זה נעשה: גם הסגנון הזה, וגם כתובת או מייל שנכתבו כמו שהם.
_LNKS = 'color:#1a5fb4;text-decoration:underline'
_MD_LNK = re.compile(r'\[([^\]\n]{1,140})\]\(\s*'
                     r'((?:https?://|mailto:|tel:|www\.)[^)\s]{3,400})\s*\)')
_BARE_URL = re.compile(r'(?<![\w@/">.])((?:https?://|www\.)[^\s<>"\'()]{4,400})')
_BARE_EM = re.compile(r'(?<![\w.@:/">])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24})\b')


def _links(h):
    """הופך את הקישורים שבטקסט לקישורים לחיצים. הקישור שכבר נבנה נשמר
    בצד ולא נסרק שוב, אחרת הכתובת שבתוכו הייתה מקבלת קישור משל עצמה."""
    keep = []

    def stash(url, txt):
        if url.startswith('www.'):
            url = 'http://' + url
        keep.append('<a href="%s" style="%s">%s</a>' % (url, _LNKS, txt))
        return '\x00%d\x00' % (len(keep) - 1)

    h = _MD_LNK.sub(lambda m: stash(m.group(2).strip(), m.group(1).strip()), h)
    h = _BARE_URL.sub(lambda m: stash(m.group(1), m.group(1)), h)
    h = _BARE_EM.sub(lambda m: stash('mailto:' + m.group(1), m.group(1)), h)
    return re.sub('\x00(\\d+)\x00', lambda m: keep[int(m.group(1))], h)


def _plain_links(t):
    """באותו מכתב כטקסט פשוט — הכתובת נכתבת אחרי המילה, אחרת התורם
    שקורא את הגרסה הזאת רואה "לחץ כאן" בלי לאן."""
    def one(m):
        txt, url = m.group(1).strip(), m.group(2).strip()
        if url.startswith('mailto:') or url.startswith('tel:'):
            url = url.split(':', 1)[1]
        # הכתובת כבר כתובה במילים עצמן ("www.kollelchatzot.com",
        # מספר טלפון עם מקפים) — אין טעם לחזור עליה פעמיים
        def bare(s):
            return re.sub(r'[^a-z0-9@.+]', '', s.lower()).lstrip('+')
        b1, b2 = bare(txt), bare(re.sub(r'^https?://(www\.)?', '', url))
        if b1 and b2 and (b1 in b2 or b2 in b1):
            return txt
        return '%s: %s' % (txt, url)
    return _MD_LNK.sub(one, t)


def _html(body, unsub_url, sig, d='rtl', pixel='', who=None):
    """מכתב פשוט ונקי. בלי תמונות, בלי כפתורים צבעוניים ובלי טבלאות
    שיווקיות — מכתב שנראה כמו מכתב עובר את המסננים הרבה יותר טוב.

    הטקסט מגיע לכאן כתבנית, לא מוחלף מראש: קודם מבריחים אותו כ-HTML ורק
    אחר כך מציבים את הסימונים — כך השם והקוויטל יכולים לצאת מודגשים
    וגדולים, בלי שהעיצוב ייבלע בהברחה."""
    def _p(x):
        # הקישורים נבנים לפני ההצבה של השם והקוויטל, כדי ששם שיש בו
        # נקודה או @ לא ייהפך בטעות לקישור
        x = _links(_esc(x).replace('\n', '<br>'))
        return personalize(x, who, html=True, d=d) if who is not None else x
    paras = ''.join('<p dir="auto" style="margin:0 0 12px">%s</p>' % _p(p)
                    for p in re.split(r'\n\s*\n', str(body or '').strip()) if p.strip())
    foot = ''
    if sig:
        foot += ('<p dir="auto" style="margin:18px 0 0;color:#555">%s</p>' % _p(sig))
    if pixel:
        # פיקסל מעקב פתיחות. עובד רק כשהתורם מאשר הצגת תמונות, ולכן
        # המספר תמיד נמוך מהאמת — ראה את ההסבר במסך.
        foot += '<img src="%s" width="1" height="1" alt="" style="display:block;border:0">' % _esc(pixel)
    return ('<!doctype html><html lang="%s" dir="%s"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
            '<body style="margin:0;padding:18px;background:#ffffff">'
            '<div style="max-width:600px;margin:0 auto;direction:%s;text-align:start;'
            # מאיר: "הייתי רוצה אולי להגדיל טיפונת את כל הטקסט באנגלית".
            # 17px במקום 16. כל שאר הגדלים במכתב נגזרים מזה ב-em — השם,
            # שם האברך ותיבת הקוויטל — ולכן הכל גדל יחד ובאותו יחס.
            'font-family:Arial,\'Segoe UI\',sans-serif;font-size:17px;line-height:1.7;color:#222">'
            % (('en', 'ltr', 'ltr') if d == 'ltr' else ('he', 'rtl', 'rtl'))
            + paras + foot + '</div></body></html>')


def plain_text(body, who, unsub_url='', sig=''):
    """גוף המכתב כטקסט פשוט — בדיוק מה שנשלח, וגם מה שמוצג בתצוגה
    המקדימה. אותו חישוב אחד לשני המקומות, כדי שלא ייפרדו."""
    out = personalize(_plain_links(body or ''), who)
    if (sig or '').strip():
        out += '\n\n' + _plain_links(sig.strip())
    # מאיר: "אני לא רוצה שיהיה רשום להסרה מהרשימה בכלל, שזה לא יהיה כתוב.
    # אם תורם לא רוצה לקבל — הוא ישלח אימייל." לכן אין שורת הסרה בגוף
    # המכתב. כותרת List-Unsubscribe נשארת, כי היא אינה נראית לקורא אך
    # בלעדיה הדיוור נופל לספאם — וזה בדיוק מה שמאיר ביקש למנוע.
    return out


def build(to, who, subject, body, unsub_url='', sig='', attachments=None, pixel=''):
    """הודעה אישית אחת. בשורת הנמען יש כתובת אחת בלבד — ואין ולא יהיה
    כאן Cc או Bcc.

    ההודעה נבנית בסגנון הקלאסי (MIME) ולא ב-EmailMessage החדש, מסיבה
    מעשית: הכותב החדש מקפל כתובת ארוכה בכותרת List-Unsubscribe ומקודד
    אותה כ-=?utf-8?q?...?= — וכתובת מקודדת אינה כתובת. ג'ימייל לא היה
    מזהה את ההסרה, וזה בדיוק מה שמפיל דיוור לספאם. כאן הכותרת נשמרת
    בדיוק כפי שנכתבה.
    """
    c = cfg()
    if isinstance(who, str):
        who = {'name': who}
    name = (who.get('name') or '').strip()
    txt = personalize(body, who)
    subj = personalize(subject, who) or 'כולל חצות'

    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText(plain_text(body, who, unsub_url, sig), 'plain', 'utf-8'))
    dirn = letter_dir(str(body or '') + ' ' + str(sig or ''))
    alt.attach(MIMEText(_html(body, unsub_url, sig, dirn, pixel, who),
                        'html', 'utf-8'))
    atts = [a for a in (attachments or []) if a and a[2]]
    if atts:
        msg = MIMEMultipart('mixed')
        msg.attach(alt)
        for (fname, mime, data) in atts:
            maintype, _, subtype = (mime or 'application/octet-stream').partition('/')
            part = MIMEBase(maintype or 'application', subtype or 'octet-stream')
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment',
                            filename=('utf-8', '', fname or 'file'))
            msg.attach(part)
    else:
        msg = alt

    msg['From'] = formataddr((str(c['name']), c['frm']), charset='utf-8')
    msg['To'] = (formataddr((str(name or '').strip(), to), charset='utf-8')
                 if (name or '').strip() else to)
    msg['Subject'] = Header(subj, 'utf-8').encode()
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain=domain())
    if c['reply'] and c['reply'] != c['frm']:
        msg['Reply-To'] = c['reply']
    if unsub_url:
        # RFC 8058 — הסרה בלחיצה אחת. חייבת להיות כתובת גלויה, בלי קיפול
        # ובלי קידוד, אחרת ג'ימייל לא מזהה אותה.
        msg['List-Unsubscribe'] = '<%s>' % unsub_url
        msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'
    return msg


# ----- שליחה -----

class Sender:
    """חיבור אחד לשרת הדואר לכל המשלוח, שנפתח מחדש אם נפל באמצע."""

    def __init__(self):
        self.s = None

    def _need(self):
        if self.s is None:
            self.s = _connect()
            return
        try:
            self.s.noop()
        except Exception:
            self.close()
            self.s = _connect()

    def send(self, msg):
        """מחזיר (הצלחה, שגיאה, סופית). 'סופית' = הכתובת פסולה ואין טעם
        לנסות שוב — היא נכנסת לרשימת החסומים."""
        for attempt in (1, 2):
            try:
                self._need()
                self.s.send_message(msg)
                return True, '', False
            except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as e:
                return False, str(e)[:200], True
            except smtplib.SMTPAuthenticationError as e:
                return False, 'התחברות לדואר נכשלה: %s' % str(e)[:160], False
            except Exception as e:
                self.close()
                if attempt == 2:
                    return False, str(e)[:200], False
                time.sleep(2)
        return False, 'שליחה נכשלה', False

    def close(self):
        try:
            if self.s:
                self.s.quit()
        except Exception:
            pass
        self.s = None
