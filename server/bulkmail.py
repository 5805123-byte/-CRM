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
    ctx = ssl.create_default_context()
    if c['port'] == 465:
        s = smtplib.SMTP_SSL(c['host'], c['port'], timeout=40, context=ctx)
    else:
        s = smtplib.SMTP(c['host'], c['port'], timeout=40)
        try:
            s.starttls(context=ctx)
        except smtplib.SMTPNotSupportedError:
            pass                      # שרת מקומי לבדיקות — בלי הצפנה
    if c['pw']:
        try:
            s.login(c['user'], c['pw'])
        except smtplib.SMTPNotSupportedError:
            pass                      # ממסר פנימי שאינו דורש התחברות
    return s


def _try(host, port, user, pw):
    """ניסיון התחברות אחד. מחזיר (הצליח, שגיאה)."""
    ctx = ssl.create_default_context()
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
        return False, 'conn:' + str(e)[:160]
    finally:
        try:
            if s:
                s.quit()
        except Exception:
            pass


def probe(user, pw, host='', port=0):
    """מוצא לבד את שרת הדואר והפורט של הכתובת.

    מאיר לא אמור לדעת מהו "SMTP" ומהו "פורט 465". הוא נותן כתובת וסיסמה,
    וכאן מנסים את הצירופים המקובלים עד שאחד מהם מתחבר. מחזיר
    (הצליח, שרת, פורט, הודעה בעברית).
    """
    user = (user or '').strip()
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
    for h in hosts:
        for pt in ports:
            ok, err = _try(h, pt, user, pw)
            if ok:
                return True, h, pt, 'מחובר · שולח מ־%s' % user
            if err.startswith('auth:'):
                # השרת נמצא ועונה — הסיסמה היא הבעיה, אין טעם לנסות עוד
                lastauth = err[5:]
    if lastauth:
        return False, '', 0, ('שרת הדואר נמצא אבל דחה את הסיסמה. בדוק את הסיסמה '
                              'של התיבה %s. (%s)' % (user, lastauth[:80]))
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
BIG = '<b style="font-size:1.32em;letter-spacing:.01em">%s</b>'
BOLD = '<b>%s</b>'
KVBOX = ('<span style="display:block;margin:14px 0;padding:13px 17px;background:#faf6ec;'
         'border-%s:4px solid #9c7a2e;border-radius:9px;font-size:1.18em;font-weight:700;'
         'line-height:1.85;color:#1c1710">')
KVLINE = '<span style="display:block">%s</span>'


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
    simple = {'שם': first, 'משפחה': last, 'שם מלא': full,
              'תואר': (who.get('title') or TITLE_ALL).strip() or TITLE_ALL,
              # מאיר: "יששכר־זבולון — אני רוצה למזג לו את השם של האברך
              # שלומד בשבילו בתוך המכתב, ואת הקוויטל שלו"
              'אברך': (who.get('avreich') or '').strip(),
              'name': first, 'lastname': last, 'fullname': full,
              'avreich': (who.get('avreich') or '').strip()}
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
        if key in ('אברך', 'avreich'):
            av = (who.get('avreich') or '').strip()
            if not av:
                return ''
            return (BOLD % _esc(av)) if html else av
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


def _html(body, unsub_url, sig, d='rtl', pixel='', who=None):
    """מכתב פשוט ונקי. בלי תמונות, בלי כפתורים צבעוניים ובלי טבלאות
    שיווקיות — מכתב שנראה כמו מכתב עובר את המסננים הרבה יותר טוב.

    הטקסט מגיע לכאן כתבנית, לא מוחלף מראש: קודם מבריחים אותו כ-HTML ורק
    אחר כך מציבים את הסימונים — כך השם והקוויטל יכולים לצאת מודגשים
    וגדולים, בלי שהעיצוב ייבלע בהברחה."""
    def _p(x):
        x = _esc(x).replace('\n', '<br>')
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
            'font-family:Arial,\'Segoe UI\',sans-serif;font-size:16px;line-height:1.7;color:#222">'
            % (('en', 'ltr', 'ltr') if d == 'ltr' else ('he', 'rtl', 'rtl'))
            + paras + foot + '</div></body></html>')


def plain_text(body, who, unsub_url='', sig=''):
    """גוף המכתב כטקסט פשוט — בדיוק מה שנשלח, וגם מה שמוצג בתצוגה
    המקדימה. אותו חישוב אחד לשני המקומות, כדי שלא ייפרדו."""
    out = personalize(body, who)
    if (sig or '').strip():
        out += '\n\n' + sig.strip()
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
