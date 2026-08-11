# -*- coding: utf-8 -*-
"""משיכת אנשי הקשר של גוגל ישירות מהחשבון — כתובות, טלפונים ומיילים.
משתמש באותם פרטי התחברות של משיכת המיילים: GMAIL_USER + GMAIL_APP_PASSWORD,
דרך CardDAV (אותו פרוטוקול שבו טלפונים מסנכרנים אנשי קשר).
"""
import os, re, base64, http.client, urllib.parse
import xml.etree.ElementTree as ET

HOST = 'www.googleapis.com'
BASE = '/carddav/v1/principals/%s/lists/default/'
NS = {'d': 'DAV:', 'c': 'urn:ietf:params:xml:ns:carddav'}

STATUS = {'running': False, 'done': False, 'error': '', 'found': 0, 'filled': 0, 'scanned': 0}


def configured():
    return bool(os.environ.get('GMAIL_USER') and os.environ.get('GMAIL_APP_PASSWORD'))


def _req(method, path, body=None, depth='1', timeout=60):
    user = (os.environ.get('GMAIL_USER') or '').strip()
    pw = (os.environ.get('GMAIL_APP_PASSWORD') or '').replace(' ', '')
    auth = base64.b64encode(('%s:%s' % (user, pw)).encode()).decode()
    conn = http.client.HTTPSConnection(HOST, timeout=timeout)
    hdr = {'Authorization': 'Basic ' + auth, 'Depth': depth,
           'Content-Type': 'text/xml; charset=utf-8', 'User-Agent': 'KollelChatzosCRM/1.0'}
    conn.request(method, path, body=(body.encode('utf-8') if body else None), headers=hdr)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, data


_QUERY = ('<?xml version="1.0" encoding="utf-8" ?>'
          '<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">'
          '<D:prop><D:getetag/><C:address-data/></D:prop></C:addressbook-query>')


def _unfold(text):
    """שורות vCard ארוכות נשברות עם רווח בתחילת השורה הבאה — מאחדים אותן חזרה."""
    return re.sub(r'\r?\n[ \t]', '', text or '')


def _unesc(v):
    return (v or '').replace('\\n', ' ').replace('\\,', ',').replace('\\;', ';').replace('\\\\', '\\')


def parse_vcard(text):
    """מפרק כרטיס vCard אחד לשדות שמעניינים אותנו."""
    out = {'name': '', 'first': '', 'last': '', 'org': '', 'note': '',
           'emails': [], 'phones': [], 'addrs': []}
    for line in _unfold(text).split('\n'):
        line = line.rstrip('\r')
        if ':' not in line:
            continue
        head, _, val = line.partition(':')
        key = head.split(';')[0].upper()
        if key == 'FN':
            out['name'] = _unesc(val).strip()
        elif key == 'N':
            p = [_unesc(x).strip() for x in val.split(';')]
            out['last'] = p[0] if p else ''
            out['first'] = p[1] if len(p) > 1 else ''
        elif key == 'ORG':
            out['org'] = _unesc(val.split(';')[0]).strip()
        elif key == 'NOTE':
            out['note'] = _unesc(val).strip()
        elif key == 'EMAIL':
            v = _unesc(val).strip().lower()
            if '@' in v and v not in out['emails']:
                out['emails'].append(v)
        elif key == 'TEL':
            v = _unesc(val).strip()
            if v and v not in out['phones']:
                out['phones'].append(v)
        elif key == 'ADR':
            # ADR: po;ext;street;city;state;zip;country
            p = [_unesc(x).strip() for x in val.split(';')]
            while len(p) < 7:
                p.append('')
            street = ' '.join(x for x in (p[0], p[1], p[2]) if x).strip()
            full = ', '.join(x for x in (street, p[3], p[4], p[5], p[6]) if x)
            full = re.sub(r'\s{2,}', ' ', full).strip(' ,')
            if full and full not in out['addrs']:
                out['addrs'].append(full)
    if not out['name']:
        out['name'] = (out['last'] + ' ' + out['first']).strip() or out['org']
    return out


def fetch(status=None):
    """מחזיר את כל אנשי הקשר בחשבון. מרים חריגה עם הסבר בעברית אם ההתחברות נכשלה."""
    st = status if status is not None else {}
    user = (os.environ.get('GMAIL_USER') or '').strip()
    if not configured():
        raise RuntimeError('המייל לא מוגדר בשרת')
    path = BASE % urllib.parse.quote(user)
    code, data = _req('REPORT', path, _QUERY)
    if code in (401, 403):
        raise RuntimeError('גוגל דחתה את ההתחברות לאנשי הקשר (%d). '
                           'סיסמת האפליקציה תקפה למייל אבל לא לאנשי הקשר.' % code)
    if code == 404:
        raise RuntimeError('לא נמצא פנקס אנשי קשר בחשבון %s' % user)
    if code >= 300:
        raise RuntimeError('גוגל החזירה שגיאה %d' % code)
    try:
        root = ET.fromstring(data)
    except Exception as e:
        raise RuntimeError('תשובה לא מובנת מגוגל: %s' % e)
    out = []
    for node in root.findall('.//c:address-data', NS):
        card = (node.text or '').strip()
        if not card:
            continue
        c = parse_vcard(card)
        if c['name'] or c['emails'] or c['phones']:
            out.append(c)
    st['found'] = len(out)
    return out
