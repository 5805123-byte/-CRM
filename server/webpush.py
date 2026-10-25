"""📱 תזכורות קופצות בטלפון — Web Push (RFC 8291 / 8292) בלי ספריות חיצוניות מלבד cryptography.

מאיר: "אני רוצה שכל תזכורת שיש לי, שיקפוץ לי בטלפון… כמו שביומן גוגל, שיקפוץ לי בטלפון במסך הראשי".
הטלפון נרשם פעם אחת (pushManager.subscribe עם המפתח הציבורי שלנו), ומאז השרת שולח הודעה
מוצפנת לשירות הדחיפה של הדפדפן (גוגל / אפל / מוזילה), והוא מקפיץ אותה גם כשהאפליקציה סגורה.

המפתחות (VAPID) נוצרים פעם אחת ונשמרים במסד (app_kv) — המפתח הפרטי לא יוצא מהשרת.
"""
import base64
import json
import os
import struct
import time
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def b64u(b):
    return base64.urlsafe_b64encode(b).decode('ascii').rstrip('=')


def b64u_dec(s):
    s = str(s or '').strip()
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


# ---------- מפתחות VAPID ----------
def new_keys():
    """(PEM של המפתח הפרטי, המפתח הציבורי ב-base64url, 65 בתים לא דחוסים)"""
    k = ec.generate_private_key(ec.SECP256R1())
    pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode('ascii')
    return pem, public_of(pem)


def public_of(pem):
    k = serialization.load_pem_private_key(pem.encode('ascii'), password=None)
    raw = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64u(raw)


def vapid_header(pem, endpoint, sub='mailto:admin@example.com'):
    """Authorization: vapid t=<JWT>, k=<public>"""
    k = serialization.load_pem_private_key(pem.encode('ascii'), password=None)
    u = urllib.parse.urlparse(endpoint)
    aud = '%s://%s' % (u.scheme, u.netloc)
    head = b64u(json.dumps({'typ': 'JWT', 'alg': 'ES256'}, separators=(',', ':')).encode())
    claims = b64u(json.dumps({'aud': aud, 'exp': int(time.time()) + 12 * 3600, 'sub': sub}, separators=(',', ':')).encode())
    signing = ('%s.%s' % (head, claims)).encode('ascii')
    der = k.sign(signing, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    sig = b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))
    jwt = '%s.%s.%s' % (head, claims, sig)
    return 'vapid t=%s, k=%s' % (jwt, public_of(pem))


# ---------- הצפנת התוכן (aes128gcm) ----------
def _hkdf(salt, ikm, info, length):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(ua_public_b64, auth_b64, plaintext):
    ua_pub = b64u_dec(ua_public_b64)
    auth = b64u_dec(auth_b64)
    if len(ua_pub) != 65 or len(auth) != 16:
        raise ValueError('bad subscription keys')
    as_key = ec.generate_private_key(ec.SECP256R1())
    as_pub = as_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
    shared = as_key.exchange(ec.ECDH(), ua_key)
    salt = os.urandom(16)
    ikm = _hkdf(auth, shared, b'WebPush: info\x00' + ua_pub + as_pub, 32)
    cek = _hkdf(salt, ikm, b'Content-Encoding: aes128gcm\x00', 16)
    nonce = _hkdf(salt, ikm, b'Content-Encoding: nonce\x00', 12)
    rs = 4096
    body = AESGCM(cek).encrypt(nonce, plaintext + b'\x02', None)
    return salt + struct.pack('>I', rs) + bytes([len(as_pub)]) + as_pub + body


def send(sub, payload, pem, sub_email='mailto:admin@example.com', ttl=3600, timeout=15):
    """שליחת הודעה אחת. sub = {'endpoint', 'keys': {'p256dh', 'auth'}}. מחזיר (הצלחה, קוד/שגיאה).
    410 / 404 = הרישום כבר לא תקף (האפליקציה הוסרה / ההרשאה בוטלה) — צריך למחוק אותו."""
    ep = sub.get('endpoint') or ''
    keys = sub.get('keys') or {}
    try:
        data = encrypt(keys.get('p256dh'), keys.get('auth'), json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    except Exception as e:
        return False, 'encrypt: %s' % str(e)[:80]
    req = urllib.request.Request(ep, data=data, method='POST', headers={
        'Content-Type': 'application/octet-stream', 'Content-Encoding': 'aes128gcm',
        'TTL': str(ttl), 'Urgency': 'high', 'Authorization': vapid_header(pem, ep, sub_email)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, str(r.status)
    except urllib.error.HTTPError as e:
        return False, '%s %s' % (e.code, (e.read() or b'')[:120].decode('utf-8', 'replace'))
    except Exception as e:
        return False, str(e)[:120]
