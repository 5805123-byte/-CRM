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


def _env(k, d=''):
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
        return False, 'שם המשתמש או הסיסמה של הדואר אינם נכונים'
    except Exception as e:
        return False, 'אין תקשורת אל שרת הדואר: %s' % e
    c = cfg()
    msg = 'מחובר · שולח מ־%s' % c['frm']
    if free_domain():
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


def personalize(text, name):
    """{{שם}} בגוף המכתב מוחלף בשם התורם. גם באנגלית, למי שנוח לו כך."""
    n = (name or '').strip()
    out = str(text or '')
    for k in ('{{שם}}', '{{ שם }}', '{{name}}', '{{ name }}', '{שם}'):
        out = out.replace(k, n)
    return out


def _html(body, unsub_url, sig):
    """מכתב פשוט ונקי. בלי תמונות, בלי כפתורים צבעוניים ובלי טבלאות
    שיווקיות — מכתב שנראה כמו מכתב עובר את המסננים הרבה יותר טוב."""
    paras = ''.join('<p style="margin:0 0 12px">%s</p>' % _esc(p).replace('\n', '<br>')
                    for p in re.split(r'\n\s*\n', str(body or '').strip()) if p.strip())
    foot = ''
    if sig:
        foot += ('<p style="margin:18px 0 0;color:#555">%s</p>'
                 % _esc(sig).replace('\n', '<br>'))
    if unsub_url:
        foot += ('<p style="margin:16px 0 0;font-size:12px;color:#888">'
                 'אם אינך מעוניין לקבל מאיתנו מיילים — '
                 '<a href="%s" style="color:#888">לחץ כאן להסרה</a></p>' % _esc(unsub_url))
    return ('<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
            '<body style="margin:0;padding:18px;background:#ffffff">'
            '<div style="max-width:600px;margin:0 auto;direction:rtl;text-align:right;'
            'font-family:Arial,\'Segoe UI\',sans-serif;font-size:16px;line-height:1.7;color:#222">'
            + paras + foot + '</div></body></html>')


def plain_text(body, name, unsub_url='', sig=''):
    """גוף המכתב כטקסט פשוט — בדיוק מה שנשלח, וגם מה שמוצג בתצוגה
    המקדימה. אותו חישוב אחד לשני המקומות, כדי שלא ייפרדו."""
    out = personalize(body, name)
    if (sig or '').strip():
        out += '\n\n' + sig.strip()
    if unsub_url:
        out += '\n\nלהסרה מרשימת התפוצה: ' + unsub_url
    return out


def build(to, name, subject, body, unsub_url='', sig='', attachments=None):
    """הודעה אישית אחת. בשורת הנמען יש כתובת אחת בלבד — ואין ולא יהיה
    כאן Cc או Bcc.

    ההודעה נבנית בסגנון הקלאסי (MIME) ולא ב-EmailMessage החדש, מסיבה
    מעשית: הכותב החדש מקפל כתובת ארוכה בכותרת List-Unsubscribe ומקודד
    אותה כ-=?utf-8?q?...?= — וכתובת מקודדת אינה כתובת. ג'ימייל לא היה
    מזהה את ההסרה, וזה בדיוק מה שמפיל דיוור לספאם. כאן הכותרת נשמרת
    בדיוק כפי שנכתבה.
    """
    c = cfg()
    txt = personalize(body, name)
    subj = personalize(subject, name) or 'כולל חצות'

    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText(plain_text(body, name, unsub_url, sig), 'plain', 'utf-8'))
    alt.attach(MIMEText(_html(txt, unsub_url, sig), 'html', 'utf-8'))
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
