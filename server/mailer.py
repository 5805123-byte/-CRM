# -*- coding: utf-8 -*-
"""שליחת מייל מהשרת (SMTP של ג'ימייל) — כולל צירוף קבצים, למשל תמונת הקדשת פרנס יום.
משתמש באותם פרטי התחברות של משיכת הקוויטלים: GMAIL_USER + GMAIL_APP_PASSWORD.
"""
import os, smtplib
from email.message import EmailMessage
from email.utils import make_msgid, formataddr


def configured():
    return bool(os.environ.get('GMAIL_USER') and os.environ.get('GMAIL_APP_PASSWORD'))


def send(to, subject, body, attachments=None, reply_to=None, profile=None, pixel='', rtl=True):
    """שולח מייל. attachments = רשימת (שם, mime, bytes). מחזיר dict תוצאה.
    profile='comm' — מיילי הקהילה, יוצאים מ-neder1818 (COMM_MAIL_PASS; בלעדיו — "מאת" בלבד)."""
    user = os.environ.get('GMAIL_USER')
    pw = os.environ.get('GMAIL_APP_PASSWORD')
    frm = user
    fname = 'כולל חצות'
    if profile == 'comm':
        import bulkmail
        cc = bulkmail.comm_cfg()
        frm = cc['frm']
        reply_to = reply_to or frm
        fname = cc['name']
        if cc['own_login']:
            user, pw = cc['user'], (os.environ.get('COMM_MAIL_PASS') or '').strip().replace(' ', '')
    if not (user and pw):
        return {'ok': False, 'error': 'not_configured'}
    to = (to or '').strip()
    if not to:
        return {'ok': False, 'error': 'no_recipient'}
    msg = EmailMessage()
    mid = make_msgid(domain=(user.split('@')[-1] or 'gmail.com'))   # מזהה משלנו — כדי לתייק בלי כפילות
    msg['Message-ID'] = mid
    msg['From'] = formataddr((fname, frm), charset='utf-8')
    msg['To'] = to
    msg['Subject'] = subject or 'כולל חצות'
    if reply_to:
        msg['Reply-To'] = reply_to
    msg.set_content(body or '')
    if pixel:
        # מאיר: "לראות כל מייל אם פתחו" — גרסת HTML של אותו טקסט, עם פיקסל מעקב זעיר
        import html as _h
        d = 'rtl' if rtl else 'ltr'
        msg.add_alternative('<!doctype html><html dir="%s"><body style="font-family:Arial,sans-serif;font-size:15px;direction:%s;text-align:%s">%s'
                            '<img src="%s" width="1" height="1" alt="" style="display:block;border:0"></body></html>'
                            % (d, d, 'right' if rtl else 'left', _h.escape(body or '').replace('\n', '<br>'), _h.escape(pixel)), subtype='html')
    for (name, mime, data) in (attachments or []):
        if not data:
            continue
        maintype, _, subtype = (mime or 'application/octet-stream').partition('/')
        msg.add_attachment(data, maintype=maintype or 'application',
                           subtype=subtype or 'octet-stream', filename=(name or 'file'))
    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return {'ok': True, 'msg_id': mid}
    except smtplib.SMTPAuthenticationError as e:
        return {'ok': False, 'error': 'login_failed', 'detail': str(e)}
    except Exception as e:
        return {'ok': False, 'error': 'send_failed', 'detail': str(e)}
