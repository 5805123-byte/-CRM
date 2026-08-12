# -*- coding: utf-8 -*-
"""שליחת מייל מהשרת (SMTP של ג'ימייל) — כולל צירוף קבצים, למשל תמונת הקדשת פרנס יום.
משתמש באותם פרטי התחברות של משיכת הקוויטלים: GMAIL_USER + GMAIL_APP_PASSWORD.
"""
import os, smtplib
from email.message import EmailMessage
from email.utils import make_msgid


def configured():
    return bool(os.environ.get('GMAIL_USER') and os.environ.get('GMAIL_APP_PASSWORD'))


def send(to, subject, body, attachments=None, reply_to=None, in_reply_to=None):
    """שולח מייל. attachments = רשימת (שם, mime, bytes). מחזיר dict תוצאה.
    in_reply_to = ה-Message-ID של המייל שעליו עונים, כדי שהתשובה תישב
    באותו שרשור אצל התורם ולא כמייל חדש."""
    user = os.environ.get('GMAIL_USER')
    pw = os.environ.get('GMAIL_APP_PASSWORD')
    if not (user and pw):
        return {'ok': False, 'error': 'not_configured'}
    to = (to or '').strip()
    if not to:
        return {'ok': False, 'error': 'no_recipient'}
    msg = EmailMessage()
    mid = make_msgid(domain=(user.split('@')[-1] or 'gmail.com'))   # מזהה משלנו — כדי לתייק בלי כפילות
    msg['Message-ID'] = mid
    msg['From'] = 'כולל חצות <%s>' % user
    msg['To'] = to
    msg['Subject'] = subject or 'כולל חצות'
    if reply_to:
        msg['Reply-To'] = reply_to
    irt = (in_reply_to or '').strip()
    if irt.startswith('<'):        # רק Message-ID אמיתי; מפתח פנימי שלנו לא מתאים כאן
        msg['In-Reply-To'] = irt
        msg['References'] = irt
    msg.set_content(body or '')
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
